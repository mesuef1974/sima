"""زر «إصدار جديد» في المنصة (قرار المالك 2026-11-20): بعد إصدار مغلق تغيّر بعده موجزه أو محتوى بيان اعتماده يُفتح إصدار
بـ`sima run --new-version` من المنصة، ولا يُفتح بلا مدخل جديد ولا على إصدار مفتوح ولا بمفتاح غير المعروض. لا نموذج ولا شبكة."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from sima.adapters.pipeline_jobs import PipelineJobs
from sima.services import inbox

RUN = {"project": "p", "key": "h-s1", "brief_hash": "h", "seed": 1, "version": 1, "brief_source": "briefs/p.yaml", "closed": True}


@pytest.fixture
def out(tmp_path, monkeypatch):
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs" / "p.yaml").write_text("x", encoding="utf-8")
    v = tmp_path / "out" / "p" / "v1"
    (v / "stages").mkdir(parents=True)
    (v / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    (v / "stages" / "adopted.json").write_text(json.dumps({"digest": "old"}), encoding="utf-8")
    live = {"hash": "h", "digest": "old"}
    monkeypatch.setattr(inbox, "load_brief", lambda p: SimpleNamespace(hash=lambda: live["hash"]))
    monkeypatch.setattr(inbox.adopt, "load", lambda b: SimpleNamespace(digest=live["digest"]))
    return tmp_path, live


def test_reason_only_after_a_closed_latest_version_whose_inputs_changed(out):
    root, live = out
    o = root / "out"
    assert inbox.renew_reason(o, root, "p", 1) == ""  # لا مدخل جديد
    live["digest"] = "new"
    assert "بيان الاعتماد" in inbox.renew_reason(o, root, "p", 1)
    live["digest"], live["hash"] = "old", "h2"
    assert "موجز المشروع" in inbox.renew_reason(o, root, "p", 1)
    assert inbox.renew_reason(o, root, "p", 2) == "" and inbox.renew_reason(o, root, "../p", 1) == ""
    (o / "p" / "v1" / "run.json").write_text(json.dumps({**RUN, "closed": False}), encoding="utf-8")
    assert inbox.renew_reason(o, root, "p", 1) == ""  # المفتوح يُستأنف ولا يُفتح بعده إصدار


def test_renew_refuses_a_stale_page_or_no_new_input(out):
    root, live = out
    o = root / "out"
    with pytest.raises(inbox.InboxError, match="لا إصدار جديد بلا مدخل جديد"):
        inbox.renew(o, root, "p", 1, "h-s1")
    live["digest"] = "new"
    with pytest.raises(inbox.InboxError, match="حدّثها"):
        inbox.renew(o, root, "p", 1, "other")
    assert "يُفتح v2" in inbox.renew(o, root, "p", 1, "h-s1")


def test_jobs_pass_new_version_once_and_never_join_a_running_job(tmp_path):
    calls = []

    def runner(brief, **kw):
        calls.append(kw)
        return 0, ""

    jobs = PipelineJobs(tmp_path, runner=runner, settle=0)
    jobs._work(SimpleNamespace(settle_until=0.0, rerun=True, code=None, message="", ended="", ended_at=0.0, state="running"),
               tmp_path / "b.yaml", {"new_version": True})
    assert calls == [{"new_version": True}, {}]  # قرار وصل أثناءه يُستأنف على الإصدار الذي فُتح، لا إصدار ثالث
    jobs._jobs["p"] = SimpleNamespace(state="running", settle_until=0.0, rerun=False)
    assert jobs.start("p", tmp_path / "b.yaml", new_version=True) is False and jobs._jobs["p"].rerun is False
