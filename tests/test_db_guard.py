"""حارس الإيقاف النظيف للقاعدة: منطقه بلا ويندوز ولا قاعدة حيّة."""
from __future__ import annotations

from sima import config
from sima.adapters import db_guard, registry


def _pid_file(pgdata, pid="4242"):
    pgdata.mkdir(exist_ok=True)
    (pgdata / "postmaster.pid").write_text(f"{pid}\nD:/x\n1\n", encoding="ascii")


def test_postmaster_pid_reads_first_line_and_treats_damage_as_stopped(tmp_path):
    assert db_guard.postmaster_pid(tmp_path) is None
    _pid_file(tmp_path)
    assert db_guard.postmaster_pid(tmp_path) == 4242
    (tmp_path / "postmaster.pid").write_text("", encoding="ascii")
    assert db_guard.postmaster_pid(tmp_path) is None


def test_fast_stop_signals_then_waits_for_the_pid_file_to_go(tmp_path):
    assert db_guard.fast_stop(tmp_path, send=lambda pid: 1 / 0) == "absent"  # لا إشارة لقاعدة متوقفة
    _pid_file(tmp_path)
    sent = []

    def send(pid):
        sent.append(pid)
        return True

    ticks = iter(range(100))
    naps = []

    def sleep(s):
        naps.append(s)
        if len(naps) == 3:
            (tmp_path / "postmaster.pid").unlink()

    assert db_guard.fast_stop(tmp_path, send=send, sleep=sleep, clock=lambda: next(ticks) * 0.1) == "stopped"
    assert sent == [4242] and len(naps) == 3
    _pid_file(tmp_path)
    assert db_guard.fast_stop(tmp_path, send=lambda pid: False) == "refused"
    ticks = iter(range(100))
    assert db_guard.fast_stop(tmp_path, send=send, wait_s=0.5, sleep=lambda s: None, clock=lambda: next(ticks) * 0.1) == "timeout"


def test_guard_stops_once_and_restarts_only_a_database_it_stopped(tmp_path):
    _pid_file(tmp_path)
    lines, stops, restarts = [], [], []

    def stop(pgdata):
        stops.append(pgdata)
        (pgdata / "postmaster.pid").unlink(missing_ok=True)
        return "stopped"

    g = db_guard.Guard(tmp_path, lines.append, stop=stop, restart=lambda: restarts.append(1) or "بدأت")
    assert not g.idle_done()
    g.on_query_end()
    g.on_query_end()
    g.on_end(True)  # الجلسة تنتهي فعلًا: لا إيقاف ثانٍ ولا إعادة تشغيل
    assert len(stops) == 1 and restarts == [] and not g.idle_done()  # أوقفها الحارس: يبقى ليعيدها إن أُلغي الإيقاف
    g.on_end(False)
    assert restarts == [1] and "أُلغي الإيقاف" in lines[-1]
    g.on_end(False)
    assert restarts == [1]
    assert g.idle_done()  # لا ملف عملية ولم يوقفها الحارس: توقفت بغيره

    other = db_guard.Guard(tmp_path, lines.append, stop=lambda p: "refused", restart=lambda: restarts.append(2) or "")
    other.on_end(True)  # لم يصل الاستعلام: محاولة أخيرة عند الانتهاء
    other.on_end(False)
    assert restarts == [1] and "refused" in lines[-1]


def test_mutex_name_is_per_cluster(tmp_path):
    a, b = db_guard.mutex_name(tmp_path / "a"), db_guard.mutex_name(tmp_path / "b")
    assert a != b and a.startswith("Local\\sima-db-guard-") and a == db_guard.mutex_name(tmp_path / "A")


def test_guard_is_off_by_switch_and_never_spawns_then(monkeypatch):
    monkeypatch.setattr(config, "ENV", {**config.ENV, "SIMA_DB_GUARD": "0"})
    monkeypatch.setattr(registry.subprocess, "Popen", lambda *a, **k: 1 / 0)
    assert registry.start_guard() is False
