"""مجموعة تقييم الرسّام: الخط نفسه يُشغَّل على حالة بطابع ثابت ويقف عند نقطة التقييم، والأرقام مما كتبه الخط. نموذج زائف بلا كلفة."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sima import config
from sima.cli import EVAL_DIR, build_parser
from sima.domain import brief_from_dict
from sima.services import drawer_eval as ev
from sima.services import style
from sima.services.autopilot import ModelResult, run_until_owner
from sima.services.pipeline import AWAIT_OWNER, Pipeline
from sima.services.shaping import ShapingService
from sima.services.workspace import open_workspace

from .fakes import FakeRenderer, rect_svg
from .test_domain_ledger_workspace import BRIEF
from .test_pipeline import NoShaper, _judge
from .test_thumbs import _concepts, _ideas, _read

FIVE = {
    "c1": "{rect: [40, 40, 176, 176]}",
    "c2": "{rect: [40, 100, 176, 56]}",
    "c3": "{rect: [100, 40, 56, 176]}",
    "c4": "{union: [{rect: [40, 40, 80, 176]}, {rect: [136, 40, 80, 176]}]}",
    "c5": "{union: [{rect: [40, 40, 176, 60]}, {rect: [40, 156, 176, 60]}]}",
}


def _build(text: str, title: str) -> str:
    """بديل أداة البناء: مستطيلات فقط، بصيغة يرسمها المصيّر الزائف (مسارات skia لا يرسمها)."""
    mark = yaml.safe_load(text)["mark"]
    first, *rest = [mark["rect"]] if "rect" in mark else [r["rect"] for r in mark["union"]]
    return rect_svg(*first, "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#000000"/>' for x, y, w, h in rest))


def _pipe(tmp_path):
    return Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, tmp_path / "out", catalog=[], decide_cmd="sima decide b.yaml",
                    build_mark=_build, thumbs_gate=True)


class ScriptedDrawer:
    """يكتب ما يطلبه كل طلب كما يكتبه الرسّام والقارئ والحَكَم، بكلفة معلنة."""

    def __init__(self, ws, judge_score: int):
        self.ws, self.judge_score, self.calls = ws, judge_score, []

    def run(self, request: Path, version_root: Path, *, cap_usd: float, tick=None) -> ModelResult:
        name = request.name
        self.calls.append(name)
        if name == "REQUEST-thumbs.md":
            _ideas(self.ws)
        elif name == "REQUEST-blind-thumbs.md":
            _read(self.ws, blocked=("i0", "i1"))
        elif name == "REQUEST-diverge.md":
            _concepts(self.ws, ["i6", "i2", "i3", "i4", "i5"])
            for cid, spec in FIVE.items():  # بناء _concepts واحد للخمسة فتتطابق؛ الفحوص تريد خمسة متباعدة
                (self.ws.concepts_dir / f"{cid}.mark.yaml").write_text(f"mark: {spec}", encoding="utf-8")
        elif name.startswith("REQUEST-critique"):
            (self.ws.critique_dir / "round1.yaml").write_text(
                yaml.safe_dump({"round": 1, "verdicts": {f"c{n}": {"action": "keep"} for n in range(1, 6)}}), encoding="utf-8")
        elif name == "REQUEST-judge.md":
            _judge(self.ws, self.judge_score, c4=5)
        else:
            raise AssertionError(f"طلب بعد نقطة التقييم: {name}")
        return ModelResult(True, 1.25, 10.0, "تم", model="drawer", models_used=("claude-x",), reserved_usd=cap_usd)


def _case(tmp_path):
    case = ev.Case("demo", brief_from_dict(BRIEF, source="b.yaml"), ("s2",))
    ws = open_workspace(tmp_path / "out", case.brief)
    ev.prepare(ws, case)
    return case, ws


def test_real_cases_are_valid_distinct_and_permitted():
    cases = ev.load_cases(EVAL_DIR / "cases")
    assert len(cases) >= 4 and len({c.brief.hash() for c in cases}) == len(cases)
    assert all(c.brief.cloud.model and not c.brief.identity.enabled and c.id.startswith("eval_") for c in cases)
    assert len({c.styles for c in cases}) >= 3  # الحالات تغطي أكثر من طابع
    assert [c.id for c in ev.load_cases(EVAL_DIR / "cases", ["eval_watad"])] == ["eval_watad"]
    with pytest.raises(ev.EvalError, match="حالة مجهولة"):
        ev.load_cases(EVAL_DIR / "cases", ["nope"])


def test_case_without_a_fixed_style_is_refused(tmp_path):
    (tmp_path / "x.yaml").write_text(yaml.safe_dump({**BRIEF, "project": "x", "eval": {"styles": ["s9"]}}, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ev.EvalError, match=r"eval\.styles"):
        ev.load_cases(tmp_path)


@pytest.mark.style_gate
def test_stops_at_thumbs_without_style_samples_or_owner(tmp_path):
    case, ws = _case(tmp_path)
    pipe, model = _pipe(tmp_path), ScriptedDrawer(ws, 4)
    out = run_until_owner(ev.stepper(lambda: pipe.run(case.brief), "thumbs"), model, 10, 8)
    assert out.code == AWAIT_OWNER and out.message == ev.STOP
    assert model.calls == ["REQUEST-thumbs.md", "REQUEST-blind-thumbs.md"]  # لا عينات طابع، ولا رسم بعد المصغّرات
    assert style.current(ws)["styles"] == ["s2"] and not (ws.work / "REQUEST-style.md").exists()
    row = ev.collect(ws, case.id, "thumbs", out.message)
    assert row["reached"] and row["calls"] == 2 and row["cost_usd"] == 2.5 and row["models"] == ["claude-x"]
    assert row["thumbs"] == {"ideas": 12, "blocked": 2, "exhausted": False, "reach_mean": None}
    assert set(row["requests"]) == {"thumbs", "blind-thumbs"} and row["judge"] is None and row["concepts"] == 0


@pytest.mark.style_gate
def test_stops_at_first_verdict_before_any_refinement(tmp_path):
    case, ws = _case(tmp_path)
    pipe, model = _pipe(tmp_path), ScriptedDrawer(ws, 3)  # دون العتبة: الخط سيطلب صقلًا، والتقييم يقف قبله
    out = run_until_owner(ev.stepper(lambda: pipe.run(case.brief), "judge"), model, 10, 20)
    assert out.code == AWAIT_OWNER and out.message == ev.STOP
    assert model.calls[-1] == "REQUEST-judge.md" and (ws.work / "REQUEST-refine.md").is_file()
    row = ev.collect(ws, case.id, "judge", out.message)
    j = row["judge"]
    assert row["reached"] and row["concepts"] == 5 and row["critique_rounds"] == 1 and row["audit_passed"] == 5
    assert j["best_total"] == 40 and j["passed"] == 1 and j["concepts"]["c1"]["total"] == 24
    assert j["mean_total"] == 27.2 and j["criteria"]["idea"] == 3.4
    assert row["requests"]["critique"]["calls"] == 1 and row["cost_usd"] == 6.25


def test_summary_and_comparison_read_the_direction_of_each_metric():
    def row(case, mean, best, passed, cost, blocked):
        scores = dict.fromkeys(config.JUDGE_CRITERIA, mean / 8)
        return {"case": case, "reached": True, "stopped": ev.STOP, "calls": 5, "cost_usd": cost, "seconds": 100, "requests": {},
                "models": ["m"], "thumbs": {"ideas": 12, "blocked": blocked, "exhausted": False, "reach_mean": None}, "concepts": 5,
                "audit_passed": 5, "critique_rounds": 1, "blind": {"read": 5, "blocked": 1},
                "judge": {"concepts": {f"c{n}": {} for n in range(5)}, "mean_total": mean, "best_total": best, "passed": passed, "criteria": scores}}

    meta = {"judge_model": "opus", "bar": [30, 3, {}]}
    a = ev.summarize("a", "t", "", "judge", meta, [row("x", 24, 28, 0, 6.0, 4), row("y", 26, 30, 1, 7.0, 2)])
    b = ev.summarize("b", "t", "جهد أعلى", "judge", meta, [row("x", 28, 33, 2, 9.0, 2), row("y", 28, 31, 1, 8.0, 2)])
    assert a["totals"]["judge_mean"] == 25 and a["totals"]["pass_rate"] == 0.1 and a["totals"]["thumb_block_rate"] == 0.25
    assert a["totals"]["cost_usd"] == 13.0 and a["totals"]["blind_block_rate"] == 0.2 and a["totals"]["audit_pass_rate"] == 1.0
    text = "\n".join(ev.compare(a, b))
    assert "متوسط مجموع الحَكَم (من 40): 25 ← 28 · الفرق +3 (أفضل)" in text
    assert "الكلفة بالدولار: 13 ← 17 · الفرق +4 (أسوأ)" in text  # الأعلى ليس أفضل في كل مقياس
    assert "نسبة المصغّرات المردودة عند القارئ: 0.25 ← 0.167 · الفرق -0.083 (أفضل)" in text
    assert "- x: متوسط الحَكَم 24 ← 28" in text and "تنبيه" not in text and "لم يُقَس تذبذبها" in text
    other = ev.summarize("c", "t", "", "thumbs", {"judge_model": "sonnet", "bar": [30, 3, {}]}, [row("x", 28, 33, 2, 9.0, 2)])
    warned = "\n".join(ev.compare(a, other))
    assert warned.count("تنبيه") == 3  # نقطة التوقف، والحالات، والحَكَم: كلها تمنع قراءة الفرق حُكمًا
    assert "جهد أعلى" in ev.report(b)[0]


def test_eval_command_defaults_cap_spending():
    args = build_parser().parse_args(["eval", "run", "--case", "eval_watad"])
    assert args.until == "judge" and args.case_usd == 8.0 and args.total_usd == 30.0 and args.max_calls == 10 and not args.no_model
