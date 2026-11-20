"""المرحلة 2 من إصلاح مراجعة الأتمتة (2026-11-14): متانة ما يكتبه النموذج وما يُطلب منه.

كل اختبار باسم بنده في `docs/automation-review-2026-11-14.md` (خ1 م3 خ3 إلى خ7 خ10 خ12 إلى خ16)، ويسقط على الشيفرة السابقة.
"""
from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from sima import config
from sima import env as envmod
from sima.adapters.geometry import build_svg
from sima.domain import Medium, Verdict, brief_from_dict
from sima.services import autopilot, blind, live_preview, protocol, thumbs
from sima.services import judge as judging
from sima.services.autopilot import ModelResult, run_until_owner
from sima.services.inbox import owner_inbox
from sima.services.pipeline import AWAIT_MODEL, AWAIT_OWNER, FIX_REQUEST, Outcome, Pipeline, record_decision
from sima.services.shaping import ShapingService

from .fakes import FakeRenderer, rect_svg
from .test_autopilot import FakeModel, _ws
from .test_domain_ledger_workspace import BRIEF
from .test_pipeline import NoShaper, _after_critique, _blind, _blind_pipeline, _five_distinct, _judge, _pipeline, _write_concepts
from .test_thumbs import _concepts, _ideas, _pipe, _read


def _brief():
    return brief_from_dict(BRIEF, source="b.yaml")


# ----- خ1: ملف يكتبه النموذج بشكل غير متوقع يعود إليه مشكلةً ولا يُسقط الخط -----

@pytest.mark.parametrize("text", ["- id: i1\n  family: literal\n", "ideas: نص لا قائمة\n", "ideas:\n  - i1\n  - i2\n", "ideas: [{id: i1}]\n",
                                  "ideas: [unclosed\n"])
def test_kh1_malformed_ideas_file_returns_to_the_model_not_a_crash(tmp_path, text):
    b = _brief()
    pipe = _pipe(tmp_path)
    ws = pipe.run(b).workspace
    (ws.work / "ideas.yaml").write_text(text, encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and out.request == FIX_REQUEST and "work/ideas.yaml" in out.message
    assert "work/ideas.yaml" in (ws.work / FIX_REQUEST).read_text(encoding="utf-8")
    with pytest.raises(protocol.FormatError):
        protocol.read_ideas(ws)  # من يعرض فقط يلتقط نوعًا واحدًا


@pytest.mark.parametrize("text", ["- c1: {action: keep}\n", "round: 1\nverdicts:\n  c1: keep\n", "round: 1\nverdicts: [c1, c2]\n",
                                  "verdicts: {c1: {action: maybe}}\n", "verdicts: {c1: [unclosed\n"])
def test_kh1_malformed_critique_round_is_asked_again_with_its_problems(tmp_path, text):
    b = _brief()
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    assert "الجولة 1" in pipe.run(b).message
    (ws.critique_dir / "round1.yaml").write_text(text, encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and out.request == "REQUEST-critique-r1.md" and "لا تُقرأ صيغته" in out.message
    req = (ws.work / "REQUEST-critique-r1.md").read_text(encoding="utf-8")
    assert "مشاكل في ملف هذه الجولة" in req and "work/critique/round1.yaml" in req and not ws.done("critique")
    (ws.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {"c1": {"action": "keep"}}}), encoding="utf-8")
    assert "الحَكَم" in pipe.run(b).message  # صُحّح الملف فمضى الخط


@pytest.mark.parametrize("text", ["- c1\n- c2\n", "verdicts: [c1]\n", "verdicts: {c1: {scores: [4, 4]}}\n", "verdicts: {c1: keep}\n"])
def test_kh1_malformed_judge_file_is_a_problem_not_a_crash(tmp_path, text):
    ws = _ws(tmp_path)
    judging.judge_dir(ws).mkdir()
    judging.judge_path(ws, "d1").write_text(text, encoding="utf-8")
    j = judging.read(ws, "d1", ["c1"])
    assert j is not None and j.problems and not j.scores


