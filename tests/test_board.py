"""اختبارات لوحة الأتمتة: خطوات البطاقة من الأحداث، وحالة سِمة من علامات المراحل."""
from __future__ import annotations

import json

from sima.services.board import board_state, card_steps


def _status(steps, key):
    return next(s["status"] for s in steps if s["key"] == key)


def test_card_progress_marks_next_as_current():
    steps = card_steps([{"event": "created"}, {"event": "ready"}, {"event": "claimed"}])
    assert _status(steps, "claimed") == "done" and _status(steps, "coded") == "current" and _status(steps, "merged") == "pending"


def test_prepush_failure_replaces_ok_step():
    steps = card_steps([{"event": e} for e in ("created", "ready", "claimed", "coded", "prepush_failed")])
    assert _status(steps, "prepush_failed") == "failed"
    assert not any(s["status"] == "current" for s in steps)


def test_retry_after_failure_shows_progress():
    evs = [{"event": e} for e in ("created", "ready", "claimed", "coded", "prepush_failed", "ready", "claimed", "coded", "prepush_ok")]
    steps = card_steps(evs)
    assert _status(steps, "prepush_ok") == "done" and _status(steps, "pr_opened") == "current"


def test_board_state_reads_ledger_and_stages(tmp_path):
    led = tmp_path / "repo" / "automation" / "ledger"
    led.mkdir(parents=True)
    (led / "c1.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in [
        {"card": "c1", "event": "created", "at": "2026-01-01T00:00:00+00:00", "title": "بطاقة"},
        {"card": "c1", "event": "pr_opened", "at": "2026-01-01T00:05:00+00:00", "url": "https://example.test/pr/1"},
    ]) + "\nnot-json\n", encoding="utf-8")
    st = tmp_path / "out" / "proj" / "v2" / "stages"
    st.mkdir(parents=True)
    for s in ("brief", "research"):
        (st / f"{s}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "out" / "proj" / "v1").mkdir()
    state = board_state(tmp_path / "repo", tmp_path / "out", "now")
    card = state["cards"][0]
    assert card["title"] == "بطاقة" and card["state"] == "pr_opened" and card["url"].endswith("/1")
    run = state["sima"][0]
    assert run["version"] == "v2" and _status(run["steps"], "research") == "done" and _status(run["steps"], "diverge") == "current"
    assert board_state(None, tmp_path / "missing", "now") == {"now": "now", "repo": "", "sima": [], "cards": [],
                                                              "runner": {"running": False, "pid": ""}}


def _ev(*names):
    return [{"event": n, "at": f"2026-01-01T00:0{i}:00+00:00"} for i, n in enumerate(names)]


def test_track_marks_active_node_and_chip():
    from sima.services.board import card_track
    t = card_track(_ev("created", "ready", "claimed", "coded", "prepush_ok", "pr_opened"))
    assert t["p"] == 3 and t["chip"] == "run"
    assert [n["status"] for n in t["nodes"]] == ["done", "done", "done", "active"] + ["pending"] * 4


def test_track_failure_and_retry_attempt():
    from sima.services.board import card_track
    t = card_track(_ev("created", "ready", "claimed", "coded", "prepush_failed"))
    assert t["p"] == 2 and t["chip"] == "bad" and t["nodes"][2]["status"] == "fail" and t["status_kind"] == "bad"
    t2 = card_track(_ev("created", "ready", "claimed", "coded", "prepush_failed", "ready"))
    assert t2["p"] == 0 and t2["nodes"][0]["status"] == "active" and t2["attempts"] == 1


def test_track_finished_and_log_newest_first():
    from sima.services.board import card_log, card_track
    evs = _ev("created", "ready", "claimed", "coded", "prepush_ok", "pr_opened", "approved", "merged", "deployed")
    t = card_track(evs)
    assert t["chip"] == "good" and all(n["status"] == "done" for n in t["nodes"])
    log = card_log(evs)
    assert log[0]["text"].startswith("نُشرت") and log[0]["kind"] == "good" and log[-1]["text"].startswith("أُنشئت")


def test_safe_out_path_rejects_escape_hidden_and_work(tmp_path):
    from sima.services.board import safe_out_path
    pkg = tmp_path / "p" / "v1" / "package"
    pkg.mkdir(parents=True)
    (pkg / "mark.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "p" / "v1" / "work").mkdir()
    (tmp_path / "p" / "v1" / "work" / "x.svg").write_text("x", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("s", encoding="utf-8")
    assert safe_out_path(tmp_path, "p/v1/package/mark.svg") == (pkg / "mark.svg").resolve()
    for bad in ("../secret.txt", "p/../../secret.txt", "p/v1/work/x.svg", ".git/config", "p/v1/package/missing.svg", "p/v1"):
        assert safe_out_path(tmp_path, bad) is None


def test_project_detail_reads_decisions_and_name_check(tmp_path):
    from sima.services.board import project_detail
    v = tmp_path / "proj" / "v1"
    (v / "package").mkdir(parents=True)
    (v / "package" / "x-lockup.svg").write_text("<svg/>", encoding="utf-8")
    (v / "name_check.yaml").write_text("name: x\nstatus: clear\nchecked_at: '2026-01-01T00:00:00+00:00'\nnote: أولي\n", encoding="utf-8")
    d = project_detail(v)
    assert d["mark"].endswith("package/x-lockup.svg") and d["name_check"]["status"] == "clear"
    assert any(f["name"] == "x-lockup.svg" for f in d["files"]) and d["decisions"] == []


def test_track_preview_wait_and_rejection():
    from sima.services.board import card_track
    base = ("created", "ready", "claimed", "coded", "prepush_ok", "pr_opened", "ci_green", "preview_ready")
    t = card_track(_ev(*base))
    assert t["p"] == 4 and t["nodes"][4]["key"] == "preview" and t["nodes"][4]["status"] == "active" and t["chip"] == "run"
    r = card_track(_ev(*base, "preview_rejected"))
    assert r["p"] == 5 and r["nodes"][5]["status"] == "fail" and r["chip"] == "bad"


def test_without_hidden_filters_display_only():
    from sima.services.board import without_hidden

    st = {"now": "t", "sima": [{"project": "sima"}, {"project": "math_papers"}], "inbox": [{"project": "math_papers"}, {"project": "sima"}],
          "jobs": [{"project": "math_papers"}], "cards": [{"id": 1}]}
    got = without_hidden(st, ("math_papers",))
    assert [x["project"] for x in got["sima"]] == ["sima"] and [x["project"] for x in got["inbox"]] == ["sima"]
    assert got["jobs"] == [] and got["cards"] == [{"id": 1}] and got["now"] == "t"
    assert len(st["sima"]) == 2  # الأصل لا يتغيّر
    assert without_hidden(st, ()) is st


def test_cost_state_levels_and_judge_state(tmp_path):
    import json

    from sima.services.board import cost_state, judge_state

    v = tmp_path / "p" / "v1"
    (v / "stages").mkdir(parents=True)
    assert cost_state(v, 10) == {"usd": 0.0, "calls": 0, "ref": 10, "level": "ok", "unknown": 0}
    (v / "model_calls.jsonl").write_text("\n".join(json.dumps({"cost_usd": x}) for x in (3.0, 4.2)), encoding="utf-8")
    assert cost_state(v, 10)["level"] == "warn" and cost_state(v, 10)["usd"] == 7.2  # 72% من المرجع
    assert cost_state(v, 7)["level"] == "over" and cost_state(v, 100)["level"] == "ok"
    (v / "stages" / "shortlist.json").write_text(json.dumps({"scores": {"c5": 23, "c2": 31}}), encoding="utf-8")
    assert judge_state(v, "c5") == {"total": 23, "bar": 30, "below": True}
    assert judge_state(v, "c2")["below"] is False
    assert judge_state(v, "zz") == {"total": None, "bar": 30, "below": False} and judge_state(v, "")["total"] is None
