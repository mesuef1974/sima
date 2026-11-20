"""علامة النتيجة (مراجعة الأتمتة 2026-11-14، المرحلة 1): الخط يكتب ما وقف عنده في الإصدار، والوارد والصندوق والسجل يقرؤونه
ولا يستنتجونه؛ فلا إصدار يقف عند المالك بلا بطاقة، ولا بطاقة والخط عند غيره؛ والتوقف حالة بسببها تُستأنف بزر."""
from __future__ import annotations

import inspect
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from sima.adapters.pipeline_jobs import PipelineJobs
from sima.domain.identity import Gate
from sima.services import outcome
from sima.services.autopilot import STOPPED, ModelResult, run_until_owner
from sima.services.identity_protocol import digest, directions_digest, ledger, strategy_path
from sima.services.inbox import InboxError, identity_decide, owner_inbox, resume
from sima.services.namecheck import read_name_check, write_name_check
from sima.services.pipeline import AWAIT_MODEL, AWAIT_OWNER, Outcome
from sima.services.timeline import timeline
from sima.services.workspace import Workspace

from .test_adopt import project  # noqa: F401  (علامة واتجاه معتمدان خارج الخط: يبلغ بوابات الهوية بلا نموذج)
from .test_autopilot import FakeModel, _ws


def _card(tmp: Path) -> dict | None:
    return next(iter(owner_inbox(tmp / "out")), None)


# ---------- الخط يكتب نتيجته، والوارد يقرؤها ----------
def test_line_writes_what_it_stopped_at_and_the_inbox_shows_that_gate(project):  # noqa: F811
    tmp, _, brief, pipe = project
    out = pipe.run(brief)
    ws = out.workspace
    o = outcome.current(ws.root)
    assert (out.gate, out.digest) == ("directions", directions_digest(ws))
    assert o["who"] == "owner" and (o["gate"], o["digest"], o["code"]) == ("directions", directions_digest(ws), AWAIT_OWNER)
    assert _card(tmp)["gate"] == "directions"
    # قرار يُكتب بعد النتيجة يُبطلها حتى يُستأنف الخط: لا يُقرأ منها من يُنتظر
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    assert outcome.current(ws.root) is None and outcome.superseded(ws.root)
    now = timeline(ws.root)["now"]
    assert now["resume"] and "لم يُستأنف الخط" in now["text"]
    out = pipe.run(brief)
    assert out.gate == "book" and outcome.current(ws.root)["gate"] == "book" and _card(tmp)["gate"] == "book"


def test_owner_stop_without_a_decision_card_still_shows_with_resume(project):  # noqa: F811
    """ب13: اتجاه معتمد واحد طلب المالك تعديله. الخط يقف عنده برمز 4 ولا قرار يُعرض في بطاقة؛ كان الوارد فارغًا."""
    tmp, _, brief, pipe = project
    ws = pipe.run(brief).workspace
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "revise", "d1", "غيّر الذهبي")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and out.gate == "" and "غيّر الذهبي" in out.message
    item = _card(tmp)
    assert item["kind"] == "stalled" and "غيّر الذهبي" in item["message"] and item["title"] == "الخط واقف عندك"
    now = timeline(ws.root, item)["now"]
    assert now["who"] == "owner" and now["state"] == "stopped" and now["resume"]
    with pytest.raises(InboxError, match="لم يعد ينتظر هذا القرار"):  # ما وقف عنده الخط ليس بوابة تُقرَّر
        identity_decide(tmp / "out", "demo", ws.version, ws.key.key, "directions", item["digest"], "approved", "d1", "")


def test_strategy_edited_after_approval_shows_its_gate_not_a_stale_book(project):  # noqa: F811
    """ب1 وب10 وب12: منصة عُدّلت بعد اعتمادها. الخط يقف عند بوابتها؛ كانت علامتها الباقية تخفي بطاقتها وتُعرض بطاقة الدليل
    القديم. وطلب تعديل أجابه النموذج بلا تغيير يعود إلى المالك بجوابه كاملًا بدل أن ينتظر النموذج أبدًا."""
    tmp, _, brief, pipe = project
    ws = pipe.run(brief).workspace
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    assert pipe.run(brief).gate == "book" and _card(tmp)["gate"] == "book"
    strategy_path(ws).write_text(strategy_path(ws).read_text(encoding="utf-8") + "\n# عُدّلت بعد الاعتماد\n", encoding="utf-8")
    out = pipe.run(brief)
    dg = digest([strategy_path(ws)])
    assert out.code == AWAIT_OWNER and (out.gate, out.digest) == ("strategy", dg), out.message
    item = _card(tmp)
    assert (item["gate"], item["digest"], item["reply"]) == ("strategy", dg, None)

    asked = ledger(ws).record(Gate.STRATEGY, dg, "revise", reason="لماذا هذا الوعد؟")
    out = pipe.run(brief)
    assert out.code == AWAIT_MODEL and out.request == "REQUEST-strategy.md" and _card(tmp) is None
    answer = "الوعد مأخوذ من الموجز: " + "تفصيل " * 120  # أطول من خلاصة السجل (400 حرف)
    call = {"at": asked.at, "request": "REQUEST-strategy.md", "ok": True, "summary": answer[-400:], "reply": answer}
    (ws.root / "model_calls.jsonl").write_text(json.dumps(call, ensure_ascii=False) + "\n", encoding="utf-8")
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and out.gate == "strategy" and "جواب الخط" in out.message, out.message
    item = _card(tmp)
    assert item["gate"] == "strategy" and item["reply"] == {"note": "لماذا هذا الوعد؟", "text": answer.strip()}


