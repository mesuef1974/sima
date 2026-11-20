"""مسار المصمّم الخارجي: الخط يكتب نص الطلب وينتظر الاستلام، المالك يختار سكتشًا واحدًا، والمتجه المستلم يدخل بيانَ اعتماد
ببصماته؛ وبعد السكتش لا يعود الخط إليه إلا بتحقق الاسم ثم الدليل. لا اتصال شبكي ولا نموذج في هذه الاختبارات."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from sima.adapters.font_shaper import HarfBuzzShaper
from sima.cli import build_parser
from sima.domain import NameStatus, brief_from_dict
from sima.domain.brief import load_brief
from sima.domain.identity import Gate
from sima.services import designer
from sima.services.board import safe_out_path
from sima.services.identity_protocol import digest, directions_digest, directions_path, idir, ledger, strategy_path
from sima.services.inbox import InboxError, choose_sketch, owner_inbox
from sima.services.ledger import Ledger
from sima.services.namecheck import record_name_check
from sima.services.pipeline import AWAIT_DESIGNER, AWAIT_MODEL, AWAIT_OWNER, Pipeline
from sima.services.shaping import ShapingService
from sima.services.timeline import timeline

from .fakes import FakeRenderer
from .test_adopt import IDENTITY, MARK, MOTIF, WORD, _manifest
from .test_domain_ledger_workspace import BRIEF
from .test_identity import STRATEGY

TRACK = {**IDENTITY, "designer": "external"}


@pytest.fixture
def track(tmp_path: Path):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "demo.yaml").write_text(yaml.safe_dump({**BRIEF, "identity": TRACK}, allow_unicode=True), encoding="utf-8")
    pipe = Pipeline(FakeRenderer(), ShapingService(HarfBuzzShaper()), None, tmp_path / "out", catalog=[])
    return tmp_path, load_brief(briefs / "demo.yaml"), pipe


def _sheet(ws, n: int = 16, picks=(3, 7), image: bytes = b"\xff\xd8\xff-sheet") -> None:
    d = designer.ddir(ws)
    d.mkdir(parents=True, exist_ok=True)
    (d / "sketches.jpg").write_bytes(image)
    rows = [{"id": i, "idea": f"فكرة السكتش {i}"} for i in range(1, n + 1)]
    designer.sheet_path(ws).write_text(yaml.safe_dump({"image": "sketches.jpg", "source": "صفحة تجربة", "sketches": rows, "picks": list(picks)},
                                                      allow_unicode=True), encoding="utf-8")


def _delivery(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, svg in (("logo.svg", WORD), ("icon.svg", MARK), ("motif.svg", MOTIF)):
        (folder / name).write_text(svg, encoding="utf-8")
    (folder / "direction.yaml").write_text(yaml.safe_dump(_manifest()["direction"], allow_unicode=True), encoding="utf-8")
    (folder / "concept.yaml").write_text(yaml.safe_dump({"name": "وتد مائل", "sentence": "خط يثبت ما حوله", "construction": "شبكة 8"},
                                                        allow_unicode=True), encoding="utf-8")
    return folder


def test_designer_field_changes_key_only_when_present():
    plain, ext = brief_from_dict({**BRIEF, "identity": IDENTITY}), brief_from_dict({**BRIEF, "identity": TRACK})
    assert not designer.enabled(plain) and designer.enabled(ext) and plain.hash() != ext.hash()
    with pytest.raises(ValueError, match="external"):
        brief_from_dict({**BRIEF, "identity": {**IDENTITY, "designer": "chatgpt"}})


def test_sketches_then_owner_pick_then_vector_then_only_the_book_gate(track):
    tmp, brief, pipe = track
    out_dir = tmp / "out"
    out = pipe.run(brief)
    ws = out.workspace
    assert out.code == AWAIT_DESIGNER and "صفحة السكتشات" in out.message
    assert [p.name for p in ws.work.glob("REQUEST-*.md")] == [designer.REQ_SKETCHES]  # لا عينات طابع ولا مصغّرات ولا نموذج
    req = (ws.work / designer.REQ_SKETCHES).read_text(encoding="utf-8")
    sent = req.split(designer.SENT, 1)[1]
    assert brief.name_ar in sent and "16 سكتشًا" in sent and "من 1 إلى 16" in sent and "الاختيار لصاحب العلامة" in sent
    assert all(a in sent for a in brief.taste.avoid) and str(tmp) not in sent  # الممنوعات تصل، ولا مسار محلي يخرج
    assert owner_inbox(out_dir) == [] and timeline(ws.root)["now"]["who"] == "designer"

    _sheet(ws, n=3)  # استلام ناقص لا يُعرض على المالك
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "من 6 إلى 24" in out.message and owner_inbox(out_dir) == []
    _sheet(ws)
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "اختر سكتشًا" in out.message
    [item] = owner_inbox(out_dir)
    assert item["kind"] == "sketches" and item["title"] == "اختيار السكتش" and len(item["sketches"]) == 16
    assert [s["id"] for s in item["sketches"] if s["pick"]] == [3, 7] and "الدليل وحده" in item["after"]
    assert safe_out_path(out_dir, item["img"]) is not None
    key = item["key"]
    with pytest.raises(InboxError, match="تغيّرت صفحة السكتشات"):
        choose_sketch(out_dir, "demo", 1, key, "old", 5, "")
    with pytest.raises(InboxError, match="من 1 إلى 16"):
        choose_sketch(out_dir, "demo", 1, key, item["digest"], 99, "")
    assert "السكتش 5" in choose_sketch(out_dir, "demo", 1, key, item["digest"], 5, "احفظ الميل")
    assert owner_inbox(out_dir) == []

    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "بناء السكتش 5 متجهًا" in out.message
    sent = (ws.work / designer.REQ_VECTOR).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert "السكتش رقم 5" in sent and "فكرة السكتش 5" in sent and "احفظ الميل" in sent and "Cairo[slnt,wght].ttf" in sent
    assert "انقل الفكرة والبناء كما هما" in sent and "logo.svg" in sent and "direction.yaml" in sent
    folder = _delivery(tmp / "delivery")
    designer.write_manifest(ws, 4, folder)  # تسليم لسكتش غير المختار لا يدخل
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "مبني للسكتش 4" in out.message and not ws.done("adopted")
    designer.write_manifest(ws, 5, folder)

    out = pipe.run(brief)  # المنصة الاستراتيجية يكتبها نموذج الخط كعادته
    assert out.code == AWAIT_MODEL and "المنصة الاستراتيجية" in out.message and ws.done("adopted")
    approved = Ledger(ws.ledger_path).approved()
    assert approved.concept_id == "a1" and "اختار السكتش 5 في منصة سِمة" in approved.reason and "احفظ الميل" in approved.reason
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    out = pipe.run(brief)  # تمرّ المنصة بالقاعدة، ويبقى تحقق الاسم للمالك
    assert out.code == AWAIT_OWNER and owner_inbox(out_dir)[0]["kind"] == "name_check"
    assert ledger(ws).latest(Gate.STRATEGY, digest([strategy_path(ws)])).reason == designer.RULE
    record_name_check(ws, brief, NameStatus.CLEAR, ["WIPO"], "")
    out = pipe.run(brief)  # يمرّ الاتجاه بالقاعدة، والبوابة الوحيدة الدليل
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    dec = ledger(ws).latest(Gate.DIRECTIONS, directions_digest(ws))
    assert dec.option == "d1" and dec.reason == designer.RULE
    [item] = owner_inbox(out_dir)
    assert item["kind"] == "identity" and item["gate"] == "book"
    t = timeline(ws.root)
    ruled = [e for e in t["events"] if "بقاعدة مسار المصمّم الخارجي" in e["text"]]
    assert len(ruled) == 2 and all(e["who"] == "script" for e in ruled)  # لا تُنسب إلى المالك
    owned = [e["text"] for e in t["events"] if e["who"] == "owner"]
    assert not any("المنصة الاستراتيجية" in x or "اتجاه الهوية" in x for x in owned)  # قراره المسجّل اختيار السكتش وحده
    assert any("المفهوم a1" in x and "اختار السكتش 5" in x for x in owned)
    assert not ws.done("identity")
    ledger(ws).record(Gate.BOOK, digest([ws.package_dir / "identity" / "brand-book.html"]), "approved")
    assert pipe.run(brief).code == 0


def test_new_sheet_reopens_the_gate_and_incomplete_delivery_is_refused(track):
    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, 2, "", sheet.digest)
    assert designer.current(ws, sheet)["sketch"] == 2
    _sheet(ws, image=b"\xff\xd8\xff-second")  # صفحة جديدة: الاختيار السابق لا يسري عليها
    again, _ = designer.read_sheet(ws)
    assert again.digest != sheet.digest and designer.current(ws, again) is None
    assert pipe.run(brief).code == AWAIT_OWNER and owner_inbox(tmp / "out")[0]["kind"] == "sketches"
    folder = _delivery(tmp / "delivery")
    (folder / "icon.svg").unlink()
    with pytest.raises(designer.DesignerError, match=r"icon\.svg"):
        designer.write_manifest(ws, 2, folder)
    designer.sheet_path(ws).write_text("sketches: [{id: 1, idea: أ}, {id: 3, idea: ب}]\nimage: ../x.jpg\n", encoding="utf-8")
    none, problems = designer.read_sheet(ws)
    assert none is None and len(problems) == 2


def test_rejected_delivery_returns_to_the_designer_without_asking_the_owner(track, monkeypatch):
    """ما يردّه الفحص يعود إلى المصمّم بسببه كما قيس: طلب تصحيح لا سؤال للمالك، بعدد جولات محدود."""
    from types import SimpleNamespace

    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, 5, "", sheet.digest)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    why = "أصغر سماكة عند 16 بكسل = 0.97 أقل من 1.5"

    def rejected(self, ws, brief, concepts, svgs, smalls, small_base=16, min_stroke=None, **_):
        ok, bad = SimpleNamespace(passed=True, findings=[]), SimpleNamespace(passed=False, findings=[why])
        return {concepts[0].id: ok, concepts[0].id + "-small": bad}

    monkeypatch.setattr(Pipeline, "_stage_render", rejected)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "الجولة 1" in out.message and why in out.message
    sent = (ws.work / designer.REQ_FIX).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert f"`icon.svg`: {why}" in sent and "logo.svg" not in sent and "لا تغيّر الفكرة" in sent and str(tmp) not in sent
    from sima.services.workshop import workshop

    [shown] = workshop(tmp / "out", [])  # المتجه المستلم يُرى في الورشة للاطلاع قبل الدليل
    assert shown["designer"] and [c["id"] for c in shown["concepts"]] == ["a1"] and shown["stage"] == "تصحيح ما ردّه الفحص"
    ws.mark_done("identity_build", {})
    assert workshop(tmp / "out", []) == []
    ws.marker("identity_build").unlink()
    kinds = [i["kind"] for i in owner_inbox(tmp / "out")]  # لا بطاقة قرار عن الردّ؛ تحقق الاسم خطوته الباقية كعادته
    assert kinds == ["name_check"] and timeline(ws.root)["now"]["who"] == "designer"
    build = designer.build(ws)
    assert pipe.run(brief).code == AWAIT_DESIGNER and designer.fix_round(ws, "x", build) == 2  # التسليم نفسه لا يُعدّ جولة ثانية
    ws.mark_done(designer.FIX_MARKER, {"build": build, "digests": ["a", "b", "c"]})
    out = pipe.run(brief)  # تسليم رابع مردود: يُعرض الحال على المالك ولا يدور (ب4: كان خروجًا بالرمز 1 بلا بطاقة)
    assert out.code == AWAIT_OWNER and "بعد 3 جولات" in out.message


def test_designer_command_takes_a_pick_or_an_intake_folder():
    p = build_parser()
    assert p.parse_args(["designer", "b.yaml", "--pick", "3", "--note", "م"]).pick == 3
    assert p.parse_args(["designer", "b.yaml", "--intake", "d"]).intake == "d"
    with pytest.raises(SystemExit):
        p.parse_args(["designer", "b.yaml"])


def test_owner_declared_minimum_overrides_the_delivery_and_checks_the_logo_at_it(track):
    """المالك يقبل علامة رفيعة كما هي فوق حجم معلوم (قراره 2026-11-13 على «أوراق»): حدّه المعلن عند الاستلام يغلب ما في
    concept.yaml، والكلمة والرمز كلاهما يُفحصان عنده، وحدّ خارج المدى خطأ المالك فلا يُكتب بيان ولا يعود شيء إلى المصمّم."""
    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, 5, "", sheet.digest)
    folder = _delivery(tmp / "delivery")
    with pytest.raises(designer.DesignerError, match="بين 16 و320"):
        designer.write_manifest(ws, 5, folder, 400)
    assert not designer.manifest_path(ws).is_file()
    designer.write_manifest(ws, 5, folder, 160)
    assert yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))["min_mark_px"] == 160
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    pipe.run(brief)
    audit = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
    assert audit["a1"]["metrics"]["base_size"] == 160 and audit["a1-small"]["metrics"]["base_size"] == 160
    assert build_parser().parse_args(["designer", "b.yaml", "--intake", "d", "--min-mark-px", "160"]).min_mark_px == 160
    assert build_parser().parse_args(["designer", "b.yaml", "--intake", "d"]).min_mark_px is None


def test_rejected_direction_returns_to_the_designer_too(track):
    """اتجاه المصمّم الذي يردّه الفحص يعود إليه بسببه كما قيس، لا إلى المالك «يُصلح في بيان الاعتماد»؛ وتصحيحه يمضي إلى الدليل."""
    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, 5, "", sheet.digest)
    folder = _delivery(tmp / "delivery")
    good = (folder / "direction.yaml").read_text(encoding="utf-8")
    pale = yaml.safe_load(good)
    pale["colors"]["ink"] = "#B0AAA2"  # حبر باهت على الورق: النص لا يُقرأ (لون العلامة الباهت صار له دور نص أغمق، 2026-11-18)
    (folder / "direction.yaml").write_text(yaml.safe_dump(pale, allow_unicode=True), encoding="utf-8")
    designer.write_manifest(ws, 5, folder)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    pipe.run(brief)
    record_name_check(ws, brief, NameStatus.CLEAR, ["WIPO"], "")
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "الجولة 1" in out.message and "النص على الخلفية" in out.message
    sent = (ws.work / designer.REQ_FIX).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert "`direction.yaml`: تباين النص على الخلفية" in sent and "(الحد 4.5)" in sent and "هو الملزم" in sent
    assert "أصغر سماكة" not in sent and "icon.svg" not in sent and str(tmp) not in sent
    assert owner_inbox(tmp / "out") == [] and timeline(ws.root)["now"]["who"] == "designer"  # لا يُسأل المالك عن الردّ
    (folder / "direction.yaml").write_text(good, encoding="utf-8")
    designer.write_manifest(ws, 5, folder)
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message


def test_requests_name_the_mark_by_its_short_name_when_the_full_name_is_a_description():
    """الشعار يحمل الاسم المختصر («أوراق») لا الاسم الوصفي الكامل؛ والتشكيل وحده لا يجعلهما اسمين («وَتَد»)."""
    long = brief_from_dict({**BRIEF, "name_ar": "مولّد أوراق الرياضيات", "name_short": "أوراق", "identity": TRACK})
    sent = designer.sketch_prompt(long)
    assert "علامة اسمها «أوراق» (اسمها الوصفي الكامل: مولّد أوراق الرياضيات)" in sent and designer.mark_name(long) == "أوراق"
    same = brief_from_dict({**BRIEF, "name_ar": "وَتَد", "name_short": "وتد", "identity": TRACK})
    assert "علامة اسمها «وَتَد»." in designer.sketch_prompt(same) and designer.mark_name(same) == "وَتَد"


def test_owner_rejects_the_sheet_with_a_reason_and_it_returns_to_the_designer(track):
    """رفض المالك الصفحة كلها بسبب: لا تبقى بطاقتها، ويُكتب طلب صفحة جديدة بسببه بنصّه، والمرفوضة تُحفظ؛ صفحة جديدة تفتح البوابة."""
    from sima.services.inbox import reject_sketches

    tmp, brief, pipe = track
    out_dir = tmp / "out"
    ws = pipe.run(brief).workspace
    _sheet(ws)
    assert pipe.run(brief).code == AWAIT_OWNER
    [item] = owner_inbox(out_dir)
    with pytest.raises(InboxError, match="سبب الرفض"):
        reject_sketches(out_dir, "demo", 1, item["key"], item["digest"], " ")
    with pytest.raises(InboxError, match="تغيّرت صفحة السكتشات"):
        reject_sketches(out_dir, "demo", 1, item["key"], "old", "كلها أوراق متراكبة")
    assert "رُفضت صفحة السكتشات" in reject_sketches(out_dir, "demo", 1, item["key"], item["digest"], "كلها أوراق متراكبة، أريد رمزًا واحدًا")
    assert owner_inbox(out_dir) == []
    kept = designer.ddir(ws) / designer.REJECTED_DIR / item["digest"]
    assert (kept / "sketches.jpg").is_file() and (kept / "sketches.yaml").is_file()

    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "صفحة سكتشات جديدة" in out.message and "أريد رمزًا واحدًا" in out.message
    sent = (ws.work / designer.REQ_SKETCHES).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert "سببه بنصّه: «كلها أوراق متراكبة، أريد رمزًا واحدًا»" in sent and "لا تُعد سكتشًا من المرفوض" in sent
    assert "16 سكتشًا" in sent and str(tmp) not in sent and timeline(ws.root)["now"]["who"] == "designer"
    assert pipe.run(brief).code == AWAIT_DESIGNER and owner_inbox(out_dir) == []  # الصفحة المرفوضة لا تعود إلى المالك

    _sheet(ws, image=b"\xff\xd8\xff-sheet-2")  # صفحة جديدة من المصمّم: تفتح البوابة من جديد
    assert pipe.run(brief).code == AWAIT_OWNER
    [again] = owner_inbox(out_dir)
    assert again["kind"] == "sketches" and again["digest"] != item["digest"]
    reject_sketches(out_dir, "demo", 1, again["key"], again["digest"], "ما زالت حرفية")
    pipe.run(brief)
    sent = (ws.work / designer.REQ_SKETCHES).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert "سببه بنصّه: «ما زالت حرفية»" in sent and "ورفض قبلها صفحات أخرى لهذه الأسباب: «كلها أوراق متراكبة، أريد رمزًا واحدًا»" in sent
    args = build_parser().parse_args(["designer", "b.yaml", "--reject", "--reason", "سبب"])
    assert args.reject and args.reason == "سبب" and args.pick is None


def test_product_explanation_enters_the_request_and_a_rejection_survives_the_new_version(track):
    """شرح المنتج (`product`) يدخل طلب المصمّم ويدخل المفتاح؛ وإن عُدّل الموجز بعد رفضٍ ففُتح إصدار جديد بقي سبب المالك في طلبه."""
    from sima.services.inbox import reject_sketches

    tmp, brief, pipe = track
    plain = brief_from_dict({**BRIEF, "identity": TRACK})
    told = brief_from_dict({**BRIEF, "identity": TRACK, "product": "منصة يفتحها المعلم\n  فيولّد ورقة بضغطة"})
    assert plain.product is None and plain.hash() == brief.hash() and told.hash() != plain.hash()  # الغياب لا يغيّر مفتاحًا قائمًا
    assert "المنتج بالتفصيل: منصة يفتحها المعلم فيولّد ورقة بضغطة" in designer.sketch_prompt(told)
    assert "المنتج بالتفصيل" not in designer.sketch_prompt(plain)

    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    [item] = owner_inbox(tmp / "out")
    reject_sketches(tmp / "out", "demo", 1, item["key"], item["digest"], "اشرح المنصة بشكل أوضح")
    out = pipe.run(told)  # الموجز عُدّل استجابةً للرفض: إصدار جديد، وسبب الرفض معه
    ws2 = out.workspace
    assert ws2.version == 2 and out.code == AWAIT_DESIGNER and designer.prior_rejections(ws2) and not designer.rejections(ws2)
    sent = (ws2.work / designer.REQ_SKETCHES).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert "سببه بنصّه: «اشرح المنصة بشكل أوضح»" in sent and "المنتج بالتفصيل: منصة يفتحها المعلم" in sent
    _sheet(ws2, image=b"\xff\xd8\xff-sheet-2")
    assert pipe.run(told).code == AWAIT_OWNER and owner_inbox(tmp / "out")[0]["version"] == 2
    assert designer.prior_rejections(ws) == []  # الإصدار الأول لا سابق له


def test_owner_asks_to_develop_a_sketch_and_gets_a_sheet_around_it_before_any_vector(track):
    """«طوّر هذا السكتش»: المالك يختار سكتشًا ويريد صفحة معالجات حوله قبل بنائه؛ يعود إلى المصمّم بطلبه بنصّه ولا يُكتب طلب متجه."""
    from sima.services import designer_box
    from sima.services.inbox import develop_sketch

    tmp, brief, pipe = track
    out_dir = tmp / "out"
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    [item] = owner_inbox(out_dir)
    with pytest.raises(InboxError, match="من 1 إلى 16"):
        develop_sketch(out_dir, "demo", 1, item["key"], item["digest"], 99, "")
    choose_sketch(out_dir, "demo", 1, item["key"], item["digest"], 14, "أريد تعديلات احترافية وسكتشات أخرى حول الفكرة")
    sheet, _ = designer.read_sheet(ws)
    designer.develop(ws, sheet, 14, "أريد تعديلات احترافية وسكتشات أخرى حول الفكرة", sheet.digest)  # طلب التطوير يعلو الاختيار السابق
    assert designer.current(ws, sheet) is None and designer.development(ws, sheet)["idea"] == "فكرة السكتش 14"
    assert owner_inbox(out_dir) == [] and (designer.ddir(ws) / designer.DEVELOPED_DIR / sheet.digest / "sketches.jpg").is_file()

    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "صفحة تطوير للسكتش 14" in out.message and not (ws.work / designer.REQ_VECTOR).is_file()
    req = (ws.work / designer.REQ_SKETCHES).read_text(encoding="utf-8")
    sent = req.split(designer.SENT, 1)[1]
    assert "تطوير السكتش 14" in req.splitlines()[0] and "السكتش رقم 14: «فكرة السكتش 14»" in sent
    assert "طلبه بنصّه: «أريد تعديلات احترافية وسكتشات أخرى حول الفكرة»" in sent and "كلها تطوير لهذه الفكرة نفسها" in sent
    assert "كل سكتش معالجة مختلفة للفكرة" in sent and "لا تنويع على جاره" not in sent and "رفض صفحة السكتشات" not in sent
    [box] = designer_box.outbox(out_dir)
    assert box["kind"] == "sketches" and box["text"] == sent.strip()

    _sheet(ws, n=3, image=b"\xff\xd8\xff-sheet-2")  # صفحة ناقصة: الطلب يبقى طلب تطوير بما ينقص
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "صفحة تطوير للسكتش 14" in out.message and "من 6 إلى 24" in out.message
    _sheet(ws, image=b"\xff\xd8\xff-sheet-2")  # صفحة المعالجات: تفتح البوابة من جديد، والاختيار منها يُبنى متجهًا
    assert pipe.run(brief).code == AWAIT_OWNER
    [again] = owner_inbox(out_dir)
    assert again["digest"] != item["digest"] and designer_box.outbox(out_dir) == []
    choose_sketch(out_dir, "demo", 1, again["key"], again["digest"], 2, "")
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "بناء السكتش 2 متجهًا" in out.message


def test_owner_returns_the_built_vector_and_the_same_sketch_goes_back_to_the_designer(track):
    """ردّ المتجه (قرار المالك 2026-11-13 على دليل «أوراق»): المبني لا يطابق السكتش المتفق عليه، فيعود السكتش نفسه إلى المصمّم
    بسبب المالك بنصّه، ولا يُسأل نموذج الخط عمّا لا يملكه؛ والتسليم الجديد يحلّ محلّ المردود في الإصدار نفسه ويُبنى الدليل عليه."""
    from sima.services import adopt, designer_box
    from sima.services.inbox import return_vector

    from .fakes import rect_svg

    tmp, brief, pipe = track
    out_dir = tmp / "out"
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    with pytest.raises(designer.DesignerError, match="يتبع استلامه"):  # لا اختيار ولا تسليم بعد
        designer.rebuild(ws, sheet, "ليس هذا الشعار")
    designer.record(ws, sheet, 11, "", sheet.digest)
    folder = _delivery(tmp / "delivery")
    designer.write_manifest(ws, 11, folder)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    pipe.run(brief)
    record_name_check(ws, brief, NameStatus.CLEAR, ["WIPO"], "")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message and ws.done("package")
    book = ws.package_dir / "identity" / "brand-book.html"
    first, built = digest([book]), designer.manifest_digest(ws)

    why = "ليس هذا الشعار الذي اتفقنا عليه راجع سكيتش 11"
    with pytest.raises(designer.DesignerError, match="سبب ردّ المتجه"):
        designer.rebuild(ws, sheet, " ")
    [card] = owner_inbox(out_dir)  # من بطاقة الدليل نفسها: ردّ الشعار غير «طلب تعديل»
    assert card["gate"] == "book" and card["designer_sketch"] == 11
    with pytest.raises(InboxError, match="سبب ردّ المتجه"):
        return_vector(out_dir, "demo", 1, card["key"], card["digest"], " ")
    with pytest.raises(InboxError, match="تغيّر ما عُرض"):
        return_vector(out_dir, "demo", 1, card["key"], "old", why)
    assert "رُدّ متجه السكتش 11" in return_vector(out_dir, "demo", 1, card["key"], card["digest"], why)
    with pytest.raises(designer.DesignerError, match="مردود من قبل"):
        designer.rebuild(ws, sheet, why)
    assert designer.current(ws, sheet)["sketch"] == 11 and designer.pending_rebuild(ws, sheet)["reason"] == why
    assert (designer.ddir(ws) / designer.REBUILT_DIR / built / "icon.svg").read_text(encoding="utf-8") == MARK

    out = pipe.run(brief)  # لا نموذج ولا بطاقة: الدور للمصمّم
    assert out.code == AWAIT_DESIGNER and "إعادة بناء السكتش 11" in out.message and why in out.message
    assert owner_inbox(out_dir) == [] and not (ws.work / "REQUEST-revise.md").is_file()
    sent = (ws.work / designer.REQ_VECTOR).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert sent.strip().startswith(f"صاحب العلامة ردّ المتجه الذي سلّمتَه لهذا السكتش. سببه بنصّه: «{why}».")
    assert "السكتش رقم 11" in sent and "مطابقًا لهيئته المرسومة" in sent and "الملفات الخمسة" in sent and str(tmp) not in sent
    [box] = designer_box.outbox(out_dir)
    assert box["kind"] == "vector" and box["text"] == sent.strip()
    assert pipe.run(brief).code == AWAIT_DESIGNER  # التسليم المردود نفسه لا يمضي

    (folder / "icon.svg").write_text(rect_svg(40, 40, 176, 176).replace("#000000", "#2A2622"), encoding="utf-8")
    designer.write_manifest(ws, 11, folder)  # التسليم الجديد: يحلّ محلّ المردود ولو بُنيت الحزمة
    assert designer.pending_rebuild(ws, sheet) is None and designer_box.outbox(out_dir) == []
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    assert digest([book]) != first and 'width="176"' in (ws.package_dir / "demo-mark.svg").read_text(encoding="utf-8")
    [item] = owner_inbox(out_dir)
    assert item["kind"] == "identity" and item["gate"] == "book"

    (folder / "icon.svg").write_text(rect_svg(44, 44, 168, 168).replace("#000000", "#2A2622"), encoding="utf-8")
    # تغيير ثالث بلا ردّ جديد من المالك: القاعدة كما هي، وتُفرض عند الاستلام فلا يدخل ما يعلّق الإصدار عند المصمّم (ب9: كان يدخل
    # ثم يحوّل الخط خطأ القاعدة إلى «ينتظر المصمّم» أبدًا)
    with pytest.raises(designer.DesignerError, match="بعد بناء الحزمة"):
        designer.write_manifest(ws, 11, folder)
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message
    data = yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))  # وبيان غُيّر في مكانه: خطأ القاعدة لا يذهب إلى المصمّم
    designer.manifest_path(ws).write_text(yaml.safe_dump({**data, "min_mark_px": 32}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(adopt.PackagedError):
        adopt.sync(ws, designer.adoption(ws, sheet, designer.current(ws, sheet)))
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "بعد بناء الحزمة" in out.message and designer_box.outbox(out_dir) == []
    args =build_parser().parse_args(["designer", "b.yaml", "--rebuild", "--reason", why])
    assert args.rebuild and args.reason == why


def test_waiting_for_the_designer_ends_the_platform_job_instead_of_looping_as_busy():
    """رمز «المشروع مقفل» لا يساوي أي رمز انتظار: كان 5 كرمز انتظار المصمّم، فظلّت المنصة تعيد تشغيل الخط كل خمس ثوانٍ."""
    import time

    from sima.adapters.pipeline_jobs import CODE_AR, PipelineJobs
    from sima.adapters.run_lock import BUSY

    assert BUSY not in (0, 1, AWAIT_MODEL, AWAIT_OWNER, AWAIT_DESIGNER) and AWAIT_DESIGNER in CODE_AR
    runs = []
    jobs = PipelineJobs(Path("."), runner=lambda b: runs.append(b) or (AWAIT_DESIGNER, "بانتظار المصمّم الخارجي"), settle=0)
    assert jobs.start("demo", Path("demo.yaml"))
    for _ in range(100):
        if jobs.snapshot()[0]["state"] != "running":
            break
        time.sleep(0.05)
    [job] = jobs.snapshot()
    assert job["state"] == "done" and job["code_ar"] == "بانتظار المصمّم الخارجي" and len(runs) == 1


def test_new_version_inherits_the_designer_mark_and_locks_it_with_the_name_from_the_heading_font(track):
    """«أوراق» v4: المصمّم سلّم الرمز بلا كتابة الاسم فخرج القفل رمزًا بلا كلمة. قرار المالك 2026-11-13: إصدار جديد يرث العلامة
    كما هي، والاسم يُشكَّل من خط عناوين الاتجاه. لا سكتشات جديدة ولا مصمّم ولا نموذج: يعود الخط إليه بالدليل وحده."""
    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, 5, "", sheet.digest)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    pipe.run(brief)
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    pipe.run(brief)
    record_name_check(ws, brief, NameStatus.CLEAR, ["WIPO"], "")
    assert pipe.run(brief).code == AWAIT_OWNER
    ledger(ws).record(Gate.BOOK, digest([ws.package_dir / "identity" / "brand-book.html"]), "approved")
    assert pipe.run(brief).code == 0 and ws.done("identity")
    old_lock = (ws.package_dir / "demo-lockup.svg").read_text(encoding="utf-8")
    assert 'id="symbol"' not in old_lock  # بلا الحقل: القفل هو ملف المصمّم نفسه

    plain = brief_from_dict({**BRIEF, "identity": TRACK})
    with pytest.raises(ValueError, match="heading"):
        brief_from_dict({**BRIEF, "identity": {**TRACK, "lockup_word": "serif"}})
    with pytest.raises(ValueError, match="من خارج الخط"):
        brief_from_dict({**BRIEF, "identity": {**IDENTITY, "lockup_word": "heading"}})
    (tmp / "briefs" / "demo.yaml").write_text(yaml.safe_dump(
        {**BRIEF, "identity": {**TRACK, "inherit_mark": "v1", "lockup_word": "heading"}}, allow_unicode=True), encoding="utf-8")
    brief2 = load_brief(tmp / "briefs" / "demo.yaml")
    assert brief2.hash() != brief.hash() and plain.hash() == brief.hash()  # غياب الحقل لا يغيّر مفاتيح الإصدارات القائمة
    ws.mark_done(designer.FIX_MARKER, {"build": designer.build(ws), "digests": ["a", "b", "c"]})

    out = pipe.run(brief2)
    ws2 = out.workspace
    assert ws2.version == 2 and out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    assert not ws2.done(designer.FIX_MARKER)  # عدّاد جولات التصحيح للبناء الجاري لا لسلفه (ب4)
    assert not list(ws2.work.glob("REQUEST-designer-*.md")) or designer.read_sheet(ws2)[0].digest == sheet.digest
    assert designer.current(ws2, designer.read_sheet(ws2)[0])["sketch"] == 5 and not ws2.done("identity")
    assert ledger(ws2).latest(Gate.DIRECTIONS, directions_digest(ws2)).reason == designer.RULE
    pkg = ws2.package_dir
    word = (pkg / "demo-wordmark.svg").read_text(encoding="utf-8")
    lock = (pkg / "demo-lockup.svg").read_text(encoding="utf-8")
    assert word != (ws.package_dir / "demo-wordmark.svg").read_text(encoding="utf-8") and word.count("<path") == 1  # كلمة مشكَّلة من الخط
    assert lock.count('id="wordmark"') == 1 and lock.index('id="symbol"') < lock.index('id="wordmark"')
    ink, symbol = brief2.palette.ink, lock.split('id="symbol"', 1)[1].split('id="wordmark"', 1)[0]
    assert f'fill="{ink}"' in lock.split('id="wordmark"', 1)[1] and ink not in symbol and "#000000" not in symbol  # الرمز بلون العلامة
    vue = (pkg / "BrandLockup.vue").read_text(encoding="utf-8")
    assert 'class="brand-lockup" :height="height"' in vue and "var(--color-mark-ink, " in vue and f"var(--color-ink, {ink})" in vue
    assert "<title>" not in vue and "height?: number" in vue
    # الرمز المعتمد كما هو: أيقونة الإصدار الجديد هي أيقونة السابق
    assert (pkg / "demo-mark-mono.svg").read_text(encoding="utf-8") == (ws.package_dir / "demo-mark-mono.svg").read_text(encoding="utf-8")
    assert json.loads((ws.root / "run.json").read_text(encoding="utf-8"))["closed"] and ws.done("identity")  # السابق لم يُمسّ
    book = digest([pkg / "identity" / "brand-book.html"])
    assert book != digest([ws.package_dir / "identity" / "brand-book.html"])  # دليل جديد ببصمته: قرار السابق لا يسري عليه
    ledger(ws2).record(Gate.BOOK, book, "approved")
    assert pipe.run(brief2).code == 0 and ws2.done("identity")


def test_three_directions_over_the_designer_mark_are_the_owners_choice_and_the_word_follows_it(track):
    """«أوراق» v5: المالك وجد اتجاهًا واحدًا في الدليل وطلب الثلاثة (قراره 2026-11-14). `identity.directions: three` يفتح بوابة
    الاتجاه له فوق العلامة المعتمدة كما هي: اتجاه التسليم أول الثلاثة ولا يُعدَّل، والنموذج يكتب الآخرَين، وقاعدة المسار
    لا تقرّر عنه؛ وكلمة القفل تتبع خط عناوين الاتجاه الذي يختاره."""
    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, 5, "", sheet.digest)
    designer.write_manifest(ws, 5, _delivery(tmp / "delivery"))
    pipe.run(brief)
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    pipe.run(brief)
    record_name_check(ws, brief, NameStatus.CLEAR, ["WIPO"], "")
    assert pipe.run(brief).code == AWAIT_OWNER  # v1 عند الدليل باتجاه واحد مرّ بقاعدة المسار

    with pytest.raises(ValueError, match="three"):
        brief_from_dict({**BRIEF, "identity": {**TRACK, "directions": "five"}})
    with pytest.raises(ValueError, match="من خارج الخط"):
        brief_from_dict({**BRIEF, "identity": {**IDENTITY, "directions": "three"}})
    assert brief_from_dict({**BRIEF, "identity": TRACK}).hash() == brief.hash()  # غياب الحقل لا يغيّر المفاتيح القائمة
    (tmp / "briefs" / "demo.yaml").write_text(yaml.safe_dump(
        {**BRIEF, "identity": {**TRACK, "inherit_mark": "v1", "lockup_word": "heading", "directions": "three"}}, allow_unicode=True),
        encoding="utf-8")
    brief3 = load_brief(tmp / "briefs" / "demo.yaml")

    out = pipe.run(brief3)
    ws3 = out.workspace
    assert ws3.version == 2 and out.code == AWAIT_MODEL and "ثلاثة اتجاهات" in out.message, out.message
    req = (ws3.work / "REQUEST-directions.md").read_text(encoding="utf-8")
    assert "`d1`" in req and "لا تعدّلهما" in req and "خط عناوين كل اتجاه" in req
    assert not ledger(ws3).history(Gate.DIRECTIONS)  # قاعدة المسار لا تعتمد اتجاهًا عن المالك هنا
    assert not [i for i in owner_inbox(tmp / "out") if i.get("version") == 2]

    # النموذج يكتب اتجاهين ويغيّر في طريقه اتجاه التسليم ونمطه: الأداة تعيدهما كما اعتُمدا
    path, motifs = directions_path(ws3), idir(ws3) / "motifs"
    d1 = yaml.safe_load(path.read_text(encoding="utf-8"))["directions"][0]
    d1_motif = (motifs / "d1.svg").read_text(encoding="utf-8")

    def alt(i: int, font: str, brand: str) -> dict:
        return {**d1, "id": f"d{i}", "name": f"بديل {i}", "idea": "إيقاع آخر فوق العلامة نفسها", "colors": {**d1["colors"], "brand": brand},
                "type": {**d1["type"], "heading": {"font": font, "weight": 700}},
                "motif": {"file": f"motifs/d{i}.svg", "rule": d1["motif"]["rule"]}}

    written = [alt(2, "IBMPlexSansArabic-Bold.ttf", "#1F4E79"), {**d1, "name": "اسم غيّره النموذج"}, alt(3, "Almarai-Bold.ttf", "#2F5D50")]
    path.write_text(yaml.safe_dump({"directions": written}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for i in (2, 3):
        (motifs / f"d{i}.svg").write_text(MOTIF, encoding="utf-8")
    (motifs / "d1.svg").write_text(MOTIF.replace('width="10"', 'width="12"'), encoding="utf-8")
    out = pipe.run(brief3)
    assert out.code == AWAIT_OWNER and "ثلاثة اتجاهات" in out.message, out.message
    kept = yaml.safe_load(path.read_text(encoding="utf-8"))["directions"]
    assert kept[0] == d1 and [x["id"] for x in kept] == ["d1", "d2", "d3"]
    assert (motifs / "d1.svg").read_text(encoding="utf-8") == d1_motif
    [item] = [i for i in owner_inbox(tmp / "out") if i.get("version") == 2]
    assert item["gate"] == "directions" and [o["id"] for o in item["options"]] == ["d1", "d2", "d3"]
    assert pipe.run(brief3).message == out.message and not ledger(ws3).history(Gate.DIRECTIONS)  # الإعادة لا تغيّر ولا تقرّر

    shaper = ShapingService(HarfBuzzShaper())
    by_font = {f: shaper.wordmark(brief3.wordmark_text, f, 700, title=brief3.wordmark_text).svg
               for f in ("Cairo[slnt,wght].ttf", "IBMPlexSansArabic-Bold.ttf")}
    assert by_font["Cairo[slnt,wght].ttf"] != by_font["IBMPlexSansArabic-Bold.ttf"]
    assert (ws3.work / "wordmark.svg").read_text(encoding="utf-8") == by_font["Cairo[slnt,wght].ttf"]  # قبل الاختيار: خط اتجاه التسليم

    ledger(ws3).record(Gate.DIRECTIONS, directions_digest(ws3), "approved", "d2", "الثاني")
    out = pipe.run(brief3)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    assert ws3.read_marker("directions")["option"] == "d2"
    assert (ws3.work / "wordmark.svg").read_text(encoding="utf-8") == by_font["IBMPlexSansArabic-Bold.ttf"]  # الكلمة بخط المختار
    lock = (ws3.package_dir / "demo-lockup.svg").read_text(encoding="utf-8")
    assert "#1F4E79" in lock.split('id="symbol"', 1)[1].split('id="wordmark"', 1)[0]  # الرمز بلون الاتجاه المختار
    assert (ws3.package_dir / "identity" / "brand-book.html").is_file() and not ws3.done("identity")
