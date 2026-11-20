"""اختبار الخط كاملًا بمصيّر زائف: من الموجز إلى الحزمة مع بوابتَي النموذج والمالك."""
import json

import pytest
import yaml

from sima.domain import NameStatus, Verdict, brief_from_dict
from sima.services import protocol
from sima.services.namecheck import checklist_md, record_name_check
from sima.services.pipeline import AWAIT_MODEL, AWAIT_OWNER, Pipeline, record_decision
from sima.services.ports import ReferenceEntry
from sima.services.shaping import ShapingService

from .fakes import FakeLibrary, FakeRenderer, rect_svg
from .test_domain_ledger_workspace import BRIEF

FAMILIES = ["literal", "metaphorical", "abstract", "typographic", "symbolic"]


class NoShaper:
    def shape(self, text, font_path, weight):
        raise FileNotFoundError("لا خط في الاختبار")


def _pipeline(tmp_path, library=None):
    r = FakeRenderer()
    return r, Pipeline(r, ShapingService(NoShaper()), library, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml")


def _write_concepts(ws, svgs: dict[str, str], medium="abstract_mark"):
    ideas = [{"id": f"i{n}", "family": FAMILIES[n % 5], "sentence": f"فكرة {n}", "twist": f"حيلة {n}"} for n in range(12)]
    (ws.work / "ideas.yaml").write_text(yaml.safe_dump({"ideas": ideas}, allow_unicode=True), encoding="utf-8")
    concepts = []
    for n, (cid, svg) in enumerate(svgs.items()):
        concepts.append({"id": cid, "name": f"م{n}", "family": FAMILIES[n], "medium": medium, "sentence": f"جملة {n}",
                         "idea_id": f"i{n}", "reference": "ابن الهيثم، كتاب المناظر" if FAMILIES[n] == "symbolic" else ""})
        (ws.concepts_dir / f"{cid}.svg").write_text(svg, encoding="utf-8")
    (ws.work / "concepts.yaml").write_text(yaml.safe_dump({"concepts": concepts}, allow_unicode=True), encoding="utf-8")


def _judge(ws, score=4, **per):
    """يكتب حكم الحَكَم على المحتوى الحالي: درجة واحدة لكل المعايير، أو درجة خاصة لمفهوم (c2=2)."""
    from sima import config
    concepts = protocol.read_concepts(ws)
    dg = protocol.merged_digest(protocol.read_concept_svgs(ws, concepts), protocol.read_small_svgs(ws, concepts))
    verdicts = {c.id: {"scores": {k: per.get(c.id, score) for k in config.JUDGE_CRITERIA}, "blockers": ["عيب"], "direction": "اتجاه"}
                for c in concepts}
    (ws.work / "judge").mkdir(exist_ok=True)
    (ws.work / "judge" / f"{dg}.yaml").write_text(yaml.safe_dump({"digest": dg, "verdicts": verdicts}), encoding="utf-8")
    return dg


def _to_owner(pipe, b, ws):
    _write_concepts(ws, _five_distinct())
    pipe.run(b)
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {f"c{n}": {"action": "keep"} for n in range(1, 6)}}), encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message
    _judge(ws)
    out = pipe.run(b)
    assert out.code == AWAIT_OWNER, out.message
    return out


def _five_distinct():
    return {
        "c1": rect_svg(40, 40, 176, 176),
        "c2": rect_svg(40, 100, 176, 56),
        "c3": rect_svg(100, 40, 56, 176),
        "c4": rect_svg(40, 40, 80, 176, '<rect x="136" y="40" width="80" height="176" fill="#000000"/>'),
        "c5": rect_svg(40, 40, 176, 60, '<rect x="40" y="156" width="176" height="60" fill="#000000"/>'),
    }