def test_name_check_inherited_for_another_name_is_asked_again(project):  # noqa: F811
    """ب3: «متاح» مسجّل لاسم آخر لا يكفي الخط، فلا يكفي البطاقة. كانت تفحص الحالة وحدها فتعرض بطاقة الاتجاه والخط عند الاسم."""
    tmp, _, brief, pipe = project
    ws = pipe.run(brief).workspace
    write_name_check(ws, replace(read_name_check(ws), name="اسم قديم"))
    assert _card(tmp)["kind"] == "name_check"  # قبل أن يُستأنف الخط أيضًا
    out = pipe.run(brief)
    assert out.code == AWAIT_OWNER and out.gate == "name_check"
    item = _card(tmp)
    assert item["kind"] == "name_check" and item["name"] == brief.wordmark_text and item["status"] == "" and "اسم قديم" in item["note"]


def test_inherited_version_does_not_carry_gate_markers_and_the_card_ignores_them(project, tmp_path):  # noqa: F811
    """ب2: قرارات بوابات الهوية لا تورَّث، فعلاماتها لا تورَّث؛ وعلامة `directions` ببصمة مطابقة بلا قرار لا تخفي البطاقة."""
    tmp, _, brief, pipe = project
    ws = pipe.run(brief).workspace
    ws.mark_done("directions", {"digest": directions_digest(ws), "option": "d1"})  # علامة باقية بلا قرار في السجل
    assert _card(tmp)["gate"] == "directions"
    (ws.root / outcome.FILE).unlink()  # وبلا نتيجة مكتوبة (إصدار أقدم من العلامة): الاستنتاج من الملفات لا يُخفيها كذلك
    assert _card(tmp)["gate"] == "directions"

    src = tmp_path / "inherit" / "demo" / "v1"
    (src / "work").mkdir(parents=True)
    (src / "stages").mkdir()
    (src / "decisions.jsonl").write_text("", encoding="utf-8")
    kept, dropped = {"render", "adopted"}, {"strategy", "directions", "directions_board", "name_check", "designer_fix", "package", "identity"}
    for name in kept | dropped:
        (src / "stages" / f"{name}.json").write_text("{}", encoding="utf-8")
    heir = Workspace(root=src.parent / "v2", key=ws.key, version=2)
    pipe._inherit_mark(heir, replace(brief, identity=replace(brief.identity, inherit_mark="v1")))
    assert {p.stem for p in (heir.root / "stages").glob("*.json")} == kept | {"inherited"}


# ---------- التوقف حالة بسببها، لا اكتمال ----------
def test_autopilot_stop_is_a_distinct_code_with_its_reason_on_disk(tmp_path):
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-diverge.md").write_text("طلب", encoding="utf-8")
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, "بانتظار النموذج", ws, request="REQUEST-diverge.md"), FakeModel(cost=0.1), max_calls=1)
    assert out.code == STOPPED == 6 and "سقف 1 استدعاءات" in out.message
    o = outcome.current(ws.root)
    assert o["who"] == "model" and o["request"] == "REQUEST-diverge.md" and "سقف 1 استدعاءات" in o["stopped"]
    now = timeline_now(ws)
    assert now["state"] == "stopped" and now["resume"] and "سقف 1 استدعاءات" in now["text"] and "رسم المفاهيم" in now["text"]
    assert inspect.signature(run_until_owner).parameters["max_usd"].default == 15  # قرار المالك 2026-11-14


def timeline_now(ws: Workspace) -> dict:
    (ws.root / "run.json").write_text(json.dumps({"project": "p", "key": "h-s1", "brief_hash": "h", "seed": 1, "version": 1,
                                                  "closed": False}), encoding="utf-8")
    return timeline(ws.root)["now"]


def test_default_caps_follow_the_owner_decision(monkeypatch):
    from sima import config
    from sima.adapters import claude_model

    monkeypatch.setattr(config, "ENV", {})  # القارئ الوحيد للبيئة
    assert (claude_model.max_calls(), claude_model.max_total_usd()) == (16, 15.0)


