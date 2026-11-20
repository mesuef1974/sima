"""خدمة الهوية الكاملة: البوابات الثلاث (المنصة، الاتجاه، الدليل)، وطلبات النموذج، ولوحة الاتجاهات، وبناء package/identity.

حتمية ومتساوية الأثر: كل بناء مربوط بـhash مدخلاته، وكل قرار بـhash ما عُرض. لا شبكة.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..domain import Brief
from ..domain.identity import CheckReport, Direction, Gate, Strategy
from . import svgtools
from .applications import APPS, BOARD_APPS, AppKit, email_signature
from .brand_book import brand_book, directions_board
from .color_system import ROLES, build_system, check_system, with_night
from .colorize import colorize
from .compose import Font, Typesetter
from .design_tokens import css, dtcg, scss, tailwind
from .identity_protocol import (
    GATE_REQUEST,
    SAMPLES,
    digest,
    directions_count,
    directions_digest,
    directions_path,
    icons_path,
    idir,
    keep_adopted_direction,
    ledger,
    read_directions,
    read_icons,
    read_strategy,
    revise_reply,
    strategy_path,
)
from .ports import FontShaper, Renderer
from .product_screens import SIZES, ScreenKit, screens
from .reveal import Chapter, Deck, deck
from .type_system import check_type, family_name, license_file
from .workspace import Workspace

MODEL, OWNER = "model", "owner"


@dataclass(frozen=True)
class Wait:
    who: str  # model | owner
    message: str
    failures: tuple[str, ...] = ()  # ما ردّه فحص اتجاه معتمد خارج الخط كما قيس: مسار المصمّم الخارجي يعيده إليه لا إلى المالك
    gate: str = ""  # البوابة التي ينتظر عندها المالك (strategy | directions | book)؛ فارغة حين لا قرار يُعرض في بطاقة
    digest: str = ""  # بصمة ما عُرض في البوابة
    request: str = ""  # اسم ملف الطلب الذي ينتظره الخط من النموذج


@dataclass(frozen=True)
class MarkSet:
    """صيغ العلامة بلوحة الاتجاه: الرمز والقفل بالألوان وأبيض وأسود."""
    mark: str
    mark_white: str
    mark_mono: str
    lockup: str
    lockup_white: str
    lockup_mono: str


def mark_set(mark_bw: str, lockup_bw: str, colors: dict[str, str]) -> MarkSet:
    from .export import _wordmark_ink  # الدالة نفسها التي يلوّن بها التصدير القفل

    base = svgtools.strip_background(mark_bw)
    lock = svgtools.strip_background(lockup_bw)
    return MarkSet(
        mark=colorize(base, colors["brand"], colors["accent"]), mark_white=svgtools.mono(base, "#FFFFFF"), mark_mono=svgtools.mono(base),
        lockup=_wordmark_ink(colorize(lock, colors["brand"], colors["accent"]), colors["brand"], colors["ink"]),
        lockup_white=svgtools.mono(lock, "#FFFFFF"), lockup_mono=svgtools.mono(lock),
    )


class IdentityFlow:
    def __init__(self, renderer: Renderer, shaper: FontShaper, fonts_dir: Path):
        self._r = renderer
        self._t = Typesetter(shaper)
        self._fonts = fonts_dir

    # ---------- البوابة 1: المنصة الاستراتيجية ----------
    def strategy(self, ws: Workspace, brief: Brief, auto: str | None = None) -> Strategy | Wait:
        """`auto`: نص قاعدة يمرّ بها ما لم يُقرَّر بعد دون عرضه بوابةً (مسار المصمّم الخارجي: الدليل قرار المالك الوحيد)؛
        تُسجَّل القاعدة سببًا فلا تُقرأ قرارًا من المالك."""
        s, problems = read_strategy(ws)
        led = ledger(ws)
        if s is None:
            self._request(ws, "strategy", brief, problems if strategy_path(ws).is_file() else [], led.history(Gate.STRATEGY))
            return Wait(MODEL, f"بانتظار النموذج: المنصة الاستراتيجية. الطلب في {ws.work / 'REQUEST-strategy.md'}",
                        request=GATE_REQUEST[Gate.STRATEGY])
        dg = digest([strategy_path(ws)])
        (ws.root / "STRATEGY.md").write_text(strategy_md(brief, s), encoding="utf-8")
        dec = led.latest(Gate.STRATEGY, dg)
        if dec is None and auto:
            dec = led.record(Gate.STRATEGY, dg, "approved", "", auto)
        if dec is None:
            return Wait(OWNER, f"المنصة الاستراتيجية جاهزة لقرارك: {ws.root / 'STRATEGY.md'}", gate=Gate.STRATEGY.value, digest=dg)
        if dec.verdict != "approved":
            if revise_reply(ws, dec, Gate.STRATEGY) is not None:  # أجاب النموذج ولم تتغيّر المنصة: القرار للمالك مع الجواب (ب12)
                return Wait(OWNER, "لم يغيّر طلب التعديل شيئًا في المنصة الاستراتيجية؛ جواب الخط على ملاحظتك في بطاقتها.",
                            gate=Gate.STRATEGY.value, digest=dg)
            self._request(ws, "strategy", brief, [f"قرار المالك ({dec.verdict}): {dec.reason}"], led.history(Gate.STRATEGY))
            return Wait(MODEL, "بانتظار النموذج: تعديل المنصة الاستراتيجية بملاحظة المالك.", request=GATE_REQUEST[Gate.STRATEGY])
        ws.mark_done("strategy", {"digest": dg})
        return s

    # ---------- البوابة 3: الاتجاهات ----------
    def evaluate(self, brief: Brief, d: Direction) -> tuple[dict, CheckReport, dict]:
        system = build_system(d.colors)
        night = brief.identity.night
        if night:
            system = with_night(system, night["colors"])
        bp = {"paper": brief.palette.paper, "ink": brief.palette.ink, "brand": brief.palette.brand, "accent": brief.palette.accent}
        rep = check_system(d.colors, system, accent_informational=d.accent_informational, policy=brief.identity.palette_policy,
                           brief_palette=bp)
        if night:
            rep.add("ليل الهوية من اتجاه معتمد آخر", True, f"{night['name']}: أدوار الوضع الداكن من ألوانه لا من ألوان هذا الاتجاه", blocking=False)
        check_type(self._fonts, "العناوين", d.heading, d.numerals, rep)
        check_type(self._fonts, "النص", d.body, d.numerals, rep)
        fonts = {}
        for role, tc in (("heading", d.heading), ("body", d.body)):
            p = self._fonts / tc.font
            fonts[role] = {"family": family_name(p) if p.is_file() else tc.font, "file": tc.font, "weight": tc.weight}
        return system, rep, fonts

    def draft_strategy(self, ws: Workspace) -> Strategy | None:
        """المنصة كما كتبها النموذج قبل قرار المالك؛ تكفي لبناء لوحة اطلاع لا للاعتماد."""
        s, _ = read_strategy(ws)
        return s

    def preview(self, ws: Workspace, brief: Brief, strategy: Strategy, mark_bw: str, lockup_bw: str, concept: str = "") -> None:
        """لوحة الاتجاهات للاطلاع بينما تنتظر المنصة الاستراتيجية قرار المالك: تُبنى إن كانت الاتجاهات مكتوبة وتجتاز الفحوص،
        ولا تفتح بوابة ولا تكتب طلبًا للنموذج. القرار عليها يبقى بعد اعتماد المنصة."""
        dirs, _ = read_directions(ws)
        if not dirs:
            return
        evals = {d.id: self.evaluate(brief, d) for d in dirs}
        if any(evals[d.id][1].failures for d in dirs):
            return
        dg = directions_digest(ws)
        if self._board_stale(ws, dg, mark_bw, lockup_bw):
            self._board(ws, brief, strategy, dirs, evals, mark_bw, lockup_bw, concept)
            ws.mark_done("directions_board", {"digest": dg, "mark": _mark_key(mark_bw, lockup_bw)})

    def directions(self, ws: Workspace, brief: Brief, strategy: Strategy, mark_bw: str, lockup_bw: str, concept: str = "",
                   auto: str | None = None, *, kept: tuple[dict, str] | None = None,
                   lockup_for: Callable[[Direction], str] | None = None) -> tuple[Direction, dict, CheckReport, dict] | Wait:
        """`kept` (بند الاتجاه، نمطه): اتجاه التسليم المعتمد حين يطلب الموجز ثلاثة اتجاهات فوق علامة من خارج الخط
        (`identity.directions: three`)؛ يبقى كما هو أولَ الثلاثة، والنموذج يكتب الآخرَين، والقرار للمالك لا لقاعدة المسار.
        `lockup_for`: قفل كل اتجاه حين تُشكَّل كلمته من خط عناوينه، فتُرى الكلمة في اللوحة بخط ذلك الاتجاه."""
        adopted = ws.done("adopted")
        three = adopted and directions_count(ws) > 1
        if three and kept is not None:
            keep_adopted_direction(ws, *kept)
        dirs, problems = read_directions(ws)
        led = ledger(ws)
        if adopted and not three:
            return self._adopted_direction(ws, brief, strategy, dirs, problems, mark_bw, lockup_bw, concept, auto)
        keep = str(kept[0]["id"]) if three and kept is not None else None

        def ask(why: list[str]) -> None:
            self._request(ws, "directions", brief, why, led.history(Gate.DIRECTIONS), keep=keep)

        if not dirs:
            ask(problems if directions_path(ws).is_file() else [])
            return Wait(MODEL, f"بانتظار النموذج: ثلاثة اتجاهات للهوية. الطلب في {ws.work / 'REQUEST-directions.md'}",
                        request=GATE_REQUEST[Gate.DIRECTIONS])
        evals = {d.id: self.evaluate(brief, d) for d in dirs}
        if keep and evals[keep][1].failures:  # اتجاه التسليم نفسه مردود: يعود إلى صاحبه كما قيس، لا إلى نموذج الخط
            bad = evals[keep][1].failures
            return Wait(OWNER, "الاتجاه المعتمد لا يجتاز الفحوص (يُصلح في بيان الاعتماد ثم يُعاد التشغيل): " + "؛ ".join(bad), tuple(bad))
        failing = [f"{d.id} {f}" for d in dirs for f in evals[d.id][1].failures]
        if failing:
            ask(failing)
            return Wait(MODEL, "بانتظار النموذج: اتجاهات لا تجتاز الفحوص: " + "؛ ".join(failing[:4]), request=GATE_REQUEST[Gate.DIRECTIONS])
        dg = directions_digest(ws)
        if self._board_stale(ws, dg, mark_bw, lockup_bw):
            self._board(ws, brief, strategy, dirs, evals, mark_bw, lockup_bw, concept, lockup_for)
            ws.mark_done("directions_board", {"digest": dg, "mark": _mark_key(mark_bw, lockup_bw)})
        dec = led.latest(Gate.DIRECTIONS, dg)
        if dec is None:
            return Wait(OWNER, f"ثلاثة اتجاهات جاهزة لقرارك: {ws.root / 'directions.html'}", gate=Gate.DIRECTIONS.value, digest=dg)
        chosen = next((d for d in dirs if d.id == dec.option), None)
        if dec.verdict != "approved" or chosen is None:
            if dec.verdict != "approved" and revise_reply(ws, dec, Gate.DIRECTIONS) is not None:  # أجاب النموذج ولم تتغيّر الاتجاهات (ب12)
                return Wait(OWNER, "لم يغيّر طلب التعديل شيئًا في الاتجاهات؛ جواب الخط على ملاحظتك في بطاقتها.",
                            gate=Gate.DIRECTIONS.value, digest=dg)
            ask([f"قرار المالك ({dec.verdict}): {dec.reason}"])
            return Wait(MODEL, "بانتظار النموذج: تعديل الاتجاهات بملاحظة المالك.", request=GATE_REQUEST[Gate.DIRECTIONS])
        ws.mark_done("directions", {"digest": dg, "option": chosen.id})
        system, rep, fonts = evals[chosen.id]
        return chosen, system, rep, fonts

    def _adopted_direction(self, ws: Workspace, brief: Brief, strategy: Strategy, dirs: list[Direction], problems: list[str],
                           mark_bw: str, lockup_bw: str, concept: str, auto: str | None = None
                           ) -> tuple[Direction, dict, CheckReport, dict] | Wait:
        """اتجاه واحد اعتمده المالك خارج الخط: يُفحص ويُعرض عليه مكتملًا، ولا يُطلب من النموذج شيء. ما لا يجتاز يُصلح في
        بيان الاعتماد، فتتغيّر البصمة وتُفتح البوابة من جديد."""
        fix = "يُصلح في بيان الاعتماد ثم يُعاد التشغيل"
        if not dirs:
            return Wait(OWNER, f"الاتجاه المعتمد لا يُقرأ ({fix}): " + "؛ ".join(problems), tuple(problems))
        d = dirs[0]
        evals = {d.id: self.evaluate(brief, d)}
        failing = evals[d.id][1].failures
        if failing:
            return Wait(OWNER, f"الاتجاه المعتمد لا يجتاز الفحوص ({fix}): " + "؛ ".join(failing), tuple(failing))
        dg = directions_digest(ws)
        if self._board_stale(ws, dg, mark_bw, lockup_bw):
            self._board(ws, brief, strategy, dirs, evals, mark_bw, lockup_bw, concept)
            ws.mark_done("directions_board", {"digest": dg, "mark": _mark_key(mark_bw, lockup_bw)})
        dec = ledger(ws).latest(Gate.DIRECTIONS, dg)
        if dec is None and auto:
            dec = ledger(ws).record(Gate.DIRECTIONS, dg, "approved", d.id, auto)
        if dec is None:
            return Wait(OWNER, f"الاتجاه المعتمد مكتملًا (ألوانه كلها ووضعه الداكن ونمطه) جاهز لقرارك: {ws.root / 'directions.html'}",
                        gate=Gate.DIRECTIONS.value, digest=dg)
        if dec.verdict != "approved" or dec.option != d.id:
            return Wait(OWNER, f"قرار المالك على الاتجاه ({dec.verdict}): {dec.reason} — {fix}.")
        ws.mark_done("directions", {"digest": dg, "option": d.id})
        return (d, *evals[d.id])

    @staticmethod
    def _board_stale(ws: Workspace, dg: str, mark_bw: str, lockup_bw: str) -> bool:
        """اللوحة تُبنى من جديد إن تغيّر الاتجاه أو العلامة المعروضة فيها («مسك» v9: بُدّلت الأيقونة في البيان وبقيت اللوحة على
        القديمة). العلامة خارج بصمة البوابة: تسليم جديد لا يُسقط اختيار المالك للاتجاه (ب8). لوحة بلا مفتاح علامة (قبل هذا الحقل) تُبنى مرة."""
        m = ws.read_marker("directions_board")
        return (m.get("digest") != dg or m.get("mark") != _mark_key(mark_bw, lockup_bw)
                or not (ws.root / "directions.html").is_file())

    def _board(self, ws: Workspace, brief: Brief, strategy: Strategy, dirs: list[Direction], evals: dict, mark_bw: str, lockup_bw: str,
               concept: str = "", lockup_for: Callable[[Direction], str] | None = None) -> None:
        bdir = ws.root / "identity-board"
        bdir.mkdir(parents=True, exist_ok=True)
        self._copy_fonts(ws.root / "assets" / "fonts", [f for d in dirs for f in (d.heading.font, d.body.font)])
        boards, chapters = [], []
        icons, problems = read_icons(ws, brief)
        icons = icons if not problems else []
        for d in dirs:
            system, rep, fonts = evals[d.id]
            ms = mark_set(mark_bw, lockup_for(d) if lockup_for else lockup_bw, d.colors)
            kit = self._kit(brief, strategy, d, system, ms, ws)
            apps = []
            for fn in BOARD_APPS:
                app = fn(kit, self._t)
                (bdir / f"{d.id}-{app.id}.svg").write_text(app.svg, encoding="utf-8")
                apps.append((app.title, f"identity-board/{d.id}-{app.id}.svg"))
            (bdir / f"{d.id}-motif.svg").write_text(kit.motif_soft, encoding="utf-8")
            boards.append({"direction": d, "system": system, "fonts": fonts, "checks": rep, "apps": apps,
                           "motif_band": f"identity-board/{d.id}-motif.svg"})
            shots = self._screens(brief, strategy, d, system, fonts, ms, kit, icons, bdir / "screens" / d.id, "../../../assets/fonts/",
                                  f"identity-board/screens/{d.id}/")
            chapters.append(self._chapter(d, system, fonts, rep, ms, kit, shots, apps, icons))
        self._deck(ws.root / "reveal.html", "directions", brief, strategy, concept, chapters, ws, "assets/fonts/",
                   "اختر اتجاهًا واحدًا من الثلاثة" if len(dirs) > 1 else "اعتمد الاتجاه مكتملًا أو اطلب تعديلًا بسبب")
        html = directions_board(brief.name_ar, ws.version, ws.key.key, strategy, boards, "assets/fonts/")
        (ws.root / "directions.html").write_text(html, encoding="utf-8")
        shot = getattr(self._r, "html_png", None)
        if shot is not None:
            (ws.root / "directions.png").write_bytes(shot(ws.root / "directions.html"))

    # ---------- البناء والبوابة 4: الدليل ----------
    def build(self, ws: Workspace, brief: Brief, strategy: Strategy, d: Direction, system: dict, rep: CheckReport, fonts: dict,
              pkg_root: Path, mark_bw: str, lockup_bw: str, concept_sentence: str) -> Wait | None:
        icons: list[dict] = []
        led = ledger(ws)
        if brief.identity.full:
            icons, problems = read_icons(ws, brief)
            if problems:
                self._request(ws, "icons", brief, problems if icons_path(ws).is_file() else [], [], direction=d)
                return Wait(MODEL, f"بانتظار النموذج: مجموعة الأيقونات. الطلب في {ws.work / 'REQUEST-icons.md'}", request="REQUEST-icons.md")
        inputs = digest([strategy_path(ws), directions_path(ws), *sorted((idir(ws) / "motifs").glob("*.svg")),
                         *sorted((idir(ws) / "icons").glob("*.svg")), pkg_root / f"{brief.project}-mark.svg"]) + d.id
        if ws.done("adopted"):  # الكلمة المعتمدة تدخل البصمة مع الرمز (الإصدارات المرسومة تبقى ببصمتها)
            inputs += digest([pkg_root / f"{brief.project}-lockup.svg"])
        out = pkg_root / "identity"
        if ws.read_marker("identity_build").get("inputs") != inputs or not (out / "brand-book.html").is_file():
            self._build(ws, brief, strategy, d, system, rep, fonts, out, icons, mark_bw, lockup_bw, concept_sentence, inputs)
            ws.mark_done("identity_build", {"inputs": inputs})
        bg = digest([out / "brand-book.html"])
        dec = led.latest(Gate.BOOK, bg)
        if dec is None:
            return Wait(OWNER, f"دليل الهوية جاهز لمراجعتك: {out / 'brand-book.html'}", gate=Gate.BOOK.value, digest=bg)
        if dec.verdict != "approved":
            if revise_reply(ws, dec) is not None:  # أجاب النموذج ولم يتغيّر الدليل: لا يُعاد الطلب، والقرار للمالك مع الجواب
                return Wait(OWNER, f"لم يغيّر طلب التعديل شيئًا في الدليل؛ جواب الخط على ملاحظتك في بطاقته: {out / 'brand-book.html'}",
                            gate=Gate.BOOK.value, digest=bg)
            self._request(ws, "revise", brief, [f"ملاحظة المالك على الدليل: {dec.reason}"], led.history(Gate.BOOK), direction=d)
            return Wait(MODEL, "بانتظار النموذج: تعديل الهوية بملاحظة المالك على الدليل.", request=GATE_REQUEST[Gate.BOOK])
        ws.mark_done("identity", {"book": bg, "direction": d.id})
        return None

    def _build(self, ws: Workspace, brief: Brief, strategy: Strategy, d: Direction, system: dict, rep: CheckReport, fonts: dict,
               out: Path, icons: list[dict], mark_bw: str, lockup_bw: str, concept_sentence: str, inputs: str = "") -> None:
        slug = brief.project
        if out.exists():
            shutil.rmtree(out)
        for sub in ("tokens", "fonts", "patterns", "applications", "icons", "motion"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        def put(rel: str, content: str | bytes) -> None:
            p = out / rel
            p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content, encoding="utf-8")
            files.append(rel)

        ms = mark_set(mark_bw, lockup_bw, d.colors)
        kit = self._kit(brief, strategy, d, system, ms, ws)
        put("STRATEGY.md", strategy_md(brief, strategy))
        put("tokens/tokens.css", css(slug, system, fonts, d.radius, d.numerals))
        put("tokens/_tokens.scss", scss(slug, system))
        put("tokens/tokens.json", dtcg(slug, system, fonts, d.radius))
        put("tokens/tailwind.preset.js", tailwind(slug, system, fonts))
        for rel in self._copy_fonts(out / "fonts", [d.heading.font, d.body.font]):
            files.append(f"fonts/{rel}")
        put("patterns/motif-soft.svg", kit.motif_soft)
        put("patterns/motif-strong.svg", kit.motif_strong)
        put("patterns/motif-mono.svg", self._motif(ws, d, "#000000", "#000000"))
        for i in icons:
            put(f"icons/{i['id']}.svg", i["svg"])
        apps_list: list[tuple[str, str]] = []
        if brief.identity.full:
            wide = getattr(self._r, "render_png_wide", None)
            for fn in APPS:
                app = fn(kit, self._t)
                put(f"applications/{app.id}.svg", app.svg)
                if wide is not None:
                    put(f"applications/{app.id}.png", wide(app.svg, app.width, app.height, None))
                apps_list.append((app.title, f"applications/{app.id}.svg"))
            put("applications/email-mark.png", self._r.render_png(ms.mark, 128, None))
            put("applications/email-signature.html", email_signature(kit, fonts["heading"]["family"], fonts["body"]["family"], "email-mark.png"))
            put("motion/mark-intro.html", motion_html(ms.mark, brief.name_ar))
        mark_files = [(f"{slug}-lockup.svg", "القفل بالألوان", False), (f"{slug}-mark.svg", "الرمز بالألوان", False),
                      (f"{slug}-mark-mono.svg", "أحادي للطباعة", False), (f"{slug}-mark-reversed.svg", "معكوس على داكن", False)]
        mark_files = [m for m in mark_files if (out.parent / m[0]).is_file()]
        tokens_css = (out / "tokens/tokens.css").read_text(encoding="utf-8")
        ctx = {"name_ar": brief.name_ar, "slug": slug, "version": ws.version, "key": ws.key.key, "strategy": strategy, "direction": d,
               "system": system, "fonts": fonts, "checks": rep, "mark_files": mark_files, "apps": apps_list, "icons": icons,
               "tokens_css": tokens_css, "motion": brief.identity.full, "concept": concept_sentence,
               "lockup_file": f"{slug}-lockup.svg" if (out.parent / f"{slug}-lockup.svg").is_file() else f"{slug}-mark.svg",
               "files": sorted([*files, "brand-book.html", *(["brand-book.pdf"] if brief.identity.full else [])])}
        # الدليل يعرض الرمز والقفل صورًا خارجية، فنص الصفحة لا يتغيّر بتغيّرهما؛ ختمه ببصمة مدخلاته يربط قرار المالك بما عُرض فعلًا
        put("brand-book.html", brand_book(ctx).replace("<head>", f'<head>\n<meta name="sima-build" content="{inputs}">', 1))
        if brief.identity.full:
            shots = self._screens(brief, strategy, d, system, fonts, ms, kit, icons, out / "screens", "../fonts/", "screens/")
            files += [f"screens/{n}.{e}" for n in shots for e in ("html", "png")]
            best = ("social-post", "slide-title", "card-front", "social-cover")
            featured = sorted([a for a in apps_list if any(a[1].endswith(f"/{x}.svg") for x in best)],
                              key=lambda a: next(i for i, x in enumerate(best) if a[1].endswith(f"/{x}.svg")))
            ch = self._chapter(d, system, fonts, rep, ms, kit, shots, featured, icons)
            self._deck(out / "reveal.html", "final", brief, strategy, concept_sentence, [ch], ws, "fonts/",
                       "اعتمد الهوية أو اطلب تعديلًا بسبب")
            files.append("reveal.html")
            pdf_ = getattr(self._r, "html_pdf", None)
            if pdf_ is not None:
                put("reveal.pdf", pdf_(out / "reveal.html", landscape=True))
        pdf = getattr(self._r, "html_pdf", None)
        if brief.identity.full and pdf is not None:
            put("brand-book.pdf", pdf(out / "brand-book.html"))
        put("checks.json", json.dumps({"direction": d.id, "ok": rep.ok, "checks": [c.__dict__ for c in rep.checks]},
                                      ensure_ascii=False, indent=2))

    # ---------- عرض الكشف وشاشات المنتج ----------
    def _screens(self, brief: Brief, strategy: Strategy, d: Direction, system: dict, fonts: dict, ms: MarkSet, kit: AppKit,
                 icons: list[dict], dest: Path, fonts_base: str, rel: str) -> dict[str, str]:
        """يكتب شاشات المنتج HTML ويصوّرها PNG؛ يعيد اسم الشاشة → مسار PNG نسبي لمكان العرض."""
        dest.mkdir(parents=True, exist_ok=True)
        by_subject = {i["subject"]: i["svg"] for i in icons}
        sk = ScreenKit(name_ar=brief.name_ar, tagline=strategy.tagline, samples=dict(strategy.samples),
                       traits=tuple((t.trait, t.means) for t in strategy.personality), light=system["light"], dark=system["dark"], fonts=fonts,
                       mark=ms.mark, mark_white=ms.mark_white, lockup=ms.lockup, lockup_white=ms.lockup_white, lockup_mono=ms.lockup_mono,
                       motif_soft=kit.motif_soft, radius=d.radius, nav=tuple(brief.identity.icons), icons=by_subject)
        shot = getattr(self._r, "html_png", None)
        out = {}
        for name, html in screens(sk, fonts_base).items():
            (dest / f"{name}.html").write_text(html, encoding="utf-8")
            if shot is not None:
                w, h = SIZES[name]
                (dest / f"{name}.png").write_bytes(shot(dest / f"{name}.html", w, h))
                out[name] = f"{rel}{name}.png"
        return out

    @staticmethod
    def _chapter(d: Direction, system: dict, fonts: dict, rep: CheckReport, ms: MarkSet, kit: AppKit, shots: dict[str, str],
                 apps: list[tuple[str, str]], icons: list[dict]) -> Chapter:
        return Chapter(direction=d, system=system, fonts=fonts, checks=rep, mark=ms.mark, mark_white=ms.mark_white, mark_mono=ms.mark_mono,
                       lockup=ms.lockup, lockup_white=ms.lockup_white, motif_soft=kit.motif_soft, motif_strong=kit.motif_strong,
                       screens=shots, apps=apps, icons=icons)

    @staticmethod
    def _deck(path: Path, mode: str, brief: Brief, strategy: Strategy, concept: str, chapters: list[Chapter], ws: Workspace,
              fonts_base: str, ask: str) -> None:
        d = Deck(mode=mode, name_ar=brief.name_ar, version=ws.version, key=ws.key.key, purpose=brief.purpose, audience=brief.audience,
                 three_words=tuple(brief.three_words), strategy=strategy, concept=concept or chapters[0].direction.idea, chapters=chapters,
                 fonts_base=fonts_base, ask=ask)
        path.write_text(deck(d), encoding="utf-8")

    # ---------- مساعدات ----------
    def _motif(self, ws: Workspace, d: Direction, main: str, accent: str) -> str:
        return colorize((idir(ws) / d.motif_file).read_text(encoding="utf-8"), main, accent)

    def _kit(self, brief: Brief, strategy: Strategy, d: Direction, system: dict, ms: MarkSet, ws: Workspace) -> AppKit:
        r = system["light"]
        return AppKit(
            name_ar=brief.name_ar, tagline=strategy.tagline, headline=strategy.samples.get("headline", strategy.tagline),
            points=strategy.voice_do, roles=r, heading=Font(d.heading.font, d.heading.weight), body=Font(d.body.font, d.body.weight),
            numerals=d.numerals, mark=ms.mark, mark_white=ms.mark_white, mark_mono=ms.mark_mono, lockup=ms.lockup,
            lockup_white=ms.lockup_white, lockup_mono=ms.lockup_mono,
            motif_soft=self._motif(ws, d, r["brand_soft"], r["accent_soft"]),
            motif_strong=self._motif(ws, d, r["brand_strong"], r["accent"]), radius=d.radius)

    def _copy_fonts(self, dest: Path, names: list[str]) -> list[str]:
        dest.mkdir(parents=True, exist_ok=True)
        out = []
        for n in dict.fromkeys(names):
            src = self._fonts / n
            if not src.is_file():
                continue
            shutil.copy2(src, dest / n)
            out.append(n)
            lic = license_file(self._fonts, n)
            if lic and not (dest / lic.name).is_file():
                shutil.copy2(lic, dest / lic.name)
                out.append(lic.name)
        return out

    def _request(self, ws: Workspace, kind: str, brief: Brief, problems: list[str], history: list, direction: Direction | None = None,
                 *, keep: str | None = None) -> None:
        ws.write_request(f"REQUEST-{kind}.md", request_md(kind, brief, problems, history, direction, self._fonts, keep=keep))


def strategy_md(brief: Brief, s: Strategy) -> str:
    lines = [f"# المنصة الاستراتيجية: {brief.name_ar}", "", f"**التموضع:** {s.positioning}", "", f"**الوعد:** {s.promise}", "",
             f"**الشعار اللفظي:** {s.tagline}", "", "## الشخصية"]
    lines += [f"- **{t.trait}:** {t.means} (ليس: {t.not_})" for t in s.personality]
    lines += ["", "## نبرة الصوت", "نقول:", *[f"- {x}" for x in s.voice_do], "", "لا نقول:", *[f"- {x}" for x in s.voice_dont], "",
              "## أمثلة", *[f"- {k}: {v}" for k, v in s.samples.items()]]
    if s.imagery:
        lines += ["", "## اتجاه الصورة", s.imagery]
    return "\n".join(lines) + "\n"


def motion_html(mark_svg: str, name_ar: str) -> str:
    root = svgtools.parse(mark_svg)
    root.set("class", "mark")
    for i, el in enumerate(list(root)):
        if svgtools._local(el.tag) in ("title", "desc", "defs"):
            continue
        el.set("style", f"--i:{i}")
    svg = svgtools.to_string(root)
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>ظهور رمز {name_ar}</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#fff}}.mark{{width:min(40vmin,320px);height:auto}}
.mark>*{{animation:sima-rise .6s cubic-bezier(.2,0,0,1) both;animation-delay:calc(var(--i,0) * 90ms);transform-box:fill-box;transform-origin:50% 100%}}
@keyframes sima-rise{{from{{opacity:0;transform:translateY(12%) scale(.96)}}to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion:reduce){{.mark>*{{animation:none}}}}
</style></head><body>{svg}</body></html>"""