def test_kh1_malformed_concepts_file_does_not_break_the_checks_around_it(tmp_path):
    b = _brief()
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    (ws.work / "concepts.yaml").write_text("concepts:\n  - c1\n  - {id: c2, family: literal, medium: poster}\n", encoding="utf-8")
    concepts, problems = protocol.parse_concepts(ws)
    assert concepts == [] and "البند 1 ليس خريطة" in problems[0] and "medium «poster»" in problems[1]
    assert thumbs.concept_problems(ws) == [] and protocol.compile_marks(ws, build_svg) == {}
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and out.request == FIX_REQUEST


# ----- م3: ملف معطوب في مشروع واحد لا يُسقط وارد المنصة كله -----

def test_m3_one_broken_project_does_not_take_the_inbox_down(tmp_path):
    from .test_inbox import CONCEPTS, _reached_owner

    for name in ("good", "half", "bent"):
        v = tmp_path / name / "v1"
        (v / "work" / "concepts").mkdir(parents=True)
        (v / "run.json").write_text(json.dumps({"project": name, "key": "k-s1", "brief_hash": "k", "seed": 1, "version": 1,
                                                "brief_source": "b.yaml", "closed": False}), encoding="utf-8")
        (v / "preview.html").write_text("<html></html>", encoding="utf-8")
        (v / "work" / "concepts.yaml").write_text(CONCEPTS, encoding="utf-8")
        (v / "work" / "concepts" / "w1.svg").write_text("<svg/>", encoding="utf-8")
        _reached_owner(v)
    (tmp_path / "half" / "v1" / "run.json").write_text('{"project": "half", "key": ', encoding="utf-8")  # نصف مكتوب
    (tmp_path / "bent" / "v1" / "work" / "concepts.yaml").write_text("- w1\n- w2\n", encoding="utf-8")  # صيغة لا تُقرأ
    items = {i["project"]: i for i in owner_inbox(tmp_path)}
    assert items["good"]["kind"] == "concepts"
    for name in ("half", "bent"):
        assert items[name]["kind"] == "stalled" and items[name]["problem"] and "تعذّرت قراءة" in items[name]["message"]
        assert items[name]["version"] == 1 and items[name]["title"] and items[name]["after"]


# ----- خ3: قيم family مذكورة للنموذج، وخلل الصيغة يعود بطلب ضيّق بجهد متوسط -----

def test_kh3_requests_name_the_family_values_the_reader_accepts(tmp_path):
    b = _brief()
    pipe = _pipe(tmp_path)
    ws = pipe.run(b).workspace
    req = (ws.work / thumbs.REQUEST).read_text(encoding="utf-8")
    pipe._write_request_diverge(ws, b, Medium.ABSTRACT_MARK, [])
    diverge = (ws.work / "REQUEST-diverge.md").read_text(encoding="utf-8")
    for text in (req, diverge):
        assert all(f"`{v}`" in text for v in ("literal", "metaphorical", "abstract", "typographic", "symbolic"))


