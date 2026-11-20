"""سجلّ سِمة في PostgreSQL: المزامنة idempotent، والهوية المعتمدة تُحفظ بأصولها، والاعتماد غير المسجّل يُرفض.

تعمل على قاعدة اختبار مؤقتة (test_<db>) تُنشأ وتُحذف هنا؛ تُتخطّى إن لم تكن قاعدة سِمة المحلية تعمل.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sima import config

pytest.importorskip("django")



def _latest_identity(project: str) -> Path:
    """أحدث إصدار محلي للمشروع فيه اتجاهات هوية؛ الإصدارات القديمة تُحذف عند التنظيف، والحيّ يبقى (حُذف v2 في 2026-11-20)."""
    versions = [v for v in (config.ROOT / "out" / project).glob("v*") if (v / "work" / "identity" / "directions.yaml").is_file()]
    return max(versions, key=lambda v: int(v.name[1:]), default=config.ROOT / "out" / project / "v0")


REAL = _latest_identity("math_papers")


@pytest.fixture(scope="module")
def db():
    from sima.web import setup

    setup()
    from django.db import connection

    try:
        connection.ensure_connection()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة سِمة غير متاحة: {e}")
    old = connection.settings_dict["NAME"]
    connection.creation.create_test_db(verbosity=0, autoclobber=True, keepdb=False)
    yield
    connection.creation.destroy_test_db(old, verbosity=0)


def _approved_copy(tmp: Path) -> Path:
    """نسخة من أحدث إصدار حقيقي لأوراق مع اعتماد مصطنع للدليل على بصمة ثابتة، وحزمة صغيرة."""
    if not (REAL / "work" / "identity" / "directions.yaml").is_file():
        pytest.skip("لا مخرجات هوية محلية لأوراق لاختبار التكامل")
    from sima.domain.identity import Gate
    from sima.services.identity_protocol import ledger
    from sima.services.workspace import workspace_of

    root = tmp / "math_papers" / REAL.name
    shutil.copytree(REAL, root, ignore=shutil.ignore_patterns("identity-board", "assets", "*.png", "*.pdf", "identity_decisions.jsonl",
                                                     "designer_decisions.jsonl"))  # بوابات الهوية الثلاث وحدها
    ws = workspace_of(root)
    led = ledger(ws)
    led.record(Gate.STRATEGY, "s" * 16, "approved")
    led.record(Gate.DIRECTIONS, "d" * 16, "approved", option="d1")
    led.record(Gate.BOOK, "b" * 16, "approved")
    ws.mark_done("identity", {"book": "b" * 16, "direction": "d1"})
    pkg = ws.package_dir
    (pkg / "identity" / "tokens").mkdir(parents=True, exist_ok=True)
    (pkg / "identity" / "tokens" / "tokens.css").write_text(":root{--brand:#123}", encoding="utf-8")
    (pkg / "identity" / "reveal.html").write_text("<html>كشف</html>", encoding="utf-8")
    (pkg / "mark.svg").write_text("<svg/>", encoding="utf-8")
    (pkg / "font.woff2").write_bytes(b"\x00\x01\x02")
    return root


def test_asset_kind_by_path():
    from sima.web import setup

    setup()
    from sima.web.registry.models import AssetKind
    from sima.web.registry.service import _kind

    assert _kind("identity/icons/book.svg") == AssetKind.ICON
    assert _kind("identity/reveal.pdf") == AssetKind.REVEAL
    assert _kind("identity/brand-book.html") == AssetKind.BOOK
    assert _kind("identity/STRATEGY.md") == AssetKind.DOC
    assert _kind("mark-bw.svg") == AssetKind.MARK
    assert _kind("tokens.css") == AssetKind.TOKENS


def test_record_identity_is_idempotent_and_keeps_text(db, tmp_path):
    from sima.web.registry.models import ApprovedIdentity, Asset, GateDecision
    from sima.web.registry.service import record_identity, sync_run

    root = _approved_copy(tmp_path)
    first = record_identity(root)
    again = record_identity(root)
    sync_run(root)
    assert first.pk == again.pk
    assert ApprovedIdentity.objects.count() == 1
    assert GateDecision.objects.filter(run=first.run).count() == 3
    assert first.direction_id == "d1" and first.approval.gate == "book"
    assert first.roles_light and first.roles_dark and first.strategy["positioning"]
    css = Asset.objects.get(identity=first, path="identity/tokens/tokens.css")
    assert css.kind == "tokens" and css.content == ":root{--brand:#123}" and len(css.sha256) == 64
    assert Asset.objects.get(identity=first, path="font.woff2").content is None
    (root / "package" / "mark.svg").unlink()
    record_identity(root)
    assert not Asset.objects.filter(identity=first, path="mark.svg").exists()


def test_record_refuses_without_approval_on_current_book(db, tmp_path):
    from sima.services.workspace import workspace_of
    from sima.web.registry.service import RegistryError, record_identity

    root = _approved_copy(tmp_path)
    ws = workspace_of(root)
    ws.mark_done("identity", {"book": "f" * 16, "direction": "d1"})
    with pytest.raises(RegistryError):
        record_identity(root)
