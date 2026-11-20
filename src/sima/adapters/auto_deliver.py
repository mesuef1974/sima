"""التسليم الآلي بعد اعتماد الدليل: إن كان للمشروع مستودع في deliver_targets.yaml يُسلَّم الإصدار بطاقةً لمشغّله.

موافقة المالك (2026-11-09). سِمة لا تدفع ولا تفتح طلبًا؛ المشغّل في المستودع هو من يفعل. الفشل لا يُبطل الاعتماد،
ويُعرض للمالك مع الأمر اليدوي البديل.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .. import config

TARGETS = config.ROOT / "deliver_targets.yaml"


def targets(path: Path = TARGETS) -> dict[str, dict]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): dict(v or {}) for k, v in data.items()}


def options(target: dict | None) -> dict:
    """خيارات التسليم من بند الهدف في deliver_targets.yaml، مصدرًا واحدًا للتسليم الآلي وأمر الطرفية."""
    t = target or {}
    return {"static_prefix": str(t.get("static_prefix", "/static/")), "unify_brand": bool(t.get("unify_brand")),
            "apply_identity": t.get("apply_identity") or None, "apply_paper": t.get("apply_paper") or None,
            "profile": str(t.get("profile", "spa")), "styles": tuple(t.get("styles") or ()),
            **({"tokens_path": str(t["tokens"])} if t.get("tokens") else {}),
            **({"mirrors": {str(k): str(v) for k, v in t["mirrors"].items()}} if t.get("mirrors") else {})}


def deliver_if_configured(root: Path) -> str:
    from ..domain.brief import load_frozen_brief
    from ..services.deliver import deliver
    from ..services.workspace import workspace_of
    from .ledger_runner import LedgerRunnerTarget

    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    project = str(run["project"])
    t = targets().get(project)
    if t and t.get("in_place"):
        return (f"مشروع {project} هو مستودع سِمة نفسه: طبّق الحزمة هنا ثم سجّل نقطتها بالأمر: "
                f"uv run sima deliver {run['brief_source']} --in-place <نقطة git>")
    if t and t.get("profile") == "django_static":
        return (f"مشروع {project}: تسليم الهوية إلى تطبيق Django مراحل بقرارات المالك، فلا تسليم آلي؛ "
                f"بالأمر: uv run sima deliver {run['brief_source']}")
    if not t or not t.get("repo"):
        return f"لا مستودع تسليم مسجّل لـ {project} في deliver_targets.yaml؛ التسليم بالأمر sima deliver."
    repo = Path(str(t["repo"])).resolve()
    try:
        brief = load_frozen_brief(root)
        rc = deliver(workspace_of(root), brief, LedgerRunnerTarget(repo, co_authors=co_authors(root)), repo, **options(t))
    except Exception as e:  # noqa: BLE001 — يُبلَّغ ولا يُبطل الاعتماد
        return f"تنبيه: تعذّر التسليم الآلي ({type(e).__name__}: {e}). سلّم بالأمر: uv run sima deliver {run['brief_source']} --repo \"{repo}\""
    from .ledger_runner import BASE_NOTE

    removed = f"، منها {len(rc.deleted)} محذوفًا من هوية سابقة" if rc.deleted else ""
    return (f"سُلّم آليًا: البطاقة {rc.card_id} جاهزة لمشغّل {repo.name} على الفرع {rc.branch} (تغيّر {len(rc.changed)} ملفًا{removed}). "
            + BASE_NOTE)


def resolve_commit(ref: str, repo_root: Path | None = None) -> str:
    """النقطة الكاملة لمرجع git في مستودع سِمة، أو نص فارغ إن لم توجد."""
    import subprocess

    p = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=(repo_root or config.ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def _model_name(model_id: str) -> str:
    """اسم النموذج كما يُكتب في سطر النسبة من معرّفه: `claude-fable-5-2` ← «Claude Fable 5.2» (التاريخ واللاحقة يسقطان)."""
    import re

    parts = re.sub(r"\[.*?\]", "", model_id).removeprefix("claude-").split("-")
    words = [p.capitalize() for p in parts if p.isalpha()]
    nums = [p for p in parts if p.isdigit() and len(p) <= 2]
    return " ".join(["Claude", *words, *([".".join(nums)] if nums else [])])


def co_authors(root: Path) -> list[str]:
    """سطور النسبة لنقطة مخرجات الإصدار: النماذج التي عملت فيه فعلًا كما سجّلها `model_calls.jsonl`، لا اسم ثابت. إصدار بلا
    استدعاء نموذج (اعتماد خارجي أو مصمّم خارجي) بلا سطر: لا نموذج شارك فيه."""
    f = root / "model_calls.jsonl"
    names: set[str] = set()
    for line in f.read_text(encoding="utf-8").splitlines() if f.is_file() else []:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or not rec.get("ok"):
            continue
        used = [str(m) for m in rec.get("models_used") or []] or [str(rec.get("model") or "")]
        names |= {_model_name(m) for m in used if m and m != "default"}
    return [f"Co-Authored-By: {n} <noreply@anthropic.com>" for n in sorted(names)]


def commit_outputs(root: Path, repo_root: Path | None = None) -> str:
    """نقطة git محلية لمخرجات الإصدار المعتمد وقراراته (قاعدة «نقطة بعد كل مرحلة»). تُودَع مسارات الإصدار وحدها، فلا يمسّ
    عملًا آخر غير مودَع في المستودع، ولا دفع. idempotent: لا شيء جديد، لا نقطة."""
    import subprocess

    base = (repo_root or config.ROOT).resolve()
    try:
        rel = root.resolve().relative_to(base).as_posix()
    except ValueError:
        return "مخرجات الإصدار خارج مستودع سِمة؛ لا نقطة git لها."
    if not (base / ".git").exists():
        return ""

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=base, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)

    added = git("add", "--", rel)
    if added.returncode != 0:  # فهرس مقفل مثلًا: كان يُهمل فيعود الأمر فارغًا كأن لا جديد (ت6)
        return f"تنبيه: تعذّرت نقطة git لمخرجات الإصدار (git add): {(added.stderr or added.stdout).strip()[:200]}"
    if git("diff", "--cached", "--quiet", "--", rel).returncode == 0:
        return ""
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    msg = f"إصدار {run.get('project')} v{run.get('version')} معتمد: مخرجاته وقراراته (نقطة آلية من سِمة، بلا رفع)"
    authors = co_authors(root)  # قاعدة المالك: كل نقطة تنتهي بنسبة النموذج العامل فعلًا
    if authors:
        msg += "\n\n" + "\n".join(authors)
    p = git("commit", "-q", "-m", msg, "--", rel)
    if p.returncode != 0:
        return f"تنبيه: تعذّرت نقطة git لمخرجات الإصدار: {(p.stderr or p.stdout).strip()[:200]}"
    return f"أُودعت مخرجات الإصدار في نقطة git محلية ({git('rev-parse', '--short', 'HEAD').stdout.strip()})."


def after_identity(root: Path) -> str:
    """منفذ ما بعد اعتماد الدليل: الحفظ في قاعدة سِمة، ثم التسليم الآلي، ثم نقطة git لمخرجات الإصدار."""
    from .registry import record_identity

    lines = [record_identity(root), deliver_if_configured(root), commit_outputs(root)]
    return "\n".join(x for x in lines if x)
