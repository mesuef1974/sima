"""خدمة السجل: تنقل ما على القرص (out/<project>/v<n>) إلى PostgreSQL بلا تكرار، وتحفظ الهوية المعتمدة بأصولها.

كل الدوال idempotent: إعادة تشغيلها على الإصدار نفسه لا تُنشئ صفوفًا مكررة. القرص هو المصدر، والقاعدة السجلّ الدائم المستعلَم.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime
from pathlib import Path

from django.db import transaction

from ... import config
from ...domain.identity import Gate as GateEnum
from ...services.identity_flow import IdentityFlow
from ...services.identity_protocol import ledger, read_directions, read_strategy
from ...services.ledger import Ledger
from ...services.workspace import Workspace, workspace_of
from .models import ApprovedIdentity, Asset, AssetKind, ConceptDecision, Gate, GateDecision, Project, Run, Verdict

TEXT = {".svg", ".css", ".scss", ".json", ".js", ".md", ".html", ".txt", ".webmanifest", ".vue"}
MAX_TEXT = 512 * 1024


class RegistryError(RuntimeError):
    """تعذّر الحفظ في السجل بسبب يُعرض للمالك كما هو."""


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _workspace(root: Path) -> tuple[Workspace, dict]:
    return workspace_of(root), json.loads((root / "run.json").read_text(encoding="utf-8"))


@transaction.atomic
def sync_run(root: Path) -> Run:
    """المشروع والإصدار وقرارات المالك كلها (المفاهيم والبوابات) من ملفات الإصدار."""
    ws, data = _workspace(root)
    brief = json.loads((root / "brief.json").read_text(encoding="utf-8")) if (root / "brief.json").is_file() else {}
    project, _ = Project.objects.update_or_create(slug=data["project"], defaults={"name_ar": brief.get("name_ar") or data["project"]})
    run, _ = Run.objects.update_or_create(project=project, version=ws.version, defaults={
        "key": ws.key.key, "brief_hash": ws.key.brief_hash, "seed": ws.key.seed, "brief_source": str(data.get("brief_source", "")),
        "closed": bool(data.get("closed"))})
    for d in Ledger(ws.ledger_path).read():
        ConceptDecision.objects.get_or_create(run=run, concept_id=d.concept_id or "", verdict=d.verdict.value, decided_at=_dt(d.at),
                                              defaults={"medium": d.medium.value, "reason": d.reason, "round": d.round})
    for g in ledger(ws).read():
        GateDecision.objects.get_or_create(run=run, gate=g.gate.value, digest=g.digest, decided_at=_dt(g.at),
                                           defaults={"verdict": g.verdict, "option": g.option, "reason": g.reason})
    for digest, verdict, option, reason, at in designer_decisions(ws):
        GateDecision.objects.get_or_create(run=run, gate=Gate.DESIGNER, digest=digest, decided_at=_dt(at),
                                           defaults={"verdict": verdict, "option": option, "reason": reason})
    return run


def designer_decisions(ws: Workspace) -> list[tuple[str, str, str, str, str]]:
    """قرارات المالك في مسار المصمّم الخارجي (`designer_decisions.jsonl`) بصيغة قرار بوابة: (بصمة الصفحة، الحكم، الخيار،
    السبب، الوقت). كانت خارج القاعدة فلا يُرى فيها أي سكتش اختار ولماذا ردّ متجهًا (ت11). اختيار سكتش اعتماد وخياره `sN`،
    وطلب تطويره تعديل، ورفض الصفحة أو ردّ متجه السكتش رفض بسببه."""
    from ...services import designer

    rows = []
    for c in designer.choices(ws):
        if not isinstance(c, dict) or not c.get("at") or not c.get("digest"):
            continue
        option = f"s{c['sketch']}" if c.get("sketch") is not None else ""
        if c.get("rejected") or c.get("rebuild"):
            verdict, reason = Verdict.REJECTED, str(c.get("reason") or "")
        elif c.get("develop"):
            verdict, reason = Verdict.REVISE, str(c.get("note") or "")
        else:
            verdict, reason = Verdict.APPROVED, str(c.get("note") or "")
        rows.append((str(c["digest"]), verdict.value, option, reason, str(c["at"])))
    return rows


def _kind(rel: str) -> str:
    name = rel.rsplit("/", 1)[-1]
    if rel.startswith("identity/"):
        sub = rel.split("/")[1]
        return {"tokens": AssetKind.TOKENS, "fonts": AssetKind.FONT, "patterns": AssetKind.PATTERN, "icons": AssetKind.ICON,
                "applications": AssetKind.APPLICATION, "screens": AssetKind.SCREEN, "motion": AssetKind.MOTION}.get(sub) or (
            AssetKind.REVEAL if name.startswith("reveal") else AssetKind.BOOK if name.startswith("brand-book") else AssetKind.DOC)
    if name.endswith((".svg", ".png", ".ico")) or name in ("BrandMark.vue", "BrandLockup.vue"):  # القفل علامة لا وثيقة (ت11)
        return AssetKind.MARK
    return AssetKind.TOKENS if name == "tokens.css" else AssetKind.DOC


@transaction.atomic
def record_identity(root: Path) -> ApprovedIdentity:
    """الهوية المعتمدة: تُستدعى بعد اعتماد المالك للدليل. ترفض إن لم يكن الاعتماد مسجلًا على بصمة الدليل الحالي."""
    run = sync_run(root)
    ws, _ = _workspace(root)
    marker = ws.read_marker("identity")
    if not marker:
        raise RegistryError("الهوية لم تُعتمد بعد في هذا الإصدار.")
    approval = (GateDecision.objects.filter(run=run, gate=GateEnum.BOOK.value, digest=marker["book"], verdict="approved")
                .order_by("-decided_at").first())
    if approval is None:
        raise RegistryError("لا اعتماد مسجّل على بصمة الدليل الحالية.")
    strategy, _ = read_strategy(ws)
    dirs, _ = read_directions(ws)
    d = next((x for x in dirs if x.id == marker["direction"]), None)
    approved_concept = Ledger(ws.ledger_path).approved()
    if strategy is None or d is None or approved_concept is None:
        raise RegistryError("ملفات المنصة أو الاتجاهات أو قرار المفهوم ناقصة على القرص.")
    system, rep, fonts = IdentityFlow(None, None, config.FONTS_DIR).evaluate(_brief(root), d)  # type: ignore[arg-type]  # evaluate لا يصيّر
    identity, _ = ApprovedIdentity.objects.update_or_create(run=run, defaults={
        "approval": approval, "concept_id": approved_concept.concept_id or "", "direction_id": d.id, "direction_name": d.name,
        "direction_idea": d.idea, "colors": d.colors, "roles_light": system["light"], "roles_dark": system["dark"],
        "scales": {k: {str(s): v for s, v in sc.items()} for k, sc in system["scales"].items()}, "fonts": fonts,
        "numerals": d.numerals, "radius": d.radius,
        "strategy": {"positioning": strategy.positioning, "promise": strategy.promise, "tagline": strategy.tagline,
                     "personality": [{"trait": t.trait, "means": t.means, "not": t.not_} for t in strategy.personality],
                     "voice_do": list(strategy.voice_do), "voice_dont": list(strategy.voice_dont), "samples": dict(strategy.samples),
                     "imagery": strategy.imagery},
        "checks_passed": sum(1 for c in rep.checks if c.ok), "checks_total": len(rep.checks), "book_digest": marker["book"],
        "package_path": str(ws.package_dir.relative_to(config.ROOT) if ws.package_dir.is_relative_to(config.ROOT) else ws.package_dir),
        "approved_at": approval.decided_at})
    seen = set()
    for f in sorted(ws.package_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(ws.package_dir).as_posix()
        seen.add(rel)
        raw = f.read_bytes()
        text = raw.decode("utf-8") if f.suffix.lower() in TEXT and len(raw) <= MAX_TEXT else None
        Asset.objects.update_or_create(identity=identity, path=rel, defaults={
            "kind": _kind(rel), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
            "media_type": mimetypes.guess_type(f.name)[0] or "application/octet-stream", "content": text})
    Asset.objects.filter(identity=identity).exclude(path__in=seen).delete()
    return identity


def _brief(root: Path):
    """الموجز المجمّد في الإصدار لفحص سياسة الألوان كما فُحصت وقت البناء، لا الموجز الحي بعد تعديله."""
    from ...domain.brief import load_frozen_brief

    return load_frozen_brief(root)


def sync_all(out_dir: Path) -> dict:
    """مزامنة كل الإصدارات في out/، وتسجيل كل هوية معتمدة لم تُسجَّل. كل إصدار محروس: المعطوب يُذكر بسببه في `failed`
    ولا يوقف مزامنة ما بعده (كان أول إصدار معطوب يُسقط الأمر كله، ت11)."""
    runs = identities = 0
    failed: list[str] = []
    for run_json in sorted(out_dir.glob("*/v*/run.json")):
        root = run_json.parent
        try:
            sync_run(root)
            runs += 1
            ws, _ = _workspace(root)
            if ws.done("identity"):
                record_identity(root)
                identities += 1
        except Exception as e:  # noqa: BLE001 — يُبلَّغ بسببه ويُكمَل
            failed.append(f"{root.parent.name}/{root.name}: {type(e).__name__}: {e}")
    return {"runs": runs, "identities": identities, "failed": failed}
