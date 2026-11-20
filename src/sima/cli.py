"""واجهة سطر الأوامر الوحيدة: sima run | status | decide | identity-decide | name-check | deliver | board | db | render | audit | shape | eval. كل الرسائل بالعربية."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import config
from .domain import Verdict, load_brief
from .services import protocol
from .services.workspace import Workspace, find_workspace, last_version, open_workspace, run_key

KEY_MISMATCH = 7  # رمز خروج `sima run --expect-key`: الموجز لا يطابق مفتاح الإصدار المطلوب استئنافه؛ لا يُفتح إصدار آخر


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def _pipeline(brief_path: str, out_dir: Path | None = None):
    """out_dir لتشغيل خارج مخرجات المشاريع (التقييم): لا حفظ في القاعدة ولا تسليم."""
    from .adapters.auto_deliver import after_identity
    from .adapters.font_shaper import HarfBuzzShaper
    from .adapters.geometry import build_svg
    from .adapters.playwright_renderer import PlaywrightRenderer
    from .adapters.reference_library import VendoredLibrary
    from .services.pipeline import Pipeline
    from .services.shaping import ShapingService

    renderer = PlaywrightRenderer()
    lib = VendoredLibrary()
    from .adapters import local_embed

    embedder = local_embed.LocalEmbedder() if local_embed.enabled() else None  # محلي على 127.0.0.1؛ المتوقف يُتجاوز
    return renderer, Pipeline(
        renderer, ShapingService(HarfBuzzShaper()), lib if lib.available() else None, out_dir or config.OUT_DIR,
        catalog=lib.catalog(), decide_cmd=f"uv run sima decide {brief_path}",
        on_identity_approved=after_identity if out_dir is None else None,
        build_mark=build_svg, embedder=embedder, blind_gate=config.BLIND_GATE, thumbs_gate=config.THUMBS_GATE,
    )


def _version(brief) -> Workspace | None:
    """إصدار هذا الموجز إن وُجد. أمر غير `run` لا يفتح إصدارًا (مراجعة 2026-11-14، خ9 وت5): موجز عُدّل بعد آخر إصدار كان
    يفتح إصدارًا فارغًا يُقرأ ويُسجَّل فيه."""
    ws = find_workspace(config.OUT_DIR, brief)
    if ws is None:
        n = last_version(config.OUT_DIR, brief.project)
        print(f"لا إصدار في مخرجات {brief.project} بمفتاح هذا الموجز ({run_key(brief).key}): آخر إصدار v{n} بمفتاح آخر، أي أن الموجز "
              "عُدّل بعده. هذا الأمر لا يفتح إصدارًا: أعد الموجز كما كان، أو شغّل `sima run` ليُفتح إصدار جديد به." if n else
              f"لا إصدار للمشروع {brief.project} بعد. شغّل `sima run` أولًا.")
    return ws


def _card(ws: Workspace, kind: str) -> dict | None:
    """ما ينتظر المالك الآن في هذا الإصدار بعينه كما تعرضه المنصة، أو None. قرار الطرفية يمرّ بحراسة البطاقة نفسها (ب14)."""
    from .services.inbox import owner_inbox

    item = next((i for i in owner_inbox(config.OUT_DIR) if i["project"] == ws.key.project), None)
    same = item is not None and item["kind"] == kind and item["version"] == ws.version and item["key"] == ws.key.key
    return item if same else None


def cmd_run(args: argparse.Namespace) -> int:
    brief = load_brief(args.brief)
    if args.seed is not None:
        from dataclasses import replace
        brief = replace(brief, seed=args.seed)
    expect = getattr(args, "expect_key", None)
    if expect and run_key(brief).key != expect:  # استئناف من المنصة على إصدار بعينه: موجز عُدّل لا يفتح إصدارًا آخر (م2)
        print(f"الموجز لا يطابق مفتاح الإصدار المطلوب استئنافه ({expect})؛ مفتاحه الآن {run_key(brief).key}. لم يُفتح إصدار جديد: "
              "أعد الموجز كما كان ثم استأنف من المنصة، أو شغّل `sima run` بلا --expect-key لفتح إصدار جديد بالموجز المعدَّل.")
        return KEY_MISMATCH
    from .adapters import claude_model
    from .services.autopilot import run_until_owner

    renderer, pipe = _pipeline(args.brief)
    first = [args.new_version]

    def step():
        nv, first[0] = first[0], False  # الإصدار الجديد مرة واحدة؛ الاستئناف بعد النموذج على الإصدار نفسه
        return pipe.run(brief, new_version=nv)

    from .adapters.run_lock import BUSY, ProjectBusy, project_lock

    wanted = claude_model.enabled() and not getattr(args, "no_model", False)
    model = claude_model.ClaudeCodeModel() if wanted and brief.cloud.model else None  # إذن المشروع فوق إعداد الجهاز
    watch = None
    if model is not None and config.LIVE_PREVIEW:
        from .adapters.geometry import build_svg
        from .services.live_preview import LivePreview

        watch = LivePreview(renderer, build_svg)  # عين الرسّام: يرى ما يكتبه أثناء الاستدعاء
    try:
        with project_lock(config.OUT_DIR, brief.project):
            out = run_until_owner(step, model, claude_model.max_calls(), claude_model.max_total_usd(), watch=watch)
    except ProjectBusy as e:
        print(str(e) + " لم يبدأ هذا التشغيل؛ سيُستأنف الخط بعد انتهاء الجاري إن طُلب من المنصة.")
        return BUSY
    finally:
        renderer.close()
    print(out.message)
    from .services.pipeline import AWAIT_MODEL

    if wanted and not brief.cloud.model and out.code == AWAIT_MODEL:
        print("لم يُستدعَ النموذج آليًا: موجز هذا المشروع لا يأذن بالاستدعاء السحابي. الإذن سطر `cloud: {model: true}` في الموجز.")
    print(f"الإصدار: v{out.workspace.version} · المفتاح: {out.workspace.key.key} · المجلد: {out.workspace.root}")
    return out.code


def cmd_status(args: argparse.Namespace) -> int:
    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1
    stages = ["brief", "research", "diverge", "render", "critique", "preview", "name_check", "package", "deliver"]
    print(f"المشروع {brief.project} · v{ws.version} · {ws.key.key}")
    for s in stages:
        print(f"  {'✓' if ws.done(s) else '·'} {s}")
    print(f"  جولات النقد: {protocol.critique_rounds_done(ws)}")
    from .services.ledger import Ledger
    ledger = Ledger(ws.ledger_path)
    for d in ledger.read():
        print(f"  قرار {d.at}: {d.verdict.value} {d.concept_id or ''} — {d.reason}")
    lock = ledger.lock()
    cur = lock.current()
    print(f"  الوسيط الحالي: {cur.value if cur else 'لا شيء'}")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    """قرار المالك في مفهوم معروض، بحراسة بطاقة المنصة نفسها (`inbox.decide`): ما يُعرض الآن وبصمته، وسبب للرفض والتعديل.
    كان يسجّل بلا تحقق: اعتماد مفهوم لا وجود له، أو اعتماد قبل الرسم والحَكَم (مراجعة 2026-11-14، خ9 وب14)."""
    from .services.inbox import InboxError, decide, switch_medium

    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1
    item = _card(ws, "concepts")
    if item is None:
        print("لا مفاهيم تنتظر قرارك الآن في هذا الإصدار؛ شغّل `sima run` أو راجع المنصة.")
        return 1
    where = (config.OUT_DIR, brief.project, item["version"], item["key"])
    try:
        if args.medium:
            print(switch_medium(*where, args.medium, args.reason, item["digest"]))
        else:
            verdict, concept = ((Verdict.APPROVED, args.approve) if args.approve else
                                (Verdict.REJECTED, args.reject) if args.reject else (Verdict.REVISE, args.revise))
            print(decide(*where, verdict.value, concept, args.reason, item["digest"]))
    except InboxError as e:
        print(e)
        return 1
    print(f"شغّل `uv run sima run {args.brief}` للمتابعة.")
    return 0


def cmd_designer(args: argparse.Namespace) -> int:
    """مسار المصمّم الخارجي: قرارات المالك على صفحة السكتشات والمتجه (بديل بطاقتَي المنصة وبحراستهما، ب14)، و--intake
    استلام تسليم المصمّم بيانَ اعتماد."""
    from .services import designer, inbox

    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1

    def shown(item: dict) -> tuple:
        return config.OUT_DIR, brief.project, item["version"], item["key"], item["digest"]

    try:
        if args.rebuild:
            item = _card(ws, "identity")
            if item is None or item.get("gate") != "book":
                item = _card(ws, "stalled")  # أو بعد استنفاد جولات التصحيح: الخط واقف عند المالك ببصمة التسليم المردود
            if item is None:
                print("ردّ المتجه يكون من بطاقة الدليل أو بعد استنفاد جولات التصحيح، ولا شيء منهما ينتظر قرارك الآن؛ شغّل "
                      "`sima run` أو راجع المنصة.")
                return 1
            print(inbox.return_vector(*shown(item), args.reason or ""))
        elif args.intake is None:
            item = _card(ws, "sketches")
            if item is None:
                print("لا صفحة سكتشات تنتظر قرارك الآن في هذا الإصدار؛ شغّل `sima run` أو راجع المنصة.")
                return 1
            if args.reject:
                print(inbox.reject_sketches(*shown(item), args.reason or ""))
            elif args.develop is not None:
                print(inbox.develop_sketch(*shown(item), args.develop, args.note or ""))
            else:
                print(inbox.choose_sketch(*shown(item), args.pick, args.note or ""))
        if args.intake is None:
            print(f"شغّل `uv run sima run {args.brief}` للمتابعة.")
            return 0
        sheet, problems = designer.read_sheet(ws)
        if sheet is None:
            print("صفحة السكتشات لم تُستلم بعد" + (": " + "؛ ".join(problems) if problems else "؛ شغّل `sima run` لكتابة طلبها."))
            return 1
        choice = designer.current(ws, sheet)
        if choice is None:
            print("لا اختيار للمالك بعد على هذه الصفحة؛ الاستلام يتبع اختياره.")
            return 1
        path = designer.write_manifest(ws, choice["sketch"], Path(args.intake), args.min_mark_px, args.min_stroke_px)
    except (designer.DesignerError, inbox.InboxError) as e:
        print(e)
        return 1
    kept, stroke = designer.declared_min(ws, choice["sketch"]), designer.declared_stroke(ws, choice["sketch"])
    print(f"كُتب بيان الاعتماد ببصماته: {path}." + (f" الحد الأدنى المعلن للعلامة {kept} بكسل." if kept else "")
          + (f" حدّ السماكة المعلن {stroke:g} بكسل." if stroke is not None else "")
          + " شغّل `sima run` لفحصه وبناء الهوية.")
    return 0


def cmd_style(args: argparse.Namespace) -> int:
    """اختيار الطابع البصري (البديل المكافئ لبطاقة الطابع في المنصة). يصح بعد عرض العينات، ويصح لاحقًا لتغيير الطابع."""
    from .services import style

    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1
    if style.validate(ws, {}):
        print("عينات الطابع لم تكتمل بعد؛ شغّل `sima run` أولًا.")
        return 1
    try:
        row = style.record(ws, args.pick, args.note or "", style.digest(ws))
    except ValueError as e:
        print(e)
        return 1
    print("اختير الطابع: " + "، ".join(style.catalog()[s][0] for s in row["styles"]) + ". شغّل `sima run` للرسم به.")
    return 0


def cmd_identity_decide(args: argparse.Namespace) -> int:
    """قرار بوابة هوية بالمحتوى المعروض الآن (البديل المكافئ لصندوق القرارات في المنصة)."""
    from .services.inbox import InboxError, identity_decide

    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1
    item = _card(ws, "identity")
    if item is None or item["gate"] != args.gate:
        print("لا بوابة هوية بهذا الاسم تنتظر قرارك الآن؛ شغّل `sima run` أو راجع المنصة.")
        return 1
    verdict, option = ("approved", args.approve) if args.approve is not None else (("revise", "") if args.revise else ("rejected", ""))
    try:
        print(identity_decide(config.OUT_DIR, brief.project, item["version"], item["key"], args.gate, item["digest"], verdict,
                              option or "", args.reason))
    except InboxError as e:
        print(str(e))
        return 1
    print(f"شغّل `uv run sima run {args.brief}` للمتابعة.")
    return 0


def cmd_name_check(args: argparse.Namespace) -> int:
    """تسجيل نتيجة تحقق المالك اليدوي من توافر الاسم (الأداة لا تتصل بالشبكة)."""
    from .domain import NAME_STATUS_AR, NameStatus
    from .services.namecheck import checklist_md, read_name_check, record_name_check, result_problem

    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1
    problem = result_problem(NameStatus(args.status), args.source, args.note) if args.status else None
    if problem:  # قواعد بطاقة المنصة نفسها (ب14): كان «متاح» يُسجَّل بلا مصدر
        print(problem)
        return 1
    if args.status is None:
        nc = read_name_check(ws)
        path = ws.root / "NAME-CHECK.md"
        path.write_text(checklist_md(brief, nc), encoding="utf-8")
        print(f"قائمة التحقق: {path}")
        print(f"الحالة: {NAME_STATUS_AR[nc.status] if nc else 'لم يُسجَّل شيء'}")
        return 0
    nc = record_name_check(ws, brief, NameStatus(args.status), args.source, args.note)
    print(f"سُجّل: «{nc.name}» {NAME_STATUS_AR[nc.status]} ({len(nc.sources)} مصادر). شغّل `sima run {args.brief}` للمتابعة.")
    return 0


def cmd_deliver(args: argparse.Namespace) -> int:
    """تسليم الحزمة المعتمدة إلى مستودع المشروع بطاقةً للمشغّل (worktree + إيداع محلي + ready). لا push."""
    from .adapters.auto_deliver import targets
    from .adapters.ledger_runner import LedgerRunnerTarget
    from .domain.brief import load_frozen_brief
    from .services.deliver import deliver

    brief = load_brief(args.brief)
    ws = _version(brief)
    if ws is None:
        return 1
    if (ws.root / "brief.json").is_file():
        brief = load_frozen_brief(ws.root)  # ما جُمّد في الإصدار المعتمد
    placed = ws.read_marker("deliver") if ws.done("deliver") else {}
    if args.in_place or placed.get("in_place"):
        from .adapters.auto_deliver import resolve_commit
        from .services.deliver import deliver_in_place

        commit = str(placed.get("commit") or "") or resolve_commit(args.in_place)
        if not commit:
            print(f"لا نقطة git بهذا المرجع في مستودع سِمة: {args.in_place}", file=sys.stderr)
            return 2
        try:
            done = deliver_in_place(ws, brief, commit)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"الإصدار v{ws.version} من {brief.project} مسلَّم في مكانه: هويته مطبّقة في مستودع سِمة بالنقطة {str(done['commit'])[:8]}.")
        return 0
    if args.manual or placed.get("manual"):
        from .adapters.auto_deliver import resolve_commit
        from .services.deliver import deliver_manual

        if placed.get("manual"):
            repo, commit = Path(str(placed.get("repo", ""))), str(placed.get("commit", ""))
        else:
            if not args.repo:
                print("التسليم اليدوي يلزمه --repo <مستودع المشروع> الذي دُمجت فيه النقطة.", file=sys.stderr)
                return 2
            repo = Path(args.repo).resolve()
            commit = resolve_commit(args.manual, repo) if (repo / ".git").exists() else ""
            if not commit:
                print(f"لا نقطة git بهذا المرجع في {repo}: {args.manual}", file=sys.stderr)
                return 2
        try:
            done = deliver_manual(ws, brief, repo, commit)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"الإصدار v{ws.version} من {brief.project} مسلَّم يدويًّا: هويته مدموجة في {Path(str(done['repo'])).name} "
              f"بالنقطة {str(done['commit'])[:8]}.")
        return 0
    repo_arg = args.repo or targets().get(brief.project, {}).get("repo")
    if not repo_arg:
        print("حدّد --repo أو سجّل المشروع في deliver_targets.yaml.", file=sys.stderr)
        return 2
    repo = Path(str(repo_arg)).resolve()
    from .adapters.auto_deliver import co_authors, options

    opts = options(targets().get(brief.project))
    if opts["profile"] == "django_static":
        from .adapters.branch_target import BranchTarget

        target = BranchTarget(repo, f"identity-{brief.project}-v{ws.version}", co_authors=co_authors(ws.root))
    else:
        target = LedgerRunnerTarget(repo, co_authors=co_authors(ws.root))
    before = ws.done("deliver") and not args.redeliver
    rc = deliver(ws, brief, target, repo, **{**opts, "static_prefix": args.static_prefix}, redeliver=args.redeliver)
    if opts["profile"] == "django_static":
        print(f"الفرع {rc.branch} · worktree {rc.worktree} · الرأس {rc.head[:8]} · تغيّر {len(rc.changed)} ملفًا من {len(rc.paths)} في الخطة"
              + (" (سُلّم سابقًا)" if before else ""))
        print("فرع محلي في مستودع الهدف بلا دفتر ولا push ولا طلب دمج؛ المالك يقرر الدفع وفتح الطلب.")
        return 0
    if before:
        from .adapters.ledger_runner import card_events

        last = (card_events(repo, rc.card_id) or [{}])[-1]
        print(f"سُلّم هذا الإصدار سابقًا في البطاقة {rc.card_id}، وحالتها في دفتر المشروع الآن: {last.get('event', 'غير مقروءة')}.")
        print(f"الفرع {rc.branch} · الرأس {rc.head[:8]} · تغيّر {len(rc.changed)} ملفًا. لا تسليم جديد (استعمل sima run --new-version لإصدار جديد، أو --redeliver لبطاقة جديدة للإصدار نفسه بعد تغيير بند هدفه).")
        return 0
    print(f"البطاقة {rc.card_id} جاهزة (ready) في {repo}")
    print(f"الفرع {rc.branch} · worktree {rc.worktree} · الرأس {rc.head[:8]} · تغيّر {len(rc.changed)} ملفًا من {len(rc.paths)} في الخطة"
          + (f" · حُذف {len(rc.deleted)} من هوية سابقة" if rc.deleted else ""))
    from .adapters.ledger_runner import BASE_NOTE

    print(BASE_NOTE)
    print("يلتقطها مشغّل المشروع (python automation/runner.py --once) أو جلسته؛ ويتابع صندوق «ماذا جرى؟» حالتها حتى الدمج.")
    return 0


def _frontend_ready() -> str:
    """حزمة Vue مبنية وأحدث من مصادرها، وإلا تُبنى بـ npm (بلا نافذة). يعيد سطر خطأ أو نصًا فارغًا."""
    import shutil
    import subprocess

    front = config.ROOT / "frontend"
    manifest = config.ROOT / "src" / "sima" / "web" / "frontend_dist" / ".vite" / "manifest.json"
    sources = [p for p in (front / "src").rglob("*") if p.is_file()] if (front / "src").is_dir() else []
    if manifest.is_file() and all(p.stat().st_mtime <= manifest.stat().st_mtime for p in sources):
        return ""
    npm = shutil.which("npm")
    if not npm or not (front / "node_modules").is_dir():
        return "واجهة المنصة غير مبنية: شغّل npm install ثم npm run build في frontend/."
    print("تُبنى واجهة المنصة (Vue)…", flush=True)
    p = subprocess.run([npm, "run", "build"], cwd=front, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    return "" if p.returncode == 0 else "تعذّر بناء واجهة المنصة: " + (p.stdout + p.stderr)[-1500:]


def cmd_board(args: argparse.Namespace) -> int:
    """منصة سِمة الحية: Django وواجهة Vue على 127.0.0.1 بصفحات اليوم والمشاريع والقرارات والأتمتة."""
    out_dir = Path(args.out).resolve() if args.out else config.OUT_DIR
    os.environ["SIMA_OUT"] = str(out_dir)  # التشغيل الخلفي بعد القرار يقرأ المجلد نفسه
    os.environ["SIMA_BOARD_PORT"] = str(args.port)
    if args.repo:
        os.environ["SIMA_BOARD_REPO"] = str(Path(args.repo).resolve())
    problem = _frontend_ready()
    if problem:
        print(problem, file=sys.stderr)
        return 1
    from .web.server import serve

    serve(port=args.port)
    return 0


def cmd_db(args: argparse.Namespace) -> int:
    from .adapters import registry

    if args.action in {"start", "stop", "status"}:
        rc, msg = registry.cluster(args.action)
        print(msg)
        return rc
    if args.action == "migrate":
        registry.migrate()
        print("طُبّقت ترحيلات قاعدة سِمة.")
        return 0
    out = Path(args.out) if args.out else config.OUT_DIR
    n = registry.sync(out)
    print(f"المزامنة: {n['runs']} إصدار، و{n['identities']} هوية معتمدة في قاعدة سِمة.")
    for line in n.get("failed", []):
        print(f"تعذّرت مزامنة {line}", file=sys.stderr)
    return 1 if n.get("failed") else 0


def cmd_render(args: argparse.Namespace) -> int:
    """إعادة تصيير وفحص المفاهيم فقط (يحذف علامة render ليُعاد الحساب)."""
    brief = load_brief(args.brief)
    if args.seed is not None:
        from dataclasses import replace
        brief = replace(brief, seed=args.seed)
    ws = find_workspace(config.OUT_DIR, brief)  # لا إصدار بعد: يفتحه `run` نفسه ويصيّر
    if ws is not None and ws.done("render"):
        ws.marker("render").unlink()
    return cmd_run(args)


def cmd_audit(args: argparse.Namespace) -> int:
    """فحص ملف SVG واحد خارج أي مشروع."""
    from .adapters.playwright_renderer import PlaywrightRenderer
    from .adapters.reference_library import VendoredLibrary
    from .services.audit import AuditService
    from .services.similarity import SimilarityService

    renderer = PlaywrightRenderer()
    try:
        lib = VendoredLibrary()
        sim = SimilarityService(renderer, lib if lib.available() and not args.no_library else None)
        svc = AuditService(renderer, sim)
        rep = svc.audit(Path(args.svg).stem, Path(args.svg).read_text(encoding="utf-8"), stage=args.stage)
    finally:
        renderer.close()
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    return 0 if rep.passed else 1


def cmd_shape(args: argparse.Namespace) -> int:
    """تشكيل كلمة عربية إلى مسار SVG (بلا نص حي) لاستعماله مادةً خامًا في مفهوم كلامي."""
    from .adapters.font_shaper import HarfBuzzShaper
    from .services.shaping import ShapingService

    wm = ShapingService(HarfBuzzShaper()).wordmark(args.text, args.font, args.weight, height=args.height, padding=args.padding, title=args.text)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(wm.svg, encoding="utf-8")
    print(f"كُتب {args.out} (عرض {wm.width:.1f} × ارتفاع {wm.height:.0f})")
    return 0


EVAL_DIR = config.ROOT / "evals" / "drawer"


def _eval_meta(caps: dict | None = None) -> dict:
    """ما يلزم لنسبة النتيجة إلى إعدادها: النماذج والجهد والعتبة، ونقطة git، وبصمة مراجع الرسّام."""
    import hashlib
    import subprocess

    from .adapters import claude_model

    def git(*a: str) -> str:
        p = subprocess.run(["git", *a], cwd=config.ROOT, capture_output=True, text=True, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.stdout.strip() if p.returncode == 0 else ""

    h = hashlib.sha256()
    for f in sorted(x for x in config.SKILL_DIR.rglob("*") if x.is_file()):
        h.update(f.relative_to(config.SKILL_DIR).as_posix().encode("utf-8") + bytes([0]) + f.read_bytes().replace(b"\r\n", b"\n"))
    return {**claude_model.settings(), "bar": [config.JUDGE_MIN_TOTAL, config.JUDGE_MIN_EACH, config.JUDGE_KEY_MIN],
            "commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "references": h.hexdigest()[:12], "caps": caps or {}}


def _eval_run(args: argparse.Namespace) -> int:
    import re
    import shutil
    from datetime import UTC, datetime

    from .adapters import claude_model
    from .services import drawer_eval as ev
    from .services.autopilot import MIN_CALL_USD, run_until_owner

    cases = ev.load_cases(EVAL_DIR / "cases", args.case or [])
    prior = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((EVAL_DIR / "results").glob("*.json"))]
    warn = ev.cap_warning(prior, args.until, args.case_usd)
    if warn:
        print(warn, file=sys.stderr)
    now = datetime.now(UTC)
    slug = re.sub(r"[^a-z0-9]+", "-", args.label.lower()).strip("-")
    run_id = now.strftime("%Y%m%d-%H%M%S") + (f"-{slug}" if slug else "")
    out = config.OUT_DIR / "_eval" / run_id  # مجلد يبدأ بشرطة سفلية: لا تعرضه المنصة، وخارج git
    renderer, pipe = _pipeline("<حالة تقييم>", out_dir=out)
    model = claude_model.ClaudeCodeModel() if claude_model.enabled() and not args.no_model else None
    watch = None
    if model is not None and config.LIVE_PREVIEW:
        from .adapters.geometry import build_svg
        from .services.live_preview import LivePreview

        watch = LivePreview(renderer, build_svg)
    rows, spent = [], 0.0
    try:
        for case in cases:
            ws = open_workspace(out, case.brief)
            ev.prepare(ws, case)
            left = args.total_usd - spent
            use = model if case.brief.cloud.model and left >= MIN_CALL_USD else None
            cap = min(args.case_usd, left)
            res = run_until_owner(ev.stepper(lambda b=case.brief: pipe.run(b), args.until), use, args.max_calls,
                                  cap, watch=watch if use is not None else None)
            capped = model is not None and use is None and case.brief.cloud.model
            row = ev.collect(ws, case.id, args.until, "بلغ التشغيل سقف الإنفاق الإجمالي قبل هذه الحالة" if capped else res.message,
                             cap_usd=round(cap, 2))
            spent += row["cost_usd"]
            rows.append(row)
            print(f"{case.id}: {'بلغت نقطة التقييم' if row['reached'] else 'لم تبلغها'} · {row['calls']} استدعاء · {row['cost_usd']:g}$")
    finally:
        renderer.close()
    summary = ev.summarize(run_id, now.isoformat(timespec="seconds"), args.label, args.until,
                           _eval_meta({"case_usd": args.case_usd, "total_usd": args.total_usd, "max_calls": args.max_calls}), rows)
    print("\n".join(ev.report(summary)))
    if not summary["totals"]["calls"]:
        shutil.rmtree(out, ignore_errors=True)
        print("لم يُستدعَ النموذج (معطّل أو --no-model): تشغيل تجريبي لا تُحفظ له نتيجة.")
        return 0
    results = EVAL_DIR / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / f"{run_id}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"النتيجة: {results / f'{run_id}.json'} · الأعمال للمعاينة في {out}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """مجموعة تقييم الرسّام: run يشغّل الحالات (مدفوع)، list يسرد الحالات والنتائج، compare يقارن نتيجتين."""
    from .services import drawer_eval as ev

    results = EVAL_DIR / "results"
    try:
        if args.action == "run":
            return _eval_run(args)
        if args.action == "hide":
            from .services.workshop import hide_eval

            run = hide_eval(config.OUT_DIR)
            print(f"أُخفي تشغيل التقييم {run} من الورشة؛ أعماله ونتيجته كما هي." if run else "لا تشغيل تقييم يُخفى.")
            return 0
        if args.action == "list":
            for c in ev.load_cases(EVAL_DIR / "cases"):
                print(f"حالة {c.id}: «{c.brief.name_ar}» · الطابع {', '.join(c.styles)}")
            for p in sorted(results.glob("*.json")) if results.is_dir() else []:
                s = json.loads(p.read_text(encoding="utf-8"))
                print("\n".join(ev.report(s)[:2]))
            return 0
        if len(args.runs) != 2:
            print("المقارنة تحتاج معرّفَي تشغيلين: sima eval compare <أ> <ب> (المعرّفات من sima eval list).", file=sys.stderr)
            return 2
        pair = []
        for r in args.runs:
            p = results / f"{r}.json"
            if not p.is_file():
                print(f"لا نتيجة بهذا المعرّف: {r}", file=sys.stderr)
                return 2
            pair.append(json.loads(p.read_text(encoding="utf-8")))
        print("\n".join(ev.compare(*pair)))
        return 0
    except ev.EvalError as e:
        print(str(e), file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sima", description="سِمة: من موجز العلامة إلى حزمة هوية معتمدة، محليًا وبلا نافذة.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="تشغيل الخط كاملًا أو متابعته من حيث توقف")
    r.add_argument("brief")
    r.add_argument("--new-version", action="store_true", help="إصدار جديد حتى لو لم يتغير الموجز")
    r.add_argument("--seed", type=int, default=None)
    r.add_argument("--no-model", action="store_true", help="لا استدعاء آلي للنموذج في هذا التشغيل")
    r.add_argument("--expect-key", default=None, metavar="KEY",
                   help="استئناف إصدار بعينه (تمرّره المنصة): يخرج بالرمز 7 إن لم يطابقه مفتاح الموجز، ولا يفتح إصدارًا آخر")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("status", help="حالة المراحل والقرارات")
    s.add_argument("brief")
    s.set_defaults(fn=cmd_status)
    d = sub.add_parser("decide", help="تسجيل قرار المالك")
    d.add_argument("brief")
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", metavar="ID")
    g.add_argument("--reject", metavar="ID")
    g.add_argument("--revise", metavar="ID")
    g.add_argument("--medium", choices=["abstract_mark", "wordmark", "emblem", "pattern"],
                   help="ارسم من جديد بالمعيار في هذا الوسيط (ولو الحالي)؛ الوسيط لا يتغيّر إلا بهذا")
    d.add_argument("--reason", default="")
    d.set_defaults(fn=cmd_decide)
    st = sub.add_parser("style", help="اختيار الطابع البصري من العينات الست (واحد أو اثنان)")
    st.add_argument("brief")
    st.add_argument("--pick", action="append", required=True, help="معرّف الأسلوب s1..s6 (يتكرر لاثنين)")
    st.add_argument("--note", default="", help="ملاحظة للرسّام والحَكَم")
    st.set_defaults(fn=cmd_style)
    dz = sub.add_parser("designer", help="مسار المصمّم الخارجي: اختيار السكتش أو استلام المتجه")
    dz.add_argument("brief")
    dg = dz.add_mutually_exclusive_group(required=True)
    dg.add_argument("--pick", type=int, metavar="N", help="رقم السكتش الذي اختاره المالك")
    dg.add_argument("--develop", type=int, metavar="N", help="طوّر هذا السكتش: صفحة معالجات حوله من المصمّم قبل بنائه (مع --note)")
    dg.add_argument("--intake", metavar="DIR", help="مجلد فيه logo.svg وicon.svg وmotif.svg وdirection.yaml وconcept.yaml")
    dg.add_argument("--reject", action="store_true", help="رفض صفحة السكتشات كلها؛ يلزمه --reason ويعود به الطلب إلى المصمّم")
    dg.add_argument("--rebuild", action="store_true",
                    help="ردّ المتجه المبني للسكتش المختار؛ يلزمه --reason ويعود به السكتش نفسه إلى المصمّم ليبنيه من جديد")
    dz.add_argument("--note", default="")
    dz.add_argument("--reason", default="", help="سبب رفض الصفحة أو ردّ المتجه، يُنقل إلى المصمّم بنصّه")
    dz.add_argument("--min-mark-px", type=int, metavar="PX",
                    help="مع --intake: حدّ أدنى يعلنه المالك للعلامة (16 إلى 320)، تُفحص عنده ويُذكر في قواعد الاستعمال")
    dz.add_argument("--min-stroke-px", type=float, metavar="PX",
                    help="مع --intake: حدّ سماكة أدنى يعلنه المالك بدل 1.5 (من 0.75 إلى أقل من 1.5) عند الحجم المعلن؛ قراره وحده")
    dz.set_defaults(fn=cmd_designer)
    idd = sub.add_parser("identity-decide", help="قرار بوابة الهوية: المنصة الاستراتيجية أو الاتجاه أو الدليل")
    idd.add_argument("brief")
    idd.add_argument("--gate", choices=["strategy", "directions", "book"], required=True)
    gi = idd.add_mutually_exclusive_group(required=True)
    gi.add_argument("--approve", nargs="?", const="", metavar="DIRECTION", help="للاتجاه: معرّفه (d1..)")
    gi.add_argument("--revise", action="store_true")
    gi.add_argument("--reject", action="store_true")
    idd.add_argument("--reason", default="")
    idd.set_defaults(fn=cmd_identity_decide)
    nc = sub.add_parser("name-check", help="قائمة التحقق من توافر الاسم أو تسجيل نتيجتها")
    nc.add_argument("brief")
    nc.add_argument("--status", choices=["clear", "conflict", "pending"], default=None, help="بلا status: يكتب قائمة التحقق فقط")
    nc.add_argument("--source", action="append", default=[], help="مصدر فُحص فعليًا (يتكرر)")
    nc.add_argument("--note", default="")
    nc.set_defaults(fn=cmd_name_check)
    dl = sub.add_parser("deliver", help="تسليم الحزمة المعتمدة إلى مستودع المشروع بطاقةً للمشغّل")
    dl.add_argument("brief")
    dl.add_argument("--repo", default=None, help="جذر مستودع المشروع (فيه automation/ledger.py)؛ الافتراضي من deliver_targets.yaml")
    dl.add_argument("--static-prefix", default="/static/", help="بادئة الملفات الثابتة في manifest")
    dl.add_argument("--in-place", default=None, metavar="COMMIT",
                    help="المشروع هو مستودع سِمة نفسه: سجّل نقطة git التي طبّقت الحزمة تسليمًا، بلا بطاقة ولا worktree")
    dl.add_argument("--manual", default=None, metavar="COMMIT",
                    help="تسليم يدوي بقرار المالك: جلسة المشروع طبّقت الحزمة ودمجتها؛ سجّل نقطة الدمج في --repo تسليمًا ودمجًا")
    dl.add_argument("--redeliver", action="store_true",
                    help="بطاقة جديدة للإصدار المسلَّم نفسه بعد تغيير بند هدفه في deliver_targets.yaml؛ السابقة تُلغى إن لم تُلتقط")
    dl.set_defaults(fn=cmd_deliver)
    bd = sub.add_parser("board", help="منصة سِمة الحية على 127.0.0.1 (اليوم، المشاريع، القرارات، الأتمتة)")
    bd.add_argument("--repo", default=None, help="مستودع فيه automation/ledger (اختياري)")
    bd.add_argument("--port", type=int, default=8766)
    bd.add_argument("--out", default=None, help="مجلد المخرجات (الافتراضي out/ أو SIMA_OUT)")
    bd.set_defaults(fn=cmd_board)
    db = sub.add_parser("db", help="قاعدة سِمة (PostgreSQL محلي): start | stop | status | migrate | sync")
    db.add_argument("action", choices=["start", "stop", "status", "migrate", "sync"])
    db.add_argument("--out", default=None, help="مجلد المخرجات للمزامنة (الافتراضي out/)")
    db.set_defaults(fn=cmd_db)
    rr = sub.add_parser("render", help="إعادة التصيير والفحص بعد تعديل SVG")
    rr.add_argument("brief")
    rr.add_argument("--new-version", action="store_true")
    rr.add_argument("--seed", type=int, default=None)
    rr.set_defaults(fn=cmd_render)
    a = sub.add_parser("audit", help="فحص ملف SVG واحد")
    a.add_argument("svg")
    a.add_argument("--stage", choices=["bw", "color"], default="bw")
    a.add_argument("--no-library", action="store_true")
    a.set_defaults(fn=cmd_audit)
    sh = sub.add_parser("shape", help="تشكيل كلمة عربية إلى مسارات SVG")
    sh.add_argument("text")
    sh.add_argument("--font", default="ReemKufi[wght].ttf")
    sh.add_argument("--weight", type=int, default=700)
    sh.add_argument("--height", type=float, default=256.0)
    sh.add_argument("--padding", type=float, default=0.08)
    sh.add_argument("-o", "--out", required=True)
    sh.set_defaults(fn=cmd_shape)
    e = sub.add_parser("eval", help="مجموعة تقييم الرسّام: run (مدفوع) | list | compare <أ> <ب> | hide (إخفاء آخر تشغيل من الورشة)")
    e.add_argument("action", choices=["run", "list", "compare", "hide"])
    e.add_argument("runs", nargs="*", help="للمقارنة: معرّفا تشغيلين")
    e.add_argument("--case", action="append", help="حالة بعينها (يتكرر)؛ الافتراضي كل الحالات")
    e.add_argument("--until", choices=["judge", "thumbs"], default="judge", help="نقطة التوقف: أول حكم مستقل، أو اختيار المصغّرات (أرخص)")
    e.add_argument("--case-usd", type=float, default=8.0, help="سقف الإنفاق للحالة الواحدة")
    e.add_argument("--total-usd", type=float, default=30.0, help="سقف الإنفاق للتشغيل كله")
    e.add_argument("--max-calls", type=int, default=10, help="سقف الاستدعاءات للحالة الواحدة")
    e.add_argument("--label", default="", help="وصف قصير لما يُقاس (يدخل معرّف التشغيل)")
    e.add_argument("--no-model", action="store_true", help="تشغيل تجريبي بلا نموذج ولا كلفة")
    e.set_defaults(fn=cmd_eval)
    return p


def main(argv: list[str] | None = None) -> int:
    _utf8()
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