def test_kh3_a_bad_item_gets_a_narrow_fix_request_not_the_creative_request_again(tmp_path, monkeypatch):
    from sima.adapters import claude_model

    b = _brief()
    pipe = _pipe(tmp_path)
    ws = pipe.run(b).workspace
    _ideas(ws)
    creative = (ws.work / thumbs.REQUEST).read_text(encoding="utf-8")
    data = yaml.safe_load((ws.work / "ideas.yaml").read_text(encoding="utf-8"))
    data["ideas"][7]["family"] = "metaphoric"  # الخطأ الذي كلّف 3.05$ واستُبدلت فيه أربع أفكار
    (ws.work / "ideas.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    out = pipe.run(b)
    assert out.code == AWAIT_MODEL and out.request == FIX_REQUEST
    assert (ws.work / thumbs.REQUEST).read_text(encoding="utf-8") == creative  # الطلب الإبداعي لم يُعَد
    fix = (ws.work / FIX_REQUEST).read_text(encoding="utf-8")
    assert "الفكرة i7: family «metaphoric» ليست من القيم المقبولة" in fix and "`metaphorical`" in fix
    assert "لا تغيّر أي بند آخر" in fix and "الفكرة i3" not in fix
    monkeypatch.setattr(claude_model, "_env", lambda k, d: d)
    flags = claude_model.design_flags(FIX_REQUEST)
    assert flags == ["--model", claude_model.DRAWER_MODEL, "--effort", "medium"]  # الرسّام بجهد الصقل لا جهد الأفكار
    assert claude_model.design_flags(thumbs.REQUEST)[-1] == "high"
    data["ideas"][7]["family"] = "metaphorical"
    (ws.work / "ideas.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert pipe.run(b).request == thumbs.BLIND_REQUEST  # صُحّح البند فمضى الخط إلى قراءة المصغّرات


# ----- خ4: الحَكَم يُعطى ما ردّه القارئ، والمفهوم الذي استُبدلت فكرته يُقرأ من جديد -----

def test_kh4_judge_request_lists_the_ideas_the_blind_reader_blocked(tmp_path):
    b = _brief()
    pipe = _pipe(tmp_path)
    ws = pipe.run(b).workspace
    _ideas(ws)
    pipe.run(b)
    _read(ws, blocked=("i0", "i1"))
    pipe.run(b)
    _concepts(ws, ["i6", "i2", "i3", "i4", "i5"])
    assert "الجولة 1" in pipe.run(b).message
    pipe._write_request_judge(ws, b, protocol.read_concepts(ws), {}, "d1", [])
    req = (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")
    assert "أفكار المصغّرات عند القارئ الأعمى" in req and "- i0: رأى «حرف لاتيني»" in req and "فلا تسمِّ" in req
    assert "المجتازة: " in req and "i6" in req.split("المجتازة: ")[1].splitlines()[0]


def test_kh4_a_concept_whose_idea_was_replaced_is_read_again_after_the_rounds_are_spent(tmp_path):
    b = _brief()
    pipe = _blind_pipeline(tmp_path)
    ws, _out = _after_critique(pipe, b)
    _blind(ws, c2="ö")
    assert "REQUEST-refine-blind.md" in pipe.run(b).message
    (ws.concepts_dir / "c2.svg").write_text(rect_svg(40, 90, 176, 76), encoding="utf-8")
    pipe.run(b)
    _blind(ws)  # القراءة الثانية: استُنفدت القراءتان
    assert pipe.run(b).request == "REQUEST-judge.md"
    _judge(ws, score=3)
    assert "REQUEST-refine.md" in pipe.run(b).message
    # صقل الحَكَم: c3 عُدّل شكله وحده، وc2 استُبدلت فكرته بفكرة لم تمرّ بمصغّرة ولا بقارئ
    (ws.concepts_dir / "c3.svg").write_text(rect_svg(96, 40, 64, 176), encoding="utf-8")
    (ws.concepts_dir / "c2.svg").write_text(rect_svg(40, 96, 176, 64), encoding="utf-8")
    data = yaml.safe_load((ws.work / "concepts.yaml").read_text(encoding="utf-8"))
    data["concepts"][1] |= {"sentence": "فكرة جديدة من خارج الملف", "idea_id": None}
    (ws.work / "concepts.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    out = pipe.run(b)
    assert out.request == blind.REQUEST, out.message
    req = (ws.work / blind.REQUEST).read_text(encoding="utf-8")
    assert "## c2" in req and "## c3" not in req and "## c1" not in req  # المستبدَل وحده
    assert pipe.run(b).request == blind.REQUEST  # idempotent حتى تُكتب القراءة
    concepts = protocol.read_concepts(ws)
    dg = protocol.merged_digest(protocol.read_concept_svgs(ws, concepts), protocol.read_small_svgs(ws, concepts))
    blind.path(ws, dg).write_text(yaml.safe_dump({"digest": dg, "readings": {
        "c2": {"seen": "حرف لاتيني", "reads_as": "ö", "kind": "foreign_letter", "strength": 3}}}, allow_unicode=True), encoding="utf-8")
    out = pipe.run(b)
    assert out.request == "REQUEST-judge.md", out.message  # بعد الاستنفاد: القراءة أمام الحَكَم بلا صقل آخر
    assert "## c2" in (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")
    assert "قارئ أعمى مستقل (بلا اسم ولا فكرة) رأى «حرف لاتيني»" in (ws.work / "REQUEST-judge.md").read_text(encoding="utf-8")


# ----- خ5: قوالب الملفات بأول معرّف فعلي لا بـ c1 -----

def test_kh5_templates_use_a_real_id(tmp_path):
    ws = _ws(tmp_path)
    blind.write_request(ws, ["i0", "i1"], "d1", [], kind=thumbs.KIND, name=thumbs.BLIND_REQUEST, images=lambda iid: [])
    text = (ws.work / thumbs.BLIND_REQUEST).read_text(encoding="utf-8")
    assert "readings:\n  i0:" in text and "c1" not in text
    b = _brief()
    _r, pipe = _pipeline(tmp_path / "w")
    ws2 = pipe.run(b).workspace
    svgs = {f"w{n}": s for n, s in enumerate(_five_distinct().values(), 1)}
    _write_concepts(ws2, svgs)
    pipe.run(b)
    assert "verdicts:\n  w1: {action" in (ws2.work / "REQUEST-critique-r1.md").read_text(encoding="utf-8")
    (ws2.critique_dir / "round1.yaml").write_text(yaml.safe_dump({"round": 1, "verdicts": {"w1": {"action": "keep"}}}), encoding="utf-8")
    pipe.run(b)
    assert "verdicts:\n  w1:\n" in (ws2.work / "REQUEST-judge.md").read_text(encoding="utf-8")


# ----- خ6: كل مرجع في طلب مسار يُحلّ من جذر المستودع -----

def test_kh6_every_reference_a_request_cites_resolves_from_the_repo_root(tmp_path):
    b = _brief()
    pipe = Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml",
                    build_mark=build_svg, thumbs_gate=True, blind_gate=True)
    ws = pipe.run(b).workspace
    _write_concepts(ws, _five_distinct())
    concepts = protocol.read_concepts(ws)
    pipe._write_request_diverge(ws, b, Medium.ABSTRACT_MARK, [])
    pipe._write_request_critique(ws, b, concepts, {}, 1)
    pipe._write_request_judge(ws, b, concepts, {}, "d1", [])
    pipe._write_request_refine(ws, b, concepts, "REQUEST-refine.md", "صقل", [("c1", ["عيب"], "اتجاه", False)])
    seen = 0
    for req in sorted(ws.work.glob("REQUEST-*.md")):
        for ref in re.findall(r"`([^`\s]*references/[^`\s]+\.md)`", req.read_text(encoding="utf-8")):
            seen += 1
            assert (config.ROOT / ref).is_file(), f"{req.name}: {ref}"
    assert seen >= 12 and len(list(ws.work.glob("REQUEST-*.md"))) == 5


# ----- خ7: جولات النقد الإضافية بسقف، ثم يُعرض الفشل على المالك -----

def test_kh7_forced_critique_rounds_are_capped_then_the_owner_sees_the_failure(tmp_path):
    b = _brief()
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    svgs = _five_distinct()
    svgs["c2"] = rect_svg(40, 120, 176, 8)  # يردّه فحص السماكة ولا يصلحه الرسّام
    _write_concepts(ws, svgs)
    pipe.run(b)
    keep = yaml.safe_dump({"round": 1, "verdicts": {"c2": {"action": "keep"}}})
    names = []
    for n in range(1, config.MAX_CRITIQUE_ROUNDS + config.FORCED_CRITIQUE_ROUNDS + 1):
        (ws.critique_dir / f"round{n}.yaml").write_text(keep, encoding="utf-8")
        out = pipe.run(b)
        names.append(out.request)
        if n == 1:  # جولة النقد الثانية تُطلب بتغيّر الرسم؛ هنا لم يتغيّر فتنتهي الجولات وتبدأ الإضافية
            assert out.code == AWAIT_MODEL
    assert names[:3] == ["REQUEST-critique-r2.md", "REQUEST-critique-r3.md", "REQUEST-critique-r4.md"] or names[0] == "REQUEST-critique-r2.md"
    forced = [p for p in sorted(ws.work.glob("REQUEST-critique-r*.md")) if "جولة إضافية" in p.read_text(encoding="utf-8")]
    assert len(forced) == config.FORCED_CRITIQUE_ROUNDS
    head = forced[0].read_text(encoding="utf-8").splitlines()[0]
    assert f"جولة إضافية 1 من {config.FORCED_CRITIQUE_ROUNDS}" in head and " من 2 من" not in head
    assert out.code == AWAIT_OWNER and "c2" in out.message and "سماكة" in out.message and "--medium abstract_mark" in out.message
    n_requests = len(list(ws.work.glob("REQUEST-critique-r*.md")))
    again = pipe.run(b)
    assert again.code == AWAIT_OWNER and len(list(ws.work.glob("REQUEST-critique-r*.md"))) == n_requests  # لا طلب جديد بعد السقف
    record_decision(ws, None, Verdict.SWITCH, "ارسم من جديد")  # مخرج المالك: رسم جديد يبدأ الدورة من أولها
    assert pipe.run(b).request == "REQUEST-diverge.md"


# ----- خ10: مفاتيح الإيقاف تُقرأ من `.env` كما تُقرأ من البيئة، وبلا إعدادات Django -----

def test_kh10_switches_are_read_from_dotenv_and_the_environment_wins(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# تعليق\nSIMA_THUMBS=0\nSIMA_BLIND = 0\nSIMA_COST_REF_USD=7\n", encoding="utf-8")
    assert envmod.load(f, {})["SIMA_THUMBS"] == "0" and envmod.load(f, {"SIMA_THUMBS": "1"})["SIMA_THUMBS"] == "1"
    real = envmod.load
    with pytest.MonkeyPatch.context() as m:
        m.setattr(envmod, "load", lambda path, environ=None: real(f, {}))
        importlib.reload(config)
        try:
            assert not config.THUMBS_GATE and not config.BLIND_GATE and config.COST_REF_USD == 7.0
        finally:
            m.undo()
            importlib.reload(config)


def test_kh10_model_and_embed_switches_do_not_need_django_settings():
    code = ("import sys\nfrom sima.adapters import claude_model, local_embed\nclaude_model.enabled(); local_embed.enabled(); "
            "claude_model.max_calls()\nassert 'sima.web.settings' not in sys.modules and 'django' not in sys.modules\n")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", check=False)
    assert p.returncode == 0, p.stderr


# ----- خ12: الحد الأدنى للاستدعاء بحسب نوع الطلب -----

def test_kh12_a_drawing_request_is_not_started_on_a_budget_that_cannot_finish_it(tmp_path):
    assert autopilot.min_call_for("REQUEST-thumbs.md") == 3.0 and autopilot.min_call_for("REQUEST-diverge.md") == 1.5
    assert autopilot.min_call_for("REQUEST-refine-owner.md") == 0.75 and autopilot.min_call_for("REQUEST-critique-r2.md") == 0.25
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-diverge.md").write_text("طلب", encoding="utf-8")
    model = FakeModel(cost=0.1)
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, "بانتظار الرسم", ws, request="REQUEST-diverge.md"), model, max_calls=5, max_usd=1.0)
    assert model.calls == [] and out.code == autopilot.STOPPED and "لا يكفي استدعاءً لـREQUEST-diverge.md" in out.message
    ws2 = _ws(tmp_path / "b")
    (ws2.work / "REQUEST-blind.md").write_text("طلب", encoding="utf-8")
    steps = iter([Outcome(AWAIT_MODEL, "قراءة", ws2, request="REQUEST-blind.md"), Outcome(AWAIT_OWNER, "جاهز", ws2)])
    cheap = FakeModel(cost=0.1)
    assert run_until_owner(lambda: next(steps), cheap, max_calls=5, max_usd=1.0).code == AWAIT_OWNER and cheap.calls == ["REQUEST-blind.md"]


# ----- خ13: عدّاد المعاينات لكل استدعاء، والحد مفروض -----

def test_kh13_preview_count_is_per_call_and_the_limit_is_enforced(tmp_path):
    from .test_live_preview import FakeRenderer as CountingRenderer
    from .test_live_preview import build, touch

    d = tmp_path / "concepts"
    d.mkdir()
    spec = d / "c1.mark.yaml"
    note = d / ("c1" + live_preview.LIMIT_SUFFIX)
    touch(spec, "a", 1_000)
    r = CountingRenderer()
    lp = live_preview.LivePreview(r, build)
    lp.begin(tmp_path)
    t = 2_000
    for n in range(1, config.LIVE_PREVIEW_MAX + 1):
        touch(spec, "a" * (n + 1), t := t + 1_000)
        lp(tmp_path)
        assert lp(tmp_path) == ["concepts/c1"] and f"c1 #{n}" in r.calls[-1][0]
    touch(spec, "zzzzzzzz", t := t + 1_000)  # المعاينة الخامسة في الاستدعاء نفسه: لا تُصيَّر ويُكتب سببها
    lp(tmp_path)
    assert lp(tmp_path) == [] and len(r.calls) == config.LIVE_PREVIEW_MAX
    assert note.is_file() and not live_preview.preview_path(spec).exists()
    lp.begin(tmp_path)  # استدعاء جديد في الأمر نفسه: العدّاد يبدأ من صفر
    assert not note.exists()
    touch(spec, "new", t + 1_000)
    lp(tmp_path)
    assert lp(tmp_path) == ["concepts/c1"] and "c1 #1" in r.calls[-1][0]
    assert f"`<id>{live_preview.LIMIT_SUFFIX}`" in "\n".join(live_preview.lines())


def test_kh13_autopilot_marks_the_start_of_each_call(tmp_path):
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")
    events: list[str] = []

    class Watch:
        def begin(self, work):
            events.append("begin")

        def __call__(self, work):
            events.append("tick")

    steps = iter([Outcome(AWAIT_MODEL, "أ", ws), Outcome(AWAIT_MODEL, "ب", ws), Outcome(AWAIT_OWNER, "جاهز", ws)])
    run_until_owner(lambda: next(steps), FakeModel(cost=0.1), max_calls=5, watch=Watch())
    assert events == ["begin", "tick", "begin", "tick"]


# ----- خ14: مجلدا الحَكَم والقارئ مقفلان على الرسّام من أول استدعاء -----

def test_kh14_judge_and_blind_folders_are_locked_before_they_are_first_used(tmp_path):
    from sima.adapters import claude_model

    b = _brief()
    _r, pipe = _pipeline(tmp_path)
    ws = pipe.run(b).workspace
    assert (ws.work / "judge").is_dir() and (ws.work / "blind").is_dir()  # منذ فتح الإصدار
    v = tmp_path / "repo" / "out" / "p" / "v1"
    (v / "work").mkdir(parents=True)
    (v / "work" / "REQUEST-diverge.md").write_text("r", encoding="utf-8")
    m = claude_model.ClaudeCodeModel(root=tmp_path / "repo", budget_usd=1, timeout_s=60)
    assert {p.name for p in m._locked(v / "work" / "REQUEST-diverge.md", v)} == {"REQUEST-diverge.md", "judge", "blind"}
    cmd = m.command(v / "work" / "REQUEST-diverge.md", v)
    denied = cmd[cmd.index("--disallowedTools"):]
    assert {"Write(./out/p/v1/work/judge/**)", "Edit(./out/p/v1/work/judge/**)", "Write(./out/p/v1/work/blind/**)"} <= set(denied)
    judge = m.command(v / "work" / "REQUEST-judge.md", v)
    assert "Write(./out/p/v1/work/judge/**)" not in judge[judge.index("--disallowedTools"):]  # الحَكَم يكتب مجلده


# ----- خ15: مجلد مؤقت لكل استدعاء -----

def test_kh15_each_call_gets_its_own_temp_folder(tmp_path, monkeypatch):
    import contextlib

    from sima.adapters import claude_model, win_isolation

    root = tmp_path
    v = root / "out" / "p" / "v1"
    (v / "work").mkdir(parents=True)
    req = v / "work" / "REQUEST-diverge.md"
    req.write_text("r", encoding="utf-8")
    base = root / "var" / claude_model.TMP_DIR
    temps: list[Path] = []

    def run_low(cmd, cwd, timeout, env=None, tick=None):
        tmp = Path(env["TEMP"])
        assert tmp.is_dir() and tmp.parent == base and env["TMP"] == env["TEMP"]
        if not temps:  # استدعاء مشروع آخر يبدأ وينتهي في أثناء هذا: مؤقت هذا يبقى
            temps.append(tmp)
            m._spawn(["x"], req, v, None)
            assert tmp.is_dir()
        else:
            temps.append(tmp)
        return subprocess.CompletedProcess(cmd, 0, "{}", "")

    monkeypatch.setattr(claude_model, "isolation", lambda: "low")
    monkeypatch.setattr(win_isolation, "protect", lambda paths: None)
    monkeypatch.setattr(win_isolation, "write_window", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(win_isolation, "run_low", run_low)
    m = claude_model.ClaudeCodeModel(root=root, budget_usd=1, timeout_s=60)
    m._spawn(["x"], req, v, None)
    assert len(temps) == 2 and temps[0] != temps[1] and not base.exists()  # كلٌّ بمجلده، ويزول الأب حين يفرغ


# ----- خ16: كلفة المقطوع لا تُسجَّل صفرًا، ونقطة المخرجات بسطر نسبة -----

def test_kh16_a_timed_out_call_is_charged_its_reservation_as_an_upper_bound(tmp_path, monkeypatch):
    from sima.adapters import claude_model

    root = tmp_path
    v = root / "out" / "p" / "v1"
    (v / "work").mkdir(parents=True)
    req = v / "work" / "REQUEST-diverge.md"
    req.write_text("r", encoding="utf-8")
    monkeypatch.setattr(claude_model, "_env", lambda k, d: d)
    monkeypatch.setattr(claude_model, "isolation", lambda: "")
    m = claude_model.ClaudeCodeModel(root=root, budget_usd=5, timeout_s=60)

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(["claude"], 60)

    monkeypatch.setattr(m, "_spawn", timeout)
    res = m.run(req, v, cap_usd=2.0)
    assert not res.ok and res.cost_usd == 2.0 and not res.cost_known and "حدًّا أعلى" in res.summary
    monkeypatch.setattr(m, "_spawn", lambda *a, **k: subprocess.CompletedProcess(["claude"], 1, "", "سقط قبل البدء"))
    res = m.run(req, v, cap_usd=2.0)
    assert not res.ok and res.cost_usd == 0.0 and not res.cost_known
    done = json.dumps({"result": "تم", "total_cost_usd": 0.4})
    monkeypatch.setattr(m, "_spawn", lambda *a, **k: subprocess.CompletedProcess(["claude"], 0, done, ""))
    res = m.run(req, v, cap_usd=2.0)
    assert res.ok and res.cost_usd == 0.4 and res.cost_known
    # وسقف الأمر يحسب المقطوع: استدعاء قُطع بمحجوزه يُسجَّل بكلفته في سجل الإصدار
    ws = _ws(tmp_path / "auto")
    (ws.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")

    class Cut:
        def run(self, request, version_root, *, cap_usd, tick=None):
            return ModelResult(False, cap_usd, 2700.0, "تجاوز المهلة", reserved_usd=cap_usd, cost_known=False)

    run_until_owner(lambda: Outcome(AWAIT_MODEL, "بانتظار", ws), Cut(), max_calls=3, max_usd=4.0)
    row = json.loads((ws.root / "model_calls.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["cost_usd"] == 4.0 and row["cost_known"] is False


def test_kh16_outputs_commit_ends_with_the_models_that_actually_worked(tmp_path):
    from sima.adapters.auto_deliver import _model_name, co_authors, commit_outputs

    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    v = tmp_path / "out" / "p" / "v1"
    v.mkdir(parents=True)
    (v / "run.json").write_text(json.dumps({"project": "p", "version": 1}), encoding="utf-8")
    calls = [{"ok": True, "model": "claude-fable-5-2", "models_used": ["claude-fable-5-2", "claude-haiku-5-5-20261001"]},
             {"ok": True, "model": "opus", "models_used": []}, {"ok": False, "model": "sonnet", "models_used": ["claude-sonnet-5-5"]},
             {"ok": True, "model": "default", "models_used": []}]
    (v / "model_calls.jsonl").write_text("\n".join(json.dumps(c) for c in calls) + "\nسطر معطوب\n", encoding="utf-8")
    assert _model_name("claude-opus-5-5[1m]") == "Claude Opus 5.5"
    assert co_authors(v) == [f"Co-Authored-By: {n} <noreply@anthropic.com>" for n in ("Claude Fable 5.2", "Claude Haiku 5.5", "Claude Opus")]
    assert "أُودعت" in commit_outputs(v, tmp_path)
    body = git("log", "-1", "--format=%B").strip().splitlines()
    assert body[-3:] == co_authors(v) and body[-4] == ""
    plain = tmp_path / "out" / "q" / "v1"  # إصدار بلا استدعاء نموذج: لا سطر نسبة لنموذج لم يعمل
    plain.mkdir(parents=True)
    (plain / "run.json").write_text(json.dumps({"project": "q", "version": 1}), encoding="utf-8")
    commit_outputs(plain, tmp_path)
    assert "Co-Authored-By" not in git("log", "-1", "--format=%B")
