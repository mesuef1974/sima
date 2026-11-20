"""أوامر الطرفية والإصدار المقصود (مراجعة الأتمتة 2026-11-14، المرحلة 3: خ9، ت5، ب14، م2).

أمر غير `run` لا يفتح إصدارًا؛ قرار الطرفية يمرّ بحراسة المنصة نفسها؛ وقرار على vN لا يستأنف الخط على إصدار آخر."""
from __future__ import annotations

import inspect
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from sima import cli, config
from sima.adapters import pipeline_jobs
from sima.adapters.pipeline_jobs import PipelineJobs
from sima.domain import NameStatus, Verdict
from sima.domain.brief import load_brief
from sima.services import designer
from sima.services.inbox import InboxError, brief_unchanged, owner_inbox, resume_args
from sima.services.ledger import Ledger
from sima.services.namecheck import read_name_check
from sima.services.pipeline import AWAIT_DESIGNER, AWAIT_OWNER, record_decision
from sima.services.workspace import find_workspace, open_workspace

from .test_designer import _sheet, track  # noqa: F401  (مسار المصمّم الخارجي حتى بطاقة السكتش بلا نموذج)
from .test_domain_ledger_workspace import BRIEF
from .test_inbox import CONCEPTS, _reached_owner
from .test_web_api import _post, _token, client  # noqa: F401


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def shell(tmp_path: Path, monkeypatch):
    """موجز على القرص ومجلد مخرجات مؤقت تقرؤه أوامر الطرفية."""
    out = tmp_path / "out"
    monkeypatch.setattr(config, "OUT_DIR", out)
    return out, _write(tmp_path / "briefs" / "demo.yaml", BRIEF)


def _edit(brief: Path) -> None:
    _write(brief, {**BRIEF, "purpose": "اختبار بعد تعديل الموجز"})


def _shown(out: Path, brief: Path):
    """إصدار وصل فيه الخط إلى قرار المالك على مفهومين (كما تعرضه بطاقة المنصة)."""
    ws = open_workspace(out, load_brief(brief))
    (ws.root / "preview.html").write_text("<html></html>", encoding="utf-8")
    (ws.work / "concepts.yaml").write_text(CONCEPTS, encoding="utf-8")
    (ws.concepts_dir / "w1.svg").write_text("<svg/>", encoding="utf-8")
    _reached_owner(ws.root)
    return ws


def _versions(out: Path) -> list[str]:
    return sorted(p.name for p in (out / "demo").iterdir()) if (out / "demo").is_dir() else []


COMMANDS = (["status"], ["decide", "--approve", "w1", "--reason", "الأوضح"], ["name-check"], ["name-check", "--status", "pending"],
            ["deliver", "--repo", "."], ["style", "--pick", "s1"], ["designer", "--pick", "1"])


# ---------- خ9 / ت5: أمر غير run لا يفتح إصدارًا ----------
def test_commands_other_than_run_never_open_a_version(shell, capsys):
    out, brief = shell
    for argv in COMMANDS:  # لا إصدار بعد: لا يُنشأ واحد فارغ
        assert cli.main([argv[0], str(brief), *argv[1:]]) != 0, argv
    assert not (out / "demo").exists()
    assert "شغّل `sima run`" in capsys.readouterr().out

    ws = _shown(out, brief)
    _edit(brief)  # الموجز عُدّل بعد v1: مفتاحه لا يطابق أي إصدار
    for argv in COMMANDS:
        assert cli.main([argv[0], str(brief), *argv[1:]]) != 0, argv
    assert _versions(out) == ["v1"]
    assert Ledger(ws.ledger_path).read() == [] and read_name_check(ws) is None
    assert "عُدّل بعده" in capsys.readouterr().out
    for name in ("cmd_status", "cmd_decide", "cmd_designer", "cmd_style", "cmd_name_check", "cmd_deliver", "cmd_render",
                 "cmd_identity_decide"):
        assert "open_workspace(" not in inspect.getsource(getattr(cli, name)), name


def test_find_workspace_looks_up_and_never_creates(tmp_path):
    brief = load_brief(_write(tmp_path / "b.yaml", BRIEF))
    assert find_workspace(tmp_path / "out", brief) is None and not (tmp_path / "out").exists()
    ws = open_workspace(tmp_path / "out", brief)
    assert find_workspace(tmp_path / "out", brief).root == ws.root


# ---------- خ9 / ب14: قرار الطرفية بحراسة المنصة ----------
def test_cli_decide_goes_through_the_platform_guards(shell, capsys):
    out, brief = shell
    ws = open_workspace(out, load_brief(brief))
    assert cli.main(["decide", str(brief), "--approve", "w1"]) == 1  # قبل الرسم والحَكَم: لا مفاهيم معروضة
    assert Ledger(ws.ledger_path).read() == [] and "لا مفاهيم" in capsys.readouterr().out

    _shown(out, brief)
    assert cli.main(["decide", str(brief), "--approve", "c9"]) == 1  # مفهوم غير موجود
    assert cli.main(["decide", str(brief), "--reject", "w2"]) == 1  # رفض بلا سبب
    assert cli.main(["decide", str(brief), "--medium", "wordmark"]) == 1  # رسم جديد بلا ما يقرؤه الرسّام
    assert Ledger(ws.ledger_path).read() == []
    assert cli.main(["decide", str(brief), "--revise", "w2", "--reason", "أوضح الأسطر"]) == 0
    assert cli.main(["decide", str(brief), "--approve", "w1"]) == 0
    assert Ledger(ws.ledger_path).approved().concept_id == "w1"


def test_recording_a_decision_on_an_unknown_concept_is_refused(shell):
    out, brief = shell
    ws = _shown(out, brief)
    with pytest.raises(ValueError, match="c9"):
        record_decision(ws, "c9", Verdict.APPROVED, "اعتماد")
    assert Ledger(ws.ledger_path).read() == []


