"""القراءة العمياء: بروتوكول ملفها، وحساب الردّ الحتمي، والطلب الذي لا يكشف الاسم ولا الفكرة."""
import yaml

from sima import config
from sima.domain import brief_from_dict
from sima.services import blind
from sima.services.workspace import open_workspace

from .test_domain_ledger_workspace import BRIEF


def _ws(tmp_path):
    ws = open_workspace(tmp_path / "out", brief_from_dict(BRIEF, source="b.yaml"))
    ws.ensure()
    return ws


def _write(ws, digest, rows):
    blind.blind_dir(ws).mkdir(exist_ok=True)
    blind.path(ws, digest).write_text(yaml.safe_dump({"digest": digest, "readings": rows}, allow_unicode=True), encoding="utf-8")


def test_blocks_only_foreign_letters_symbols_icons_and_brands_at_clear_strength():
    def r(kind, strength):
        return blind.Reading("c1", "وصف", "ö", kind, strength)

    assert config.BLIND_BLOCK == 2
    assert all(r(k, 2).blocked and r(k, 3).blocked and not r(k, 1).blocked for k in blind.BLOCKING)
    assert not any(r(k, 3).blocked for k in ("arabic", "object", "none"))  # قراءة عربية أو شيء مقصود: يحكم فيها الحَكَم
    assert "حرف غير عربي «ö» بقوة 3 من 3" in r("foreign_letter", 3).line()


def test_read_returns_none_then_readings_then_problems(tmp_path):
    ws = _ws(tmp_path)
    assert blind.read(ws, "d1", ["c1", "c2"]) is None and blind.rounds(ws) == 0
    _write(ws, "d1", {"c1": {"seen": "حرف o بنقطتين", "reads_as": "ö", "kind": "foreign_letter", "strength": 3},
                      "c2": {"seen": "كلمة عربية", "reads_as": "سمة", "kind": "arabic", "strength": 3}})
    got = blind.read(ws, "d1", ["c1", "c2"])
    assert not got.problems and [x.concept_id for x in got.blocked()] == ["c1"] and blind.rounds(ws) == 1
    _write(ws, "d2", {"c1": {"seen": "", "kind": "foreign_letter", "strength": 2},
                      "c2": {"seen": "شيء", "kind": "letter", "strength": 2},
                      "c3": {"seen": "شيء", "kind": "none", "strength": 7}})
    bad = blind.read(ws, "d2", ["c1", "c2", "c3", "c4"])
    assert len(bad.problems) == 4 and not bad.readings  # seen فارغة، kind مجهول، قوة خارج المدى، مفهوم بلا قراءة
    blind.path(ws, "d3").write_text("readings: [", encoding="utf-8")
    assert "غير صالح" in blind.read(ws, "d3", ["c1"]).problems[0]


def test_archive_moves_readings_so_next_cycle_starts_at_zero(tmp_path):
    ws = _ws(tmp_path)
    blind.archive(ws, "owner")  # لا شيء يُؤرشف: لا مجلد فارغ
    assert not (ws.work / "history").exists()
    _write(ws, "d1", {"c1": {"seen": "س", "kind": "none", "strength": 0}})
    blind.archive(ws, "owner")
    assert blind.rounds(ws) == 0 and (ws.work / "history" / "blind-owner-1" / "d1.yaml").is_file()


def test_request_is_blind_no_name_no_idea_only_images(tmp_path):
    ws = _ws(tmp_path)
    blind.write_request(ws, ["c1", "c2"], "abc", ["لا قراءة للمفهوم c2"])
    req = (ws.work / blind.REQUEST).read_text(encoding="utf-8")
    b = brief_from_dict(BRIEF, source="b.yaml")
    assert b.name_ar not in req and b.purpose not in req and "concepts.yaml" not in req
    assert "work/blind/abc.yaml" in req and "foreign_letter" in req and "لا قراءة للمفهوم c2" in req
    assert str(ws.render_dir / "c1" / "256.png") in req and str(ws.render_dir / "c2" / "blurred.png") in req