def test_full_flow_to_package(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and (out.workspace.work / "REQUEST-diverge.md").is_file()
    assert (out.workspace.work / "research.md").is_file()
    ws = out.workspace
    _write_concepts(ws, _five_distinct())
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الجولة 1" in out.message
    audits = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
    assert all(a["passed"] for a in audits.values()), audits
    assert (ws.render_dir / "c1" / "16.png").is_file() and (ws.render_dir / "c1" / "reversed.png").is_file()
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {k: {"action": "keep"} for k in audits}}), encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message
    assert "40-professional-bar" in (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")
    judge_req = (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")
    assert "اختبار الجملة" in judge_req and "43-lessons-v1" in judge_req and "42-arabic-lettering" in judge_req
    _judge(ws, c4=5)
    out = pipe.run(b)
    assert out.code == AWAIT_OWNER and ws.preview_path.is_file()
    assert ws.read_marker("shortlist")["ids"] == ["c4", "c1", "c2"]  # أفضل ثلاثة بالمجموع ثم المعرّف
    html = ws.preview_path.read_text(encoding="utf-8")
    assert "ورقة معاينة" in html and "م4" not in html and "م3" in html and (ws.work / "WORDMARK-ERROR.txt").is_file()
    record_decision(ws, "c2", Verdict.APPROVED, "الأوضح")
    out = pipe.run(b)
    assert out.code == AWAIT_OWNER and "توافر الاسم" in out.message and (ws.root / "NAME-CHECK.md").is_file()
    record_name_check(ws, b, NameStatus.CONFLICT, ["WIPO"], "علامة مطابقة")
    out = pipe.run(b)
    assert out.code == AWAIT_OWNER and "متعارضًا" in out.message
    record_name_check(ws, b, NameStatus.CLEAR, ["WIPO", "MOCI"], "لا تعارض")
    out = pipe.run(b)
    assert out.code == 0, out.message
    pkg = ws.package_dir
    assert (pkg / "demo-mark.svg").is_file() and (pkg / "favicon.ico").is_file() and (pkg / "USAGE.md").is_file()
    assert json.loads((pkg / "concept.json").read_text(encoding="utf-8"))["id"] == "c2"
    # idempotent: إعادة التشغيل لا تنشئ إصدارًا جديدًا ولا تغيّر النتيجة
    mtime = (pkg / "USAGE.md").stat().st_mtime
    out2 = pipe.run(b)
    assert out2.code == 0 and out2.workspace.root == ws.root and (pkg / "USAGE.md").stat().st_mtime == mtime


def test_thin_stroke_fails_audit_and_requests_fix(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    svgs = _five_distinct()
    svgs["c2"] = rect_svg(40, 120, 176, 8)  # 8 وحدات = 0.5 بكسل عند 16
    _write_concepts(ws, svgs)
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL
    audits = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
    assert not audits["c2"]["passed"] and any("سماكة" in f for f in audits["c2"]["findings"])
    req = (ws.work / "REQUEST-critique-r1.md").read_text(encoding="utf-8")
    assert "فشل" in req and "c2" in req
    # النموذج يطلب تعديلًا لكن لا يعدّل: يُطالَب بالتعديل
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {"c2": {"action": "revise"}}}), encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "لم تُنفَّذ" in out.message
    assert "action=drop رأيك أن المفهوم لا يستحق العرض" in req and "revise بلا تعديل فعلي" in req
    # بعد التعديل تُعاد الفحوص وتُطلب جولة ثانية للنظر
    (ws.concepts_dir / "c2.svg").write_text(rect_svg(40, 100, 176, 56), encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الجولة 2" in out.message
    audits = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
    assert audits["c2"]["passed"]


def test_owner_rejection_redraws_in_same_medium_then_rejudges(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _to_owner(pipe, b, ws)
    for cid in ("c1", "c2", "c3"):
        record_decision(ws, cid, Verdict.REJECTED, "أين الحداثة")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "ملاحظات المالك" in out.message
    req = (ws.work / "REQUEST-refine-owner.md").read_text(encoding="utf-8")
    assert "أين الحداثة" in req and "استبدال الفكرة" in req and "c1" in req
    assert not (ws.work / "MEDIUM-ROTATED.md").is_file()  # الرفض لا يغيّر الوسيط
    assert pipe.run(b).code == AWAIT_MODEL  # لم يُعَد الرسم بعد
    (ws.concepts_dir / "c1.svg").write_text(rect_svg(60, 60, 136, 136), encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message  # دورة تحكيم جديدة للمحتوى الجديد
    assert ws.read_marker("owner_feedback")["handled"] == 3 and (ws.work / "history").is_dir()
    _judge(ws)
    assert pipe.run(b).code == AWAIT_OWNER


def test_below_bar_refines_then_shows_best_with_flag(tmp_path):
    from sima import config
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    pipe.run(b)
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {}}), encoding="utf-8")
    pipe.run(b)
    for k in range(config.JUDGE_MAX_ROUNDS):
        _judge(ws, score=3, c1=5)  # c1 وحده يجتاز: دون ثلاثة
        out = pipe.run(b)
        if k < config.JUDGE_MAX_ROUNDS - 1:
            assert out.code == AWAIT_MODEL and "صقل" in out.message
            req = (ws.work / "REQUEST-refine.md").read_text(encoding="utf-8")
            assert "c2" in req and "c1 «" not in req and "دون 4" in req
            (ws.concepts_dir / "c2.svg").write_text(rect_svg(40, 90 - k * 6, 176, 56), encoding="utf-8")
            nxt = pipe.run(b)
            assert "الحَكَم" in nxt.message, nxt.message
    assert out.code == AWAIT_OWNER
    sl = ws.read_marker("shortlist")
    assert sl["below_bar"] is True and sl["ids"][0] == "c1" and sl["passed"] == ["c1"]


def test_owner_switch_redraws_even_in_same_medium(tmp_path):
    from sima.domain import Medium
    from sima.services.pipeline import record_switch
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _to_owner(pipe, b, ws)
    (ws.concepts_dir / "c1.mark.yaml").write_text("mark: {circle: [128, 128, 90]}", encoding="utf-8")
    record_decision(ws, "c1", Verdict.REJECTED, "ضعيف")
    record_switch(ws, Medium.ABSTRACT_MARK, "ارسم من جديد بالمعيار")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and not (ws.work / "concepts.yaml").is_file()
    assert (ws.work / "history" / "medium-abstract_mark-1" / "c1.svg").is_file()
    assert not list(ws.concepts_dir.glob("*"))  # لا يبقى بناء قديم يعيد توليد رسوم الوسيط السابق
    assert not list(ws.critique_dir.glob("round*"))  # ولا بصمة طلب نقد قديم تُحسب «تعديلًا» على الرسم الجديد
    req = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert "ضعيف" in req and "ارسم من جديد بالمعيار" in req and "twist" in req
    record_switch(ws, Medium.EMBLEM, "شارة")
    pipe.run(b)
    assert "emblem" in (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    _write_concepts(ws, _five_distinct(), medium="emblem")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الجولة 1" in out.message  # الرفض القديم لا يُعاد رسمًا في الوسيط الجديد


def test_similarity_warning_against_library(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    lib = FakeLibrary([ReferenceEntry("acme.svg", "acme", rect_svg(40, 40, 176, 176))])
    _r, pipe = _pipeline(tmp_path, lib)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    pipe.run(b)
    audits = json.loads((ws.work / "audit.json").read_text(encoding="utf-8"))
    assert any("acme" in w for w in audits["c1"]["warnings"]), audits["c1"]
    assert audits["c1"]["metrics"]["similarity"][0]["distance"] == 0


def test_validate_diverge_reports_problems(tmp_path):
    from sima.domain import Medium
    from sima.services.workspace import open_workspace
    b = brief_from_dict(BRIEF, source="b.yaml")
    ws = open_workspace(tmp_path, b)
    v = protocol.validate_diverge(ws, Medium.ABSTRACT_MARK)
    assert not v.ok and any("ideas.yaml" in p for p in v.problems)
    svgs = _five_distinct()
    svgs.pop("c5")
    _write_concepts(ws, svgs)
    v = protocol.validate_diverge(ws, Medium.ABSTRACT_MARK)
    assert any("عدد المفاهيم 4" in p for p in v.problems) and any("symbolic" in p for p in v.problems)


@pytest.mark.parametrize("n", [11, 21])
def test_ideas_count_bounds(tmp_path, n):
    from sima.domain import Medium
    from sima.services.workspace import open_workspace
    b = brief_from_dict(BRIEF, source="b.yaml")
    ws = open_workspace(tmp_path, b)
    _write_concepts(ws, _five_distinct())
    ideas = [{"id": f"i{k}", "family": "abstract", "sentence": "س"} for k in range(n)]
    (ws.work / "ideas.yaml").write_text(yaml.safe_dump({"ideas": ideas}), encoding="utf-8")
    v = protocol.validate_diverge(ws, Medium.ABSTRACT_MARK)
    assert any("عدد الأفكار" in p for p in v.problems)


def test_name_checklist_is_deterministic_and_arabic():
    b = brief_from_dict(BRIEF)
    md = checklist_md(b)
    assert md == checklist_md(b)
    assert "التحقق من توافر الاسم" in md and "branddb.wipo.int" in md and "sima name-check" in md
    assert "Awraq" not in md and "أوراق" not in md  # لا اسم مشروع آخر مكتوبًا في القالب
    assert "(Sima)" in checklist_md(brief_from_dict({**BRIEF, "name_latin": "Sima"}))  # التهجئة من الموجز لا التقريبية


def test_closed_identity_version_resumes_a_failed_delivery(tmp_path):
    from sima.services.workspace import open_workspace

    b = brief_from_dict({**BRIEF, "identity": {"scope": "full"}})
    calls: list = []
    r = FakeRenderer()
    pipe = Pipeline(r, ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="x",
                    on_identity_approved=lambda root: calls.append(root) or "سُلّم آليًا")
    ws = open_workspace(tmp_path / "out", b)
    ws.ensure()
    ws.mark_done("package")
    ws.mark_done("identity")
    out = pipe.run(b)
    assert out.code == 0 and "سُلّم آليًا" in out.message and calls == [ws.root]
    ws.mark_done("deliver", {"card_id": "c"})
    assert "سُلّم آليًا" not in pipe.run(b).message and len(calls) == 1


def _write_style_samples(ws):
    from sima.services import style
    d = style.styles_dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    for n, sid in enumerate(style.catalog()):
        (d / f"{sid}.svg").write_text(rect_svg(20 + n * 4, 40, 120, 60), encoding="utf-8")


@pytest.mark.style_gate
def test_style_gate_asks_samples_then_owner_then_constrains_drawing(tmp_path):
    from sima.services import style
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    out = pipe.run(b)
    ws = out.workspace
    assert out.code == AWAIT_MODEL and (ws.work / "REQUEST-style.md").is_file()
    assert not (ws.work / "REQUEST-diverge.md").exists()  # لا رسم قبل الطابع
    req = (ws.work / "REQUEST-style.md").read_text(encoding="utf-8")
    assert all(sid in req for sid in style.catalog())
    _write_style_samples(ws)
    out = pipe.run(b)
    assert out.code == AWAIT_OWNER and "الطابع" in out.message
    assert ws.read_marker("style_board")["digest"] == style.digest(ws)
    style.record(ws, ["s1", "s4"], "بلا زخرفة", style.digest(ws))
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL
    req = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert "الطابع الذي اختاره المالك" in req and "بلا زخرفة" in req and "work/styles/s4.svg" in req


@pytest.mark.style_gate
def test_new_style_choice_archives_existing_concepts(tmp_path):
    from sima.services import style
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _write_style_samples(ws)
    pipe.run(b)
    style.record(ws, ["s2"], "", style.digest(ws))
    pipe.run(b)
    _write_concepts(ws, _five_distinct())
    pipe.run(b)
    assert (ws.work / "concepts.yaml").is_file()  # الاختيار الأول قبل الرسم لا يؤرشف شيئًا
    record_decision(ws, "c1", Verdict.REJECTED, "قديم")
    style.record(ws, ["s3"], "أريد انسيابًا", style.digest(ws))
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and not (ws.work / "concepts.yaml").is_file()
    assert (ws.work / "history" / "style-1" / "c1.svg").is_file()
    req = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert "انسيابي معاصر" in req and "قديم" in req


def test_style_record_validates_picks(tmp_path):
    from sima.services import style
    from sima.services.workspace import open_workspace
    ws = open_workspace(tmp_path / "out", brief_from_dict(BRIEF, source="b.yaml"))
    ws.ensure()
    for bad in ([], ["s1", "s2", "s3"], ["s9"], ["s1", "s1"]):
        with pytest.raises(ValueError):
            style.record(ws, bad, "", "x")
    assert style.current(ws) is None


def test_font_bases_and_shared_font_rule(tmp_path):
    """خمسة مفاهيم على خط واحد تنويعات لا مفاهيم: الأداة ترفض أكثر من FONT_BASE_MAX على العائلة نفسها."""
    from types import SimpleNamespace

    from sima.services import protocol

    assert protocol.font_family("ReemKufi[wght].ttf") == protocol.font_family("ReemKufi-Bold.ttf") == "ReemKufi"
    assert protocol.font_family("IBMPlexSansArabic-SemiBold.ttf") == "IBMPlexSansArabic"
    spec = 'defs:\n  a: {text: "سِمة", font: "ReemKufi[wght].ttf", size: 100, at: [0, 0]}\nmark: {union: [a, {text: "س", font: "Cairo[slnt,wght].ttf"}]}\n'
    assert protocol.font_bases(spec) == {"ReemKufi", "Cairo"}
    assert protocol.font_bases("mark: {circle: [1, 2, 3]}") == set() == protocol.font_bases("{bad: [")
    d = tmp_path / "concepts"
    d.mkdir()
    ws = SimpleNamespace(concepts_dir=d)
    fonts = {"c1": "ReemKufi[wght].ttf", "c2": "ReemKufi[wght].ttf", "c3": "ReemKufi-Bold.ttf", "c4": "Cairo[slnt,wght].ttf"}
    for cid, f in fonts.items():
        (d / f"{cid}.mark.yaml").write_text(f'mark: {{text: "سمة", font: "{f}"}}\n', encoding="utf-8")
    (d / "c5.mark.yaml").write_text("mark: {circle: [128, 128, 60]}\n", encoding="utf-8")
    concepts = [SimpleNamespace(id=c) for c in ("c1", "c2", "c3", "c4", "c5")]
    problems = protocol.shared_font_problems(ws, concepts)
    assert len(problems) == 1 and "ReemKufi في c1، c2، c3" in problems[0]
    (d / "c3.mark.yaml").write_text('mark: {text: "سمة", font: "Almarai-Bold.ttf"}\n', encoding="utf-8")
    assert protocol.shared_font_problems(ws, concepts) == []


class OneHotEmbedder:
    """نص مطابق = متجه مطابق (تشابه 1)، وأي نص آخر متعامد (تشابه 0)."""
    model = "onehot"

    def __init__(self):
        self.seen: dict[str, int] = {}

    def embed(self, texts):
        for t in texts:
            self.seen.setdefault(t, len(self.seen))
        return [[1.0 if i == self.seen[t] else 0.0 for i in range(64)] for t in texts]


def _novel_pipeline(tmp_path):
    return Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml",
                    embedder=OneHotEmbedder())


def _set_idea(ws, cid, name, sentence):
    data = yaml.safe_load((ws.work / "concepts.yaml").read_text(encoding="utf-8"))
    for c in data["concepts"]:
        if c["id"] == cid:
            c["name"], c["sentence"] = name, sentence
    (ws.work / "concepts.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_rejected_idea_is_logged_before_redraw_and_its_return_is_refused(tmp_path):
    """الرفض يحفظ فكرة المفهوم قبل إعادة الرسم؛ وإعادة رسم الشكل مع إبقاء الفكرة تُرَدّ قبل أن تبلغ الحَكَم."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _novel_pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _to_owner(pipe, b, ws)
    record_decision(ws, "c1", Verdict.REJECTED, "أين الحداثة")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "ملاحظات المالك" in out.message  # المرفوض للتوّ يذهب إلى طلب إعادة الرسم لا إلى فحص الجِدّة
    log = [json.loads(ln) for ln in (ws.work / "history" / "rejected.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["id"], r["sentence"], r["reason"]) for r in log] == [("c1", "جملة 0", "أين الحداثة")]
    assert "## أفكار رفضها المالك" in (ws.work / "REQUEST-refine-owner.md").read_text(encoding="utf-8")
    (ws.concepts_dir / "c1.svg").write_text(rect_svg(60, 60, 136, 136), encoding="utf-8")  # شكل جديد والفكرة نفسها
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "يعود إلى فكرة رفضها المالك" in out.message and "c1" in out.message
    assert len((ws.work / "history" / "rejected.jsonl").read_text(encoding="utf-8").splitlines()) == 1  # لا يُسجَّل الجديد مرفوضًا
    _set_idea(ws, "c1", "جديد", "فكرة من منطقة معنى أخرى")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message, out.message
    assert ws.read_marker("owner_feedback")["handled"] == 1 and ws.read_marker("novelty")["problems"] == []


def test_pending_rejection_folds_into_redraw_request_once(tmp_path):
    """إن كان الرسّام سيُستدعى لمشكلة تباعد، ضُمّ رفض المالك المعلّق إلى الطلب نفسه ولا يُكتب طلب ثانٍ بعده."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _novel_pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _to_owner(pipe, b, ws)
    old = ws.work / "history" / "medium-abstract_mark"
    old.mkdir(parents=True)
    (old / "concepts.yaml").write_text(yaml.safe_dump({"concepts": [{"id": "c9", "name": "م1", "sentence": "جملة 1"}]}, allow_unicode=True),
                                       encoding="utf-8")  # c2 الحالي يطابق فكرة مؤرشفة
    record_decision(ws, "c1", Verdict.REJECTED, "أين الحداثة")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "REQUEST-diverge.md" in out.message
    req = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert "المفهوم c2 «م1» يعود إلى فكرة رفضها المالك" in req and "رفض المالك للمفهوم c1: «أين الحداثة»" in req
    assert not (ws.work / "REQUEST-refine-owner.md").is_file()
    assert ws.read_marker("owner_feedback")["request"]["upto"] == 1
    (ws.concepts_dir / "c1.svg").write_text(rect_svg(60, 60, 136, 136), encoding="utf-8")
    _set_idea(ws, "c1", "جديد", "فكرة أولى جديدة")
    _set_idea(ws, "c2", "أجدّ", "فكرة ثانية جديدة")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message, out.message
    assert ws.read_marker("owner_feedback") == {"handled": 1} and not (ws.work / "REQUEST-refine-owner.md").is_file()


def test_redraw_for_spread_problem_resets_judge_rounds(tmp_path):
    """رسم يُعاد لمشكلة تباعد يؤرشف أحكام الرسم السابق: الجديد ينال جولات صقله كاملة ولا يُعرض بعد تحكيم واحد."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _novel_pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _to_owner(pipe, b, ws)
    assert any((ws.work / "judge").glob("*.yaml")) and ws.done("shortlist")
    old = ws.work / "history" / "medium-abstract_mark"
    old.mkdir(parents=True)
    (old / "concepts.yaml").write_text(yaml.safe_dump({"concepts": [{"id": "c9", "name": "م1", "sentence": "جملة 1"}]}, allow_unicode=True),
                                       encoding="utf-8")  # c2 الحالي يطابق فكرة مؤرشفة
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "REQUEST-diverge.md" in out.message
    assert not any((ws.work / "judge").glob("*.yaml")) and not ws.done("shortlist")
    assert any((ws.work / "history").glob("judge-redraw-*/*.yaml"))
    assert pipe.run(b).code == AWAIT_MODEL and len(list((ws.work / "history").glob("judge-redraw-*"))) == 1  # idempotent


def test_spread_problem_during_auto_refine_keeps_judge_rounds(tmp_path):
    """مشكلة تباعد تظهر في أثناء الصقل الآلي (لا قائمة معروضة على المالك) لا تصفّر جولات التحكيم: سقف الصقل يبقى ساريًا."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _novel_pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _to_owner(pipe, b, ws)
    ws.marker("shortlist").unlink()  # لم تُعرض بعد: مجموعة قيد الصقل
    old = ws.work / "history" / "medium-abstract_mark"
    old.mkdir(parents=True)
    (old / "concepts.yaml").write_text(yaml.safe_dump({"concepts": [{"id": "c9", "name": "م1", "sentence": "جملة 1"}]}, allow_unicode=True),
                                       encoding="utf-8")
    before = len(list((ws.work / "judge").glob("*.yaml")))
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "REQUEST-diverge.md" in out.message
    assert len(list((ws.work / "judge").glob("*.yaml"))) == before and not list((ws.work / "history").glob("judge-redraw-*"))


def test_wordmark_is_constructed_with_its_small_mark(tmp_path):
    """وسيط الكلمة يُبنى كغيره (فيرى الرسّام ناتجه بالمعاينة الحية): الطلب يطلب البناء والمصغّر المبني، والتحقق يرفض غيابهما."""
    from sima.adapters.geometry import build_svg
    from sima.domain import Medium
    from sima.services.pipeline import record_switch
    b = brief_from_dict(BRIEF, source="b.yaml")
    r = FakeRenderer()
    pipe = Pipeline(r, ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml", build_mark=build_svg)
    ws = pipe.run(b).workspace
    record_switch(ws, Medium.WORDMARK, "رسم الاسم")
    out = pipe.run(b)
    req = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert out.code == AWAIT_MODEL and "41-construction.md" in req and "<id>.small.mark.yaml" in req and "`work/concepts/<id>.svg` لكل مفهوم" not in req
    assert "مناطق معنى" in req and "لوحة عريضة" in req
    _write_concepts(ws, _five_distinct(), medium="wordmark")
    for cid in _five_distinct():
        (ws.concepts_dir / f"{cid}.small.svg").write_text(rect_svg(40, 40, 176, 176), encoding="utf-8")
    problems = protocol.validate_diverge(ws, Medium.WORDMARK, construct=True).problems
    assert any("c1.mark.yaml" in p for p in problems) and any("c1.small.mark.yaml" in p for p in problems)
    for cid in _five_distinct():
        (ws.concepts_dir / f"{cid}.mark.yaml").write_text("mark: {rect: [40, 40, 176, 176]}", encoding="utf-8")
        (ws.concepts_dir / f"{cid}.small.mark.yaml").write_text("mark: {circle: [128, 128, 90]}", encoding="utf-8")
    assert protocol.validate_diverge(ws, Medium.WORDMARK, construct=True).ok


def test_judge_request_discounts_auto_crop_margin(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    pipe.run(b)
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {f"c{n}": {"action": "keep"} for n in range(1, 6)}}), encoding="utf-8")
    pipe.run(b)
    assert "أثر القص لا عيب" in (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")


def test_diverge_request_cites_drawer_profile_lessons_and_smallest_first(tmp_path):
    """طلب الرسم يحيل إلى تعريف الرسّام ودروس v1 ومرجع الحرف، ويلزم «الأصغر أولًا» واختبارَي الجملة والقراءة الخاطئة."""
    from pathlib import Path

    from sima.domain import Medium

    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml")
    ws = pipe.run(b).workspace
    pipe._write_request_diverge(ws, b, Medium.ABSTRACT_MARK, [])
    text = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    for ref in ("45-drawer-profile", "43-lessons-v1", "42-arabic-lettering", "الأصغر أولًا", "القراءة الخاطئة", "الجملة الواحدة"):
        assert ref in text, ref
    refs = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "sima-design" / "references"
    for name in ("42-arabic-lettering.md", "43-lessons-v1.md", "45-drawer-profile.md"):
        assert (refs / name).is_file(), name  # ما تحيل إليه الطلبات موجود فعلًا


def _blind(ws, **blocked):
    """يكتب قراءة القارئ الأعمى للمحتوى الحالي: كل المفاهيم مجردة إلا ما سُمّي (c2="ö") فيُقرأ حرفًا أجنبيًا بقوة 3."""
    concepts = protocol.read_concepts(ws)
    dg = protocol.merged_digest(protocol.read_concept_svgs(ws, concepts), protocol.read_small_svgs(ws, concepts))
    rows = {c.id: ({"seen": f"حرف {blocked[c.id]}", "reads_as": blocked[c.id], "kind": "foreign_letter", "strength": 3}
                   if c.id in blocked else {"seen": "شكل مجرد", "reads_as": "", "kind": "none", "strength": 0}) for c in concepts}
    (ws.work / "blind").mkdir(exist_ok=True)
    (ws.work / "blind" / f"{dg}.yaml").write_text(yaml.safe_dump({"digest": dg, "readings": rows}, allow_unicode=True), encoding="utf-8")
    return dg


def _blind_pipeline(tmp_path):
    return Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml",
                    blind_gate=True)


def _after_critique(pipe, b):
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    pipe.run(b)
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {f"c{n}": {"action": "keep"} for n in range(1, 6)}}), encoding="utf-8")
    return ws, pipe.run(b)


