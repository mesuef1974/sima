"""مدخل الاعتماد الخارجي: علامة واتجاه اعتمدهما المالك خارج خط الرسم يدخلان الخط بلا رسم ولا حَكَم، وبوابتا الاتجاه
والدليل تبقيان له. مصيّر زائف ومشكّل حقيقي بخطوط المشروع."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from sima.adapters.font_shaper import HarfBuzzShaper
from sima.domain import NameStatus, brief_from_dict
from sima.domain.brief import load_brief
from sima.domain.identity import Gate
from sima.services import adopt
from sima.services.identity_protocol import digest, directions_digest, ledger, read_directions, strategy_path
from sima.services.inbox import owner_inbox
from sima.services.ledger import Ledger
from sima.services.namecheck import record_name_check
from sima.services.pipeline import AWAIT_MODEL, AWAIT_OWNER, Pipeline
from sima.services.shaping import ShapingService
from sima.services.workspace import open_workspace

from .fakes import FakeRenderer, rect_svg
from .test_domain_ledger_workspace import BRIEF
from .test_identity import AWRAQ, STRATEGY

WORD = rect_svg(20, 96, 216, 64).replace("#000000", "#2A2622")  # بلون الحبر كما سلّمه المصمّم
MARK = rect_svg(48, 48, 160, 160).replace("#000000", "#2A2622")
MOTIF = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect x="4" y="4" width="10" height="10" fill="#000000"/>'
         '<rect data-tone="accent" x="30" y="30" width="8" height="8" fill="#000000"/></svg>')
IDENTITY = {"scope": "core", "palette_policy": "new"}


def _sha(svg: str) -> str:
    return hashlib.sha256(svg.encode()).hexdigest()


PINS = {"wordmark.svg": _sha(WORD), "mark.svg": _sha(MARK), "motif.svg": _sha(MOTIF)}


def _manifest(**over) -> dict:
    return {
        "sha256": dict(PINS),
        "concept": {"name": "الكلمة المعتمدة", "sentence": "خط واحد متصل والكسرة ضربته المستقيمة", "construction": "بناء متجه"},
        "wordmark": "wordmark.svg", "mark": "mark.svg", "motif": "motif.svg", "min_mark_px": 24,
        "owner": {"date": "2026-11-12", "words": "اعتمد 02"}, "strategy_from": "v1", "name_check_from": "v1",
        "direction": {"name": "حُكم مطبوع", "idea": "إيقاع تحريري حاسم", "colors": dict(AWRAQ), "accent_informational": False,
                      "type": {"heading": {"font": "Cairo[slnt,wght].ttf", "weight": 700},
                               "body": {"font": "Cairo[slnt,wght].ttf", "weight": 400}, "numerals": "latn"},
                      "motif": {"rule": "في الخلفيات الهادئة لا خلف النص الصغير"}, "radius": 0},
        **over,
    }


@pytest.fixture
def project(tmp_path: Path):
    """موجزان للمشروع نفسه: قديم بلا اعتماد أنتج v1 (منصة معتمدة واسم متحقق)، وجديد يشير إلى بيان الاعتماد."""
    briefs = tmp_path / "briefs"
    assets = briefs / "adopt" / "demo"
    assets.mkdir(parents=True)
    for name, svg in (("wordmark.svg", WORD), ("mark.svg", MARK), ("motif.svg", MOTIF)):
        (assets / name).write_text(svg, encoding="utf-8")
    (assets / "adopt.yaml").write_text(yaml.safe_dump(_manifest(), allow_unicode=True), encoding="utf-8")
    old = brief_from_dict({**BRIEF, "identity": IDENTITY}, source=str(briefs / "demo.yaml"))
    v1 = open_workspace(tmp_path / "out", old)
    (v1.work / "identity").mkdir(parents=True)
    strategy_path(v1).write_text(STRATEGY, encoding="utf-8")
    ledger(v1).record(Gate.STRATEGY, digest([strategy_path(v1)]), "approved", reason="موافق")
    record_name_check(v1, old, NameStatus.CLEAR, ["WIPO"], "")
    (briefs / "demo.yaml").write_text(yaml.safe_dump({**BRIEF, "identity": {**IDENTITY, "adopt": "adopt/demo/adopt.yaml"}},
                                                     allow_unicode=True), encoding="utf-8")
    r = FakeRenderer()
    pipe = Pipeline(r, ShapingService(HarfBuzzShaper()), None, tmp_path / "out", catalog=[])
    return tmp_path, assets, load_brief(briefs / "demo.yaml"), pipe


def test_adopt_field_changes_key_only_when_present():
    plain = brief_from_dict({**BRIEF, "identity": IDENTITY})
    adopted = brief_from_dict({**BRIEF, "identity": {**IDENTITY, "adopt": "adopt/demo/adopt.yaml"}})
    assert plain.identity.adopt is None and adopted.identity.adopt == "adopt/demo/adopt.yaml"
    assert plain.hash() != adopted.hash()
    frozen = Path(__file__).parent / "data" / "awraq_brief_v2.json"  # موجز أوراق v2 كما جُمّد في إصداره (out/math_papers/v2/brief.json)
    assert brief_from_dict(json.loads(frozen.read_text(encoding="utf-8"))).hash() == "a62970b5dfc8"  # مفتاح قائم لا يتغيّر


def test_cloud_permission_is_denied_by_default_and_stays_out_of_the_key():
    plain = brief_from_dict(BRIEF)
    assert not plain.cloud.model  # الغياب منع
    allowed = brief_from_dict({**BRIEF, "cloud": {"model": True}})
    assert allowed.cloud.model and allowed.hash() == plain.hash()  # إذن لا مُدخل تصميم: لا يفتح إصدارًا جديدًا
    for loose in (True, "yes", {"model": "true"}, {"model": 1}, ["model"]):  # خطأ كتابة لا يفتح الإذن
        assert not brief_from_dict({**BRIEF, "cloud": loose}).cloud.model
    root = Path(__file__).parents[1] / "briefs"
    assert load_brief(root / "sima.yaml").cloud.model and load_brief(root / "sima.yaml").hash() == "323626eb04cc"


def test_load_changes_colour_only_and_refuses_altered_asset(project):
    _, assets, brief, _ = project
    a = adopt.load(brief)
    assert "#2A2622" not in a.wordmark and 'id="wordmark"' in a.wordmark and 'width="216"' in a.wordmark
    assert "#2A2622" not in a.mark and a.direction["id"] == "d1" and a.direction["motif"]["file"] == "motifs/d1.svg"
    # البصمة إلزامية لكل أصل: أصل بلا بصمة يُرفض، والرسالة تعطي بصمته ليُثبَّت
    unpinned = _manifest(sha256={k: v for k, v in PINS.items() if k != "motif.svg"})
    (assets / "adopt.yaml").write_text(yaml.safe_dump(unpinned, allow_unicode=True), encoding="utf-8")
    with pytest.raises(adopt.AdoptError, match=f"motif.svg: بلا بصمة.*{PINS['motif.svg']}"):
        adopt.load(brief)
    # البصمة للمحتوى لا لملف البيان: كلمات المالك وتعليق لا يغيّرانها
    reworded = _manifest(owner={"date": "2026-11-12", "words": "اعتمد 02 كما هو"})
    (assets / "adopt.yaml").write_text("# تعليق\n" + yaml.safe_dump(reworded, allow_unicode=True), encoding="utf-8")
    assert adopt.load(brief).digest == a.digest
    (assets / "mark.svg").write_bytes(MARK.replace(">", ">\r\n").encode())  # نهايات أسطر Windows لا تُعدّ تعديلًا
    crlf = _manifest(sha256={**PINS, "mark.svg": _sha(MARK.replace(">", ">\n"))})
    (assets / "adopt.yaml").write_text(yaml.safe_dump(crlf, allow_unicode=True), encoding="utf-8")
    assert adopt.load(brief).mark
    (assets / "mark.svg").write_text(MARK.replace('width="160"', 'width="150"'), encoding="utf-8")
    with pytest.raises(adopt.AdoptError, match="لا يطابق البصمة"):
        adopt.load(brief)
    (assets / "mark.svg").write_text(MARK, encoding="utf-8")
    # حدّ أدنى معلن فوق حجم الترويسة مقبول حتى 192، وما فوقه ليس علامة
    (assets / "adopt.yaml").write_text(yaml.safe_dump(_manifest(min_mark_px=160), allow_unicode=True), encoding="utf-8")
    assert adopt.load(brief).min_mark_px == 160
    (assets / "adopt.yaml").write_text(yaml.safe_dump(_manifest(min_mark_px=400), allow_unicode=True), encoding="utf-8")
    with pytest.raises(adopt.AdoptError, match="بين 16 و320"):
        adopt.load(brief)
    (assets / "adopt.yaml").write_text(yaml.safe_dump(_manifest(owner={}), allow_unicode=True), encoding="utf-8")
    with pytest.raises(adopt.AdoptError, match="كلمات المالك"):
        adopt.load(brief)


def test_adopted_mark_reaches_owner_gates_without_drawing(project):
    tmp, _, brief, pipe = project
    out = pipe.run(brief)
    ws = out.workspace
    assert ws.version == 2 and out.code == AWAIT_OWNER and "الاتجاه المعتمد" in out.message, out.message
    assert not list(ws.work.glob("REQUEST-*.md"))  # لا طلب للنموذج: لا رسم ولا حَكَم ولا اتجاهات
    approved = Ledger(ws.ledger_path).approved()
    assert approved.concept_id == "a1" and "اعتمد 02" in approved.reason
    assert ledger(ws).latest(Gate.STRATEGY, digest([strategy_path(ws)])).reason.startswith("منقول من v1")
    dirs, problems = read_directions(ws)
    assert [d.id for d in dirs] == ["d1"] and not problems
    small = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))["a1-small"]
    assert small["metrics"]["base_size"] == 24  # يُفحص الرمز عند حدّه المعلن لا عند 16
    # البوابة للمالك في المنصة باتجاه واحد، ولا شيء اعتُمد عنه
    [item] = [i for i in owner_inbox(tmp / "out") if i.get("version") == 2]
    assert item["gate"] == "directions" and [o["id"] for o in item["options"]] == ["d1"]
    assert not ws.done("package")
    assert pipe.run(brief).message == out.message  # إعادة التشغيل لا تغيّر شيئًا

    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    pkg = ws.package_dir
    lockup = (pkg / "demo-lockup.svg").read_text(encoding="utf-8")
    assert AWRAQ["ink"] in lockup and AWRAQ["brand"] not in lockup  # الكلمة بلون الحبر
    assert AWRAQ["brand"] in (pkg / "demo-mark.svg").read_text(encoding="utf-8")
    usage = (pkg / "USAGE.md").read_text(encoding="utf-8")
    assert "الحد الأدنى للرمز وحده 24 بكسل" in usage and "بعلم المالك" in usage
    assert (pkg / "identity" / "brand-book.html").is_file() and not ws.done("identity")  # الدليل ينتظر المالك
    # لافتة التقدم لا تنتظر نقدًا ولا معاينة لعلامة لم تُرسم في الخط، ولا تنسب رسمها إلى النموذج
    from sima.services.timeline import timeline

    t = timeline(ws.root)
    keys = [s["key"] for s in t["progress"]["steps"]]
    assert "critique" not in keys and "preview" not in keys and t["progress"]["current"] == "identity"
    assert not any("رسم النموذج" in e["text"] for e in t["events"])
    # طلب تعديل هو سؤال: ينتظر النموذج بلا بطاقة، فإن أجاب ولم يتغيّر الدليل عادت البطاقة إلى المالك بجوابه ولا يعلق الإصدار
    book_dg = digest([pkg / "identity" / "brand-book.html"])
    asked = ledger(ws).record(Gate.BOOK, book_dg, "revise", reason="لماذا اتجاه واحد؟")
    assert pipe.run(brief).code == AWAIT_MODEL and (ws.work / "REQUEST-revise.md").is_file()
    assert not [i for i in owner_inbox(tmp / "out") if i.get("version") == 2]
    call = {"at": asked.at, "request": "REQUEST-revise.md", "ok": True, "summary": "الاتجاه واحد لأنه معتمد من خارج الخط."}
    (ws.root / "model_calls.jsonl").write_text(json.dumps(call, ensure_ascii=False) + "\n", encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "جواب الخط" in out.message, out.message
    [item] = [i for i in owner_inbox(tmp / "out") if i.get("version") == 2]
    assert item["gate"] == "book" and item["digest"] == book_dg
    assert item["reply"] == {"note": "لماذا اتجاه واحد؟", "text": "الاتجاه واحد لأنه معتمد من خارج الخط."}
    ledger(ws).record(Gate.BOOK, digest([pkg / "identity" / "brand-book.html"]), "approved")
    assert pipe.run(brief).code == 0
    t = timeline(ws.root)
    assert t["closed"] and t["progress"]["current"] == "deliver" and "بقي تسليمه" in t["now"]["text"]


def test_manifest_change_reopens_direction_gate_until_packaged(project):
    _, assets, brief, pipe = project
    ws = pipe.run(brief).workspace
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    changed = _manifest()
    changed["direction"]["colors"]["info"] = "#34566A"
    (assets / "adopt.yaml").write_text(yaml.safe_dump(changed, allow_unicode=True), encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "الاتجاه المعتمد" in out.message  # القرار مربوط بالمحتوى: يعود للمالك
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    assert "دليل الهوية" in pipe.run(brief).message
    # إصدار بُني قبل بصمة المحتوى يحمل بصمة ملف البيان: ما دام ما فيه هو ما يكتبه البيان الآن فلا يُطلب له إصدار جديد
    marker = ws.marker(adopt.MARKER)
    old = json.loads(marker.read_text(encoding="utf-8"))
    marker.write_text(json.dumps({**old, "digest": "9286ae39a7d5937f"}), encoding="utf-8")
    assert "دليل الهوية" in pipe.run(brief).message
    assert json.loads(marker.read_text(encoding="utf-8"))["digest"] == "9286ae39a7d5937f"  # الإصدار المبني لا يُمسّ
    (assets / "adopt.yaml").write_text(yaml.safe_dump(_manifest(min_mark_px=32), allow_unicode=True), encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == 1 and "--new-version" in out.message


def test_stroke_wordmark_takes_ink_in_lockup():
    from sima.services.export import _wordmark_ink

    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><g id="wordmark"><path d="M1 1 L9 9" fill="none" stroke="#8C3542"/>'
           '<circle cx="5" cy="5" r="1" fill="#8C3542"/></g><path d="M0 0 L1 1" stroke="#8C3542"/></svg>')
    out = _wordmark_ink(svg, "#8C3542", "#332B31")
    assert out.count("#332B31") == 2 and out.count("#8C3542") == 1 and 'fill="none"' in out


def test_wordmark_is_audited_at_its_declared_width_and_stroke(project):
    """«مسك» v9: الشعار الكامل كان يُفحص عند 96 بسماكة الأيقونة فيوقف الخط؛ يُفحص عند حدّه المعلن وسماكته، والرمز عند حدّه."""
    _, assets, brief, pipe = project
    (assets / "adopt.yaml").write_text(yaml.safe_dump(
        _manifest(min_wordmark_px=300, min_wordmark_stroke_px=1.0), allow_unicode=True), encoding="utf-8")
    ws = pipe.run(brief).workspace
    audit = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
    assert audit["a1"]["metrics"]["base_size"] == 300 and audit["a1-small"]["metrics"]["base_size"] == 24


def test_swapping_the_adopted_mark_rebuilds_the_direction_board(project):
    """«مسك» v9: بُدّلت الأيقونة في البيان وبقيت لوحة الاتجاه على القديمة. بصمة البوابة لا تتغيّر (ب8)، واللوحة تُبنى."""
    _, assets, brief, pipe = project
    ws = pipe.run(brief).workspace
    before, board = ws.read_marker("directions_board"), (ws.root / "directions.html").stat().st_mtime_ns
    other = rect_svg(40, 40, 176, 176).replace("#000000", "#2A2622")
    (assets / "mark.svg").write_text(other, encoding="utf-8")
    (assets / "adopt.yaml").write_text(yaml.safe_dump(
        _manifest(sha256={**PINS, "mark.svg": _sha(other)}), allow_unicode=True), encoding="utf-8")
    out = pipe.run(brief)
    after = ws.read_marker("directions_board")
    assert after["digest"] == before["digest"] == directions_digest(ws) and after["mark"] != before["mark"]
    assert (ws.root / "directions.html").stat().st_mtime_ns != board and "الاتجاه المعتمد" in out.message
