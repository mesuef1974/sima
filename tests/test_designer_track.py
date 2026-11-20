"""مسار المصمّم الخارجي بعد مراجعة الأتمتة (2026-11-14، المرحلة 4): عدّاد التصحيح للبناء الجاري واستنفاده يُعرض على المالك
(ب4)، والحد الأدنى المعلن يُحمل قُدُمًا (ب6)، وما يردّه التحقق من البيان يبلغ المصمّم بسببه وبسقف (ب7)، وتسليم جديد لا يمحو
الاتجاهين الآخرين (ب8)، وتسليم بعد الحزمة لا ينتظر المصمّم أبدًا (ب9)، ونسخ العمل للعلامة المعتمدة تُعاد كما اعتُمدت (ب11).
لا اتصال شبكي ولا نموذج في هذه الاختبارات."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from sima.domain import NameStatus
from sima.domain.brief import load_brief
from sima.domain.identity import Gate
from sima.services import adopt, designer, designer_box
from sima.services.identity_protocol import digest, directions_digest, directions_path, idir, ledger, strategy_path
from sima.services.inbox import choose_sketch, owner_inbox, return_vector
from sima.services.namecheck import record_name_check
from sima.services.pipeline import AWAIT_DESIGNER, AWAIT_MODEL, AWAIT_OWNER, Pipeline
from sima.services.timeline import timeline

from .fakes import rect_svg
from .test_adopt import MARK, MOTIF, project  # noqa: F401
from .test_designer import TRACK, _delivery, _sheet, track  # noqa: F401
from .test_designer_box import LIST, NOW, PNG, _files, _reply
from .test_domain_ledger_workspace import BRIEF
from .test_identity import STRATEGY

WHY = "أصغر سماكة عند 16 بكسل = 0.97 أقل من 1.5"
OTHER = rect_svg(40, 40, 176, 176).replace("#000000", "#2A2622")


def _rejected(self, ws, brief, concepts, svgs, smalls, small_base=16, min_stroke=None, **_):
    ok, bad = SimpleNamespace(passed=True, findings=[]), SimpleNamespace(passed=False, findings=[WHY])
    return {concepts[0].id: ok, concepts[0].id + "-small": bad}


def _picked(track, sketch: int = 5):  # noqa: F811
    tmp, brief, pipe = track
    ws = pipe.run(brief).workspace
    _sheet(ws)
    pipe.run(brief)
    sheet, _ = designer.read_sheet(ws)
    designer.record(ws, sheet, sketch, "", sheet.digest)
    return tmp, brief, pipe, ws


def _to_book(track, sketch: int = 5):  # noqa: F811
    tmp, brief, pipe, ws = _picked(track, sketch)
    folder = _delivery(tmp / "delivery")
    designer.write_manifest(ws, sketch, folder)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    pipe.run(brief)
    record_name_check(ws, brief, NameStatus.CLEAR, ["WIPO"], "")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message and ws.done("package"), out.message
    return tmp, brief, pipe, ws, folder


def test_fix_rounds_belong_to_the_current_build_and_running_out_is_shown_to_the_owner(track, monkeypatch):  # noqa: F811
    """ب4: كان العدّاد للإصدار كله أبدًا واستنفاده خروجًا بالرمز 1 بلا بطاقة. الآن يُعدّ للبناء الجاري (اختيار المالك أو ردّه
    للمتجه يبدآنه من جديد)، واستنفاده يقف عند المالك ببطاقة وبطريقين للمضيّ."""
    tmp, brief, pipe, ws = _picked(track)
    out_dir = tmp / "out"
    folder = _delivery(tmp / "delivery")
    designer.write_manifest(ws, 5, folder)
    monkeypatch.setattr(Pipeline, "_stage_render", _rejected)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "الجولة 1" in out.message
    assert ws.read_marker(designer.FIX_MARKER)["build"] == designer.build(ws)

    ws.mark_done(designer.FIX_MARKER, {"digests": ["a", "b", "c"]})  # علامة أقدم من الحقل لا تقول لأي بناء عُدّت: لا تُحسب عليه
    assert "الجولة 1" in pipe.run(brief).message
    ws.mark_done(designer.FIX_MARKER, {"build": designer.build(ws), "digests": ["a", "b", "c"]})
    out = pipe.run(brief)  # تسليم رابع مردود في البناء نفسه: يُعرض الحال على المالك ولا يدور ولا يخرج بخطأ
    assert out.code == AWAIT_OWNER and "بعد 3 جولات" in out.message and WHY in out.message and "--rebuild" in out.message
    [item] = owner_inbox(out_dir)
    assert item["kind"] == "stalled" and WHY in item["message"] and item["digest"] == designer.manifest_digest(ws)
    assert timeline(ws.root, item)["now"]["who"] == "owner" and designer_box.outbox(out_dir) == []

    # قرار المالك من هذه الحال: ردّ المتجه بسبب. بناء جديد، فيبدأ العدّ من جديد
    msg = return_vector(out_dir, "demo", 1, item["key"], item["digest"], "السماكة لا تصلح؛ ابنِ السكتش بخط أثخن")
    assert "رُدّ متجه السكتش 5" in msg
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "إعادة بناء السكتش 5" in out.message
    (folder / "icon.svg").write_text(OTHER, encoding="utf-8")
    designer.write_manifest(ws, 5, folder)
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and "الجولة 1" in out.message, out.message


def test_declared_minimum_survives_a_later_delivery_until_the_owner_changes_it(track, monkeypatch):  # noqa: F811
    """ب6: الحد الذي أعلنه المالك (160 لـ«أوراق») كان يسقط إلى 16 عند أي استلام لاحق من الصندوق. الآن قرار مسجَّل في البيان
    يُحمل إلى كل تسليم للسكتش نفسه ما لم يغيّره المالك صراحة."""
    tmp, brief, pipe, ws = _picked(track)
    out_dir = tmp / "out"
    folder = _delivery(tmp / "delivery")

    def manifest() -> dict:
        return yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))

    designer.write_manifest(ws, 5, folder, 160)
    assert (manifest()["min_mark_px"], manifest()["min_mark_px_by"]) == (160, "owner")
    monkeypatch.setattr(Pipeline, "_stage_render", _rejected)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    assert pipe.run(brief).code == AWAIT_DESIGNER
    [fix] = designer_box.outbox(out_dir)
    msg = designer_box.intake(out_dir, "demo", 1, fix["key"], _reply(_files()), None, NOW)  # تصحيح من الصندوق بلا حدّ
    assert manifest()["min_mark_px"] == 160 and "160" in msg

    old = manifest()  # بيان أقدم من الحقل: الطلب لا يسأل المصمّم عن حدّ، فما ليس 16 أعلنه المالك
    old.pop("min_mark_px_by")
    designer.manifest_path(ws).write_text(yaml.safe_dump(old, allow_unicode=True, sort_keys=False), encoding="utf-8")
    designer.write_manifest(ws, 5, folder)
    assert (manifest()["min_mark_px"], manifest()["min_mark_px_by"]) == (160, "owner")
    designer.write_manifest(ws, 5, folder, 96)  # يغيّره المالك صراحة
    assert manifest()["min_mark_px"] == 96
    designer.write_manifest(ws, 4, folder)  # سكتش آخر علامة أخرى: حدّ تلك لا يُحمل إليها
    assert (manifest()["min_mark_px"], manifest()["min_mark_px_by"]) == (16, "delivery")


def test_delivery_refused_by_the_manifest_check_reaches_the_designer_with_its_reason(track):  # noqa: F811
    """ب7: تسليم يردّه التحقق من البيان كان يعيد طلب المتجه كله وسببه فوق «النص المرسل» فلا يبلغ المصمّم، وبلا سقف. الآن
    يمرّ بطلب التصحيح نفسه بسببه وعدّاده؛ وما ليس مما يصحّحه المصمّم (بصمة لا تطابق) يقف عند المالك."""
    tmp, brief, pipe, ws = _picked(track)
    out_dir = tmp / "out"
    folder = _delivery(tmp / "delivery")
    good = (folder / "icon.svg").read_text(encoding="utf-8")
    (folder / "icon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'><rect", encoding="utf-8")
    designer.write_manifest(ws, 5, folder)
    out = pipe.run(brief)
    assert out.code == AWAIT_DESIGNER and out.request == designer.REQ_FIX and "الجولة 1" in out.message, out.message
    sent = (ws.work / designer.REQ_FIX).read_text(encoding="utf-8").split(designer.SENT, 1)[1]
    assert "`icon.svg`: SVG غير صالح" in sent and "logo.svg" not in sent and str(tmp) not in sent
    [box] = designer_box.outbox(out_dir)
    assert box["kind"] == "fix" and "SVG غير صالح" in box["text"]
    assert not ws.done("adopted") and [i["kind"] for i in owner_inbox(out_dir)] == []

    ws.mark_done(designer.FIX_MARKER, {"build": designer.build(ws), "digests": ["a", "b", "c"]})
    out = pipe.run(brief)  # السقف نفسه: لا حلقة بلا نهاية
    assert out.code == AWAIT_OWNER and "بعد 3 جولات" in out.message
    ws.marker(designer.FIX_MARKER).unlink()

    (folder / "icon.svg").write_text(good, encoding="utf-8")
    designer.write_manifest(ws, 5, folder)
    (designer.ddir(ws) / "icon.svg").write_text(OTHER, encoding="utf-8")  # تغيّر في الإصدار بعد الاستلام: ليس خطأ المصمّم
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "لا يطابق البصمة" in out.message and "--intake" in out.message
    assert designer_box.outbox(out_dir) == [] and owner_inbox(out_dir)[0]["kind"] == "stalled"
    designer.write_manifest(ws, 5, folder)
    assert pipe.run(brief).code == AWAIT_MODEL and ws.done("adopted")


def test_new_delivery_keeps_the_other_two_directions(track):  # noqa: F811
    """ب8: مع `directions: three` كان أي تسليم جديد يعيد كتابة directions.yaml باتجاه واحد فيمحو d2 وd3 واختيار المالك
    ويطلب استدعاءً مدفوعًا. الآن يُدمج اتجاه التسليم وحده."""
    tmp, _, pipe, _, folder = _to_book(track)
    (tmp / "briefs" / "demo.yaml").write_text(yaml.safe_dump(
        {**BRIEF, "identity": {**TRACK, "inherit_mark": "v1", "lockup_word": "heading", "directions": "three"}}, allow_unicode=True),
        encoding="utf-8")
    brief3 = load_brief(tmp / "briefs" / "demo.yaml")
    out = pipe.run(brief3)
    ws3 = out.workspace
    assert ws3.version == 2 and out.code == AWAIT_MODEL
    path, motifs = directions_path(ws3), idir(ws3) / "motifs"
    d1 = yaml.safe_load(path.read_text(encoding="utf-8"))["directions"][0]

    def alt(i: int, font: str, brand: str) -> dict:
        return {**d1, "id": f"d{i}", "name": f"بديل {i}", "idea": "إيقاع آخر فوق العلامة نفسها", "colors": {**d1["colors"], "brand": brand},
                "type": {**d1["type"], "heading": {"font": font, "weight": 700}},
                "motif": {"file": f"motifs/d{i}.svg", "rule": d1["motif"]["rule"]}}

    others = [alt(2, "IBMPlexSansArabic-Bold.ttf", "#1F4E79"), alt(3, "Almarai-Bold.ttf", "#2F5D50")]
    path.write_text(yaml.safe_dump({"directions": [d1, *others]}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for i in (2, 3):
        (motifs / f"d{i}.svg").write_text(MOTIF, encoding="utf-8")
    assert pipe.run(brief3).code == AWAIT_OWNER
    before = directions_digest(ws3)
    ledger(ws3).record(Gate.DIRECTIONS, before, "approved", "d2", "الثاني")

    (folder / "icon.svg").write_text(OTHER, encoding="utf-8")  # تسليم جديد يغيّر الرمز وحده
    designer.write_manifest(ws3, 5, folder)
    out = pipe.run(brief3)
    kept = yaml.safe_load(path.read_text(encoding="utf-8"))["directions"]
    assert [x["id"] for x in kept] == ["d1", "d2", "d3"] and kept[1:] == others, out.message
    assert directions_digest(ws3) == before and ws3.read_marker("directions")["option"] == "d2"  # اختيار المالك باقٍ
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message


def test_delivery_after_the_package_is_refused_at_the_door_or_reopens_it_by_the_owner(track):  # noqa: F811
    """ب9: استلام بعد الحزمة بلا ردّ للمتجه كان يدخل ثم يلتقط الخط خطأ القاعدة ويحوّله إلى «ينتظر المصمّم» أبدًا. الآن يُردّ
    عند الاستلام فلا يتغيّر شيء، ومعه حدّ يعلنه المالك يعيد فتح الحزمة قبل اعتماد الدليل؛ وبيان غُيّر باليد يقف عند المالك."""
    tmp, brief, pipe, ws, folder = _to_book(track, 11)
    out_dir = tmp / "out"
    book = ws.package_dir / "identity" / "brand-book.html"
    first, built = digest([book]), designer.manifest_digest(ws)
    (folder / "icon.svg").write_text(OTHER, encoding="utf-8")
    with pytest.raises(designer.DesignerError, match="بعد بناء الحزمة"):
        designer.write_manifest(ws, 11, folder)
    assert designer.manifest_digest(ws) == built and (designer.ddir(ws) / "icon.svg").read_text(encoding="utf-8") == MARK
    assert "دليل الهوية" in pipe.run(brief).message and digest([book]) == first

    data = yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))  # بيان غُيّر في مكانه بلا استلام
    designer.manifest_path(ws).write_text(yaml.safe_dump({**data, "min_mark_px": 32}, allow_unicode=True, sort_keys=False),
                                          encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "بعد بناء الحزمة" in out.message and "--min-mark-px" in out.message
    [stalled] = owner_inbox(out_dir)
    assert designer_box.outbox(out_dir) == [] and stalled["kind"] == "stalled"
    assert timeline(ws.root, stalled)["now"]["who"] == "owner"

    designer.write_manifest(ws, 11, folder, 160)  # المالك يقبل هذا التسليم عند حدّ يعلنه: تُبنى الحزمة والدليل عليه
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    assert digest([book]) != first and 'width="176"' in (ws.package_dir / "demo-mark.svg").read_text(encoding="utf-8")
    assert "160 بكسل" in (ws.package_dir / "USAGE.md").read_text(encoding="utf-8")
    [item] = owner_inbox(out_dir)
    assert item["kind"] == "identity" and item["gate"] == "book"
    (folder / "icon.svg").write_text(MARK, encoding="utf-8")
    with pytest.raises(designer.DesignerError, match="بعد بناء الحزمة"):  # الإذن لذلك التسليم وحده
        designer.write_manifest(ws, 11, folder)

    ledger(ws).record(Gate.BOOK, digest([book]), "approved")
    assert pipe.run(brief).code == 0
    with pytest.raises(designer.DesignerError, match="إصدار جديد"):  # الإصدار المعتمد لا يدخله تسليم ولو بحدّ
        designer.write_manifest(ws, 11, folder, 160)


def test_adopted_working_copies_are_restored_as_adopted_before_the_package(project):  # noqa: F811
    """ب11: نسخ العمل للعلامة المعتمدة داخل نافذة كتابة نموذج الخط، وكان `sync` يعود عند تطابق البصمة فيُحزَم ما عُدّل منها.
    الآن تُقارَن بما يكتبه البيان عند كل تشغيل ويُعاد ما اختلف."""
    _, _, brief, pipe = project
    ws = pipe.run(brief).workspace
    small, word = ws.concepts_dir / "a1.small.svg", ws.concepts_dir / "a1.svg"
    adopted = small.read_text(encoding="utf-8"), word.read_text(encoding="utf-8"), (ws.work / "concepts.yaml").read_text(encoding="utf-8")
    small.write_text(rect_svg(40, 40, 176, 176), encoding="utf-8")
    word.unlink()
    (ws.work / "concepts.yaml").write_text(adopted[2].replace("الكلمة المعتمدة", "اسم آخر"), encoding="utf-8")
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and "دليل الهوية" in out.message, out.message
    assert (small.read_text(encoding="utf-8"), word.read_text(encoding="utf-8"),
            (ws.work / "concepts.yaml").read_text(encoding="utf-8")) == adopted
    mark = (ws.package_dir / "demo-mark.svg").read_text(encoding="utf-8")
    assert 'width="160"' in mark and 'width="176"' not in mark
    assert adopt.load(brief).mark == adopted[0]


def test_box_intake_uses_the_same_door(track):  # noqa: F811
    """الصندوق والطرفية يكتبان البيان من الدالة نفسها: الحد المحمول وباب ما بعد الحزمة واحد لهما."""
    tmp, brief, pipe = track
    out_dir = tmp / "out"
    pipe.run(brief)
    key = designer_box.outbox(out_dir)[0]["key"]
    designer_box.intake(out_dir, "demo", 1, key, LIST, PNG, NOW)
    pipe.run(brief)
    choose_sketch(out_dir, "demo", 1, key, owner_inbox(out_dir)[0]["digest"], 5, "")
    assert pipe.run(brief).code == AWAIT_DESIGNER
    msg = designer_box.intake(out_dir, "demo", 1, key, _reply(_files()), None, NOW)
    ws = pipe.run(brief).workspace
    data = yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))
    assert data["min_mark_px_by"] == "delivery" and "باقٍ" not in msg