def test_cli_name_check_follows_the_platform_rules(shell, capsys):
    out, brief = shell
    ws = _shown(out, brief)
    assert cli.main(["name-check", str(brief), "--status", "clear"]) == 1  # «متاح» بلا مصدر
    assert cli.main(["name-check", str(brief), "--status", "clear", "--source", "EVIL"]) == 1
    assert cli.main(["name-check", str(brief), "--status", "conflict", "--source", "WIPO"]) == 1  # «متعارض» بلا ملاحظة
    assert read_name_check(ws) is None and "مصدرًا" in capsys.readouterr().out
    assert cli.main(["name-check", str(brief), "--status", "clear", "--source", "WIPO", "--source", "MOCI"]) == 0
    assert read_name_check(ws).status is NameStatus.CLEAR


def test_cli_designer_decisions_need_the_card(track, monkeypatch, capsys):  # noqa: F811
    tmp, brief, pipe = track
    monkeypatch.setattr(config, "OUT_DIR", tmp / "out")
    path = str(tmp / "briefs" / "demo.yaml")
    ws = pipe.run(brief).workspace
    _sheet(ws)  # وُضعت الصفحة ولم يصل الخط إليها بعد: لا بطاقة سكتش
    assert cli.main(["designer", path, "--pick", "5"]) == 1
    assert cli.main(["designer", path, "--reject", "--reason", "كلها حرفية"]) == 1
    assert designer.choices(ws) == []
    assert pipe.run(brief).code == AWAIT_OWNER and owner_inbox(tmp / "out")[0]["kind"] == "sketches"
    capsys.readouterr()
    assert cli.main(["designer", path, "--rebuild", "--reason", "ليس هذا الشعار"]) == 1  # ردّ المتجه من بطاقة الدليل وحدها
    assert "الدليل" in capsys.readouterr().out and designer.choices(ws) == []
    assert cli.main(["designer", path, "--pick", "5"]) == 0
    sheet, _ = designer.read_sheet(ws)
    assert designer.current(ws, sheet)["sketch"] == 5
    assert pipe.run(brief).code == AWAIT_DESIGNER


# ---------- م2: قرار على vN لا يستأنف الخط على إصدار آخر ----------
def test_a_brief_edited_under_an_open_gate_blocks_the_decision(shell):
    out, brief = shell
    _shown(out, brief)
    brief_unchanged(out, config.ROOT, "demo", 1)  # لم يتغيّر: يمرّ
    _edit(brief)
    with pytest.raises(InboxError, match="عُدّل موجز"):
        brief_unchanged(out, config.ROOT, "demo", 1)
    brief.unlink()
    brief_unchanged(out, config.ROOT, "demo", 1)  # لا موجز يُقارن به: القرار نفسه وما بعده يحكمان
    brief_unchanged(out, config.ROOT, "../x", 1)


def test_platform_refuses_then_resumes_on_the_shown_version_only(client, tmp_path, monkeypatch):  # noqa: F811
    from sima.web import runtime

    brief = _write(tmp_path / "briefs" / "demo.yaml", BRIEF)
    ws = _shown(tmp_path, brief)
    started = []

    class Jobs:
        def start(self, project, path, **kw):
            started.append((project, Path(path).name, kw))
            return True

        def snapshot(self):
            return []

    monkeypatch.setattr(runtime, "jobs", Jobs)
    [item] = [i for i in owner_inbox(tmp_path) if i["project"] == "demo"]
    body = {"project": "demo", "version": 1, "key": item["key"], "verdict": "approved", "concept": "w1", "reason": "",
            "digest": item["digest"]}
    _edit(brief)
    r = _post(client, "/api/decide", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 409 and "عُدّل موجز" in r.json()["error"]
    assert Ledger(ws.ledger_path).read() == [] and started == []  # لا قرار يُسجَّل ولا خط يُستأنف على إصدار آخر
    r = _post(client, "/api/resume", {"project": "demo", "version": 1, "key": item["key"]}, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 409 and started == []

    _write(brief, BRIEF)
    r = _post(client, "/api/decide", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 200, r.json()
    assert started == [("demo", "demo.yaml", {"seed": ws.key.seed, "expect_key": ws.key.key})]
    assert resume_args(tmp_path, "demo", 1) == {"seed": ws.key.seed, "expect_key": ws.key.key}


def test_run_refuses_a_key_other_than_the_expected_one(shell, capsys):
    out, brief = shell
    assert cli.main(["run", str(brief), "--no-model", "--expect-key", "other-s1"]) == cli.KEY_MISMATCH
    assert not (out / "demo").exists() and "لم يُفتح إصدار" in capsys.readouterr().out
    assert cli.KEY_MISMATCH not in pipeline_jobs.CODE_AR  # يظهر في المنصة فشلًا بنصّه لا اكتمالًا


def test_jobs_resume_with_the_version_seed_and_expected_key(tmp_path, monkeypatch):
    seen = []

    def fake_tree(argv, _root, _timeout):
        seen.append(argv[3:])
        return SimpleNamespace(returncode=4, stdout="بانتظار قرارك", stderr="")

    monkeypatch.setattr(pipeline_jobs, "run_tree", fake_tree)
    jobs = PipelineJobs(tmp_path, settle=0)
    assert jobs.start("demo", Path("b.yaml"), seed=7, expect_key="k-s7")
    for _ in range(100):
        if jobs.snapshot()[0]["state"] != "running":
            break
        time.sleep(0.05)
    assert seen == [["b.yaml", "--seed", "7", "--expect-key", "k-s7"]]
    assert "main(['run', *sys.argv[1:]])" in inspect.getsource(PipelineJobs._subprocess)
