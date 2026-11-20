"""محوّل السجل: يصل النواة بقاعدة PostgreSQL عبر Django دون أن تعرف النواة Django، ويدير العنقود المحلي لسِمة.

العنقود في var/pgdata على 127.0.0.1 فقط، ومنفذه من SIMA_DB_PORT في .env. الأسرار في .env خارج git ولا تُطبع.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import config

PG_BIN_CANDIDATES = (Path("C:/Program Files/PostgreSQL/17/bin"), Path("C:/Program Files/PostgreSQL/16/bin"))


def _pg_ctl() -> str:
    found = shutil.which("pg_ctl")
    if found:
        return found
    for d in PG_BIN_CANDIDATES:
        exe = d / "pg_ctl.exe"
        if exe.is_file():
            return str(exe)
    raise RuntimeError("لم يُعثر على pg_ctl؛ ثبّت PostgreSQL 17 أو أضف مجلد bin إلى PATH.")


def _port() -> str:
    from ..web.settings import DATABASES  # يقرأ .env

    return str(DATABASES["default"]["PORT"])


def data_dir() -> Path:
    return config.ROOT / "var" / "pgdata"


def _detach_flags() -> list[int]:
    """أعلام فصل العنقود عن طرفية المستدعي. Ctrl+C في الطرفية أو إغلاق لسانها كان يُسقط القاعدة (pg.log: 0xC000013A).

    `CREATE_NO_WINDOW` يعطي pg_ctl طرفية خاصة بلا نافذة يرثها cmd وpostgres، فلا يشاركهم فيها المستدعي ولا تصلهم إشاراته.
    لا `DETACHED_PROCESS` (2026-11-17): كان يترك pg_ctl بلا طرفية، فيفتح ويندوز لابنه cmd طرفية جديدة خارج تحكّمنا،
    وإغلاقها أو إشارة فيها تُسقط القاعدة بعد ثانية من بدئها (pg.log 2026-11-17 02:35). والخروج من job يبقيها بعد إغلاق
    اللسان؛ قد يُرفض فيُجرَّب بدونه."""
    if os.name != "nt":
        return [0]
    base = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    return [base | subprocess.CREATE_BREAKAWAY_FROM_JOB, base]


def start_guard() -> bool:
    """يبدأ حارس الإيقاف النظيف (`db_guard`) منفصلًا بلا نافذة. ويندوز وحده؛ الحارس نفسه يضمن واحدًا لكل عنقود.
    فشله لا يُفشل بدء القاعدة: تعود إلى الاستعادة عند الإقلاع كما كانت."""
    if os.name != "nt" or config.ENV.get("SIMA_DB_GUARD", "1") == "0":
        return False
    for flags in _detach_flags():
        try:
            subprocess.Popen([sys.executable, "-m", "sima.adapters.db_guard"], cwd=str(config.ROOT), creationflags=flags,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False


def cluster(action: str) -> tuple[int, str]:
    """start | stop | status للعنقود المحلي. البدء منفصل تمامًا (بلا أنبوب ولا مدخل) كي لا يتعلق المستدعي."""
    pgdata = data_dir()
    if not (pgdata / "PG_VERSION").is_file():
        return 1, f"لا عنقود في {pgdata}؛ أنشئه بـ initdb أولًا (انظر docs/database.md)."
    ctl = _pg_ctl()
    log = config.ROOT / "var" / "pg.log"
    if action == "start":
        st = subprocess.run([ctl, "-D", str(pgdata), "status"], capture_output=True, text=True, check=False)
        if st.returncode == 0:
            start_guard()  # قاعدة بدأت قبل وجود الحارس تأخذه دون إعادة تشغيل
            return 0, "قاعدة سِمة تعمل سلفًا."
        out = config.ROOT / "var" / "pgctl.out"
        cmd = [ctl, "-D", str(pgdata), "-l", str(log), "-o", f"-p {_port()} -c listen_addresses=127.0.0.1", "-w", "start"]
        rc = 1
        for flags in _detach_flags():
            try:
                with out.open("w", encoding="utf-8") as fh:
                    rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags,
                                        check=False).returncode
                break
            except OSError:  # الخروج من job غير مسموح في هذه البيئة: جرّب بلا CREATE_BREAKAWAY_FROM_JOB
                continue
        if rc == 0:
            start_guard()
        return rc, "بدأت قاعدة سِمة على 127.0.0.1." if rc == 0 else f"تعذّر البدء؛ راجع {log}."
    if action == "stop":
        rc = subprocess.run([ctl, "-D", str(pgdata), "-m", "fast", "stop"], capture_output=True, text=True, check=False).returncode
        return 0, "أُوقفت قاعدة سِمة." if rc == 0 else "قاعدة سِمة متوقفة سلفًا."
    rc = subprocess.run([ctl, "-D", str(pgdata), "status"], capture_output=True, text=True, check=False).returncode
    return (0, f"قاعدة سِمة تعمل على 127.0.0.1:{_port()}.") if rc == 0 else (3, "قاعدة سِمة متوقفة. شغّلها بـ: uv run sima db start")


def migrate() -> None:
    from ..web import setup

    setup()
    from django.core.management import call_command

    call_command("migrate", verbosity=0)


def sync(out_dir: Path) -> dict[str, int]:
    from ..web import setup

    setup()
    from ..web.registry.service import sync_all

    return sync_all(out_dir)


def record_identity(root: Path) -> str:
    """منفذ النواة بعد اعتماد الدليل: يحفظ الهوية المعتمدة في القاعدة ويعيد سطرًا للمالك، ولا يُسقط الخط إن تعذّر الحفظ."""
    try:
        from ..web import setup

        setup()
        from ..web.registry.service import record_identity as rec

        ident = rec(root)
        return f"حُفظت الهوية المعتمدة في قاعدة سِمة ({ident.assets.count()} أصلًا، بصمة الدليل {ident.book_digest[:12]})."
    except Exception as e:  # noqa: BLE001 — أي فشل في القاعدة يُبلَّغ ولا يُبطل الاعتماد المسجّل على القرص
        return f"تنبيه: لم تُحفظ الهوية في القاعدة ({type(e).__name__}: {e}). شغّل القاعدة ثم: uv run sima db sync"
