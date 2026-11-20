"""منسّق المراحل: brief → research → diverge → render+audit → critique → preview → decide → name_check → package.

كل مرحلة idempotent بعلامة في stages/. المراحل التي تحتاج النموذج تكتب طلبًا عربيًا وتعود برمز 3؛
المرحلة التي تحتاج المالك تعود برمز 4، والمصمّم الخارجي 5. الرمز 0 = حزمة مكتملة. وكل تشغيل يكتب ما وقف عنده في
`outcome.json` من الإصدار (services/outcome.py): منه يقرأ الوارد والصندوق والسجل من يُنتظر، فلا يستنتجونه.
"""
from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .. import config
from ..domain import FAMILY_AR, MEDIUM_AR, Brief, Concept, Medium, NameStatus, Verdict
from . import adopt, blind, designer, live_preview, novelty, outcome, protocol, style, thumbs
from . import judge as judging
from .audit import AuditReport, AuditService
from .export import ExportInputs, ExportService
from .identity_flow import IdentityFlow, Wait
from .ledger import Ledger
from .namecheck import checklist_md, read_name_check
from .ports import Embedder, ReferenceLibrary, Renderer
from .preview import build_preview
from .render import RenderService
from .research import research
from .shaping import ShapingService, WordmarkSVG
from .similarity import SimilarityService
from .workspace import Workspace, close_workspace, open_workspace

AWAIT_MODEL = 3
AWAIT_OWNER = 4
AWAIT_DESIGNER = 5  # مصمّم خارجي تُشغّله الجلسة بأمر المالك: لا نموذج الخط ولا قرار المالك (services/designer.py)
SKILL = ".claude/skills/sima-design"
REFS = SKILL + "/references"  # كل مرجع في طلب يُكتب بمساره من جذر المستودع: مسار نسبي إلى المهارة لا يُحلّ عند النموذج
FIX_REQUEST = "REQUEST-fix.md"  # تصحيح صيغة ملف كتبه النموذج: طلب ضيّق بجهد متوسط لا إعادة الطلب الإبداعي


@dataclass
class Outcome:
    """ما أعاده الخط: الرمز والرسالة، ومعهما ما يُنتظر بعينه فلا يستنتجه قارئ من الملفات (services/outcome.py).
    gate وdigest: البوابة التي ينتظر عندها المالك وبصمة ما عُرض فيها (فارغة حين لا بطاقة قرار لما وقف عنده الخط).
    request: اسم ملف الطلب الذي يُنتظر جوابه من النموذج أو المصمّم الخارجي."""
    code: int
    message: str
    workspace: Workspace
    gate: str = ""
    digest: str = ""
    request: str = ""


@dataclass(frozen=True)
class Ask:
    """انتظار للنموذج من مرحلة: الرسالة واسم ملف الطلب الذي كتبته."""
    message: str
    request: str


