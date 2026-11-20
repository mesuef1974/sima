"""التشغيل الآلي: يستدعي النموذج بالطلب الأحدث حتى قرار المالك، بسقف استدعاءات، ويسجّل كل استدعاء؛ والمحوّل يحصر الكتابة في work/."""
from __future__ import annotations

import json
from pathlib import Path

from sima import config
from sima.domain.run import RunKey
from sima.services.autopilot import ModelResult, run_until_owner
from sima.services.pipeline import AWAIT_MODEL, AWAIT_OWNER, Outcome
from sima.services.workspace import Workspace


def _ws(tmp_path: Path) -> Workspace:
    ws = Workspace(root=tmp_path / "p" / "v1", key=RunKey(project="p", brief_hash="h", seed=1), version=1)
    ws.work.mkdir(parents=True)
    return ws


class FakeModel:
    def __init__(self, ok: bool = True, writes: bool = True, cost: float = 0.4):
        self.calls: list[str] = []
        self.caps: list[float] = []
        self.ok, self.writes, self.cost = ok, writes, cost

    def run(self, request: Path, version_root: Path, *, cap_usd: float, tick=None) -> ModelResult:
        self.calls.append(request.name)
        self.caps.append(cap_usd)
        if self.writes:
            (version_root / "work" / f"out-{len(self.calls)}.txt").write_text("x", encoding="utf-8")
        return ModelResult(self.ok, self.cost, 12.0, "كُتبت الملفات", model="m", effort="high", reserved_usd=min(5.0, cap_usd))


def test_stops_when_model_writes_nothing_or_budget_is_spent(tmp_path):
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")
    always = lambda: Outcome(AWAIT_MODEL, "بانتظار النموذج", ws)  # noqa: E731
    idle = FakeModel(writes=False)
    out = run_until_owner(always, idle, max_calls=10)
    assert len(idle.calls) == 1 and "لم يكتب النموذج شيئًا" in out.message
    pricey = FakeModel(cost=2.5)
    out = run_until_owner(always, pricey, max_calls=10, max_usd=5)
    assert len(pricey.calls) == 2 and "سقف الإنفاق 5$" in out.message
    assert pricey.caps == [5, 2.5]  # يُحجز لكل استدعاء ما بقي من سقف الأمر، فلا يتجاوزه المجموع ولو أنفق كلٌّ حدّه
    tight, ws2 = FakeModel(cost=2.9), _ws(tmp_path / "tight")
    (ws2.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, "بانتظار النموذج", ws2), tight, max_calls=10, max_usd=3)
    assert len(tight.calls) == 1 and "لا يكفي استدعاءً" in out.message  # الباقي 0.10$ دون أدنى استدعاء: لا يُبدأ ثم يُقطع


def test_stops_after_two_calls_on_the_same_request_with_the_same_pipeline_answer(tmp_path):
    """النموذج يعيد كتابة ملفه كل مرة فيتغيّر work/، والخط يردّ بالرسالة نفسها: استدعاءان ثم توقف لا عشرة."""
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")
    model = FakeModel(cost=0.1)
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, "الجولة 1 تطلب تعديلات لم تُنفَّذ بعد", ws), model, max_calls=10)
    assert len(model.calls) == 2 and "وردّ الخط بالرسالة نفسها" in out.message
    msgs = iter(["مشكلة أ", "مشكلة ب", "مشكلة ج", "مشكلة د"])  # رسالة تتغيّر = تقدم: لا يتوقف
    moving = FakeModel(cost=0.1)
    ws2 = _ws(tmp_path / "b")
    (ws2.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, next(msgs), ws2), moving, max_calls=3)
    assert len(moving.calls) == 3 and "سقف 3" in out.message


def test_timeout_kills_the_whole_process_tree(tmp_path):
    import subprocess
    import sys
    import time

    import pytest

    from sima.adapters.proc import run_tree

    marker = tmp_path / "grandchild-alive.txt"
    child = f"import time,pathlib;time.sleep(3);pathlib.Path(r'{marker}').write_text('x')"
    parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(60)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_tree([sys.executable, "-c", parent], tmp_path, timeout=1)
    time.sleep(4)
    assert not marker.exists()  # الحفيد قُتل مع أبيه فلم يكتب بعد المهلة


def test_runs_model_until_owner_and_logs_calls(tmp_path):
    ws = _ws(tmp_path)
    script = iter([("diverge", AWAIT_MODEL), ("strategy", AWAIT_MODEL), (None, AWAIT_OWNER)])

    def step() -> Outcome:
        req, code = next(script)
        if req:
            (ws.work / f"REQUEST-{req}.md").write_text("طلب", encoding="utf-8")
        return Outcome(code, "", ws)

    model = FakeModel()
    out = run_until_owner(step, model, max_calls=5)
    assert out.code == AWAIT_OWNER
    assert model.calls == ["REQUEST-diverge.md", "REQUEST-strategy.md"]
    logs = [json.loads(x) for x in (ws.root / "model_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["request"] for x in logs] == model.calls and logs[0]["cost_usd"] == 0.4
    import hashlib

    assert logs[0]["request_sha256"] == hashlib.sha256("طلب".encode()).hexdigest()  # أي طلب بعينه أُرسل
    assert logs[0]["model"] == "m" and logs[0]["effort"] == "high" and logs[0]["reserved_usd"] == 5.0


def test_stops_at_cap_and_on_failure(tmp_path):
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-critique-r1.md").write_text("طلب", encoding="utf-8")
    always = lambda: Outcome(AWAIT_MODEL, "بانتظار النموذج", ws)  # noqa: E731
    model = FakeModel()
    out = run_until_owner(always, model, max_calls=2)
    assert len(model.calls) == 2 and "سقف 2" in out.message
    failing = FakeModel(ok=False)
    out = run_until_owner(always, failing, max_calls=5)
    assert len(failing.calls) == 1 and "تعذّر" in out.message


def test_disabled_model_leaves_pipeline_waiting(tmp_path):
    ws = _ws(tmp_path)
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, "بانتظار النموذج", ws), None, max_calls=5)
    assert out.code == AWAIT_MODEL and not (ws.root / "model_calls.jsonl").exists()