def test_blind_reading_gates_misread_concepts_before_the_judge(tmp_path):
    """قارئ أعمى قبل الحَكَم: المقروء حرفًا أجنبيًا يعود إلى الرسّام مرة واحدة ولا تُحسب عليه جولة تحكيم؛ بعد قراءتين يمضي
    الخط إلى الحَكَم والقراءة أمامه."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _blind_pipeline(tmp_path)
    ws, out = _after_critique(pipe, b)
    assert out.code == AWAIT_MODEL and "القراءة العمياء" in out.message and not (ws.work / "REQUEST-judge.md").exists()
    req = (ws.work / "REQUEST-blind.md").read_text(encoding="utf-8")
    assert b.name_ar not in req and "جملة 1" not in req and "م1" not in req  # لا اسم ولا فكرة: القراءة عمياء فعلًا
    _blind(ws, c2="ö")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "REQUEST-refine-blind.md" in out.message and not (ws.work / "REQUEST-judge.md").exists()
    refine = (ws.work / "REQUEST-refine-blind.md").read_text(encoding="utf-8")
    assert "## c2" in refine and "حرف غير عربي «ö» بقوة 3 من 3" in refine and "## c1" not in refine
    assert pipe.run(b).code == AWAIT_MODEL and not any((ws.work / "judge").iterdir())  # idempotent: لم يُعَد الرسم بعد
    (ws.concepts_dir / "c2.svg").write_text(rect_svg(40, 90, 176, 76), encoding="utf-8")  # الرسّام عدّل c2
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "القراءة العمياء" in out.message  # قراءة ثانية للمحتوى الجديد
    _blind(ws, c2="ö")  # ما زال يُقرأ خطأ: استُنفدت القراءتان، فيحكم الحَكَم والقراءة أمامه
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message
    judge_req = (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")
    assert "قارئ أعمى مستقل (بلا اسم ولا فكرة) رأى «حرف ö»" in judge_req
    _judge(ws, score=3)  # دون العتبة: صقل الحَكَم يغيّر المحتوى، ولا قراءة ثالثة
    assert "REQUEST-refine.md" in pipe.run(b).message
    (ws.concepts_dir / "c2.svg").write_text(rect_svg(40, 96, 176, 64), encoding="utf-8")
    out = pipe.run(b)
    assert "الحَكَم" in out.message and len(list((ws.work / "blind").glob("*.yaml"))) == 2


def test_blind_reading_clean_goes_straight_to_judge_and_resets_with_owner_redraw(tmp_path):
    b = brief_from_dict(BRIEF, source="b.yaml")
    pipe = _blind_pipeline(tmp_path)
    ws, _out = _after_critique(pipe, b)
    _blind(ws)
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and "الحَكَم" in out.message and not (ws.work / "REQUEST-refine-blind.md").exists()
    _judge(ws)
    assert pipe.run(b).code == AWAIT_OWNER
    record_decision(ws, "c1", Verdict.REJECTED, "لا يعبّر")
    assert "REQUEST-refine-owner.md" in pipe.run(b).message
    (ws.concepts_dir / "c1.svg").write_text(rect_svg(48, 48, 160, 160), encoding="utf-8")
    out = pipe.run(b)  # رسم المالك الجديد يبدأ دورة قراءة جديدة: القراءات السابقة مؤرشفة مع الأحكام
    assert "القراءة العمياء" in out.message and not any((ws.work / "blind").glob("*.yaml"))
    assert any((ws.work / "history").glob("blind-owner-*/*.yaml")) and any((ws.work / "history").glob("judge-owner-*/*.yaml"))


def test_requests_state_the_stroke_floor_the_audit_enforces(tmp_path):
    """قاعدة السماكة نص واحد عند الرسّام والحَكَم والصقل: الحَكَم لا يطلب ما يردّه الفحص ولا يقيس وزن الرمز بعينة الكلمة."""
    from sima.domain import Medium

    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws, _out = _after_critique(pipe, b)
    judge_req = (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")
    assert "قواعد الأداة الملزمة" in judge_req and "24 وحدة على لوحة 256" in judge_req and "لا بوزن الخط المطلق" in judge_req
    assert "قارئ أعمى" not in judge_req  # البوابة غير مفعّلة في هذا الخط
    _judge(ws, score=3)
    pipe.run(b)
    assert "24 وحدة على لوحة 256" in (ws.work / "REQUEST-refine.md").read_text(encoding="utf-8")
    pipe._write_request_diverge(ws, b, Medium.ABSTRACT_MARK, [])
    diverge = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    assert "قواعد الأداة الملزمة" in diverge and "قارئ أعمى قبل الحَكَم" not in diverge
    word = "\n".join(Pipeline._tool_rules(Medium.WORDMARK))
    assert "بارتفاع 96 بكسل" in word and "للرمز المصغّر" in word  # الكلمة تُفحص عند حجم الترويسة فيصحّ فيها الخط الرفيع
    blind_pipe = _blind_pipeline(tmp_path / "b")
    ws2 = blind_pipe.run(b).workspace
    assert "قارئ أعمى قبل الحَكَم" in (ws2.work / "REQUEST-diverge.md").read_text(encoding="utf-8")


def test_blind_gate_skips_content_the_judge_already_judged(tmp_path):
    """إصدار وصل إلى المالك قبل تفعيل البوابة لا يعود إلى القارئ: الحكم القائم على المحتوى نفسه يكفي، والبطاقة تبقى."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, old = _pipeline(tmp_path)
    ws = old.run(b).workspace
    _to_owner(old, b, ws)
    out = _blind_pipeline(tmp_path).run(b)
    assert out.code == AWAIT_OWNER and not (ws.work / "REQUEST-blind.md").exists()