class Pipeline:
    def __init__(self, renderer: Renderer, shaper: ShapingService, library: ReferenceLibrary | None, out_dir: Path,
                 catalog: list[dict] | None = None, decide_cmd: str = "uv run sima decide <brief>",
                 on_identity_approved: Callable[[Path], str] | None = None,
                 build_mark: Callable[[str, str], str] | None = None, embedder: Embedder | None = None,
                 blind_gate: bool = False, thumbs_gate: bool = False):
        self._r = renderer
        self._shaping = shaper
        self._lib = library
        self._out = out_dir
        self._catalog = catalog or []
        self._decide_cmd = decide_cmd
        self._on_identity = on_identity_approved  # منفذ السجل: يحفظ الهوية المعتمدة في القاعدة، والنواة لا تعرف Django
        self._build = build_mark  # منفذ أداة البناء الهندسي: يحوّل work/concepts/<id>.mark.yaml إلى SVG (adapters/geometry.py)
        self._embedder = embedder  # منفذ التضمين المحلي لفحص جِدّة الأفكار؛ None يتجاوز الفحص
        self._blind = blind_gate  # بوابة القراءة العمياء قبل الحَكَم (services/blind.py)؛ cli يفعّلها من config.BLIND_GATE
        self._thumbs = thumbs_gate  # مصغّرات الأفكار قبل الرسم (services/thumbs.py)؛ تلزمها أداة البناء
        self._sim = SimilarityService(renderer, library)
        self._audit = AuditService(renderer, self._sim)
        self._render = RenderService(renderer)
        self._export = ExportService(renderer)
        self._identity = IdentityFlow(renderer, shaper, config.FONTS_DIR)

    # ----- المدخل الوحيد -----
    def run(self, brief: Brief, *, new_version: bool = False) -> Outcome:
        """يشغّل الخط حتى أول انتظار، ويكتب نتيجته في الإصدار: الوارد والصندوق والسجل يقرؤونها ولا يستنتجونها."""
        out = self._run(brief, new_version=new_version)
        outcome.write(out.workspace.root, code=out.code, message=out.message, gate=out.gate, digest=out.digest, request=out.request)
        return out

    def _run(self, brief: Brief, *, new_version: bool = False) -> Outcome:
        ws = open_workspace(self._out, brief, new_version=new_version)
        ws.ensure()
        ident = brief.identity.enabled
        if ws.done("package") and (not ident or ws.done("identity")):
            msg = f"الحزمة مكتملة سابقًا في {ws.package_dir} (استعمل --new-version لإصدار جديد)"
            if ident and not ws.done("deliver") and self._on_identity is not None:
                msg += "\n" + self._on_identity(ws.root)  # تسليم تعثّر بعد الاعتماد يُستأنف هنا (كل خطواته idempotent)
            return Outcome(0, msg, ws)
        self._inherit_mark(ws, brief)
        try:
            adoption = adopt.load(brief)
            if adoption is not None:
                adopt.sync(ws, adoption)
        except adopt.AdoptError as e:
            return Outcome(1, str(e), ws)
        ledger = Ledger(ws.ledger_path)
        self._stage_brief(ws, brief)
        self._stage_research(ws, brief)
        auto = None
        if adoption is None and designer.enabled(brief):
            got = self._stage_designer(ws, brief)
            if isinstance(got, Outcome):
                return got
            adoption, auto = got, designer.RULE
        strategy, pending = None, None
        if ident:
            strategy = self._identity.strategy(ws, brief, auto=auto)
            if isinstance(strategy, Wait):
                draft = self._identity.draft_strategy(ws) if strategy.who == "owner" else None
                if draft is None or ledger.approved() is None:
                    return self._wait(strategy, ws)
                # العلامة معتمدة سلفًا (موروثة): يتابع الخط ليبني لوحة الاتجاهات للاطلاع، ثم يعود إلى بوابة المنصة
                pending, strategy = strategy, draft
        approved = ledger.approved()
        if adoption is not None:
            return self._run_adopted(ws, brief, adoption, strategy, pending, auto)
        medium = approved.medium if approved is not None else ledger.lock().current()
        if medium is None:
            return Outcome(1, "كل الوسائط مقفلة بعد ثلاثة رفضات لكل منها؛ يلزم موجز جديد.", ws)
        if approved is None:
            self._maybe_rotate_medium(ws, ledger, medium)
            if config.STYLE_GATE:
                wait = self._stage_style(ws, brief, ledger)
                if wait is not None:
                    return wait
        fix = self._stage_fix(ws, brief)
        if fix is not None:
            return self._ask(fix, ws)
        if approved is None:
            waiting = self._stage_thumbs(ws, brief, medium)
            if waiting is not None:
                return self._ask(waiting, ws)
        if self._build is not None:
            protocol.compile_marks(ws, self._build)
        problems = list(protocol.validate_diverge(ws, medium, construct=self._build is not None).problems)
        if approved is None:
            problems = self._spread_problems(ws, ledger, medium, problems) + thumbs.concept_problems(ws)
        if problems:
            if approved is None and ws.done("shortlist"):  # رسم يُعاد بعد عرض المجموعة على المالك: أحكامها لا تُحسب من جولات الصقل
                self._archive_verdicts(ws, "redraw")  # (في أثناء الصقل الآلي لا قائمة معروضة، فتبقى الجولات محسوبة ولا يتكرر الصقل بلا سقف)
                ws.marker("shortlist").unlink()
            self._write_request_diverge(ws, brief, medium, problems)
            return Outcome(AWAIT_MODEL, "بانتظار النموذج: " + "؛ ".join(problems) + f"\nالطلب في {ws.work / 'REQUEST-diverge.md'}", ws,
                           request="REQUEST-diverge.md")
        concepts = protocol.read_concepts(ws)
        svgs = protocol.read_concept_svgs(ws, concepts)
        smalls = protocol.read_small_svgs(ws, concepts)
        audits = self._stage_render(ws, brief, concepts, svgs, smalls)
        crit = self._stage_critique(ws, brief, concepts, svgs, smalls, audits)
        if crit is not None:
            return self._ask(crit, ws)
        passing = [c for c in concepts if self._concept_passes(c, audits)]
        if len(passing) < config.CONCEPTS_REQUIRED:
            failing = [c.id for c in concepts if not self._concept_passes(c, audits)]
            done = protocol.critique_rounds_done(ws)
            extra = done - int(ws.read_marker("critique").get("rounds", done))  # الجولات الإضافية المكتوبة بعد انتهاء النقد
            if extra >= config.FORCED_CRITIQUE_ROUNDS:
                # الجولات الإضافية كانت بلا سقف وكل منها باسم طلب جديد فتفلت من حارس التكرار: بعد السقف يُعرض الفشل على المالك
                why = "؛ ".join(f"{cid}: {'، '.join(a.findings[:2])}" for c in concepts for cid in (c.id, c.id + "-small")
                                if (a := audits.get(cid)) is not None and not a.passed)
                return Outcome(AWAIT_OWNER, f"مفاهيم لم تمرّ الفحص الحتمي بعد {extra} جولات إصلاح إضافية ({', '.join(failing)})، فلا يُعاد "
                               f"الطلب آليًا. ما ردّه الفحص: {why}.\nاطلب رسمًا جديدًا بـ`{self._decide_cmd} --medium {medium.value} "
                               "--reason \"...\"`، أو صحّح بناء المفهوم في work/concepts/ ثم استأنف.", ws)
            forced = done + 1
            self._write_request_critique(ws, brief, concepts, audits, forced, protocol.merged_digest(svgs, smalls), forced=extra + 1)
            return Outcome(AWAIT_MODEL, "مفاهيم لم تمرّ الفحوص بعد الجولات: " + ", ".join(failing), ws,
                           request=f"REQUEST-critique-r{forced}.md")
        shown = concepts
        if approved is None:
            # معيار الاحتراف: ملاحظات المالك تُعاد رسمًا أولًا، ثم حَكَم مستقل؛ لا يصل إلى المالك إلا أفضل المجتازين
            wait = self._stage_owner_feedback(ws, brief, ledger, medium, concepts, svgs, smalls)
            if wait is not None:
                return self._ask(wait, ws)
            wait = self._stage_blind(ws, brief, concepts, svgs, smalls)
            if wait is not None:
                return self._ask(wait, ws)
            picked = self._stage_judge(ws, brief, concepts, svgs, smalls, audits)
            if isinstance(picked, Ask):
                return self._ask(picked, ws)
            shown = [next(c for c in concepts if c.id == cid) for cid in picked]
        wordmark, lockups = self._stage_wordmark(ws, brief, shown, svgs)
        self._stage_preview(ws, brief, shown, svgs, smalls, audits, wordmark, lockups)
        if approved is None or approved.concept_id not in svgs:
            self._handle_rejections(ws, ledger, concepts)
            return Outcome(AWAIT_OWNER, f"ورقة المعاينة جاهزة: {ws.preview_path}\nبانتظار قرار المالك ({self._decide_cmd}).", ws,
                           gate="concepts", digest=protocol.concepts_digest(ws))
        chosen = next(c for c in concepts if c.id == approved.concept_id)
        return self._finish(ws, brief, strategy, pending, chosen, svgs, smalls, audits, wordmark, lockups)

    def _stage_designer(self, ws: Workspace, brief: Brief) -> Outcome | adopt.Adoption:
        """مسار المصمّم الخارجي: صفحة سكتشات، ثم اختيار المالك، ثم المتجه المستلم بيانَ اعتماد. الخط يكتب نص الطلب وينتظر
        الاستلام؛ الإرسال من الجلسة بأمر المالك، ولا يُستدعى نموذج الخط في هذه المرحلة."""
        if not brief.identity.enabled:
            return Outcome(1, "identity.designer يلزمه نطاق هوية (identity.scope) لأن المسار ينتهي بالدليل.", ws)
        sheet, problems = designer.read_sheet(ws)
        rejected = [str(r["reason"]) for r in (*designer.prior_rejections(ws), *designer.rejections(ws))]
        if sheet is not None and designer.rejection(ws, sheet) is not None:  # رفض المالك الصفحة: تعود إلى المصمّم بسببه
            req = designer.write_sketch_request(ws, brief, [], rejected)
            return Outcome(AWAIT_DESIGNER, f"بانتظار المصمّم الخارجي: صفحة سكتشات جديدة (رفض المالك السابقة: {rejected[-1]})"
                           + f"\nالطلب في {req}", ws, request=req.name)
        dev = designer.pending_development(ws)
        if dev is not None and (sheet is None or sheet.digest == dev["digest"]):  # «طوّر هذا السكتش»: صفحة معالجات حوله قبل بنائه
            req = designer.write_sketch_request(ws, brief, problems, None, dev)
            return Outcome(AWAIT_DESIGNER, f"بانتظار المصمّم الخارجي: صفحة تطوير للسكتش {dev['sketch']}"
                           + (" (" + "؛ ".join(problems) + ")" if problems else "") + f"\nالطلب في {req}", ws, request=req.name)
        if sheet is None:
            req = designer.write_sketch_request(ws, brief, problems, rejected)
            return Outcome(AWAIT_DESIGNER, "بانتظار المصمّم الخارجي: صفحة السكتشات"
                           + (" (" + "؛ ".join(problems) + ")" if problems else "") + f"\nالطلب في {req}", ws, request=req.name)
        ws.mark_done(designer.MARKER, {"digest": sheet.digest})
        choice = designer.current(ws, sheet)
        if choice is None:
            return Outcome(AWAIT_OWNER, "صفحة السكتشات جاهزة: اختر سكتشًا من منصة سِمة (أو `sima designer <brief> --pick <رقم>`).", ws,
                           gate="sketches", digest=sheet.digest)
        fonts = sorted(f.name for f in config.FONTS_DIR.glob("*.ttf"))
        rebuilt = [str(r["reason"]) for r in designer.rebuilds(ws, sheet, choice["sketch"])]
        if designer.pending_rebuild(ws, sheet) is not None:  # ردّ المالك المتجه المبني: السكتش نفسه يعود إلى المصمّم بسببه
            req = designer.write_vector_request(ws, brief, sheet, choice, [], fonts, rebuilt)
            return Outcome(AWAIT_DESIGNER, f"بانتظار المصمّم الخارجي: إعادة بناء السكتش {choice['sketch']} متجهًا"
                           + f" (ردّ المالك المتجه: {rebuilt[-1]})\nالطلب في {req}", ws, request=req.name)
        try:
            adoption = designer.adoption(ws, sheet, choice, brief.identity.fonts)
            if adoption is not None:
                adopt.sync(ws, adoption, reopen=designer.replaces_rejected(ws, choice) or designer.reopened_by_owner(ws))
                return adoption
            problems = []
        except designer.OtherSketch as e:  # تسليم لسكتش آخر: متجه المختار لم يُستلم بعد
            problems = [str(e)]
        except adopt.PackagedError:
            # قاعدة الخط لا خلل في الأصول: كانت تُحوَّل إلى «ينتظر المصمّم» فيعلق الإصدار عنده أبدًا (ب9)
            return Outcome(AWAIT_OWNER, "بيان اعتماد المصمّم تغيّر بعد بناء الحزمة بلا ردّ للمتجه القائم ولا حدّ معلن، فلا تُبنى عليه "
                           "الهوية وليس مما يصحّحه المصمّم. للمضيّ على تسليم جديد قبل اعتماد الدليل: `sima designer <brief> --intake "
                           "<مجلد التسليم> --min-mark-px <الحد>` (يعيد بناء الحزمة والدليل عليه)؛ وإلا فإصدار جديد.", ws)
        except adopt.AdoptError as e:
            if e.content and not e.other:
                # ما في ملفات التسليم نفسها يعود إلى المصمّم بسببه في النص المرسل وبعدّاد الجولات (ب7: كان يعيد طلب المتجه كله
                # وسببه فوق «النص المرسل» فلا يبلغه، وبلا سقف)
                return self._designer_fix(ws, brief, e.content, designer.manifest_min(ws), designer.manifest_digest(ws))
            return Outcome(AWAIT_OWNER, f"بيان اعتماد المصمّم في الإصدار لا يُقبل، وليس مما يصحّحه المصمّم: {e}.\nأعد استلام "
                           "التسليم كما وصل: `sima designer <brief> --intake <مجلد التسليم>`.", ws)
        req = designer.write_vector_request(ws, brief, sheet, choice, problems, fonts, rebuilt)
        return Outcome(AWAIT_DESIGNER, f"بانتظار المصمّم الخارجي: بناء السكتش {choice['sketch']} متجهًا"
                       + (" (" + "؛ ".join(problems) + ")" if problems else "") + f"\nالطلب في {req}", ws, request=req.name)

    def _run_adopted(self, ws: Workspace, brief: Brief, adoption: adopt.Adoption, strategy, pending: Wait | None,
                     auto: str | None = None) -> Outcome:
        """علامة اعتمدها المالك خارج الخط: لا رسم ولا نقد ولا حَكَم. تُفحص عند حدّها المعلن ثم تمضي إلى الاسم فالاتجاه فالحزمة."""
        concepts = protocol.read_concepts(ws)
        svgs, smalls = protocol.read_concept_svgs(ws, concepts), protocol.read_small_svgs(ws, concepts)
        # الشعار الكامل يُفحص عند حدّه المعلن وسماكته إن أعلنهما المالك، والرمز الصغير عند حدّه هو («مسك» v9: كان الشعار يُفحص
        # عند 96 بسماكة الأيقونة فيوقف الخط)
        audits = self._stage_render(ws, brief, concepts, svgs, smalls, small_base=adoption.min_mark_px,
                                    min_stroke=adoption.min_stroke_px, main_base=adoption.min_wordmark_px,
                                    main_stroke=adoption.min_wordmark_stroke_px)
        chosen = concepts[0]
        failing = [f"{k}: {f}" for k in (chosen.id, chosen.id + "-small") for f in audits[k].findings if not audits[k].passed]
        if failing and designer.enabled(brief):
            return self._designer_fix(ws, brief, failing, adoption.min_mark_px)
        if failing:
            return Outcome(1, "العلامة المعتمدة لا تجتاز الفحص عند الحد المعلن في بيان الاعتماد (min_mark_px): " + "؛ ".join(failing), ws)
        word_font = None
        if brief.identity.lockup_word:  # العلامة رمز بلا كتابة الاسم: الاسم من خط عناوين الاتجاه المعتمد
            heading = (adoption.direction.get("type") or {}).get("heading") or {}
            word_font = (str(heading.get("font") or ""), int(heading.get("weight") or 700))
        return self._finish(ws, brief, strategy, pending, chosen, svgs, smalls, audits, None, {}, min_mark_px=adoption.min_mark_px,
                            min_stroke_px=adoption.min_stroke_px, auto=auto, word_font=word_font, kept=(adoption.direction, adoption.motif),
                            min_wordmark_px=adoption.min_wordmark_px)

    @staticmethod
    def _designer_fix(ws: Workspace, brief: Brief, failing: list[str], min_mark_px: int, digest: str | None = None) -> Outcome:
        """ما يردّه الفحص (العلامة أو الاتجاه أو التحقق من البيان) يعود إلى المصمّم الخارجي بسببه كما قيس دون سؤال المالك
        (قراره 2026-11-13): كل بيان اعتماد مردود جولة ببصمته في البناء الجاري، وبعد الجولات المحدودة يقف الخط عند المالك
        بما رُدّ وبطريقَي المضيّ (ب4: كان خروجًا بالرمز 1 بلا بطاقة). `digest` بصمة ما لم يدخل الإصدار بعد (ردّه التحقق)."""
        n = designer.fix_round(ws, digest or str(ws.read_marker("adopted").get("digest", "")), designer.build(ws))
        if n <= designer.FIX_ROUNDS:
            req = designer.write_fix_request(ws, brief, failing, min_mark_px, n)
            return Outcome(AWAIT_DESIGNER, f"بانتظار المصمّم الخارجي: تصحيح ما ردّه الفحص (الجولة {n}): " + "؛ ".join(failing)
                           + f"\nالطلب في {req}", ws, request=req.name)
        return Outcome(AWAIT_OWNER, f"ردّ الفحص تسليم المصمّم الخارجي بعد {designer.FIX_ROUNDS} جولات تصحيح، فلا يُعاد إليه آليًّا: "
                       + "؛ ".join(failing) + ".\nقرارك: ردّ المتجه بسبب يعيد السكتش إلى المصمّم ويبدأ العدّ من جديد (`sima designer "
                       "<brief> --rebuild --reason \"...\"`)، أو قبول العلامة عند حدّ أدنى تعلنه (`sima designer <brief> --intake "
                       "<مجلد التسليم> --min-mark-px <الحد>`).", ws, gate=designer.FIX_GATE, digest=designer.manifest_digest(ws))

    def _finish(self, ws: Workspace, brief: Brief, strategy, pending: Wait | None, chosen: Concept, svgs: dict[str, str],
                smalls: dict[str, str], audits: dict[str, AuditReport], wordmark: WordmarkSVG | None, lockups: dict[str, str],
                *, min_mark_px: int = 16, min_stroke_px: float | None = None, auto: str | None = None,
                word_font: tuple[str, int] | None = None, kept: tuple[dict, str] | None = None,
                min_wordmark_px: int | None = None) -> Outcome:
        """ما بعد اعتماد المفهوم: تحقق الاسم، ثم اتجاه الهوية، ثم الحزمة والدليل.

        word_font (الخط، الوزن): العلامة المعتمدة من خارج الخط رمز بلا كتابة الاسم (`identity.lockup_word`)، فالكلمة تُشكَّل منه
        والقفل هو الرمز المعتمد كما هو مع الكلمة؛ الرمز المصغّر يبقى للأيقونات. وإن عُرضت ثلاثة اتجاهات فوق العلامة
        (`identity.directions: three`) فكلمة كل اتجاه في لوحته بخط عناوينه، وكلمة الحزمة بخط عناوين الاتجاه الذي يختاره المالك.
        kept (بند الاتجاه، نمطه): اتجاه التسليم المعتمد، يبقى كما هو بين الثلاثة."""
        ident = brief.identity.enabled
        blocked = self._stage_name_check(ws, brief)
        if blocked is not None:
            return Outcome(AWAIT_OWNER, blocked, ws, gate="name_check")
        shaped: dict[tuple[str, int], tuple[WordmarkSVG, str]] = {}

        def word_lockup(font: str, weight: int) -> tuple[WordmarkSVG, str]:
            if (font, weight) not in shaped:
                word = self._shaping.wordmark(brief.wordmark_text, font, weight, title=brief.wordmark_text)
                shaped[(font, weight)] = (word, ShapingService.lockup(svgs[chosen.id], word, rtl=(brief.language == "ar")))
            return shaped[(font, weight)]

        def keep_word(word: WordmarkSVG, lock: str) -> None:
            (ws.work / "lockups").mkdir(exist_ok=True)
            for f, text in ((ws.work / "wordmark.svg", word.svg), (ws.work / "lockups" / f"{chosen.id}.svg", lock)):
                if not f.is_file() or f.read_text(encoding="utf-8") != text:
                    f.write_text(text, encoding="utf-8")

        if word_font is not None:
            try:
                wm, lock_svg = word_lockup(*word_font)
            except (FileNotFoundError, ValueError) as exc:
                return Outcome(1, f"تعذّر تشكيل الكلمة «{brief.wordmark_text}» من خط عناوين الاتجاه ({word_font[0]}): {exc}", ws)
            mark_svg = smalls[chosen.id]
            keep_word(wm, lock_svg)
        elif chosen.medium.value in config.SMALL_REQUIRED:
            # الكلمة هي العلامة الأساسية؛ الرمز المصغّر للأيقونات، والقفل هو الكلمة نفسها
            wm = WordmarkSVG(svg=svgs[chosen.id], width=256.0, height=256.0, path_d="")
            mark_svg, lock_svg = smalls[chosen.id], svgs[chosen.id]
        else:
            wm, mark_svg, lock_svg = wordmark, svgs[chosen.id], lockups.get(chosen.id) or svgs[chosen.id]
        pkg_brief, picked = brief, None
        if pending is not None:
            self._identity.preview(ws, brief, strategy, mark_svg, lock_svg, chosen.sentence)
            return self._wait(pending, ws)
        if ident:
            per_direction = (lambda d: word_lockup(d.heading.font, d.heading.weight)[1]) if word_font is not None else None
            try:
                picked = self._identity.directions(ws, brief, strategy, mark_svg, lock_svg, chosen.sentence, auto=auto, kept=kept,
                                                   lockup_for=per_direction)
            except (FileNotFoundError, ValueError) as exc:
                return Outcome(1, f"تعذّر تشكيل الكلمة «{brief.wordmark_text}» من خط عناوين أحد الاتجاهات: {exc}", ws)
            if isinstance(picked, Wait):
                if picked.failures and designer.enabled(brief):  # اتجاه المصمّم المردود يعود إليه كالعلامة، لا إلى المالك
                    return self._designer_fix(ws, brief, [f"direction: {f}" for f in picked.failures], min_mark_px)
                return self._wait(picked, ws)
            c = picked[0].colors
            if word_font is not None:  # الكلمة تتبع خط عناوين الاتجاه الذي اختاره المالك
                wm, lock_svg = word_lockup(picked[0].heading.font, picked[0].heading.weight)
                keep_word(wm, lock_svg)
            pkg_brief = replace(brief, palette=replace(brief.palette, paper=c["paper"], ink=c["ink"], brand=c["brand"], accent=c["accent"]))
        pkg_root = self._stage_package(ws, pkg_brief, chosen, mark_svg, audits[chosen.id], wm, lock_svg, min_mark_px, min_stroke_px,
                                       min_wordmark_px)
        if picked is not None:
            d, system, rep_, fonts = picked
            w = self._identity.build(ws, brief, strategy, d, system, rep_, fonts, pkg_root, mark_svg, lock_svg, chosen.sentence)
            if w is not None:
                return self._wait(w, ws)
        close_workspace(ws)
        msg = f"الحزمة مكتملة للمفهوم {chosen.id} في {pkg_root}"
        if picked is not None and self._on_identity is not None:
            msg += "\n" + self._on_identity(ws.root)
        return Outcome(0, msg, ws)

    # ----- المراحل -----
    @staticmethod
    def _wait(w: Wait, ws: Workspace) -> Outcome:
        return Outcome(AWAIT_MODEL if w.who == "model" else AWAIT_OWNER, w.message, ws, gate=w.gate, digest=w.digest, request=w.request)

    @staticmethod
    def _ask(a: Ask, ws: Workspace) -> Outcome:
        return Outcome(AWAIT_MODEL, a.message, ws, request=a.request)

    def _inherit_mark(self, ws: Workspace, brief: Brief) -> None:
        """إصدار هوية جديد يرث العلامة المعتمدة من إصدار سابق: عملها وقراراتها وتحقق اسمها، لا حزمتها."""
        src_name = brief.identity.inherit_mark
        if not src_name or ws.done("brief") or ws.done("inherited"):
            return
        src = ws.root.parent / src_name
        if not (src / "decisions.jsonl").is_file():
            raise FileNotFoundError(f"inherit_mark: لا قرارات في {src}")
        shutil.copytree(src / "work", ws.work, dirs_exist_ok=True)
        # مسار المصمّم الخارجي: صفحة السكتشات واختيار المالك وتسليم المتجه جزء من العلامة الموروثة، وبدونها يُطلب الرسم من جديد
        for name in ("decisions.jsonl", "name_check.yaml", "NAME-CHECK.md", "DECISIONS.md", "preview.html", "preview.png",
                     "designer_decisions.jsonl"):
            if (src / name).is_file():
                shutil.copy2(src / name, ws.root / name)
        if (src / "designer").is_dir():
            shutil.copytree(src / "designer", ws.root / "designer", dirs_exist_ok=True)
        (ws.root / "stages").mkdir(parents=True, exist_ok=True)
        for m in (src / "stages").glob("*.json"):
            # الحزمة والتسليم والدليل تخصّ الإصدار السابق: إصدار يرث علامة لا يرث اكتمال هويتها
            # وقرارات بوابات الهوية لا تورَّث (`identity_decisions.jsonl`)، فعلاماتها لا تورَّث: علامة `directions` موروثة كانت
            # تخفي بطاقة الاتجاه والخط ينتظر المالك عندها (ب2). وعدّاد جولات التصحيح للبناء الجاري لا لسلفه
            if m.stem not in ("package", "deliver", "deliver_pending", "brief", "identity", "identity_build", "strategy", "directions",
                              "directions_board", "name_check", designer.FIX_MARKER, designer.REOPEN_MARKER):
                shutil.copy2(m, ws.root / "stages" / m.name)
        ws.mark_done("inherited", {"from": src_name})

    def _stage_brief(self, ws: Workspace, brief: Brief) -> None:
        if ws.done("brief"):
            return
        from dataclasses import asdict
        (ws.root / "brief.json").write_text(json.dumps(asdict(brief), ensure_ascii=False, indent=2), encoding="utf-8")
        ws.mark_done("brief", {"hash": brief.hash()})

    def _stage_research(self, ws: Workspace, brief: Brief) -> None:
        if ws.done("research"):
            return
        summary = research(brief, self._catalog, ws.work)
        ws.mark_done("research", {"groups": list(summary.get("groups", {}))})

    def _maybe_rotate_medium(self, ws: Workspace, ledger: Ledger, medium: Medium) -> None:
        """إن تغيّر الوسيط عمّا بُنيت عليه المفاهيم، أو اختار المالك وسيطًا (ولو الوسيط نفسه، أي «ارسم من جديد»)، تُؤرشف
        المفاهيم والتحكيم ويُعاد فتح diverge، وتُعدّ ملاحظات المالك السابقة معالجة (تبقى في طلب الرسم الجديد سياقًا)."""
        decisions = ledger.read()
        switches = sum(1 for d in decisions if d.verdict is Verdict.SWITCH)
        prev = ws.read_marker("diverge").get("medium")
        epoch = int(ws.read_marker("medium_epoch").get("switches", 0))
        if (prev and prev != medium.value) or (switches != epoch and (ws.work / "concepts.yaml").is_file()):
            prev = prev or medium.value
            hist = self._archive_concepts(ws, ledger, f"medium-{prev}")
            (ws.work / "MEDIUM-ROTATED.md").write_text(
                f"رسم جديد بوسيط «{MEDIUM_AR[medium]}» (السابق «{MEDIUM_AR[Medium(prev)]}»). "
                f"المفاهيم القديمة في {hist.relative_to(ws.root).as_posix()}/.", encoding="utf-8")
        if switches != epoch:
            ws.mark_done("medium_epoch", {"switches": switches})

    def _stage_style(self, ws: Workspace, brief: Brief, ledger: Ledger) -> Outcome | None:
        """بوابة الطابع قبل الرسم: عينات الأساليب الستة ثم اختيار المالك. اختيار جديد بعد وجود مفاهيم يؤرشفها ويعيد الرسم
        بالطابع المختار، وتُعدّ ملاحظات المالك السابقة معالجة (تبقى سياقًا في الطلب الجديد)."""
        picks = style.choices(ws)
        if picks:
            epoch = int(ws.read_marker("style_epoch").get("choices", 0))
            if len(picks) != epoch:
                if (ws.work / "concepts.yaml").is_file():
                    self._archive_concepts(ws, ledger, "style")
                ws.mark_done("style_epoch", {"choices": len(picks), "styles": picks[-1]["styles"]})
            return None
        problems = style.validate(ws, style.compile_samples(ws, self._build))
        if problems:
            req = style.write_request(ws, brief, problems, self._owner_history(ws))
            return Outcome(AWAIT_MODEL, "بانتظار عينات الطابع: " + "؛ ".join(problems[:3]) + f"\nالطلب في {req}", ws, request=req.name)
        ws.mark_done("style_board", {"digest": style.digest(ws)})
        return Outcome(AWAIT_OWNER, "عينات الطابع جاهزة: اختر واحدًا أو اثنين من منصة سِمة "
                                    "(أو `sima style <brief> --pick s1`).", ws, gate="style", digest=style.digest(ws))

    @staticmethod
    def _archive_concepts(ws: Workspace, ledger: Ledger, tag: str) -> Path:
        """يؤرشف المفاهيم وبناءها ونقدها وتحكيمها إلى history/<tag>-<k> ويعيد فتح الرسم من البداية."""
        decisions = ledger.read()
        k = 1
        while (ws.work / "history" / f"{tag}-{k}").exists():
            k += 1
        hist = ws.work / "history" / f"{tag}-{k}"
        hist.mkdir(parents=True, exist_ok=True)
        for p in [*ws.concepts_dir.glob("*.svg"), *ws.concepts_dir.glob("*.mark.yaml"), *ws.concepts_dir.glob("*.mark.error.txt"), ws.work / "concepts.yaml", ws.work / "ideas.yaml"]:
            if p.is_file():
                (hist / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
                p.unlink()
        for p in ws.critique_dir.glob("round*.*"):
            (hist / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            p.unlink()
        ws.work.joinpath("audit.json").unlink(missing_ok=True)
        live_preview.clear(ws.concepts_dir)
        thumbs.archive(ws, hist, tag)
        for st in ("diverge", "render", "critique", "preview", "shortlist"):
            if ws.done(st):
                ws.marker(st).unlink()
        Pipeline._archive_verdicts(ws, tag)
        ws.mark_done("owner_feedback", {"handled": len(decisions)})
        return hist

    @staticmethod
    def _concept_passes(c: Concept, audits: dict[str, AuditReport]) -> bool:
        main = audits.get(c.id)
        small = audits.get(c.id + "-small")
        if main is None or not main.passed:
            return False
        if c.medium.value in config.SMALL_REQUIRED:
            return small is not None and small.passed
        return True

    def _stage_render(self, ws: Workspace, brief: Brief, concepts: list[Concept], svgs: dict[str, str],
                      smalls: dict[str, str] | None = None, *, small_base: int = 16,
                      min_stroke: float | None = None, main_base: int | None = None,
                      main_stroke: float | None = None) -> dict[str, AuditReport]:
        smalls = smalls or {}
        main_floor = main_stroke if main_stroke is not None else min_stroke
        pal = brief.palette
        # ألوان الفحص جزء من المفتاح: إصدار يرث علامة بلون علامة جديد كان يعيد تباين سلفه من المخبأ («مرصد» v2)
        digest = (protocol.merged_digest(svgs, smalls) + (f"@{small_base}" if small_base != 16 else "")
                  + (f"#s{min_stroke:g}" if min_stroke is not None else "")
                  + (f"@w{main_base}" if main_base is not None else "") + (f"#w{main_stroke:g}" if main_stroke is not None else "")
                  + f"|{pal.paper}|{pal.ink}|{pal.brand or ''}")
        marker = ws.read_marker("render")
        if marker.get("digest") == digest and (ws.work / "audit.json").is_file():
            data = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
            return {k: AuditReport(**v) for k, v in data.items()}
        audits: dict[str, AuditReport] = {}
        pal = brief.palette
        for c in concepts:
            svg = svgs[c.id]
            out = ws.render_dir / c.id
            self._render.render_concept(c.id, svg, out)
            # حدّ أدنى معلن فوق حجم فحص الوسيط (علامة معتمدة خارج الخط): المفهوم الرئيس لا يُفحص دون حدّه المعلن
            base = max(config.AUDIT_BASE_SIZE.get(c.medium.value, 16), main_base if main_base is not None else small_base)
            rep = self._audit.audit(c.id, svg, stage="bw", paper=pal.paper, ink=pal.ink, brand=pal.brand, base_size=base,
                                    min_stroke=main_floor)
            audits[c.id] = rep
            (out / "audit.json").write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            if c.id in smalls:
                sid = c.id + "-small"
                sout = ws.render_dir / sid
                self._render.render_concept(sid, smalls[c.id], sout)
                srep = self._audit.audit(sid, smalls[c.id], stage="bw", paper=pal.paper, ink=pal.ink, brand=pal.brand,
                                         base_size=small_base, min_stroke=min_stroke)
                audits[sid] = srep
                (sout / "audit.json").write_text(json.dumps(srep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        pair = self._sim.pairwise(svgs)
        close_pairs = [p for p in pair if p["distance"] <= config.SIMILARITY_WARN]
        for p in close_pairs:
            for cid in (p["a"], p["b"]):
                audits[cid].warnings.append(f"يشبه المفهوم {p['b'] if cid == p['a'] else p['a']} إدراكيًا (مسافة {p['distance']}): ليسا متباعدين")
        (ws.work / "audit.json").write_text(json.dumps({k: v.to_dict() for k, v in audits.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
        ws.mark_done("render", {"digest": digest, "pairwise": pair})
        ws.mark_done("diverge", {"medium": concepts[0].medium.value, "digest": digest})
        return audits

    def _stage_critique(self, ws: Workspace, brief: Brief, concepts: list[Concept], svgs: dict[str, str],
                        smalls: dict[str, str], audits: dict[str, AuditReport]) -> Ask | None:
        """يعيد رسالة انتظار إن لزم النموذج، وإلا None. نقد الرسّام مرة واحدة لكل رسم جديد؛ تعديلات الحَكَم والمالك بعده
        لا تعيد فتحه (الحَكَم يحكم على كل تعديل)."""
        if ws.done("critique"):
            return None
        rounds = protocol.critique_rounds_done(ws)
        digest = protocol.merged_digest(svgs, smalls)
        all_pass = all(a.passed for a in audits.values())
        if rounds == 0:
            self._write_request_critique(ws, brief, concepts, audits, 1, digest)
            return Ask(f"بانتظار نقد النموذج (الجولة 1): {ws.work / 'REQUEST-critique-r1.md'}", "REQUEST-critique-r1.md")
        verdicts, bad = protocol.read_critique(ws, rounds) or ({}, [])
        requested_digest = protocol.read_critique_request(ws, rounds).get("digest")
        if bad:  # ملف الجولة لا تُقرأ صيغته: يعود في طلب الجولة نفسها بمشاكله، ولا يسقط الخط ولا تُحسب الجولة منجزة
            self._write_request_critique(ws, brief, concepts, audits, rounds, requested_digest or digest, problems=bad)
            return Ask(f"ملف نقد الجولة {rounds} لا تُقرأ صيغته: " + "؛ ".join(bad[:3]) + f"\nالطلب في {ws.work / f'REQUEST-critique-r{rounds}.md'}",
                       f"REQUEST-critique-r{rounds}.md")
        # drop رأي الرسّام أن المفهوم لا يستحق العرض: لا يُنتظر بعده تعديل (كان يُحسب تعديلًا معلّقًا فيُعاد الطلب نفسه بلا نهاية:
        # ست استدعاءات نقد في دورة سِمة v2 الرابعة حيث يكفي اثنان). الحَكَم يحكم على الخمسة والقائمة القصيرة تسقط الأضعف.
        wants_revision = any(v.get("action") == "revise" for v in verdicts.values())
        revised = requested_digest is not None and requested_digest != digest
        if wants_revision and not revised:
            return Ask(f"الجولة {rounds} تطلب تعديلات لم تُنفَّذ بعد: عدّل work/concepts/*.svg ثم أعد التشغيل",
                       f"REQUEST-critique-r{rounds}.md")
        if all_pass and not revised:
            ws.mark_done("critique", {"rounds": rounds, "digest": digest})
            return None
        if rounds >= config.MAX_CRITIQUE_ROUNDS:
            ws.mark_done("critique", {"rounds": rounds, "digest": digest, "exhausted": True})
            return None
        self._write_request_critique(ws, brief, concepts, audits, rounds + 1, digest)
        return Ask(f"بانتظار نقد النموذج (الجولة {rounds + 1}): {ws.work / f'REQUEST-critique-r{rounds + 1}.md'}",
                   f"REQUEST-critique-r{rounds + 1}.md")

    @staticmethod
    def _pending_feedback(ws: Workspace, ledger: Ledger, medium: Medium, concepts: list[Concept]):
        """قرارات المالك (رفض أو طلب تعديل) التي لم تُنفَّذ بعد على المفاهيم الحالية: (كل القرارات، عدد المنفَّذ، المعلّق)."""
        decisions = ledger.read()
        handled = int(ws.read_marker("owner_feedback").get("handled", 0))
        ids = {c.id for c in concepts}
        pending = [d for d in decisions[handled:]
                   if d.verdict in (Verdict.REJECTED, Verdict.REVISE) and d.concept_id in ids and d.medium is medium]
        return decisions, handled, pending

    def _spread_problems(self, ws: Workspace, ledger: Ledger, medium: Medium, problems: list[str]) -> list[str]:
        """تباعد حقيقي قبل أي تصيير: لا قاعدة خط واحدة للجميع، ولا عودة إلى فكرة رفضها المالك. وفكرة كل مفهوم مرفوض
        تُحفظ هنا قبل أن يُعاد الرسم فوقها. وإن كان الرسّام سيُستدعى الآن على أي حال ضُمّت ملاحظات المالك المعلّقة إلى
        الطلب نفسه، فلا يُعاد رسم المفهوم مرتين."""
        drawn, bad = protocol.parse_concepts(ws)
        if bad:  # ملف لا تُقرأ صيغته: مشكلته مذكورة في problems
            return problems
        decisions, handled, pending = self._pending_feedback(ws, ledger, medium, drawn)
        digest = protocol.merged_digest(protocol.read_concept_svgs(ws, drawn), protocol.read_small_svgs(ws, drawn))
        req = ws.read_marker("owner_feedback").get("request") or {}
        waiting = pending if not req.get("digest") or req["digest"] == digest else []  # لم يُعَد رسمها بعد
        by_id = {c.id: c for c in drawn}
        for d in waiting:
            if d.verdict is Verdict.REJECTED:
                novelty.record(ws, by_id[d.concept_id], d.reason, d.at)
        if not problems:
            if self._build is not None:
                problems = problems + protocol.shared_font_problems(ws, drawn)
            problems = problems + novelty.check(ws, drawn, self._embedder, skip={d.concept_id for d in waiting})
        if problems and waiting and not req.get("digest"):
            problems = problems + [
                f"{'رفض' if d.verdict is Verdict.REJECTED else 'طلب تعديل'} المالك للمفهوم {d.concept_id}: «{d.reason}» — "
                + ("استبدل فكرته بفكرة جديدة أقوى حيلةً" if d.verdict is Verdict.REJECTED else "عدّله بهذه الملاحظة")
                for d in waiting]
            ws.mark_done("owner_feedback", {"handled": handled, "request": {"digest": digest, "upto": len(decisions)}})
        return problems

    def _stage_owner_feedback(self, ws: Workspace, brief: Brief, ledger: Ledger, medium: Medium, concepts: list[Concept],
                              svgs: dict[str, str], smalls: dict[str, str]) -> Ask | None:
        """رفض المالك أو طلبه تعديلًا لمفهوم معروض يُعاد رسمًا في الوسيط نفسه بسببه، ثم يعود إلى الحَكَم.
        يُعدّ الطلب منفّذًا حين يتغيّر محتوى الرسوم عن لحظة كتابته."""
        decisions, handled, pending = self._pending_feedback(ws, ledger, medium, concepts)
        mk = ws.read_marker("owner_feedback")
        if not pending:
            return None
        digest = protocol.merged_digest(svgs, smalls)
        req = mk.get("request") or {}
        if req.get("digest") and req["digest"] != digest:
            ws.mark_done("owner_feedback", {"handled": int(req["upto"])})
            self._archive_verdicts(ws, "owner")
            if ws.done("shortlist"):
                ws.marker("shortlist").unlink()
            return None
        items = [(d.concept_id, d.reason, d.verdict) for d in pending]
        self._write_request_refine(ws, brief, concepts, "REQUEST-refine-owner.md",
                                   "إعادة رسم بملاحظات المالك",
                                   [(cid, [f"{'رفض' if v is Verdict.REJECTED else 'طلب تعديل'} المالك: {r}"], "", v is Verdict.REJECTED)
                                    for cid, r, v in items])
        ws.mark_done("owner_feedback", {"handled": handled, "request": {"digest": digest, "upto": len(decisions)}})
        return Ask(f"بانتظار إعادة الرسم بملاحظات المالك ({', '.join(sorted({i[0] for i in items}))}): "
                   f"{ws.work / 'REQUEST-refine-owner.md'}", "REQUEST-refine-owner.md")

    @staticmethod
    def _family_values() -> str:
        """قيم family كما تُكتب في الملف، وبجانب كل منها اسمها العربي: الطلبات كانت تسرد العربي وحده، فكتب النموذج
        `metaphoric` وكلّف تصحيحها استدعاءً بثلاثة دولارات."""
        return "، ".join(f"`{f.value}` ({ar})" for f, ar in FAMILY_AR.items())

    def _stage_fix(self, ws: Workspace, brief: Brief) -> Ask | None:
        """ملف أفكار أو مفاهيم لا تُقرأ صيغته يعود بطلب تصحيح ضيّق باسمه: البنود المذكورة وحدها، بجهد متوسط، ويُمنع تغيير
        غيرها. كانت أي مشكلة تعيد طلب المصغّرات أو الرسم كاملًا بالجهد العالي، فاستُبدلت أربع أفكار لم يُطلب تغييرها."""
        problems = protocol.format_problems(ws)
        if not problems:
            return None
        lines = [
            f"# طلب تصحيح صيغة: {brief.name_ar}", "",
            "ملف كتبتَه لا تقرؤه الأداة بصيغته. صحّح البنود المذكورة تحت «ما يُصحَّح» وحدها، في مكانها.",
            "لا تغيّر أي بند آخر، ولا تستبدل فكرة ولا مفهومًا، ولا تُعد صياغة جملة، ولا تلمس `work/thumbs/` ولا `work/concepts/`:",
            "هذا تصحيح صيغة لا طلب رسم، وما لم يُذكر يبقى بحروفه.", "",
            "## الصيغة",
            "- `work/ideas.yaml`: خريطة فيها `ideas:` قائمة بنود `{id, family, sentence, twist}`.",
            "- `work/concepts.yaml`: خريطة فيها `concepts:` قائمة بنود `{id, name, family, medium, sentence, idea_id, construction, reference}`.",
            f"- family واحدة من هذه القيم بحروفها: {self._family_values()}.",
            f"- medium واحد من: {protocol.MEDIUM_VALUES}.", "",
            "## ما يُصحَّح", *[f"- {p}" for p in problems], "",
            "ثم أعد تشغيل: `uv run sima run <brief>`",
        ]
        ws.write_request(FIX_REQUEST, "\n".join(lines))
        return Ask("ملف من النموذج لا تُقرأ صيغته: " + "؛ ".join(problems[:3]) + f"\nالطلب في {ws.work / FIX_REQUEST}", FIX_REQUEST)

    @staticmethod
    def _ideas_spec() -> str:
        """مواصفة ملف الأفكار بنص واحد في طلب المصغّرات وطلب الرسم."""
        return (f"`work/ideas.yaml`: بين {config.IDEAS_MIN} و{config.IDEAS_MAX} فكرة: `ideas: [{{id, family, sentence, twist}}]`؛"
                f" family واحدة من هذه القيم بحروفها: {Pipeline._family_values()}؛"
                " twist هو الحيلة (قراءة مزدوجة، فراغ سلبي، تحويل غير متوقع) في جملة."
                f" وزّع الأفكار على مناطق معنى مختلفة، ولا تزد على {config.IDEAS_PER_TERRITORY} في المنطقة الواحدة: شكل حروف الاسم نفسها وما"
                " فيها من مصادفات، وكل كلمة من الكلمات الثلاث على حدة، وما يفعله المنتج (الغرض)، وسياق استعماله عند جمهوره.")

    def _stage_thumbs(self, ws: Workspace, brief: Brief, medium: Medium) -> Ask | None:
        """مصغّرات الأفكار قبل الرسم الكامل: لكل فكرة مصغّرة سريعة يقرؤها القارئ الأعمى، والمردودة لا يُبنى عليها مفهوم.
        تعمل عند بدء دورة رسم فقط (لا مفاهيم بعد)؛ جولتان على الأكثر. تعيد رسالة انتظار أو None."""
        if not self._thumbs or self._build is None or ws.done(thumbs.KIND) or (ws.work / "concepts.yaml").is_file():
            return None
        ideas, problems = thumbs.validate(ws, thumbs.compile_specs(ws, self._build))
        if problems:
            self._write_request_thumbs(ws, brief, medium, problems, None)
            return Ask("بانتظار مصغّرات الأفكار: " + "؛ ".join(problems[:3]) + f"\nالطلب في {ws.work / thumbs.REQUEST}", thumbs.REQUEST)
        built = thumbs.svgs(ws, ideas)
        digest = thumbs.digest(built)
        ids = [i.id for i in ideas]
        r = blind.read(ws, digest, ids, thumbs.KIND)
        if r is None or r.problems:
            thumbs.render(ws, self._r, built)
            blind.write_request(ws, ids, digest, r.problems if r else [], kind=thumbs.KIND, name=thumbs.BLIND_REQUEST,
                                images=lambda iid: thumbs.images(ws, iid))
            return Ask(f"بانتظار القراءة العمياء للمصغّرات: {ws.work / thumbs.BLIND_REQUEST}", thumbs.BLIND_REQUEST)
        sel = thumbs.select(r, ideas, self._embedder)
        short = len(sel.allowed) < config.CONCEPTS_REQUIRED
        if short and blind.rounds(ws, thumbs.KIND) < config.THUMBS_MAX_ROUNDS:
            self._write_request_thumbs(
                ws, brief, medium,
                [f"اجتازت القراءة العمياء {len(sel.allowed)} أفكار والمطلوب {config.CONCEPTS_REQUIRED} على الأقل: استبدل كل فكرة مردودة"
                 " بفكرة جديدة من منطقة معنى أخرى (بمعرّف جديد ومصغّرة جديدة)، ولا تجمّل المصغّرة المردودة."], sel)
            return Ask(f"مصغّرات مردودة عند القارئ الأعمى ({len(sel.blocked)}): استبدال قبل الرسم {ws.work / thumbs.REQUEST}",
                       thumbs.REQUEST)
        ws.mark_done(thumbs.KIND, thumbs.marker(sel, digest, exhausted=short))
        return None

    def _write_request_thumbs(self, ws: Workspace, brief: Brief, medium: Medium, problems: list[str],
                              sel: thumbs.Selection | None) -> None:
        lines = [
            f"# طلب مصغّرات الأفكار: {brief.name_ar}", "",
            f"الوسيط الحالي: {MEDIUM_AR[medium]} ({medium.value}). قبل رسم أي مفهوم كامل: أفكار كثيرة، ولكل فكرة مصغّرة سريعة تُرى.",
            f"اقرأ `work/research.md` و`{SKILL}/SKILL.md`، ثم `{REFS}/40-professional-bar.md` (اختبارات المهنة)",
            f"و`{REFS}/45-drawer-profile.md` و`{REFS}/43-lessons-v1.md` و`{REFS}/42-arabic-lettering.md`"
            f" و`{REFS}/41-construction.md` (صيغة البناء).", "",
            "## المطلوب",
            "1. " + self._ideas_spec(),
            "2. لكل فكرة `work/thumbs/<idea_id>.mark.yaml` بصيغة أداة البناء: مصغّرة لا مفهوم. ثلاثة أشكال إلى ستة، لوحة 256، بلا تصحيحات"
            " بصرية ولا تفاصيل ولا `accent`. الغاية الوحيدة أن تُرى الحيلة عند 16 بكسل؛ ما لا يُرى في المصغّرة لن يُرى في العلامة.",
            "3. لا تكتب `work/concepts.yaml` ولا شيئًا في `work/concepts/` في هذا الطلب.", "",
            "## كيف تُقرأ",
            "قارئ مستقل لا يعرف الاسم ولا الفكرة يقرأ كل مصغّرة عند 128 ثم 16 بكسل ويكتب أول ما يراه. ما يقرؤه حرفًا غير عربي أو رمزًا",
            "شائعًا أو أيقونة واجهة أو علامة معروفة يُردّ، ولا يُبنى عليه مفهوم. والباقي يُرتَّب بقرب ما رآه مما كتبتَه في sentence وtwist؛",
            "فاكتب الجملة وصفًا لما يُرى لا لما يُقصد.",
            "الأداة تصيّر كل مصغّرة تكتبها إلى `work/thumbs/<idea_id>.preview.png` خلال ثوانٍ: انظر كل واحدة مرة. المصغّرة التي تقرؤها",
            "أنت حرفًا لاتينيًا أو رمزًا شائعًا استبدل فكرتها ولا تجمّلها؛ إعادة واحدة على الأكثر للمصغّرة.", "",
            "## الموجز",
            f"- الغرض: {brief.purpose}", f"- الجمهور: {brief.audience}", f"- النموذج الأصلي: {brief.archetype}",
            f"- الكلمات الثلاث: {'، '.join(brief.three_words)}", f"- الإحساس: {brief.taste.feeling}",
            "- ممنوع: " + "؛ ".join(list(brief.taste.avoid) + list(brief.taste.dislikes)), "",
            *style.lines(ws), *self._tool_rules(medium), *self._owner_history(ws), *novelty.lines(ws),
        ]
        if sel is not None:
            lines += ["## قراءة المصغّرات السابقة",
                      *[f"- {iid} مجتازة: {sel.seen[iid]}" for iid in sel.allowed],
                      *[f"- {iid} مردودة: {why}" for iid, why in sel.blocked.items()],
                      "أبقِ المجتازة كما هي (فكرتها ومصغّرتها)، واحذف المردودة من `work/ideas.yaml` وضع مكانها أفكارًا جديدة.", ""]
        lines += ["## ما ينقص الآن", *[f"- {p}" for p in problems], "", "ثم أعد تشغيل: `uv run sima run <brief>`"]
        ws.write_request(thumbs.REQUEST, "\n".join(lines))

    @staticmethod
    def _archive_verdicts(ws: Workspace, tag: str) -> None:
        """أحكام الحَكَم وقراءات القارئ الأعمى تخص رسمًا بعينه: تُؤرشفان معًا فتبدأ الدورة التالية بعدّادين صفرين."""
        judging.archive(ws, tag)
        blind.archive(ws, tag)
        ws.marker("blind_read").unlink(missing_ok=True)

    def _stage_blind(self, ws: Workspace, brief: Brief, concepts: list[Concept], svgs: dict[str, str],
                     smalls: dict[str, str]) -> Ask | None:
        """قارئ مستقل لا يعرف الاسم ولا الفكرة يقرأ الصور قبل الحَكَم. ما قرأه حرفًا أجنبيًا أو رمزًا شائعًا أو أيقونة واجهة
        يعود إلى الرسّام مرة واحدة؛ بعد BLIND_MAX_ROUNDS قراءة يمضي الخط إلى الحَكَم والقراءة أمامه. وبعد استنفادها لا يُقرأ
        إلا مفهوم استُبدلت فكرته منذ قراءته (صقل الحَكَم يأتي بأفكار لم تمرّ بمصغّرة ولا بقارئ)، وقراءته أمام الحَكَم بلا صقل.
        يعيد رسالة انتظار أو None."""
        if not self._blind:
            return None
        digest = protocol.merged_digest(svgs, smalls)
        if judging.judge_path(ws, digest).is_file():  # محتوى حُكم عليه قبل تفعيل البوابة أو بعد استنفادها: لا قراءة بعد الحكم
            return None
        done = blind.rounds(ws)
        mk = ws.read_marker("blind_read")  # ما قُرئ: فكرة كل مفهوم عند قراءته، ومعرّفات كل قراءة ببصمة محتواها
        ideas, scopes = dict(mk.get("ideas") or {}), dict(mk.get("scope") or {})
        key = {c.id: f"{c.idea_id or ''}|{c.sentence.strip()}" for c in concepts}
        ids = scopes.get(digest)
        if ids is None:
            if done < config.BLIND_MAX_ROUNDS or blind.path(ws, digest).is_file():
                ids = [c.id for c in concepts]
            else:
                ids = [c.id for c in concepts if c.id in ideas and ideas[c.id] != key[c.id]]
                if not ids:
                    return None
            scopes[digest] = ids
            ws.mark_done("blind_read", {"ideas": ideas, "scope": scopes})
        r = blind.read(ws, digest, ids)
        if r is None or r.problems:
            blind.write_request(ws, ids, digest, r.problems if r else [])
            return Ask(f"بانتظار القراءة العمياء: {ws.work / blind.REQUEST}", blind.REQUEST)
        ws.mark_done("blind_read", {"ideas": ideas | {cid: key[cid] for cid in ids if cid in key}, "scope": scopes})
        blocked = r.blocked()
        if not blocked or done >= config.BLIND_MAX_ROUNDS:
            return None
        self._write_request_refine(
            ws, brief, concepts, "REQUEST-refine-blind.md", f"تصحيح القراءة الخاطئة (القراءة العمياء {done})",
            [(x.concept_id, [f"قارئ مستقل لم يُعطَ الاسم ولا الفكرة {x.line()}"],
              "غيّر الشكل حتى تزول هذه القراءة من النظرة الأولى (عند 16 بكسل أيضًا)، أو استبدل الفكرة إن كانت القراءة لازمة لهيئتها."
              " لا تعالجها بإضافة تفصيل صغير يختفي عند 16.", False) for x in blocked])
        return Ask(f"قراءة خاطئة عند القارئ الأعمى ({', '.join(x.concept_id for x in blocked)}): "
                   f"صقل قبل الحَكَم {ws.work / 'REQUEST-refine-blind.md'}", "REQUEST-refine-blind.md")

    @staticmethod
    def _tool_rules(medium: Medium) -> list[str]:
        """القواعد التي يفرضها الفحص الحتمي تُسرد للرسّام والحَكَم بنص واحد، فلا يطلب أحدهما ما يردّه الفحص. في سِمة v2 طلب
        الحَكَم سماكة 16 «لتقترب من عينة الطابع» والفحص يردّ ما دون 24، فأُعيد رسم المجموعة كلها بين القاعدتين."""
        base = config.AUDIT_BASE_SIZE.get(medium.value, 16)
        px = f"{config.MIN_STROKE_AT_16:g}"
        units = round(config.MIN_STROKE_AT_16 * config.CANVAS / 16)
        if medium.value in config.SMALL_REQUIRED:
            floor = (f"أصغر سماكة أو فتحة ≥ {px} بكسل حين تُعرض العلامة بارتفاع {base} بكسل، وللرمز المصغّر ≥ {px} بكسل عند 16"
                     f" (= {units} وحدة على لوحة {config.CANVAS})")
        else:
            floor = (f"أصغر سماكة أو فتحة ≥ {px} بكسل حين تُعرض العلامة عند {base} بكسل"
                     f" (= {round(config.MIN_STROKE_AT_16 * config.CANVAS / base)} وحدة على لوحة {config.CANVAS})")
        return ["## قواعد الأداة الملزمة (فحص حتمي يسبق الحَكَم)",
                f"- {floor}. ما دونها يردّه الفحص ولا يصل إلى الحَكَم.",
                "- لا يُطلب في `direction` ولا يُنفَّذ في الصقل سماكة أو فراغ دون هذا الحد، ولا تُخفض درجة لأن الخط أثقل من عينة الطابع:"
                " العينة كلمة على لوحة عريضة لا تُعرض عند 16 بكسل. الطابع يُترجم في العلامة بثبات السماكة ونوع الأقواس والنهايات"
                " ونسبة الفراغ إلى الحبر، لا بوزن الخط المطلق.",
                "- إن ضاق الشكل عند هذه السماكة فالعلاج تقليل العناصر أو توسيع العيون والفراغات، لا ترقيق الخط.", ""]

    def _stage_judge(self, ws: Workspace, brief: Brief, concepts: list[Concept], svgs: dict[str, str],
                     smalls: dict[str, str], audits: dict[str, AuditReport]) -> list[str] | Ask:
        """الحَكَم المستقل يقيّم كل محتوى جديد؛ الأداة تحسب العتبة. دون ثلاثة مجتازين: صقل آلي حتى JUDGE_MAX_ROUNDS،
        ثم يُعرض الأفضل مع تنبيه. يعيد قائمة المعروض أو رسالة انتظار."""
        digest = protocol.merged_digest(svgs, smalls)
        ids = [c.id for c in concepts]
        j = judging.read(ws, digest, ids)
        if j is None or j.problems:
            self._write_request_judge(ws, brief, concepts, audits, digest, j.problems if j else [])
            return Ask(f"بانتظار الحَكَم المستقل: {ws.work / 'REQUEST-judge.md'}", "REQUEST-judge.md")
        eligible = [c.id for c in concepts if self._concept_passes(c, audits)]
        picked, below = judging.shortlist(j, eligible)
        if below and judging.rounds(ws) < config.JUDGE_MAX_ROUNDS:
            failing = [s for s in j.scores.values() if not s.passed]
            self._write_request_refine(ws, brief, concepts, "REQUEST-refine.md", f"صقل بعد التحكيم (الجولة {judging.rounds(ws)})",
                                       [(s.concept_id, [*s.failures(), *s.blockers], s.direction, s.replace)
                                        for s in sorted(failing, key=lambda s: -s.total)])
            return Ask(f"دون العتبة ({sum(1 for s in j.scores.values() if s.passed)} مجتاز من {config.SHORTLIST}): صقل آلي "
                       f"{ws.work / 'REQUEST-refine.md'}", "REQUEST-refine.md")
        ws.mark_done("shortlist", {"digest": digest, "ids": picked, "below_bar": below,
                                   "scores": {cid: j.scores[cid].total for cid in picked if cid in j.scores},
                                   "passed": [cid for cid in picked if cid in j.scores and j.scores[cid].passed]})
        return picked

    def _stage_wordmark(self, ws: Workspace, brief: Brief, concepts: list[Concept], svgs: dict[str, str]) -> tuple[WordmarkSVG | None, dict[str, str]]:
        if concepts and concepts[0].medium.value in config.SMALL_REQUIRED:
            # في وسيط الكلمة، المفهوم نفسه هو العلامة الكلامية والقفل
            return None, {c.id: svgs[c.id] for c in concepts}
        wm_path = ws.work / "wordmark.svg"
        try:
            wm = self._shaping.wordmark(brief.wordmark_text, brief.wordmark_font, brief.wordmark_weight, title=brief.wordmark_text)
        except (FileNotFoundError, ValueError) as exc:
            (ws.work / "WORDMARK-ERROR.txt").write_text(str(exc), encoding="utf-8")
            return None, {}
        wm_path.write_text(wm.svg, encoding="utf-8")
        lockups = {}
        for c in concepts:
            lk = ShapingService.lockup(svgs[c.id], wm, rtl=(brief.language == "ar"))
            (ws.work / "lockups").mkdir(exist_ok=True)
            (ws.work / "lockups" / f"{c.id}.svg").write_text(lk, encoding="utf-8")
            lockups[c.id] = lk
        return wm, lockups

    def _stage_preview(self, ws: Workspace, brief: Brief, concepts: list[Concept], svgs: dict[str, str], smalls: dict[str, str],
                       audits: dict[str, AuditReport], wordmark: WordmarkSVG | None, lockups: dict[str, str]) -> None:
        digest = protocol.merged_digest(svgs, smalls)
        if ws.read_marker("preview").get("digest") == digest and ws.preview_path.is_file():
            return
        renders = {}
        for c in concepts:
            d = ws.render_dir / c.id
            renders[c.id] = {p.stem: str(p) for p in d.glob("*.png")}
        for c in concepts:
            d = ws.render_dir / (c.id + "-small")
            if d.is_dir():
                renders[c.id + "-small"] = {p.stem: str(p) for p in d.glob("*.png")}
        html = build_preview(brief, ws.version, ws.key.key, concepts, svgs, renders, audits,
                             wordmark.svg if wordmark else None, lockups, self._decide_cmd, smalls=smalls)
        ws.preview_path.write_text(html, encoding="utf-8")
        shot = getattr(self._r, "screenshot_html", None)
        if shot is not None:
            try:
                (ws.root / "preview.png").write_bytes(shot(html, 1280, 900))
            except Exception as exc:  # noqa: BLE001 — اللقطة مساعدة، لا تُفشل المرحلة
                (ws.root / "preview-screenshot-error.txt").write_text(str(exc), encoding="utf-8")
        ws.mark_done("preview", {"digest": digest})

    def _stage_name_check(self, ws: Workspace, brief: Brief) -> str | None:
        """بوابة توافر الاسم قبل الحزمة: يكتب قائمة التحقق ويعيد رسالة الانتظار ما لم يسجّل المالك «clear»."""
        nc = read_name_check(ws)
        if nc is not None and nc.name == brief.wordmark_text and not nc.blocks_package:
            ws.mark_done("name_check", {"status": nc.status.value, "checked_at": nc.checked_at, "sources": list(nc.sources)})
            return None
        path = ws.root / "NAME-CHECK.md"
        path.write_text(checklist_md(brief, nc), encoding="utf-8")
        if nc is not None and nc.status is NameStatus.CONFLICT:
            return f"الاسم «{brief.wordmark_text}» مسجّل متعارضًا ({nc.note}); عدّل الاسم في الموجز وأعد التشغيل. التفاصيل: {path}"
        return f"المفهوم معتمد؛ بانتظار تحقق المالك من توافر الاسم «{brief.wordmark_text}»: {path}"

    def _handle_rejections(self, ws: Workspace, ledger: Ledger, concepts: list[Concept]) -> None:
        """يسجّل حالة القرارات في ملف عربي مقروء بجانب المعاينة."""
        decisions = ledger.read()
        lock = ledger.lock()
        lines = ["# حالة القرارات", ""]
        for d in decisions:
            lines.append(f"- {d.at}: {d.verdict.value} {d.concept_id or ''} ({MEDIUM_AR[d.medium]}) {d.reason}")
        cur = lock.current()
        sl = ws.read_marker("shortlist")
        lines += ["", f"الوسيط الحالي: {MEDIUM_AR[cur] if cur else 'لا شيء'} (لا يتغيّر إلا باختيار المالك)",
                  "الرفضات لكل وسيط: " + ", ".join(f"{MEDIUM_AR[m]}={n}" for m, n in lock.rejections.items())]
        if sl:
            lines.append("المعروض بعد التحكيم: " + "، ".join(f"{c} ({sl.get('scores', {}).get(c, '?')}/40)" for c in sl.get("ids", []))
                         + (" — دون عتبة الاحتراف بعد جولات الصقل" if sl.get("below_bar") else ""))
        (ws.root / "DECISIONS.md").write_text("\n".join(lines), encoding="utf-8")

    def _stage_package(self, ws: Workspace, brief: Brief, chosen: Concept, svg: str, audit: AuditReport,
                       wordmark: WordmarkSVG | None, lockup: str | None, min_mark_px: int = 16,
                       min_stroke_px: float | None = None, min_wordmark_px: int | None = None) -> Path:
        """الحزمة تُبنى مرة لمدخلاتها: بصمة كل ما يدخل ملفاتها (`ExportInputs.fingerprint`) لا الألوان وحدها (ت4: خط عناوين
        الاتجاه يغيّر كلمة القفل والألوان كما هي، فكانت تعود حزمة بقفل قديم). علامة قديمة بلا بصمة تُقبل بألوانها كما كانت، وإصدار
        اعتُمد دليله مغلق: حزمته وهويته التي فيها لا تُبنيان من جديد."""
        pal = [brief.palette.paper, brief.palette.ink, brief.palette.brand, brief.palette.accent]
        preview_html = ws.preview_path.read_text(encoding="utf-8") if ws.preview_path.is_file() else None
        inputs = ExportInputs(brief, chosen, svg, wordmark, lockup, audit, preview_html, min_mark_px,
                              brief_hash=ws.key.brief_hash, run_key=ws.key.key, min_stroke_px=min_stroke_px,
                              min_wordmark_px=min_wordmark_px)
        stamp = inputs.fingerprint(ws.version)
        if ws.done("package") and ws.package_dir.is_dir():
            marker = ws.read_marker("package")
            if ws.done("identity") or (marker.get("palette", pal) == pal and marker.get("inputs", stamp) == stamp):
                return ws.package_dir
        if ws.package_dir.is_dir():
            shutil.rmtree(ws.package_dir)
        pkg = self._export.export(inputs, ws.package_dir, ws.version)
        ws.mark_done("package", {"concept": chosen.id, "files": list(pkg.files), "palette": pal, "inputs": stamp})
        return pkg.root

    # ----- الطلبات الموجهة للنموذج -----
    def _write_request_diverge(self, ws: Workspace, brief: Brief, medium: Medium, problems: list[str]) -> None:
        lines = [
            f"# طلب التباعد (diverge): {brief.name_ar}", "",
            f"الوسيط الحالي: {MEDIUM_AR[medium]} ({medium.value}). اقرأ `work/research.md` و`{SKILL}/SKILL.md` أولًا،",
            f"ثم `{REFS}/40-professional-bar.md` كاملًا: سيحكم على عملك حَكَم مستقل بمعاييره الثمانية،",
            "وما دون العتبة لا يصل إلى المالك ويعود إليك. المطلوب علامة لا أيقونة: فكرة واحدة بحيلة، مبنية على شبكة معلنة بأقواس حقيقية",
            "وتصحيحات بصرية. ممنوع رصف مستطيلات ودوائر أولية، وممنوع الأشياء الحرفية المرسومة كأيقونات واجهة.",
            f"واقرأ قبل الرسم: `{REFS}/45-drawer-profile.md` (دورك ومعاييرك)، و`{REFS}/43-lessons-v1.md` (أخطاء تكررت فلا تُعَد)،",
            f"و`{REFS}/42-arabic-lettering.md` (الحرف المخصّص). **الأصغر أولًا**: احسم شكل 16 بكسل قبل تفاصيل 256، واختبر كل مفهوم",
            "بالجملة الواحدة (صف ما يُرى لا ما قُصد) وبالقراءة الخاطئة (هل يُقرأ حرفًا لاتينيًا أو رمزًا شائعًا؟) قبل أن تسلّم.", "",
            "## المطلوب",
            ("1. `work/ideas.yaml` مكتوب ومصغّراته مقروءة (قسم «الأفكار بعد القراءة العمياء للمصغّرات» أدناه): لا تُعد كتابته. اختر"
             " الخمس من المجتازة: الأقوى حيلةً مما رأى القارئ فيه ما قصدتَه، من خمس مناطق معنى لا من منطقة واحدة."
             if ws.done(thumbs.KIND) else "1. " + self._ideas_spec() + " اختر الخمس الأقوى حيلةً لا الأسهل رسمًا."
             " والمفاهيم الخمسة من خمس مناطق لا من منطقة واحدة بصياغات مختلفة."),
            f"2. `work/concepts.yaml`: {config.CONCEPTS_REQUIRED} مفاهيم متباعدة تغطي العائلات الخمس "
            f"(family بحروفها: {self._family_values()}): `concepts: [{{id, name, family, medium: {medium.value}, sentence, idea_id, construction,"
            " reference}}]`.",
            *([f"3. `work/concepts/<id>.mark.yaml` لكل مفهوم: **البناء لا الرسم**. اقرأ `{REFS}/41-construction.md`"
                " أولًا. تصف العلامة أشكالًا على شبكة (دوائر وأقواس ومستطيلات بزوايا مدوّرة ومسارات Bézier) وعمليات اتحاد وطرح وتقاطع"
                " وإزاحة وتدوير زوايا وتكرار دوراني، والأداة تولّد `<id>.svg` منها حتميًا. لا تكتب SVG بيدك؛ أي SVG يُكتب فوقه."
                + (" الكلمة على لوحة عريضة (`width` و`height` مع `fit`)، وأصغر سماكة أو فتحة فيها ≥ 1.5 بكسل حين تُعرض بارتفاع"
                   f" {config.AUDIT_BASE_SIZE.get(medium.value, 16)} بكسل، وجزء التمييز في `accent`."
                   if medium.value in config.SMALL_REQUIRED else
                   " لوحة 256، أصغر سماكة ≥ 24 وحدة (= 1.5 بكسل عند 16)، هامش 4 إلى 8%، وجزء التمييز في `accent`.")]
              if self._build is not None and medium.value in config.CONSTRUCT_REQUIRED else
              ["3. `work/concepts/<id>.svg` لكل مفهوم: أسود #000000 على أبيض، viewBox 0 0 256 256، بلا <text> ولا تدرجات ولا فلاتر ولا شفافية،"
               " أصغر سماكة ≥ 24 وحدة (= 1.5 بكسل عند 16)، هامش 4 إلى 8%. عناصر التمييز تُوسم data-tone=\"accent\" وتبقى سوداء الآن."]),
            "4. المفهوم الرمزي يذكر مرجعًا تاريخيًا موثقًا في reference.",
            "5. `construction` لكل مفهوم يعلن الشبكة ووحدة السماكة والنسبة الحاكمة وأنصاف أقطار الأقواس والتصحيحات البصرية.",
            f"6. تباعد القاعدة: لا يشترك أكثر من {config.FONT_BASE_MAX} مفاهيم في خط واحد (شكل `text`)؛ الباقي على خط آخر من fonts/ أو"
            " مبني من الصفر على شبكة. خمسة مفاهيم على خط واحد تنويعات لا مفاهيم، والأداة ترفضها.", "",
            *([f"7. وسيط «{MEDIUM_AR[medium]}»: المفهوم الرئيس يُفحص عند {config.AUDIT_BASE_SIZE.get(medium.value, 16)} بكسل (حجم الترويسة)،"
               " ويرافقه إلزاميًا رمز مصغّر يُفحص عند 16 بكسل ويُستعمل للأيقونة: "
               + ("`work/concepts/<id>.small.mark.yaml` (لوحة 256، أصغر سماكة ≥ 24 وحدة) بصيغة البناء نفسها. "
                  if self._build is not None and medium.value in config.CONSTRUCT_REQUIRED else
                  "`work/concepts/<id>.small.svg` (viewBox 0 0 256 256). ")
               + "المصغّر ليس الكلمة مصغَّرة: هو أقوى جزء فيها (الحرف أو التفصيل الحامل للحيلة) يُعرف وحده في لسان المتصفح. "
               "الكلمة تُشكَّل حروفًا حقيقية بشكل `text` في أداة البناء (خط من fonts/، وأجزاء letters وmarks وdots) ثم تُعدَّل هندسيًا،"
               " أو تُبنى حروفها من الصفر على شبكة.", ""]
              if medium.value in config.SMALL_REQUIRED else []),
            "## الموجز",
            f"- الغرض: {brief.purpose}", f"- الجمهور: {brief.audience}", f"- النموذج الأصلي: {brief.archetype}",
            f"- الكلمات الثلاث: {'، '.join(brief.three_words)}", f"- الإحساس: {brief.taste.feeling}",
            "- ممنوع: " + "؛ ".join(list(brief.taste.avoid) + list(brief.taste.dislikes)), "",
            *style.lines(ws),
            *self._tool_rules(medium),
            *thumbs.lines(ws),
            *(["## قارئ أعمى قبل الحَكَم",
               "قارئ مستقل لا يعرف الاسم ولا الفكرة يقرأ صورك قبل الحَكَم؛ ما يقرؤه حرفًا غير عربي أو رمزًا شائعًا أو أيقونة واجهة",
               "يعود إليك. فإن توقّعتَ أنت قراءة خاطئة لمفهوم فلا تسلّمه: غيّر شكله أو استبدل فكرته من `work/ideas.yaml` قبل التسليم.", ""]
              if self._blind else []),
            *(live_preview.lines() if self._build is not None else []),
            *self._owner_history(ws),
            *novelty.lines(ws),
            "## ما ينقص الآن", *[f"- {p}" for p in problems], "",
            "ثم أعد تشغيل: `uv run sima run <brief>`",
        ]
        ws.write_request("REQUEST-diverge.md", "\n".join(lines))

    @staticmethod
    def _owner_history(ws: Workspace) -> list[str]:
        """أسباب رفض المالك وتعديلاته السابقة في كل الوسائط، بلا تكرار: سياق لكل رسم جديد كي لا يُعاد ما رُفض."""
        seen: dict[str, list[str]] = {}
        for d in Ledger(ws.ledger_path).read():
            if d.verdict in (Verdict.REJECTED, Verdict.REVISE, Verdict.SWITCH) and d.reason.strip():
                seen.setdefault(d.reason.strip(), []).append(MEDIUM_AR[d.medium])
        if not seen:
            return []
        hist = sorted(p.name for p in (ws.work / "history").glob("medium-*")) if (ws.work / "history").is_dir() else []
        return ["## ما قاله المالك سابقًا (لا تكرّر ما رُفض)",
                *[f"- «{r}» ({'، '.join(dict.fromkeys(ms))})" for r, ms in seen.items()],
                *([f"- الرسوم المرفوضة في work/history/ ({'، '.join(hist)}): انظرها لتتجنّب منطقها لا لتعدّلها."] if hist else []), ""]

    def _write_request_judge(self, ws: Workspace, brief: Brief, concepts: list[Concept], audits: dict[str, AuditReport],
                             digest: str, problems: list[str]) -> None:
        crit = "، ".join(config.JUDGE_CRITERIA)
        lines = [f"# طلب التحكيم المستقل: {brief.name_ar}", "",
                 f"أنت الحَكَم، ولم ترسم هذه المفاهيم. اقرأ `{REFS}/40-professional-bar.md` كاملًا،",
                 "ثم افتح صور كل مفهوم فعليًا (256 و16 والمعكوس والمطموس) قبل أي درجة. لا تجامل: الأصل أن المسودة دون العتبة.",
                 f"واقرأ `{REFS}/43-lessons-v1.md` و`{REFS}/42-arabic-lettering.md`. **اختبار الجملة**: اكتب لنفسك ما تراه في صورة 256",
                 "في جملة قبل أن تقرأ جملة الرسّام؛ إن لم يتطابقا فالفكرة لم تصل (idea ≤ 3) واذكر في blockers ما رأيتَه فعلًا.",
                 "لا تعدّل أي SVG؛ كتابتك محصورة في work/judge/. اللوحة تُقصّ آليًا على الحبر بهامش ثابت، فقرب الحبر من حافة",
                 "الصورة أثر القص لا عيب في التصميم: احكم على توازن الكتلة داخل نفسها لا على الهامش الخارجي.", "",
                 f"اكتب `work/judge/{digest}.yaml` بالضبط، بمدخل لكل مفهوم بمعرّفه كما هو:", "", "```yaml", f"digest: {digest}", "verdicts:",
                 f"  {concepts[0].id if concepts else 'c1'}:", "    scores: {" + ", ".join(f"{k}: 0-5" for k in config.JUDGE_CRITERIA) + "}",
                 '    blockers: ["العيب بالضبط: أين وما المقاس"]',
                 '    direction: "تعديل هندسي قابل للتنفيذ"', "    replace: false  # true إن كانت الفكرة نفسها ضعيفة", "```", "",
                 f"المعايير: {crit}. العتبة تحسبها الأداة: المجموع ≥ {config.JUDGE_MIN_TOTAL} من 40، ولا معيار دون {config.JUDGE_MIN_EACH}، "
                 "و" + "، ".join(f"{k} ≥ {m}" for k, m in config.JUDGE_KEY_MIN.items()) + ".", "",
                 "## الموجز",
                 f"- الاسم: {brief.name_ar}؛ الكلمات الثلاث: {'، '.join(brief.three_words)}", f"- الإحساس: {brief.taste.feeling}", "",
                 *style.lines(ws), *(self._tool_rules(concepts[0].medium) if concepts else []), *thumbs.judge_lines(ws),
                 *self._owner_history(ws)]
        seen = blind.read(ws, digest, [c.id for c in concepts]) if self._blind else None
        if problems:
            lines += ["## مشاكل في ملف التحكيم السابق لهذا المحتوى", *[f"- {p}" for p in problems], ""]
        for c in concepts:
            d = ws.render_dir / c.id
            a = audits.get(c.id)
            lines += [f"## {c.id} «{c.name}» ({FAMILY_AR[c.family]}، {MEDIUM_AR[c.medium]})", f"الفكرة: {c.sentence}",
                      f"البناء المعلن: {c.construction}",
                      f"SVG: {protocol.concept_svg_path(ws, c.id)}",
                      *([f"البناء: {protocol.mark_spec_path(ws, c.id)}"] if protocol.mark_spec_path(ws, c.id).is_file() else []),
                      "الصور: " + ", ".join(str(d / f"{n}.png") for n in ("256", "16", "48", "reversed", "blurred"))]
            if (ws.render_dir / (c.id + "-small")).is_dir():
                lines.append(f"المصغّر: {ws.render_dir / (c.id + '-small') / '16.png'}")
            sim = (a.metrics.get("similarity") if a else None) or []
            if sim:
                lines.append("أقرب علامات مكتبة المراجع: " + "، ".join(f"{s['brand']} ({s['distance']} من 64)" for s in sim))
            if seen is not None and c.id in seen.readings:
                lines.append(f"- قارئ أعمى مستقل (بلا اسم ولا فكرة) {seen.readings[c.id].line()}")
            lines += [f"- تنبيه آلي: {w}" for w in (a.warnings if a else [])] + [""]
        ws.write_request("REQUEST-judge.md", "\n".join(lines))

    def _write_request_refine(self, ws: Workspace, brief: Brief, concepts: list[Concept], name: str, title: str,
                              items: list[tuple[str, list[str], str, bool]]) -> None:
        """طلب للرسّام: تعديل مفاهيم محددة بأسبابها، أو استبدال فكرتها (replace) بفكرة أقوى من ideas.yaml في الوسيط نفسه."""
        by_id = {c.id: c for c in concepts}
        lines = [f"# طلب {title}: {brief.name_ar}", "",
                 f"اقرأ `{REFS}/40-professional-bar.md` و`{REFS}/45-drawer-profile.md`"
                 f" و`{REFS}/43-lessons-v1.md` و`{REFS}/42-arabic-lettering.md`. عدّل بناء المفاهيم أدناه",
                 f"(`work/concepts/<id>.mark.yaml` بصيغة `{REFS}/41-construction.md`، والأداة تولّد SVG منه؛ وإن لم يوجد بناء فـ `<id>.svg`)",
                 "للمفاهيم أدناه فقط، وحدّث مدخلها في `work/concepts.yaml` (sentence وconstruction وidea_id) إن تغيّرت الفكرة. أبقِ المعرّف",
                 "والعائلة والوسيط. «استبدال» يعني فكرة جديدة أقوى حيلةً من `work/ideas.yaml` أو غيرها، لا تحسين الرسم القديم.",
                 "سيحكم حَكَم مستقل على النتيجة من جديد"
                 + ("، ومفهوم استُبدلت فكرته يقرؤه القارئ الأعمى قبله." if self._blind else "."), "", *style.lines(ws),
                 *(self._tool_rules(concepts[0].medium) if concepts else []), *thumbs.lines(ws),
                 *(live_preview.lines() if self._build is not None else []), *novelty.lines(ws),
                 f"قيد التباعد قائم أثناء الصقل: لا يشترك أكثر من {config.FONT_BASE_MAX} مفاهيم من الخمسة في خط واحد (شكل `text`)؛ الأداة",
                 "تردّ المجموعة إلى الرسم الكامل إن عاد الخمسة إلى خط واحد. راجع خطوط المفاهيم التي لا تعدّلها قبل أن تسلّم.", ""]
        for cid, reasons, direction, replace_ in items:
            c = by_id.get(cid)
            if c is None:
                continue
            lines += [f"## {cid} «{c.name}» — {'استبدال الفكرة' if replace_ else 'تعديل'}", f"الفكرة الحالية: {c.sentence}",
                      f"الصورة: {ws.render_dir / cid / '256.png'}", *[f"- {r}" for r in reasons]]
            if direction:
                lines.append(f"- الاتجاه: {direction}")
            lines.append("")
        ws.write_request(name, "\n".join(lines))

    def _write_request_critique(self, ws: Workspace, brief: Brief, concepts: list[Concept], audits: dict[str, AuditReport],
                                round_n: int, digest: str | None = None, *, forced: int = 0, problems: list[str] | None = None) -> None:
        """forced رقم الجولة الإضافية بعد انتهاء النقد (صفر لجولات النقد نفسها)؛ problems ما لا يُقرأ من ملف الجولة السابق."""
        protocol.write_critique_request(ws, round_n, digest or protocol.svgs_digest(protocol.read_concept_svgs(ws, concepts)))
        head = (f"جولة إضافية {forced} من {config.FORCED_CRITIQUE_ROUNDS} لإصلاح ما ردّه الفحص (ملف الجولة {round_n})" if forced
                else f"الجولة {round_n} من {config.MAX_CRITIQUE_ROUNDS}")
        first = concepts[0].id if concepts else "c1"  # أول معرّف فعلي: قالب بمعرّف ثابت يُكتب به والمعرّفات غيره
        lines = [f"# طلب النقد: {head}", "",
                 f"انظر PNG كل مفهوم فعليًا (16 و32 و48 و256 والمعالجات) ثم انقد بمرجع `{REFS}/08-critique-principles.md`.",
                 f"اكتب `work/critique/round{round_n}.yaml`، بمدخل لكل مفهوم بمعرّفه كما هو:", "",
                 "```yaml", f"round: {round_n}",
                 "verdicts:", f'  {first}: {{action: keep|revise|drop, score: 0-50, notes: "...", changes: ["..."]}}', "```", "",
                 "إن كان action=revise عدّل البناء `work/concepts/<id>.mark.yaml` (أو `<id>.svg` إن لم يوجد بناء) في نفس الجولة؛ "
                 "revise بلا تعديل فعلي في البناء يُعاد إليك. وaction=drop رأيك أن المفهوم لا يستحق العرض: لا تعدّله ولا تستبدله، "
                 "والحَكَم يحكم عليه مع البقية.", "",
                 *(live_preview.lines() if self._build is not None else [])]
        if forced:
            lines += ["تنبيه: الجولات انتهت ولا تزال مفاهيم فاشلة؛ هذه الجولة إضافية لإصلاح الفشل الآلي فقط. بعد"
                      f" {config.FORCED_CRITIQUE_ROUNDS} جولات إضافية يُعرض الفشل على المالك ولا يُعاد الطلب.", ""]
        if problems:
            lines += ["## مشاكل في ملف هذه الجولة كما كتبتَه (صحّح صيغته وحدها، ولا تغيّر أحكامه)", *[f"- {p}" for p in problems], ""]
        for c in concepts:
            for cid, label in ((c.id, ""), (c.id + "-small", " (الرمز المصغّر)")):
                a = audits.get(cid)
                if a is None:
                    continue
                d = ws.render_dir / cid
                lines += [f"## {cid} «{c.name}»{label} ({FAMILY_AR[c.family]}) — {'نجح' if a.passed else 'فشل'}",
                          f"الفكرة: {c.sentence}",
                          "الصور: " + ", ".join(str(d / f"{n}.png") for n in ("16", "32", "48", "256", "mono", "reversed", "mirrored", "blurred")),
                          "المقاييس: " + json.dumps({k: v for k, v in a.metrics.items() if k != "similarity"}, ensure_ascii=False)]
                sim = a.metrics.get("similarity") or []
                if sim:
                    lines.append("أقرب مراجع: " + "، ".join(f"{s['brand']} ({s['distance']})" for s in sim))
                lines += [f"- فشل: {f}" for f in a.findings] + [f"- تنبيه: {w}" for w in a.warnings] + [""]
        ws.write_request(f"REQUEST-critique-r{round_n}.md", "\n".join(lines))


def record_decision(ws: Workspace, concept_id: str | None, verdict: Verdict, reason: str) -> None:
    ledger = Ledger(ws.ledger_path)
    concepts = protocol.read_concepts(ws)
    if concept_id is not None and all(c.id != concept_id for c in concepts):  # كان يُسجَّل اعتماد مفهوم لا وجود له (خ9)
        raise ValueError(f"المفهوم {concept_id} ليس من مفاهيم هذا الإصدار.")
    medium = next((c.medium for c in concepts if c.id == concept_id), None) or ledger.lock().current() or Medium.ABSTRACT_MARK
    ledger.record(concept_id, verdict, medium, reason, protocol.critique_rounds_done(ws))


def record_switch(ws: Workspace, medium: Medium, reason: str) -> None:
    """المالك يختار الوسيط (ولو الحالي نفسه = ارسم من جديد بالمعيار): رسم جديد في التشغيل التالي."""
    Ledger(ws.ledger_path).record(None, Verdict.SWITCH, medium, reason, protocol.critique_rounds_done(ws))