def test_claude_command_confines_writes_to_version_work():
    from sima.adapters.claude_model import ClaudeCodeModel

    root = config.ROOT / "out" / "x" / "v3"
    cmd = ClaudeCodeModel(budget_usd=2, timeout_s=60).command(root / "work" / "REQUEST-strategy.md", root)
    joined = " ".join(cmd)
    assert "--max-budget-usd 2" in joined and "--permission-mode dontAsk" in joined
    assert "Write(./out/x/v3/work/**)" in cmd and "Edit(./out/x/v3/work/**)" in cmd
    assert "Bash" in cmd[cmd.index("--disallowedTools"):] and "Read(./.env)" in cmd
    assert not any(c.startswith("Write(") and "work" not in c for c in cmd)
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert allowed[0] == "Read(./**)" and not {"Read", "Glob", "Grep"} & set(allowed)  # لا إذن قراءة عام خارج المستودع
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--setting-sources") + 1] == "project"


def test_judge_writes_only_its_folder_and_design_uses_stronger_model():
    from sima.adapters.claude_model import ClaudeCodeModel

    root = config.ROOT / "out" / "x" / "v3"
    m = ClaudeCodeModel(budget_usd=2, timeout_s=60)
    judge = m.command(root / "work" / "REQUEST-judge.md", root)
    assert "Write(./out/x/v3/work/judge/**)" in judge and "Write(./out/x/v3/work/**)" not in judge
    assert "--model" in judge and "--effort" in judge
    strategy = m.command(root / "work" / "REQUEST-strategy.md", root)
    assert "--model" not in strategy
    styles = m.command(root / "work" / "REQUEST-style.md", root)
    assert "Write(./out/x/v3/work/styles/**)" in styles and "Write(./out/x/v3/work/**)" not in styles and "--model" in styles
    diverge = m.command(root / "work" / "REQUEST-diverge.md", root)
    assert "Write(./out/x/v3/work/**)" in diverge and "--model" in diverge


def test_drawer_is_fable_and_judge_is_independent_opus_by_default(monkeypatch):
    """الافتراضي: Fable يرسم (جهد عالٍ للأفكار ومتوسط للصقل) وopus يحكم؛ وكل ذلك يُستبدل بالبيئة."""
    from sima.adapters import claude_model

    env: dict[str, str] = {}
    monkeypatch.setattr(claude_model, "_env", env.get)
    assert claude_model.design_flags("REQUEST-diverge.md") == ["--model", "claude-fable-5-2", "--effort", "high"]
    assert claude_model.design_flags("REQUEST-style.md") == ["--model", "claude-fable-5-2", "--effort", "high"]
    assert claude_model.design_flags("REQUEST-refine-judge.md") == ["--model", "claude-fable-5-2", "--effort", "medium"]
    assert claude_model.design_flags("REQUEST-critique-r1.md") == ["--model", "claude-fable-5-2", "--effort", "medium"]
    assert claude_model.design_flags("REQUEST-judge.md") == ["--model", "opus", "--effort", "medium"]
    assert claude_model.design_flags("REQUEST-strategy.md") == []
    env.update({"SIMA_MODEL_DESIGN": "opus", "SIMA_MODEL_JUDGE": "sonnet", "SIMA_MODEL_JUDGE_EFFORT": "high", "SIMA_MODEL_EFFORT_IDEAS": "max"})
    assert claude_model.design_flags("REQUEST-diverge.md") == ["--model", "opus", "--effort", "max"]
    assert claude_model.design_flags("REQUEST-judge.md") == ["--model", "sonnet", "--effort", "high"]


def test_blind_reader_reads_only_renders_and_writes_only_its_folder(monkeypatch):
    """القارئ الأعمى نموذج ثالث: لا يقرأ إلا طلبه وصور التصيير (فلا يصل إلى الاسم ولا الفكرة)، ويكتب في work/blind/ وحده."""
    from sima.adapters import claude_model

    root = config.ROOT / "out" / "x" / "v3"
    cmd = claude_model.ClaudeCodeModel(budget_usd=1, timeout_s=60).command(root / "work" / "REQUEST-blind.md", root)
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert allowed == ["Read(./out/x/v3/work/REQUEST-blind.md)", "Read(./out/x/v3/work/render/**)",
                       "Write(./out/x/v3/work/blind/**)", "Edit(./out/x/v3/work/blind/**)"]
    assert "قارئ مستقل" in cmd[2] and "SKILL.md" not in cmd[2]
    monkeypatch.setattr(claude_model, "_env", lambda k, d: d)
    assert claude_model.design_flags("REQUEST-blind.md") == ["--model", "sonnet", "--effort", "low"]
    assert claude_model.design_flags("REQUEST-refine-blind.md") == ["--model", "claude-fable-5-2", "--effort", "medium"]
