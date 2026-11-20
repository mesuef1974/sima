"""ورشة الرسم: المالك يرى المصغّرات وقراءاتها ثم المفاهيم وهي تُرسم، للقراءة فقط، وتختفي حين تظهر بطاقة القرار."""
import time

from sima.adapters.geometry import build_svg
from sima.domain import brief_from_dict
from sima.services.board import safe_out_path, without_hidden
from sima.services.pipeline import Pipeline
from sima.services.shaping import ShapingService
from sima.services.workshop import EVAL_JUDGED, workshop

from .fakes import FakeRenderer
from .test_domain_ledger_workspace import BRIEF
from .test_pipeline import NoShaper, _judge
from .test_thumbs import _concepts, _ideas, _pipe, _read


def test_workshop_shows_thumbs_with_their_readings_then_the_concepts(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _pipe(tmp_path)
    out = tmp_path / "out"
    ws = pipe.run(b).workspace
    assert workshop(out, []) == []  # لا شيء مرسوم بعد
    _ideas(ws)
    pipe.run(b)
    [w] = workshop(out, [])
    assert w["project"] == ws.key.project and w["stage"] == "قراءة عمياء لمصغّرات الأفكار" and len(w["thumbs"]) == 12 and w["concepts"] == []
    t = w["thumbs"][0]
    assert t["state"] == "" and t["state_ar"] == "لم تُقرأ بعد" and t["img"].endswith("/work/thumbs/i0.svg") and t["stamp"] > 0
    assert safe_out_path(out, t["img"]) is not None and safe_out_path(out, t["img"].replace(".svg", ".mark.yaml")) is None
    _read(ws, blocked=("i0", "i1"))
    pipe.run(b)
    [w] = workshop(out, [])
    by = {t["id"]: t for t in w["thumbs"]}
    assert by["i0"]["state"] == "blocked" and "حرف لاتيني" in by["i0"]["seen"] and by["i5"]["state_ar"] == "مجتازة"
    assert [t["state"] for t in w["thumbs"]] == ["allowed"] * 10 + ["blocked"] * 2 and w["stage"] == "رسم المفاهيم"
    _concepts(ws, ["i6", "i2", "i3", "i4", "i5"])
    pipe.run(b)
    [w] = workshop(out, [])
    c = w["concepts"][0]
    assert len(w["concepts"]) == 5 and c["idea"] == "i6" and c["img"].endswith("/work/concepts/c1.svg") and c["seen"] == "" and not c["misread"]
    assert safe_out_path(out, c["img"]) is not None


def test_workshop_hides_when_the_decision_card_is_shown_and_survives_half_written_files(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _pipe(tmp_path)
    out = tmp_path / "out"
    ws = pipe.run(b).workspace
    _ideas(ws)
    pipe.run(b)
    assert workshop(out, [{"project": ws.key.project, "kind": "concepts"}]) == []  # بطاقة القرار تغني عن الورشة
    assert len(workshop(out, [{"project": ws.key.project, "kind": "style"}])) == 1
    (ws.work / "concepts.yaml").write_text("concepts:\n  - id: c1\n    name: [ناقص", encoding="utf-8")  # النموذج يكتب الآن
    [w] = workshop(out, [])
    assert w["concepts"] == [] and len(w["thumbs"]) == 12
    (ws.work / "ideas.yaml").write_text("ideas: [", encoding="utf-8")
    assert workshop(out, []) == []
    (out / "_calibration" / "v1").mkdir(parents=True)
    assert workshop(out, []) == [] and workshop(tmp_path / "missing", []) == []
    st = {"workshop": [{"project": "sima"}, {"project": "math_papers"}], "now": "t"}
    assert without_hidden(st, ("math_papers",))["workshop"] == [{"project": "sima"}]


def test_workshop_shows_exploration_boards_listed_in_their_manifest_only(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    out = tmp_path / "out"
    ws = _pipe(tmp_path).run(b).workspace
    ex = ws.work / "explore"
    ex.mkdir(parents=True)
    (ex / "d1.jpg").write_bytes(b"\xff\xd8\xff")
    (ex / "brief.md").write_text("موجز", encoding="utf-8")
    assert workshop(out, []) == []  # صورة بلا بيان لا تُعرض
    (ex / "boards.yaml").write_text(
        "source: تجربة\nboards:\n  - {id: d1, name: الكسرة, detail: الاسم وحده, misread: ختم, img: d1.jpg}\n"
        "  - {id: d2, name: غائبة, img: d2.jpg}\n  - {id: x, name: خروج, img: ../brief.md}\n  - نص\n", encoding="utf-8")
    [w] = workshop(out, [])
    [d] = w["explore"]
    assert d["id"] == "d1" and d["misread"] == "ختم" and d["source"] == "تجربة" and d["img"].endswith("/work/explore/d1.jpg") and d["stamp"] > 0
    assert w["thumbs"] == [] and w["concepts"] == []
    assert safe_out_path(out, d["img"]) is not None
    (ex / "d3.webp").write_bytes(b"RIFF")
    (ex / "boards.yaml").write_text("boards:\n  - {id: d3, name: ويب, img: d3.webp}\n", encoding="utf-8")
    [w3] = workshop(out, [])
    assert w3["explore"][0]["img"].endswith("/work/explore/d3.webp") and safe_out_path(out, w3["explore"][0]["img"]) is not None
    assert safe_out_path(out, d["img"].replace("d1.jpg", "brief.md")) is None and safe_out_path(out, d["img"].replace("d1.jpg", "boards.yaml")) is None
    (ex / "boards.yaml").write_text("boards: 7", encoding="utf-8")
    assert workshop(out, []) == []
    (ex / "boards.yaml").write_text("boards: [", encoding="utf-8")
    assert workshop(out, []) == []
    st = {"workshop": [{"project": "sima"}, {"project": "math_papers"}], "now": "t"}
    assert without_hidden(st, ("math_papers",))["workshop"] == [{"project": "sima"}]


def test_workshop_shows_the_latest_eval_run_read_only_with_the_first_verdict(tmp_path):
    """تشغيلات تقييم الرسّام في out/_eval: يُعرض آخرها وحده، بمفتاح eval ودرجة الحَكَم الأولى، ويختفي بعد يوم."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    out = tmp_path / "out"

    def run_at(run_id):
        pipe = Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, out / "_eval" / run_id, catalog=[], decide_cmd="x",
                        build_mark=build_svg, thumbs_gate=True)
        ws = pipe.run(b).workspace
        _ideas(ws)
        pipe.run(b)
        return pipe, ws

    run_at("20261112-000000")
    pipe, ws = run_at("20261113-000000-b")
    [w] = workshop(out, [])  # التشغيل الأقدم لا يُعرض
    assert w["eval"] == {"run": "20261113-000000-b", "name": b.name_ar} and w["project"] == b.project and len(w["thumbs"]) == 12
    assert w["stage"] == "قراءة عمياء لمصغّرات الأفكار" and w["explore"] == []
    img = w["thumbs"][0]["img"]
    assert img.startswith("_eval/20261113-000000-b/") and safe_out_path(out, img) is not None
    assert safe_out_path(out, img.replace("thumbs/i0.svg", "REQUEST-thumbs.md")) is None  # الطلبات لا تُخدم من التقييم أيضًا
    assert safe_out_path(out, img.replace(".svg", ".mark.yaml")) is None
    _read(ws)
    pipe.run(b)
    _concepts(ws, ["i0", "i1", "i2", "i3", "i4"])
    pipe.run(b)
    [w] = workshop(out, [])
    assert len(w["concepts"]) == 5 and "score" not in w["concepts"][0]  # لا حكم بعد
    _judge(ws, 3, c4=5)
    [w] = workshop(out, [])
    by = {c["id"]: c for c in w["concepts"]}
    assert w["stage"] == EVAL_JUDGED and by["c4"]["score"] == 40 and by["c4"]["passed"] and by["c1"]["score"] == 24 and not by["c1"]["passed"]
    assert safe_out_path(out, by["c4"]["img"]) is not None
    assert safe_out_path(out, by["c4"]["img"].rsplit("/", 2)[0] + "/judge/x.yaml") is None
    assert workshop(out, [], now=time.time() + 25 * 3600) == []  # بعد يوم تخلو له صفحة «اليوم»
    assert without_hidden({"workshop": [w]}, (b.project,))["workshop"] == []
    from sima.services.workshop import hide_eval

    assert hide_eval(out) == "20261113-000000-b" and workshop(out, []) == []  # أخفاه المالك قبل يومه: لا يعود الأقدم مكانه
    assert (ws.work / "concepts.yaml").is_file() and hide_eval(tmp_path / "none") is None  # الأعمال لا تُمسّ
    run_at("20261114-000000")
    assert [x["eval"]["run"] for x in workshop(out, [])] == ["20261114-000000"]  # التشغيل التالي يُعرض كعادته