def request_md(kind: str, brief: Brief, problems: list[str], history: list, direction: Direction | None, fonts_dir: Path,
               *, keep: str | None = None) -> str:
    """`keep`: معرّف اتجاه معتمد من خارج الخط يبقى كما هو بين الثلاثة (`identity.directions: three`)؛ النموذج يكتب الآخرَين."""
    head = {"strategy": "المنصة الاستراتيجية", "directions": "ثلاثة اتجاهات للهوية", "icons": "مجموعة الأيقونات",
            "revise": "تعديل الهوية بملاحظة المالك على الدليل"}[kind]
    fonts = sorted(p.name for p in fonts_dir.glob("*.ttf"))
    lines = [f"# طلب: {head} — {brief.name_ar}", "", "اقرأ `.claude/skills/sima-design/SKILL.md` و`docs/identity.md` و`work/research.md` أولًا.", "",
             "## الموجز", f"- الغرض: {brief.purpose}", f"- الجمهور: {brief.audience}", f"- النموذج الأصلي: {brief.archetype}",
             f"- الكلمات الثلاث: {'، '.join(brief.three_words)}", f"- الإحساس: {brief.taste.feeling}",
             "- ممنوع: " + "؛ ".join([*brief.taste.avoid, *brief.taste.dislikes]),
             f"- ألوان الموجز: ورق {brief.palette.paper}، حبر {brief.palette.ink}، علامة {brief.palette.brand}، تمييز {brief.palette.accent}"
             f" — السياسة: {brief.identity.palette_policy.value}", ""]
    if problems:
        lines += ["## ما يجب إصلاحه", *[f"- {p}" for p in problems], ""]
    if history:
        lines += ["## قرارات المالك السابقة", *[f"- {h.at}: {h.verdict} {h.option} — {h.reason}" for h in history], ""]
    lines.append("## المطلوب")
    if kind == "strategy":
        lines += ["`work/identity/strategy.yaml` بالعربية:", "```yaml", "positioning: جملة: لمن، وماذا نقدّم، وبمَ نختلف",
                  "promise: وعد واحد يمكن الوفاء به", "personality:  # ثلاث سمات بالضبط",
                  "  - {trait: ..., means: ما تعنيه عمليًا, not: ما ليست عليه}", "voice:",
                  "  do: [ثلاث جمل على الأقل]", "  dont: [ثلاث جمل على الأقل]",
                  "  samples: {" + ", ".join(f"{k}: ..." for k in SAMPLES) + "}",
                  "tagline: شعار لفظي قصير (≤ 48 حرفًا)", "imagery: اتجاه الصورة نصًا (لا تصوير يُنتج آليًا)", "```"]
    elif kind == "directions":
        lines += ["`work/identity/directions.yaml` بثلاثة اتجاهات متباعدة فعلًا (لون وخط ونمط)، و`work/identity/motifs/<id>.svg` لكل اتجاه:",
                  "```yaml", "directions:", "  - id: d1", "    name: اسم قصير", "    idea: جملة الفكرة",
                  "    colors: {" + ", ".join(f"{k}: '#RRGGBB'" for k in ROLES) + "}",
                  "    accent_informational: false  # true إن حمل التمييز معلومة (يلزمه تباين 3:1)",
                  "    type: {heading: {font: <ملف>, weight: 700}, body: {font: <ملف>, weight: 400}, numerals: latn|arab}",
                  "    motif: {file: motifs/d1.svg, rule: متى يُستعمل وأين لا يُستعمل}", "    radius: 4", "```",
                  "- الخطوط من `fonts/` فقط: " + "، ".join(fonts) + ".",
                  "- النمط بلاطة تتكرر بلا فواصل: viewBox بحجم البلاطة، أسود #000000 على شفاف، والتمييز data-tone=\"accent\"؛"
                  " بلا نص ولا تدرجات ولا فلاتر ولا شفافية، مشتق من هندسة الرمز المعتمد لا زخرفة عامة.",
                  "- الخط يبني التدرجات والوضع الداكن ويفحص التباين ومحاكاة عمى الألوان وتغطية الخطوط آليًا؛ اختر قيمًا تجتاز."]
        if keep:
            lines += [
                f"- الاتجاه `{keep}` في الملف ونمطه `motifs/{keep}.svg` من تسليم معتمد خارج الخط: لا تعدّلهما ولا تحذفهما (الأداة تعيدهما"
                " كما هما). اكتب الاتجاهين الآخرين بعده في الملف نفسه بالصيغة نفسها، ولكلٍّ ملف نمطه.",
                "- العلامة معتمدة ولا تُمسّ: الرمز في `work/concepts/a1.svg` ومصغّره `work/concepts/a1.small.svg` وصورهما في"
                " `work/render/`. اقرأها قبل الكتابة، واشتقّ نمط كل اتجاه من هندستها هي.",
                f"- الاتجاهان الجديدان بديلان حقيقيان عن `{keep}` وعن بعضهما: يختلف كلٌّ في خط العناوين وفي اللون (ضمن سياسة ألوان"
                " الموجز) وفي النمط وفي الاسم والفكرة؛ لا درجتان من الاتجاه نفسه. المالك يقارن الثلاثة مطبّقة على السياقات نفسها ويختار."]
            if brief.identity.lockup_word:
                lines.append("- اسم العلامة في القفل يُشكَّل من خط عناوين كل اتجاه بجانب الرمز؛ اختر خط عناوين يحمل الكلمة بوزن يوازن الرمز.")
    elif kind == "icons":
        stroke = "سماكة واحدة ≥ 1.5"
        lines += ["`work/identity/icons.yaml` و`work/identity/icons/<id>.svg`:", "```yaml", "stroke: 1.75", "icons:",
                  "  - {id: paper, subject: ورقة}", "```", f"- الموضوعات المطلوبة: {'، '.join(brief.identity.icons)}.",
                  f"- viewBox 0 0 24 24، `fill=\"none\" stroke=\"currentColor\"` على الجذر، {stroke} في كل الملفات، أطراف وزوايا round،"
                  " هامش 2 وحدة، مشتقة من زوايا الرمز وانحناءاته.",
                  "- الأيقونات زخرفية: بلا `<title>` ولا `<desc>` (سِمة تحذفهما وتضيف aria-hidden)؛ اسمها نص الواجهة بجانبها."]
        if direction:
            lines.append(f"- الاتجاه المعتمد: {direction.name} — {direction.idea}")
    else:
        lines += ["عدّل الملف المعني في `work/identity/` (المنصة أو الاتجاهات أو الأنماط أو الأيقونات) بحسب الملاحظة.",
                  "تعديل الاتجاهات أو أنماطها يعيد فتح بوابة الاتجاه للمالك آليًا لأن القرار مربوط بالمحتوى.",
                  "إن كانت الملاحظة سؤالًا، أو كان موضعها خارج `work/identity/`، فلا تعدّل شيئًا: أجب المالك في ردّك الأخير بفقرة"
                  " عربية قصيرة واضحة بلا مسارات شيفرة ولا أسماء دوال؛ جوابك يُعرض له بنصّه في بطاقة الدليل ويعود القرار إليه."]
    return "\n".join(lines) + "\n"


def _mark_key(mark_bw: str, lockup_bw: str) -> str:
    return hashlib.sha256((mark_bw + "\0" + lockup_bw).encode("utf-8")).hexdigest()[:16]
