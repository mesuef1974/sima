"""ضمانات كانت بلا اختبار (مراجعة الأتمتة 2026-11-14، المرحلة 7): إذن السحابة و`--no-model` عبر `cmd_run`، وتعذّر العزل،
وقيمة `--max-budget-usd` المحجوزة، ووصول مفاتيح الإيقاف إلى الخط، وحلقة سقوف التقييم، وتكافؤ قرار الطرفية والمنصة.
(ومغطّى في غيره: مفهوم بلا idea_id في test_model_files خ4، وحد المعاينات في خ13.)"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from sima import cli, config
from sima.adapters import claude_model, local_embed, win_isolation
from sima.adapters import proc as proc_mod
from sima.domain import brief_from_dict
from sima.domain.brief import load_brief
from sima.services import autopilot
from sima.services import drawer_eval as ev
from sima.services.autopilot import ModelResult
from sima.services.ledger import Ledger
from sima.services.pipeline import AWAIT_MODEL, Outcome, Pipeline
from sima.services.shaping import ShapingService
from sima.services.workspace import find_workspace, open_workspace

from .fakes import FakeRenderer
from .test_cli_version import _shown, _write
from .test_domain_ledger_workspace import BRIEF
from .test_drawer_eval import ScriptedDrawer, _build
from .test_pipeline import NoShaper
from .test_web_api import _post, _token, client  # noqa: F401

ALLOWED = {**BRIEF, "cloud": {"model": True}}


# ---------- إذن السحابة و--no-model عبر cmd_run ----------
@pytest.fixture
def run_env(tmp_path, monkeypatch):
    """`sima run` بلا خط حقيقي: ما يهمّ هنا النموذج الذي يُسلَّم إلى حلقة الاستدعاء الآلي."""
    out = tmp_path / "out"
    monkeypatch.setattr(config, "OUT_DIR", out)
    monkeypatch.setattr(config, "LIVE_PREVIEW", False)
    seen: dict = {}

    def fake_pipeline(path, out_dir=None):
        def run(brief, new_version=False):
            return Outcome(AWAIT_MODEL, "بانتظار النموذج", open_workspace(out, brief))
        return SimpleNamespace(close=lambda: None), SimpleNamespace(run=run)

    def fake_loop(step, model, max_calls, max_usd=15.0, **kw):
        seen["model"] = model
        return step()

    class Model:
        pass

    monkeypatch.setattr(cli, "_pipeline", fake_pipeline)
    monkeypatch.setattr(autopilot, "run_until_owner", fake_loop)
    monkeypatch.setattr(claude_model, "ClaudeCodeModel", Model)
    monkeypatch.setattr(claude_model, "enabled", lambda: True)
    return tmp_path, seen, Model


@pytest.mark.parametrize(("brief", "argv", "enabled", "model"), [
    (ALLOWED, [], True, True),  # كل الشروط: يُستدعى
    (ALLOWED, ["--no-model"], True, False),  # المفتاح الصريح يوقفه
    (ALLOWED, [], False, False),  # المفتاح العام (SIMA_MODEL_AUTO) مطفأ أو لا claude
    (BRIEF, [], True, False),  # الغياب منع ولو فُعّل الاستدعاء على الجهاز
    ({**BRIEF, "cloud": {"model": False}}, [], True, False),
])
def test_cmd_run_hands_the_model_to_the_loop_only_with_every_permission(run_env, monkeypatch, capsys, brief, argv, enabled, model):
    tmp, seen, Model = run_env
    monkeypatch.setattr(claude_model, "enabled", lambda: enabled)
    path = _write(tmp / "briefs" / "demo.yaml", brief)
    assert cli.main(["run", str(path), *argv]) == AWAIT_MODEL
    assert isinstance(seen["model"], Model) is model
    said = "لا يأذن بالاستدعاء السحابي" in capsys.readouterr().out
    assert said is (enabled and not argv and not (brief.get("cloud") or {}).get("model"))  # يُقال السبب حين يكون الإذن هو الناقص


# ---------- تعذّر العزل يُفشل الاستدعاء ولا يرجع إلى استدعاء بلا عزل ----------
def _model_root(tmp_path):
    v = tmp_path / "out" / "p" / "v1"
    (v / "work").mkdir(parents=True)
    req = v / "work" / "REQUEST-diverge.md"
    req.write_text("r", encoding="utf-8")
    return tmp_path, v, req


def test_isolation_failure_fails_the_call_and_never_falls_back_to_an_unisolated_one(tmp_path, monkeypatch):
    root, v, req = _model_root(tmp_path)
    spawned = []
    monkeypatch.setattr(claude_model, "isolation", lambda: "low")
    monkeypatch.setattr(proc_mod, "run_tree", lambda *a, **k: spawned.append("بلا عزل"))
    monkeypatch.setattr(claude_model, "run_tree", lambda *a, **k: spawned.append("بلا عزل"))

    def broken(paths):
        raise OSError("تعذّر وسم الملفات السرية")

    monkeypatch.setattr(win_isolation, "protect", broken)
    monkeypatch.setattr(win_isolation, "run_low", lambda *a, **k: spawned.append("عزل"))
    res = claude_model.ClaudeCodeModel(root=root, budget_usd=5, timeout_s=60).run(req, v, cap_usd=5)
    assert not res.ok and res.cost_usd == 0.0 and "تعذّر وسم" in res.summary and res.isolation == "low"
    assert spawned == []  # لا استدعاء أصلًا، لا بعزل ولا بغيره


def test_isolation_off_is_the_only_way_to_a_plain_call(tmp_path, monkeypatch):
    root, v, req = _model_root(tmp_path)
    called = []
    monkeypatch.setattr(claude_model, "isolation", lambda: "")
    monkeypatch.setattr(claude_model, "run_tree", lambda cmd, *a, **k: called.append(cmd) or subprocess.CompletedProcess(cmd, 0, "{}", ""))
    claude_model.ClaudeCodeModel(root=root, budget_usd=5, timeout_s=60).run(req, v, cap_usd=5)
    assert len(called) == 1
    monkeypatch.undo()  # الدالة الفعلية: مفتاح الإيقاف الصريح وحده يعطّل العزل
    monkeypatch.setattr(win_isolation, "available", lambda: True)
    monkeypatch.setattr(claude_model, "_env", lambda k, d: "0" if k == "SIMA_MODEL_ISOLATION" else d)
    assert claude_model.isolation() == ""
    monkeypatch.setattr(claude_model, "_env", lambda k, d: d)
    assert claude_model.isolation() == "low"


# ---------- قيمة --max-budget-usd هي المحجوز لا سقف الإعداد ----------
@pytest.mark.parametrize(("budget", "cap", "flag"), [(5, 1.5, "1.5"), (5, None, "5"), (5, 9, "5"), (5, 0.75, "0.75")])
def test_max_budget_flag_is_the_smaller_of_call_budget_and_what_is_left(tmp_path, monkeypatch, budget, cap, flag):
    root, v, req = _model_root(tmp_path)
    seen = []
    monkeypatch.setattr(claude_model, "isolation", lambda: "")
    m = claude_model.ClaudeCodeModel(root=root, budget_usd=budget, timeout_s=60)
    monkeypatch.setattr(m, "_spawn", lambda cmd, *a, **k: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0, "{}", ""))
    res = m.run(req, v, cap_usd=cap)
    cmd = seen[0]
    assert cmd[cmd.index("--max-budget-usd") + 1] == flag and res.reserved_usd == float(flag)


# ---------- مفاتيح الإيقاف تصل إلى الخط ----------
@pytest.mark.parametrize(("blind", "thumbs", "embed"), [(False, False, False), (True, True, True)])
def test_switches_reach_the_pipeline_the_cli_builds(monkeypatch, blind, thumbs, embed):
    from sima.adapters import playwright_renderer

    monkeypatch.setattr(playwright_renderer, "PlaywrightRenderer", FakeRenderer)
    monkeypatch.setattr(config, "BLIND_GATE", blind)
    monkeypatch.setattr(config, "THUMBS_GATE", thumbs)
    monkeypatch.setattr(config, "ENV", {**config.ENV, "SIMA_EMBED": "1" if embed else "0"})
    assert local_embed.enabled() is embed
    _renderer, pipe = cli._pipeline("b.yaml")
    assert pipe._blind is blind and pipe._thumbs is thumbs and (pipe._embedder is not None) is embed


# ---------- حلقة سقوف التقييم ----------
class CostedDrawer(ScriptedDrawer):
    """الرسّام المبرمج، يجد مساحة عمله من مجلد الإصدار الذي يُستدعى فيه."""

    def __init__(self, brief, cost):
        self.brief, self.cost, self.calls, self.judge_score = brief, cost, [], 4

    def run(self, request: Path, version_root: Path, *, cap_usd: float, tick=None) -> ModelResult:
        self.ws = find_workspace(version_root.parent.parent, self.brief)
        res = super().run(request, version_root, cap_usd=cap_usd, tick=tick)
        return ModelResult(True, self.cost, res.seconds, res.summary, model=res.model, models_used=res.models_used, reserved_usd=cap_usd)


@pytest.fixture
def evaluation(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setattr(config, "OUT_DIR", out)
    monkeypatch.setattr(config, "LIVE_PREVIEW", False)
    monkeypatch.setattr(cli, "EVAL_DIR", tmp_path / "evals")
    cases = [ev.Case(n, brief_from_dict({**ALLOWED, "project": n}, source=f"{n}.yaml"), ("s2",)) for n in ("eval_a", "eval_b")]
    monkeypatch.setattr(ev, "load_cases", lambda d, only=(): [c for c in cases if not only or c.id in only])

    def pipeline(path, out_dir=None):
        return FakeRenderer(), Pipeline(FakeRenderer(), ShapingService(NoShaper()), None, out_dir, catalog=[], decide_cmd="x", thumbs_gate=True,
                                            build_mark=_build)

    drawers: dict = {}

    def make_model():
        class M:
            def run(self, request, version_root, *, cap_usd, tick=None):
                name = version_root.parent.name
                d = drawers.setdefault(name, CostedDrawer(next(c.brief for c in cases if c.id == name), cost[0]))
                return d.run(request, version_root, cap_usd=cap_usd, tick=tick)
        return M()

    cost = [4.0]
    monkeypatch.setattr(cli, "_pipeline", pipeline)
    monkeypatch.setattr(claude_model, "enabled", lambda: True)
    monkeypatch.setattr(claude_model, "ClaudeCodeModel", make_model)
    monkeypatch.setattr(cli, "_eval_meta", lambda caps=None: {"judge_model": "opus", "bar": [30, 3, {}], "caps": caps or {}})
    return tmp_path, cost


def _results(tmp_path):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((tmp_path / "evals" / "results").glob("*.json"))]


@pytest.mark.style_gate
def test_eval_case_cap_stops_a_case_and_the_result_keeps_the_cap_and_the_whole_reason(evaluation, capsys):
    tmp, cost = evaluation
    cost[0] = 4.9
    # سقف الحالة 5$: المصغّرات تنفق 4.9$ ثم يبقى 0.1$ دون أدنى كلفة للطلب التالي فيقف التشغيل الآلي بسببه
    assert cli.main(["eval", "run", "--case", "eval_a", "--until", "thumbs", "--case-usd", "5", "--total-usd", "30", "--label", "t"]) == 0
    [run] = _results(tmp)
    [row] = run["cases"]
    assert run["config"]["caps"] == {"case_usd": 5.0, "total_usd": 30.0, "max_calls": 10} and row["cap_usd"] == 5.0
    assert not row["reached"] and row["calls"] == 1
    assert "سقف الإنفاق" in row["stopped"] and row["stopped"].count("\n") >= 1  # الرسالة كاملة: ما كان الخط ينتظره ثم سبب التوقف
    assert "سقف الإنفاق" in ev.stop_reason(row["stopped"]) and "بانتظار" not in ev.stop_reason(row["stopped"])
    assert "لم تبلغ: بلغ التشغيل الآلي سقف الإنفاق" in capsys.readouterr().out


@pytest.mark.style_gate
def test_eval_total_cap_skips_later_cases_and_says_so(evaluation):
    tmp, _cost = evaluation
    cli.main(["eval", "run", "--until", "thumbs", "--case-usd", "9", "--total-usd", "5.5"])
    [run] = _results(tmp)
    first, second = run["cases"]
    assert first["calls"] >= 1 and second["calls"] == 0 and not second["reached"]
    assert second["cap_usd"] < 3 and "سقف الإنفاق الإجمالي" in second["stopped"]  # ما بقي من التشغيل، لا سقف الحالة
    assert run["totals"]["cost_usd"] == first["cost_usd"]


@pytest.mark.style_gate
def test_eval_reaching_the_point_within_the_cap_and_warning_the_next_run_when_cap_is_below_measured(evaluation, capsys):
    tmp, cost = evaluation
    cost[0] = 1.0
    assert cli.main(["eval", "run", "--case", "eval_a", "--until", "thumbs", "--case-usd", "8"]) == 0
    [run] = _results(tmp)
    assert run["cases"][0]["reached"] and run["cases"][0]["cap_usd"] == 8.0
    assert "تحذير" not in capsys.readouterr().err
    assert run["cases"][0]["cost_usd"] == 2.0  # بلغتها بـ2$: سقف أدنى منها تحذير، وبلوغه أو فوقه لا
    assert ev.cap_warning([run], "thumbs", 1.0) is not None and ev.cap_warning([run], "thumbs", 1.5) is not None
    assert ev.cap_warning([run], "thumbs", 2.0) is None and ev.cap_warning([run], "thumbs", 8.0) is None


def test_cap_warning_is_measured_never_guessed():
    short = {"until": "judge", "cases": [{"reached": False, "cost_usd": 10.0}]}
    reached = {"until": "judge", "cases": [{"reached": True, "cost_usd": 12.0}]}
    assert ev.cap_warning([], "judge", 8) is None  # بلا قياس سابق لا تحذير
    assert "لم تبلغ" in ev.cap_warning([short], "judge", 10)  # وقفت عند 10$ والسقف لا يزيد
    assert ev.cap_warning([short], "judge", 20) is None
    assert "بلغت" in ev.cap_warning([reached], "judge", 8) and ev.cap_warning([reached], "judge", 12) is None
    assert ev.cap_warning([reached], "thumbs", 1) is None  # نقطة توقف أخرى: لا تقابل


# ---------- تكافؤ قرار الطرفية والمنصة ----------
def _shown_pair(tmp_path):
    briefs = {}
    for name in ("demo", "twin"):
        briefs[name] = _write(tmp_path / "briefs" / f"{name}.yaml", {**BRIEF, "project": name})
        _shown(tmp_path, briefs[name])
    return briefs


def test_terminal_and_platform_decisions_are_accepted_and_refused_alike(client, tmp_path, monkeypatch):  # noqa: F811
    from sima.services.inbox import owner_inbox
    from sima.web import runtime

    monkeypatch.setattr(config, "OUT_DIR", tmp_path)
    monkeypatch.setattr(runtime, "jobs", lambda: SimpleNamespace(start=lambda *a, **k: True, snapshot=lambda: []))
    briefs = _shown_pair(tmp_path)
    cards = {i["project"]: i for i in owner_inbox(tmp_path)}

    def api(project, verdict, concept="w1", reason=""):
        body = {"project": project, "version": 1, "key": cards[project]["key"], "verdict": verdict, "concept": concept, "reason": reason,
                "digest": cards[project]["digest"]}
        return _post(client, "/api/decide", body, HTTP_X_SIMA_TOKEN=_token()).status_code == 200

    def terminal(project, flag, concept="w1", reason=""):
        return cli.main(["decide", str(briefs[project]), flag, concept, *(["--reason", reason] if reason else [])]) == 0

    for verdict, flag, concept, reason, ok in [("approved", "--approve", "c9", "", False), ("rejected", "--reject", "w2", "", False),
                                               ("revise", "--revise", "w2", "", False), ("revise", "--revise", "w2", "أوضح الأسطر", True),
                                               ("approved", "--approve", "w1", "", True)]:
        assert terminal("demo", flag, concept, reason) is ok, (flag, concept, reason)
        assert api("twin", verdict, concept, reason) is ok, (verdict, concept, reason)

    def ledger(name):
        ws = find_workspace(tmp_path, load_brief(briefs[name]))
        return [(d.verdict, d.concept_id, d.reason) for d in Ledger(ws.ledger_path).read()]

    assert ledger("demo") == ledger("twin") and len(ledger("demo")) == 2  # التسجيلان نفسهما بالنص نفسه