def test_drop_in_critique_is_an_opinion_not_a_pending_edit(tmp_path):
    """الرسّام يسقط مفهومًا بلا تعديل: الخط يمضي ولا يعيد طلب النقد نفسه (كان يدور حتى السقف)."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    assert "الجولة 1" in pipe.run(b).message
    verdicts = {f"c{n}": {"action": "keep"} for n in range(1, 6)} | {"c2": {"action": "drop"}}
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": verdicts}), encoding="utf-8")
    out = pipe.run(b)
    assert "لم تُنفَّذ" not in out.message and ws.done("critique")


def test_render_cache_rechecks_when_palette_changes(tmp_path):
    """إصدار يرث علامة بلون علامة جديد يُعاد فحصه ولا يعيد تباين سلفه من المخبأ («مرصد» v2، 2026-11-18)."""
    b = brief_from_dict(BRIEF, source="b.yaml")
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    svgs = _five_distinct()
    _write_concepts(ws, svgs)
    concepts, _ = protocol.parse_concepts(ws)
    pale = brief_from_dict({**BRIEF, "palette": {**BRIEF["palette"], "paper": "#F2EFE8", "brand": "#08A177"}}, source="b.yaml")
    first = pipe._stage_render(ws, pale, concepts, svgs)
    assert first["c1"].metrics["contrast_brand_on_paper"] < 3.0 and not first["c1"].passed
    dark = brief_from_dict({**BRIEF, "palette": {**BRIEF["palette"], "paper": "#F2EFE8", "brand": "#089770"}}, source="b.yaml")
    second = pipe._stage_render(ws, dark, concepts, svgs)
    assert second["c1"].metrics["contrast_brand_on_paper"] >= 3.0
    assert not any("لون العلامة" in f for f in second["c1"].findings)
