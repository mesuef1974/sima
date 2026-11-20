"""عزل النظام لاستدعاء النموذج (ويندوز): عملية بمستوى سلامة منخفض لا تكتب إلا في نافذتها ولا تقرأ الأسرار الموسومة.
عمليات بايثون حقيقية على مجلد مؤقت؛ لا نموذج ولا شبكة."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sima.adapters import claude_model
from sima.adapters import win_isolation as wi

pytestmark = pytest.mark.skipif(not wi.available(), reason="عزل مستوى السلامة خاص بويندوز")

CHILD = r"""
import json, os, pathlib, sys
base, res = pathlib.Path(sys.argv[1]), {}
def attempt(name, fn):
    try:
        fn()
        res[name] = True
    except OSError:
        res[name] = False
work = base / "work"
attempt("new_in_work", lambda: (work / "concepts.yaml").write_text("x"))
attempt("edit_in_work", lambda: (work / "concepts" / "c1.yaml").write_text("new"))
attempt("new_in_judge", lambda: (work / "judge" / "forged.yaml").write_text("x"))
attempt("edit_judge", lambda: (work / "judge" / "j.yaml").write_text("x"))
attempt("edit_request", lambda: (work / "REQUEST-diverge.md").write_text("x"))
attempt("outside", lambda: (base / "escape.txt").write_text("x"))
attempt("read_secret", lambda: (base / ".env").read_text())
attempt("read_plain", lambda: (base / "plain.txt").read_text())
attempt("temp", lambda: (pathlib.Path(os.environ["TEMP"]) / "t.txt").write_text("x"))
print(json.dumps(res))
sys.stderr.write("err")
sys.exit(7)
"""


def _tree(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    (work / "concepts").mkdir(parents=True)
    (work / "judge").mkdir()
    (work / "concepts" / "c1.yaml").write_text("old", encoding="utf-8")
    (work / "judge" / "j.yaml").write_text("verdict", encoding="utf-8")
    (work / "REQUEST-diverge.md").write_text("طلب", encoding="utf-8")
    (tmp_path / ".env").write_text("CANARY", encoding="utf-8")
    (tmp_path / "plain.txt").write_text("plain", encoding="utf-8")
    (tmp_path / "tmp").mkdir()
    return work


def _probe(tmp_path: Path) -> tuple[subprocess.CompletedProcess, dict]:
    import os

    p = wi.run_low([sys.executable, "-I", "-c", CHILD, str(tmp_path)], tmp_path, 60, env={**os.environ, "TEMP": str(tmp_path / "tmp")})
    return p, json.loads(p.stdout)


def test_drawer_writes_only_in_its_window_and_cannot_read_secrets(tmp_path):
    work = _tree(tmp_path)
    wi.protect([tmp_path / ".env"])
    with wi.write_window(work, work, [work / "REQUEST-diverge.md", work / "judge"]), wi.write_window(tmp_path / "tmp", tmp_path / "tmp"):
        p, res = _probe(tmp_path)
    assert p.returncode == 7 and p.stderr == "err"  # الرمز والمخرجات تعود كما هي من عملية معزولة
    assert res == {"new_in_work": True, "edit_in_work": True, "temp": True, "read_plain": True,
                   "new_in_judge": False, "edit_judge": False, "edit_request": False, "outside": False, "read_secret": False}
    assert (work / "judge" / "j.yaml").read_text(encoding="utf-8") == "verdict" and not (tmp_path / "escape.txt").exists()
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "CANARY"  # الأب يقرأ أسراره كما كان
    # بعد الاستدعاء تُردّ النافذة: لا مجلد يُكتب فيه من المنخفض في السكون، وما كتبه النموذج يقرؤه الخط ويعدّله
    _, after = _probe(tmp_path)
    assert not after["new_in_work"] and not after["edit_in_work"] and not after["temp"]
    (work / "concepts.yaml").write_text("الخط يكتب فوق ما كتبه النموذج", encoding="utf-8")


def test_judge_window_is_its_folder_only(tmp_path):
    work = _tree(tmp_path)
    with wi.write_window(work, work / "judge", [work / "REQUEST-diverge.md"]):
        _, res = _probe(tmp_path)
    assert res["new_in_judge"] and res["edit_judge"]
    assert not res["new_in_work"] and not res["edit_in_work"] and not res["edit_request"]  # الحَكَم لا يمسّ ما يحكم عليه


def test_timeout_kills_the_isolated_tree(tmp_path):
    marker = tmp_path / "work" / "alive.txt"
    marker.parent.mkdir()
    grandchild = f"import time,pathlib;time.sleep(3);pathlib.Path(r'{marker}').write_text('x')"
    parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{grandchild!r}]);time.sleep(60)"
    ticks: list[int] = []
    with wi.write_window(tmp_path / "work", tmp_path / "work"), pytest.raises(subprocess.TimeoutExpired):
        wi.run_low([sys.executable, "-c", parent], tmp_path, timeout=1.5, tick=lambda: ticks.append(1), every=0.3)
    time.sleep(4)
    assert ticks and not marker.exists()  # الحفيد قُتل مع الـJob فلم يكتب بعد المهلة


def test_model_secrets_and_locked_sets(tmp_path, monkeypatch):
    root = tmp_path
    for d in ("var/pgdata", "var/ms-playwright", ".git", "out/p/v1/work/judge", "out/p/v1/work/blind"):
        (root / d).mkdir(parents=True)
    (root / ".env").write_text("s", encoding="utf-8")
    (root / ".env.local").write_text("s", encoding="utf-8")
    v = root / "out" / "p" / "v1"
    for name in ("REQUEST-diverge.md", "REQUEST-judge.md"):
        (v / "work" / name).write_text("r", encoding="utf-8")
    m = claude_model.ClaudeCodeModel(root=root, budget_usd=1, timeout_s=60)
    names = {p.relative_to(root).as_posix() for p in m._secrets()}
    assert names == {".env", ".env.local", ".git", "var/pgdata"}  # متصفح التصيير مستثنى: عملياته المنخفضة تقرؤه
    drawer = {p.name for p in m._locked(v / "work" / "REQUEST-diverge.md", v)}
    assert drawer == {"REQUEST-diverge.md", "REQUEST-judge.md", "judge", "blind"}
    judge = {p.name for p in m._locked(v / "work" / "REQUEST-judge.md", v)}
    assert judge == {"REQUEST-diverge.md", "REQUEST-judge.md"}
    env: dict[str, str] = {}
    monkeypatch.setattr(claude_model, "_env", lambda k, d: env.get(k, d))  # noqa: PLW0108
    assert claude_model.isolation() == "low"
    env["SIMA_MODEL_ISOLATION"] = "0"
    assert claude_model.isolation() == ""


def test_model_call_runs_isolated_and_detects_a_swapped_request(tmp_path, monkeypatch):
    """الاستدعاء كله بعملية بديلة عن claude: تكتب في work/ وتحاول الخروج، ثم تبدّل طلبها بإعادة التسمية (الثغرة التي لا تمنعها النافذة)."""
    root = tmp_path
    v = root / "out" / "p" / "v1"
    (v / "work").mkdir(parents=True)
    (root / "var").mkdir()
    (root / ".env").write_text("CANARY", encoding="utf-8")
    req = v / "work" / "REQUEST-diverge.md"
    req.write_text("طلب", encoding="utf-8")
    fake = r"""
