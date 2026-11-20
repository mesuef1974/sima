"""المنصة بعد مراجعة الأتمتة (2026-11-14، المرحلة 5): قفل لا يحجبه رقم عملية أُعيد استعماله (م4)، وبصمة في تبديل الوسيط (م5)،
ونموذج خطوات واحد وقرارات المالك كلها في السجل وتشغيلات منتهية تُسقط (م6)، وسجل لا يُخدم لمشروع مخفي (م7)، وملاحظة
أطول من حدّها تُرفض ولا تُقصّ (م8)، وقاعدة متوقفة لا تمنع المنصة (م9)، ونسبة التسليم من سجل الاستدعاءات (م10)، وإصدار
موروث يوسم أحداث سلفه وخطواته بترتيب الخط (ب15). لا اتصال شبكي ولا نموذج في هذه الاختبارات."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from sima import config
from sima.adapters import run_lock
from sima.adapters.pipeline_jobs import PipelineJobs
from sima.services import board, inbox, timeline
from sima.services.inbox import InboxError, decide, owner_inbox, switch_medium
from sima.services.ledger import Ledger

from .test_inbox import out  # noqa: F401  (إصدار عند بطاقة المفاهيم)

KEY = "abc123-s1"


# ---------- م4 ----------
def test_stale_lock_whose_pid_was_reused_does_not_block_the_project(tmp_path):
    """القفل يحمل وقت إنشاء عمليته: رقم العملية نفسه لعملية وُلدت في وقت آخر ليس صاحب القفل."""
    p = run_lock.lock_path(tmp_path, "p")
    p.parent.mkdir(parents=True)
    born = run_lock.created(os.getpid())
    if sys.platform == "win32":
        assert born  # وقت الإنشاء متاح على ويندوز، وهو منصة المالك
    p.write_text(json.dumps({"pid": os.getpid(), "started": "x", "created": 1}), encoding="utf-8")
    assert (run_lock.holder(tmp_path, "p") is None) == (born is not None)
    p.write_text(json.dumps({"pid": os.getpid(), "started": "x"}), encoding="utf-8")  # قفل أقدم من الحقل: رقم العملية وحده
    assert run_lock.holder(tmp_path, "p")["pid"] == os.getpid()
    p.unlink()
    with run_lock.project_lock(tmp_path, "p"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        assert rec["pid"] == os.getpid() and rec["created"] == born and run_lock.holder(tmp_path, "p") is not None


# ---------- م5 وم8 ----------
def test_medium_switch_is_bound_to_the_shown_concepts(out):  # noqa: F811
    [item] = owner_inbox(out)
    with pytest.raises(InboxError, match="تغيّرت رسوم المفاهيم"):
        switch_medium(out, "proj", 1, KEY, "emblem", "أريد شارة معاصرة", "old")
    assert "شارة" in switch_medium(out, "proj", 1, KEY, "emblem", "أريد شارة معاصرة", item["digest"])


def test_owner_text_over_its_limit_is_refused_and_nothing_is_recorded(out):  # noqa: F811
    assert inbox.LIMITS == {"decide": 500, "medium": 800, "identity": 1200, "note": 600, "reason": 800}
    with pytest.raises(InboxError, match="أطول من الحد"):
        decide(out, "proj", 1, KEY, "rejected", "w1", "س" * 501)
    with pytest.raises(InboxError, match="أطول من الحد"):
        switch_medium(out, "proj", 1, KEY, "emblem", "س" * 801)
    assert Ledger(out / "proj" / "v1" / "decisions.jsonl").read() == []
    assert "w1" in decide(out, "proj", 1, KEY, "rejected", "w1", "س" * 500)
    src = Path(inbox.__file__).read_text(encoding="utf-8") + (Path(inbox.__file__).parents[1] / "web" / "api.py").read_text(encoding="utf-8")
    assert "[:600]" not in src and "[:800]" not in src and "[:500]" not in src and "[:1200]" not in src  # لا قصّ صامت


def test_stalled_card_names_what_the_line_stopped_at(out):  # noqa: F811
    from sima.services import outcome

    outcome.write(out / "proj" / "v1", code=4, message="وقف الخط", gate="designer_fix", digest="d1")
    [item] = owner_inbox(out)
    assert (item["kind"], item["gate"], item["digest"]) == ("stalled", "designer_fix", "d1")


# ---------- م6 ----------
def _version(tmp_path: Path, stages: tuple[str, ...], identity: bool = True) -> Path:
    v = tmp_path / "proj" / "v1"
    (v / "stages").mkdir(parents=True)
    (v / "brief.json").write_text(json.dumps({"name_ar": "تجربة", "identity": {"scope": "core"} if identity else None}), encoding="utf-8")
    (v / "run.json").write_text(json.dumps({"project": "proj", "key": "k", "closed": False}), encoding="utf-8")
    for i, s in enumerate(stages):
        (v / "stages" / f"{s}.json").write_text(json.dumps({"at": f"2026-11-14T10:{i:02d}:00+00:00"}), encoding="utf-8")
    return v


def test_projects_page_and_log_share_one_step_model(tmp_path):
    """صفحة المشاريع كانت بتسع خطوات بلا الهوية والسجل باثنتي عشرة؛ الآن نموذج واحد بترتيب الخط."""
    v = _version(tmp_path, ("brief", "research", "strategy", "diverge", "render"))
    [row] = board.sima_state(tmp_path)
    log = timeline.timeline(v)["progress"]["steps"]
    assert row["steps"] == log and [s["key"] for s in log].index("strategy") < [s["key"] for s in log].index("package")
    keys = [s["key"] for s in log]
    assert keys == ["brief", "research", "strategy", "diverge", "render", "critique", "preview", "name_check", "directions", "package",
                    "identity_build", "identity", "deliver", "landed"]
    assert next(s["key"] for s in row["steps"] if s["status"] == "current") == "critique"
    plain = _version(tmp_path / "plain", ("brief",), identity=False)
    assert [s["key"] for s in timeline.timeline(plain)["progress"]["steps"]] == [*timeline.BASE_FLOW, "deliver", "landed"]


def test_snapshot_carries_check_counts_and_calls_with_unreported_cost(tmp_path):
    v = _version(tmp_path, ("brief",))
    (v / "work").mkdir()
    (v / "work" / "audit.json").write_text(json.dumps({"c1": {"passed": True}, "c2": {"passed": False}, "c2-small": {"passed": False}}),
                                           encoding="utf-8")
    (v / "model_calls.jsonl").write_text("\n".join(json.dumps(r) for r in (
        {"cost_usd": 1.0}, {"cost_usd": 3.0, "cost_known": False}, {"cost_usd": 0.5, "cost_known": True})), encoding="utf-8")
    [row] = board.sima_state(tmp_path)
    assert row["audit"] == {"passed": 1, "failed": 2}
    assert row["cost"]["unknown"] == 1 and row["cost"]["usd"] == 4.5 and row["cost"]["calls"] == 3
    assert board.VERDICT_AR["switch_medium"]


def test_every_owner_decision_is_in_the_log(tmp_path):
    """صفحة القرارات كانت تعرض قرارات المفاهيم وحدها: الطابع والسكتش وردّ المتجه وتحقق الاسم قرارات المالك أيضًا."""
    v = _version(tmp_path, ("brief", "name_check"))
    (v / "style_decisions.jsonl").write_text(json.dumps({"styles": ["s1"], "note": "أقرب إلى الهندسي", "at": "2026-11-14T10:05:00+00:00"},
                                                        ensure_ascii=False) + "\n", encoding="utf-8")
    rows = [{"sketch": 3, "develop": True, "note": "أوضح", "at": "2026-11-14T10:06:00+00:00"},
            {"rejected": True, "reason": "لا تشرح المنصة", "at": "2026-11-14T10:07:00+00:00"},
            {"sketch": 5, "note": "احفظ الميل", "at": "2026-11-14T10:08:00+00:00"},
            {"sketch": 5, "rebuild": True, "reason": "ليس هذا الشعار", "at": "2026-11-14T10:09:00+00:00"}]
    (v / "designer_decisions.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    owned = [e["text"] for e in timeline.timeline(v)["events"] if e["who"] == "owner"]
    for part in ("الطابع", "أقرب إلى الهندسي", "تطوير السكتش 3", "رفضت صفحة السكتشات: لا تشرح المنصة", "اخترت السكتش 5", "احفظ الميل",
                 "رددت متجه السكتش 5: ليس هذا الشعار", "تحقق الاسم"):
        assert any(part in x for x in owned), part


def test_finished_runs_leave_the_today_page(tmp_path, monkeypatch):
    jobs = PipelineJobs(tmp_path, runner=lambda b: (0, "تم"), settle=0)
    assert jobs.start("p", Path("p.yaml"))
    for _ in range(100):
        if jobs.snapshot()[0]["state"] != "running":
            break
        time.sleep(0.05)
    assert [j["state"] for j in jobs.snapshot()] == ["done"]  # يبقى قليلًا ليُرى ما انتهى إليه
    real = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real() + 3600)
    assert jobs.snapshot() == []


def test_cancelled_medium_rule_is_not_printed_any_more():
    src = Path(inbox.__file__).parent.joinpath("preview.py").read_text(encoding="utf-8")
    assert "الرفض الثالث" not in src


# ---------- م7 ----------
def test_hidden_project_log_is_not_served(tmp_path, monkeypatch):
    pytest.importorskip("django")
    monkeypatch.setenv("SIMA_OUT", str(tmp_path))
    monkeypatch.setenv("SIMA_BOARD_PORT", "8766")
    monkeypatch.delenv("SIMA_BOARD_REPO", raising=False)
    from sima.web import setup

    setup()
    from django.test import Client

    _version(tmp_path, ("brief",))
    client = Client(HTTP_HOST="127.0.0.1:8766")
    assert client.get("/api/timeline/proj").status_code == 200
    state = client.get("/api/state").json()
    assert state["limits"] == inbox.LIMITS and state["sima"][0]["audit"] == {"passed": 0, "failed": 0}
    monkeypatch.setattr(config, "BOARD_HIDDEN", ("proj",))
    assert client.get("/api/timeline/proj").status_code == 404 and client.get("/api/state").json()["sima"] == []


# ---------- م9 وم10 ----------
def test_database_failure_does_not_keep_the_platform_from_starting():
    lines = (config.ROOT / "scripts" / "start_all.ps1").read_text(encoding="utf-8").splitlines()
    at = next(i for i, ln in enumerate(lines) if "sima db start" in ln)
    block = "\n".join(lines[at:at + 4])
    assert "exit 1" not in block and "Write-Warning" in block
    assert any("sima board" in ln for ln in lines[at:])


def test_delivery_commit_is_attributed_to_the_models_that_worked_on_the_version(tmp_path):
    """نقطة التسليم في مستودع المشروع كانت تنتهي باسم نموذج ثابت؛ الآن بما سجّله `model_calls.jsonl`، وبلا سطر إن لم يعمل نموذج."""
    import subprocess

    from sima.adapters import ledger_runner
    from sima.adapters.auto_deliver import co_authors

    assert not hasattr(ledger_runner, "CO_AUTHOR")
    repo = tmp_path / "repo"
    (repo / "automation").mkdir(parents=True)
    (repo / "automation" / "ledger.py").write_text("", encoding="utf-8")

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=repo, text=True, encoding="utf-8", capture_output=True, check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@example.test")
    git("config", "user.name", "t")
    v = tmp_path / "v1"
    v.mkdir()
    (v / "model_calls.jsonl").write_text(json.dumps({"ok": True, "model": "claude-opus-5-5"}) + "\n", encoding="utf-8")
    (repo / "a.txt").write_text("1", encoding="utf-8")
    ledger_runner.LedgerRunnerTarget(repo, co_authors=co_authors(v)).commit(repo, ("a.txt",), "هوية")
    assert git("log", "-1", "--format=%B").strip().endswith("Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    (repo / "a.txt").write_text("2", encoding="utf-8")
    ledger_runner.LedgerRunnerTarget(repo).commit(repo, ("a.txt",), "هوية بلا نموذج")
    assert "Co-Authored-By" not in git("log", "-1", "--format=%B")


# ---------- ب15 ----------
def test_inherited_version_marks_its_ancestors_events(tmp_path):
    """علامة `adopted` الموروثة بوقت السلف كانت تُحسب بداية الإصدار، فلا يوسَم شيء «من الإصدار السابق»."""
    v = _version(tmp_path, ())
    st = v / "stages"
    (st / "adopted.json").write_text(json.dumps({"at": "2026-11-10T08:00:00+00:00"}), encoding="utf-8")
    (st / "research.json").write_text(json.dumps({"at": "2026-11-10T08:05:00+00:00"}), encoding="utf-8")
    (st / "inherited.json").write_text(json.dumps({"at": "2026-11-14T09:00:00+00:00"}), encoding="utf-8")
    (st / "brief.json").write_text(json.dumps({"at": "2026-11-14T09:00:01+00:00"}), encoding="utf-8")
    events = {e["at"]: e["text"] for e in timeline.timeline(v)["events"]}
    assert events["2026-11-10T08:05:00+00:00"].endswith("(من الإصدار السابق)")
    assert not events["2026-11-14T09:00:01+00:00"].endswith("(من الإصدار السابق)")
