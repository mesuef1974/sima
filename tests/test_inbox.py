"""صندوق قرارات المنصة: ما ينتظر المالك، وقرار مربوط بالمفتاح المعروض، وتحقق الاسم، وتشغيل الخلفية."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from sima.adapters.pipeline_jobs import PipelineJobs
from sima.config import ROOT
from sima.services.board import safe_out_path
from sima.services.inbox import InboxError, decide, name_check, owner_inbox

CONCEPTS = """concepts:
  - id: w1
    name: على السطر
    family: literal
    medium: wordmark
    sentence: "كلمة على سطر"
  - id: w2
    name: أسطر الدفتر
    family: metaphorical
    medium: wordmark
    sentence: "سطران يقطعان الكلمة"
"""


@pytest.fixture
def out(tmp_path: Path) -> Path:
    v = tmp_path / "proj" / "v1"
    (v / "work" / "concepts").mkdir(parents=True)
    (v / "run.json").write_text(json.dumps({"project": "proj", "key": "abc123-s1", "brief_hash": "abc123", "seed": 1, "version": 1,
                                            "brief_source": "briefs/math_papers.yaml", "closed": False}), encoding="utf-8")
    (v / "preview.html").write_text("<html></html>", encoding="utf-8")
    (v / "work" / "concepts.yaml").write_text(CONCEPTS, encoding="utf-8")
    (v / "work" / "concepts" / "w1.svg").write_text("<svg/>", encoding="utf-8")
    (v / "work" / "REQUEST-diverge.md").write_text("x", encoding="utf-8")
    _reached_owner(v)
    return tmp_path


def _reached_owner(v: Path) -> None:
    """ما يكتبه الخط حين يبني المعاينة لمحتوى الرسوم الحالي، أي حين يصل فعلًا إلى قرار المالك."""
    from sima.services.inbox import _workspace
    from sima.services.protocol import merged_digest, read_concept_svgs, read_concepts, read_small_svgs

    ws, _ = _workspace(v)
    cs = read_concepts(ws)
    ws.mark_done("preview", {"digest": merged_digest(read_concept_svgs(ws, cs), read_small_svgs(ws, cs))})


def test_card_hidden_while_pipeline_redraws(out):
    v = out / "proj" / "v1"
    (v / "work" / "concepts" / "w1.svg").write_text("<svg><rect/></svg>", encoding="utf-8")
    assert owner_inbox(out) == []  # رسم جديد لم يصل إلى المالك بعد
    _reached_owner(v)
    assert owner_inbox(out)[0]["kind"] == "concepts"


def test_inbox_lists_concepts_with_images(out):
    [item] = owner_inbox(out)
    assert item["kind"] == "concepts" and item["key"] == "abc123-s1" and item["version"] == 1
    assert [c["id"] for c in item["concepts"]] == ["w1", "w2"]
    assert item["concepts"][0]["img"] == "proj/v1/work/concepts/w1.svg" and item["concepts"][1]["img"] == ""


def test_decision_bound_to_displayed_key_and_reason_required(out):
    with pytest.raises(InboxError, match="تغيّر"):
        decide(out, "proj", 1, "old-key", "approved", "w1", "")
    with pytest.raises(InboxError, match="سببًا"):
        decide(out, "proj", 1, "abc123-s1", "rejected", "w2", "")
    with pytest.raises(InboxError, match="المعروض"):
        decide(out, "proj", 1, "abc123-s1", "approved", "zz", "")
    with pytest.raises(InboxError):
        decide(out, "../x", 1, "abc123-s1", "approved", "w1", "")
    assert "طُلب تعديل" in decide(out, "proj", 1, "abc123-s1", "revise", "w2", "أوضح الأسطر")
    assert owner_inbox(out)[0]["concepts"][1]["last"] == "طُلب تعديل"


def test_stale_page_cannot_approve_a_redrawn_concept(out):
    [item] = owner_inbox(out)
    seen = item["digest"]
    svg = out / "proj" / "v1" / "work" / "concepts" / "w1.svg"
    svg.parent.mkdir(parents=True, exist_ok=True)
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>', encoding="utf-8")  # أعاد النموذج الرسم
    with pytest.raises(InboxError, match="تغيّر ما عُرض"):  # أثناء إعادة الرسم لا بطاقة أصلًا
        decide(out, "proj", 1, "abc123-s1", "approved", "w1", "", seen)
    _reached_owner(out / "proj" / "v1")
    with pytest.raises(InboxError, match="تغيّرت رسوم المفاهيم"):
        decide(out, "proj", 1, "abc123-s1", "approved", "w1", "", seen)
    assert "w1" in decide(out, "proj", 1, "abc123-s1", "approved", "w1", "", owner_inbox(out)[0]["digest"])


def test_approval_moves_to_name_check_then_clears(out):
    decide(out, "proj", 1, "abc123-s1", "approved", "w1", "")
    [item] = owner_inbox(out)
    assert item["kind"] == "name_check" and item["concept"] == "w1" and len(item["sources"]) == 7
    with pytest.raises(InboxError, match="هذا القرار"):
        decide(out, "proj", 1, "abc123-s1", "approved", "w1", "")
    with pytest.raises(InboxError, match="مصدرًا"):
        name_check(out, ROOT, "proj", 1, "abc123-s1", "clear", [], "")
    with pytest.raises(InboxError, match="مصدر غير معروف"):
        name_check(out, ROOT, "proj", 1, "abc123-s1", "clear", ["EVIL"], "")
    with pytest.raises(InboxError, match="ملاحظة"):
        name_check(out, ROOT, "proj", 1, "abc123-s1", "conflict", ["WIPO"], "")
    assert "سُجّل" in name_check(out, ROOT, "proj", 1, "abc123-s1", "clear", ["WIPO", "MOCI"], "فحص رسمي")
    assert owner_inbox(out) == []


def test_concept_images_served_but_not_other_work_files(out):
    assert safe_out_path(out, "proj/v1/work/concepts/w1.svg") is not None
    (out / "proj" / "v1" / "work" / "styles").mkdir()
    (out / "proj" / "v1" / "work" / "styles" / "s1.svg").write_text("<svg/>", encoding="utf-8")
    (out / "proj" / "v1" / "work" / "styles" / "s1.mark.yaml").write_text("x", encoding="utf-8")
    assert safe_out_path(out, "proj/v1/work/styles/s1.svg") is not None  # عينات بطاقة الطابع
    for bad in ("proj/v1/work/REQUEST-diverge.md", "proj/v1/work/concepts.yaml", "proj/v1/work/concepts/../concepts.yaml",
                "proj/v1/work/styles/s1.mark.yaml", "proj/v1/work/judge/x.svg"):
        assert safe_out_path(out, bad) is None


def test_jobs_one_per_project_and_report_outcome(tmp_path):
    gate = threading.Event()

    def fake(_brief):
        gate.wait(5)
        return 4, "ورقة المعاينة جاهزة\nبانتظار قرار المالك"

    jobs = PipelineJobs(tmp_path, runner=fake, settle=0)
    assert jobs.start("p", tmp_path / "b.yaml") is True
    assert jobs.start("p", tmp_path / "b.yaml") is False
    gate.set()
    for _ in range(100):
        if jobs.snapshot()[0]["state"] != "running":
            break
        time.sleep(0.02)
    [j] = jobs.snapshot()
    assert j["state"] == "done" and j["code_ar"] == "بانتظار قرارك" and "بانتظار" in j["message"]


def test_decision_during_run_is_never_lost_and_busy_lock_is_awaited(tmp_path, monkeypatch):
    from sima.adapters import pipeline_jobs
    from sima.adapters.run_lock import BUSY

    monkeypatch.setattr(pipeline_jobs, "BUSY_WAIT_S", 0)
    gate = threading.Event()
    script = iter([None, BUSY, 4])
    runs: list[int] = []

    def fake(_brief):
        step = next(script)
        if step is None:
            gate.wait(5)
            step = 3
        runs.append(step)
        return step, "x"

    jobs = PipelineJobs(tmp_path, runner=fake, settle=0)
    assert jobs.start("p", tmp_path / "b.yaml") is True
    assert jobs.start("p", tmp_path / "b.yaml") is False  # قرار أثناء التشغيل: يُعلَّم ولا يُهمل
    gate.set()
    for _ in range(200):
        if jobs.snapshot()[0]["state"] != "running":
            break
        time.sleep(0.02)
    assert runs == [3, BUSY, 4] and jobs.snapshot()[0]["code_ar"] == "بانتظار قرارك"


def test_decisions_in_quick_succession_share_one_run(tmp_path):
    runs: list[float] = []

    def fake(_brief):
        runs.append(time.monotonic())
        return 4, "بانتظار قرار المالك"

    jobs = PipelineJobs(tmp_path, runner=fake, settle=0.3)
    t0 = time.monotonic()
    assert jobs.start("p", tmp_path / "b.yaml") is True
    time.sleep(0.15)
    assert jobs.start("p", tmp_path / "b.yaml") is True  # داخل المهلة: يلحق بالتشغيل نفسه ويمدّها
    assert jobs.snapshot()[0]["rerun"] is False
    for _ in range(200):
        if jobs.snapshot()[0]["state"] != "running":
            break
        time.sleep(0.02)
    assert len(runs) == 1 and runs[0] - t0 >= 0.4  # تشغيل واحد بعد آخر قرار بمهلة كاملة


def test_project_lock_blocks_second_run_and_survives_restart(tmp_path):
    import json
    import os

    import pytest

    from sima.adapters.run_lock import ProjectBusy, lock_path, project_lock

    with project_lock(tmp_path, "p"):
        with pytest.raises(ProjectBusy), project_lock(tmp_path, "p"):
            pass
        jobs = PipelineJobs(tmp_path, runner=lambda b: (0, ""), out_dir=tmp_path)
        assert [j["project"] for j in jobs.snapshot() if j["state"] == "running"] == ["p"]
    assert not lock_path(tmp_path, "p").exists()
    lock_path(tmp_path, "p").write_text(json.dumps({"pid": 999_999_999}), encoding="utf-8")  # قفل يتيم
    with project_lock(tmp_path, "p"):
        assert json.loads(lock_path(tmp_path, "p").read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_shortlist_filters_concepts_with_scores_and_old_verdicts_hide(out):
    v = out / "proj" / "v1"
    decide(out, "proj", 1, "abc123-s1", "rejected", "w1", "قديم")
    (v / "stages").mkdir(exist_ok=True)
    (v / "stages" / "shortlist.json").write_text(json.dumps({"ids": ["w2"], "below_bar": True, "scores": {"w2": 28}, "passed": []}),
                                                 encoding="utf-8")
    (v / "stages" / "owner_feedback.json").write_text(json.dumps({"handled": 1}), encoding="utf-8")
    [item] = owner_inbox(out)
    assert [c["id"] for c in item["concepts"]] == ["w2"] and item["below_bar"] is True
    assert item["concepts"][0]["score"] == 28 and item["concepts"][0]["passed"] is False and item["concepts"][0]["last"] == ""
    assert item["medium"] == "abstract_mark" and {m["id"] for m in item["mediums"]} >= {"emblem", "wordmark"}


def test_owner_switches_medium_with_reason(out):
    from sima.services.inbox import switch_medium
    from sima.services.ledger import Ledger

    with pytest.raises(InboxError, match="ما تريده"):
        switch_medium(out, "proj", 1, "abc123-s1", "emblem", "")
    with pytest.raises(InboxError, match="غير معروف"):
        switch_medium(out, "proj", 1, "abc123-s1", "logo", "أريد")
    assert "شارة" in switch_medium(out, "proj", 1, "abc123-s1", "emblem", "أريد شارة معاصرة")
    led = Ledger(out / "proj" / "v1" / "decisions.jsonl")
    assert led.lock().current().value == "emblem" and led.read()[-1].reason == "أريد شارة معاصرة"


@pytest.mark.style_gate
def test_style_card_shows_only_at_gate_and_choice_is_bound_to_samples(out):
    from sima.services import style
    from sima.services.inbox import InboxError, _workspace, choose_style, owner_inbox
    ws, _ = _workspace(out / "proj" / "v1")
    assert owner_inbox(out) == []  # لا عينات ولا اختيار: الخط ينتظر النموذج
    d = style.styles_dir(ws)
    d.mkdir(parents=True)
    for n, sid in enumerate(style.catalog()):
        (d / f"{sid}.svg").write_text(f'<svg viewBox="0 0 9 9"><path d="M0 0H{n + 1}V1Z"/></svg>', encoding="utf-8")
    assert owner_inbox(out) == []  # العينات وحدها لا تكفي: البطاقة حين يصل الخط إلى البوابة
    ws.mark_done("style_board", {"digest": style.digest(ws)})
    [item] = owner_inbox(out)
    assert item["kind"] == "style" and len(item["styles"]) == 6 and item["max"] == 2
    with pytest.raises(InboxError):
        choose_style(out, "proj", 1, item["key"], "قديم", ["s1"], "")
    with pytest.raises(InboxError):
        choose_style(out, "proj", 1, item["key"], item["digest"], ["s1", "s2", "s3"], "")
    msg = choose_style(out, "proj", 1, item["key"], item["digest"], ["s1", "s4"], "بلا زخرفة")
    assert "هندسي أحادي الخط" in msg and style.current(ws)["styles"] == ["s1", "s4"]
    assert owner_inbox(out) == []  # المفاهيم المعروضة رُسمت قبل الطابع: تختفي حتى يعيد الخط رسمها به
    ws.mark_done("style_epoch", {"choices": 1})
    assert owner_inbox(out)[0]["kind"] == "concepts"