import json, os, pathlib, sys
work = pathlib.Path(sys.argv[1])
(work / "concepts.yaml").write_text("x")
leak = ""
try:
    leak = (work.parents[3] / ".env").read_text()
except OSError:
    pass
try:
    (work.parents[3] / "escape.txt").write_text("x")
except OSError:
    pass
if "--swap" in sys.argv:
    (work / "REQUEST-diverge.md").rename(work / "old.md")
    (work / "REQUEST-diverge.md").write_text("forged")
print(json.dumps({"result": "تم " + leak, "total_cost_usd": 0.01, "modelUsage": {"claude-x": {}}}))
"""
    m = claude_model.ClaudeCodeModel(root=root, budget_usd=1, timeout_s=60)
    monkeypatch.setattr(claude_model, "_env", lambda k, d: d)
    swap: list[str] = []
    monkeypatch.setattr(m, "command", lambda request, version_root, budget_usd=None: [sys.executable, "-I", "-c", fake, str(v / "work"), *swap])
    res = m.run(req, v, cap_usd=0.5)
    assert res.ok and res.isolation == "low" and res.reserved_usd == 0.5 and res.models_used == ("claude-x",)
    assert "CANARY" not in res.summary and not (root / "escape.txt").exists() and (v / "work" / "concepts.yaml").is_file()
    assert not (root / "var" / "model-tmp").exists()  # المؤقت يُفرَّغ بعد الاستدعاء
    swap.append("--swap")
    res = m.run(req, v, cap_usd=0.5)
    assert not res.ok and "ما لا يملكه النموذج" in res.summary and res.cost_usd == 0.01