def test_autopilot_calls_the_request_the_line_named_not_the_newest_file(tmp_path):
    """خ8: طلب مطابق لنصّه السابق لا يُعاد كتابته فيبقى وقته قديمًا؛ كان أحدث ملف وقتًا يُستدعى بدل المنتظَر."""
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-refine.md").write_text("صقل", encoding="utf-8")
    time.sleep(0.02)
    (ws.work / "REQUEST-judge.md").write_text("تحكيم", encoding="utf-8")  # الأحدث وقتًا، وليس ما ينتظره الخط
    steps = iter([Outcome(AWAIT_MODEL, "صقل", ws, request="REQUEST-refine.md"), Outcome(AWAIT_OWNER, "جاهز", ws)])
    model = FakeModel(cost=0.1)
    out = run_until_owner(lambda: next(steps), model, max_calls=5)
    assert model.calls == ["REQUEST-refine.md"] and out.code == AWAIT_OWNER


def test_a_reply_without_writing_goes_back_to_the_line_before_stopping(tmp_path):
    """جواب بلا كتابة قد يكفي الخط (طلب تعديل أُجيب فيعود إلى المالك بجوابه): لا يُعدّ توقفًا إلا إن بقي الخط ينتظر النموذج."""
    ws = _ws(tmp_path)
    (ws.work / "REQUEST-revise.md").write_text("سؤال", encoding="utf-8")
    steps = iter([Outcome(AWAIT_MODEL, "تعديل", ws, request="REQUEST-revise.md"), Outcome(AWAIT_OWNER, "جواب الخط", ws, gate="book")])

    class Answering(FakeModel):
        def run(self, request, version_root, *, cap_usd, tick=None):
            self.calls.append(request.name)
            return ModelResult(True, 0.2, 5.0, "خلاصة", reply="الجواب كاملًا")

    out = run_until_owner(lambda: next(steps), Answering(writes=False), max_calls=5)
    assert out.code == AWAIT_OWNER and out.gate == "book"
    assert json.loads((ws.root / "model_calls.jsonl").read_text(encoding="utf-8"))["reply"] == "الجواب كاملًا"
    ws2 = _ws(tmp_path / "idle")
    (ws2.work / "REQUEST-diverge.md").write_text("طلب", encoding="utf-8")
    out = run_until_owner(lambda: Outcome(AWAIT_MODEL, "بانتظار", ws2, request="REQUEST-diverge.md"), FakeModel(writes=False), max_calls=5)
    assert out.code == STOPPED and "لم يكتب النموذج شيئًا" in out.message


def test_platform_job_reports_a_stop_as_stopped_not_done(tmp_path):
    for code, label in ((6, "توقّف التشغيل الآلي"), (3, "توقّف بانتظار النموذج")):
        jobs = PipelineJobs(tmp_path, runner=lambda _b, code=code: (code, "بلغ التشغيل الآلي سقف 16 استدعاءات"), settle=0)
        jobs.start("p", tmp_path / "b.yaml")
        for _ in range(200):
            if jobs.snapshot()[0]["state"] != "running":
                break
            time.sleep(0.02)
        [j] = jobs.snapshot()
        assert j["state"] == "stopped" and j["code_ar"] == label and "سقف 16" in j["message"]


def test_stop_reason_survives_a_platform_restart_and_resume_is_bound_to_the_shown_version(project):  # noqa: F811
    """م1: السبب كان في ذاكرة المنصة وحدها. الآن في الإصدار: يُقرأ بعد إعادة التشغيل، ولا بطاقة والخط عند النموذج (ب10)."""
    tmp, _, brief, pipe = project
    ws = pipe.run(brief).workspace
    ledger(ws).record(Gate.DIRECTIONS, directions_digest(ws), "approved", "d1")
    assert pipe.run(brief).gate == "book"
    outcome.write(ws.root, code=STOPPED, message="بانتظار النموذج", request="REQUEST-revise.md", stopped="بلغ التشغيل الآلي سقف الإنفاق 15$")
    assert _card(tmp) is None  # الدليل على القرص بلا قرار، والخط ليس عنده: لا تُعرض بطاقته
    now = timeline(ws.root)["now"]
    assert now["who"] == "model" and now["state"] == "stopped" and now["resume"] and "سقف الإنفاق 15$" in now["text"]
    assert not timeline(ws.root, None, {"state": "running", "started": ""})["now"]["resume"]  # لا استئناف وتشغيل جارٍ
    out_dir = tmp / "out"
    assert "يُستأنف الخط على demo v2" in resume(out_dir, "demo", 2, ws.key.key)
    for version, key in ((1, ws.key.key), (2, "مفتاح-آخر")):
        with pytest.raises(InboxError, match="تغيّر ما عُرض"):
            resume(out_dir, "demo", version, key)
    with pytest.raises(InboxError, match="غير معروف"):
        resume(out_dir, "../demo", 2, ws.key.key)
