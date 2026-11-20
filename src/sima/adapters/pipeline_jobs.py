"""تشغيل خط سِمة في الخلفية بعد قرار من المنصة: `sima run <brief>` في عملية مستقلة بلا نافذة، واحدة لكل مشروع.

العملية المنفصلة تعزل Playwright عن خادم المنصة وتُغلق متصفحها بنفسها في نهاية الأمر. ضمانات:
- لا يضيع قرار: قرار يصل أثناء تشغيل جارٍ يُعلَّم «استئنافًا معلّقًا» فيُشغَّل الخط مرة أخرى فور انتهاء الجاري.
- لا تشغيلان متوازيان: `sima run` نفسه يأخذ قفل المشروع على القرص (adapters/run_lock.py)، فإن كان مقفلًا بتشغيل من
  الطرفية أو من منصة سابقة انتظر هذا التشغيل حتى يتحرر القفل ثم أعاد المحاولة.
- لا عمليات يتيمة: المهلة تقتل الشجرة كاملة (claude وChromium)، وتُحسب من سقوف النموذج لا رقمًا ثابتًا.
- الحالة الحية في الذاكرة، والتشغيل الجاري خارجها (بعد إعادة تشغيل المنصة) يُقرأ من قفل القرص.
- التوقف ليس اكتمالًا: خطّ خرج وهو ينتظر النموذج (سقف، تكرار، فشل استدعاء، أو استدعاء آلي معطّل) حالته «stopped» لا «done»؛
  سببه في نتيجة الإصدار على القرص (`services/outcome.py`) فلا يضيع بإعادة تشغيل المنصة، ويُستأنف بزر (`POST /api/resume`).
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .proc import run_tree
from .run_lock import BUSY, holder

CODE_AR = {0: "اكتمل", 3: "توقّف بانتظار النموذج", 4: "بانتظار قرارك", 5: "بانتظار المصمّم الخارجي", 6: "توقّف التشغيل الآلي"}
STOPPED_CODES = (3, 6)  # الخط ينتظر النموذج ولا أحد سيستدعيه: 3 بلا استدعاء آلي، و6 توقف الاستدعاء الآلي بسبب (services/outcome.py)
BUSY_WAIT_S = 5
# تشغيل انتهى يبقى في «اليوم» ليُرى ما انتهى إليه ثم يُسقط (م6 ح: كان يبقى حتى إعادة تشغيل المنصة). التوقف سببه في نتيجة
# الإصدار على القرص وبطاقته، والفشل لا يحفظه غير هذا السجل فيبقى يومًا
KEEP_S = {"done": 600.0, "stopped": 600.0, "failed": 86400.0}


def settle_s() -> float:
    """مهلة تجميع القرارات: قرارات المالك المتتالية (رفض ثلاثة مفاهيم مثلًا) تُعالَج في تشغيل واحد لا في تشغيلين."""
    from .claude_model import _env

    return float(_env("SIMA_DECISION_SETTLE_S", "12"))


def timeout_s() -> int:
    """أسوأ حالة: كل استدعاءات النموذج بمهلتها كاملة، وساعة للخط نفسه (التصيير والفحص والبناء)."""
    from .claude_model import call_timeout_s, max_calls

    return max_calls() * call_timeout_s() + 3600


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Job:
    project: str
    state: str = "running"  # running | done | stopped | failed
    code: int | None = None
    started: str = field(default_factory=_now)
    ended: str = ""
    message: str = ""
    rerun: bool = False  # قرار وصل أثناء التشغيل: يُعاد الخط بعده
    settle_until: float = 0.0  # قبل هذه اللحظة لم يبدأ الخط بعد: القرار الجديد يلحق بالتشغيل نفسه ويمدّ المهلة
    ended_at: float = 0.0  # ساعة رتيبة عند الانتهاء: منها يُحسب بقاؤه في العرض

    def as_dict(self) -> dict:
        return {"project": self.project, "state": self.state, "code": self.code, "code_ar": CODE_AR.get(self.code or 0, "فشل")
                if self.code is not None else "", "started": self.started, "ended": self.ended, "message": self.message,
                "rerun": self.rerun}


class PipelineJobs:
    def __init__(self, root: Path, runner=None, out_dir: Path | None = None, settle: float | None = None):
        self._root = root
        self._settle = settle_s() if settle is None else settle
        self._out = out_dir
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._run = runner or self._subprocess

    def _subprocess(self, brief: Path, seed: int | None = None, expect_key: str = "", new_version: bool = False) -> tuple[int, str]:
        code = "import sys; from sima.cli import main; raise SystemExit(main(['run', *sys.argv[1:]]))"
        args = [str(brief), *(["--seed", str(seed)] if seed is not None else []), *(["--expect-key", expect_key] if expect_key else []),
                *(["--new-version"] if new_version else [])]
        try:
            p = run_tree([sys.executable, "-c", code, *args], self._root, timeout_s())
        except subprocess.TimeoutExpired:
            return -1, f"تجاوز التشغيل المهلة ({timeout_s()} ث)، وأُوقفت شجرة العملية كاملة."
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def start(self, project: str, brief: Path, *, seed: int | None = None, expect_key: str = "", new_version: bool = False) -> bool:
        """يبدأ تشغيلًا، أو يعلّم استئنافًا معلّقًا إن كان للمشروع تشغيل جارٍ (فيعيد False). لا يضيع قرار في الحالتين.
        seed وexpect_key: بذرة الإصدار المقصود ومفتاحه؛ يستأنف الخط عليه أو يخرج بخطأ، ولا يفتح إصدارًا آخر (م2)."""
        extra = {**({"seed": seed} if seed is not None else {}), **({"expect_key": expect_key} if expect_key else {}),
                 **({"new_version": True} if new_version else {})}
        with self._lock:
            cur = self._jobs.get(project)
            if cur and cur.state == "running":
                if new_version:  # الإصدار الجديد لا يلحق بتشغيل جارٍ: كان سيفتح إصدارين
                    return False
                if time.monotonic() < cur.settle_until:  # لم يبدأ الخط بعد: يقرأ هذا القرار مع سابقه
                    cur.settle_until = time.monotonic() + self._settle
                    return True
                cur.rerun = True
                return False
            job = Job(project, settle_until=time.monotonic() + self._settle)
            self._jobs[project] = job
        threading.Thread(target=self._work, args=(job, brief, extra), daemon=True).start()
        return True

    def _once(self, brief: Path, extra: dict) -> tuple[int, str]:
        deadline = time.monotonic() + timeout_s()
        while True:
            try:
                code, out = self._run(brief, **extra)
            except Exception as e:  # noqa: BLE001 — أي فشل يُعرض للمالك ولا يُسقط الخادم
                return -1, f"{type(e).__name__}: {e}"
            if code != BUSY or time.monotonic() > deadline:
                return code, out
            time.sleep(BUSY_WAIT_S)  # تشغيل آخر (من الطرفية أو منصة سابقة) يملك القفل: ننتظره ولا نتجاهل القرار

    def _work(self, job: Job, brief: Path, extra: dict) -> None:
        while True:  # مهلة تجميع منزلقة: كل قرار يصل فيها يمدّها
            with self._lock:
                wait = job.settle_until - time.monotonic()
                if wait <= 0:
                    job.settle_until = 0.0
                    break
            time.sleep(min(wait, 0.5))
        while True:
            code, out = self._once(brief, extra)
            extra = {k: v for k, v in extra.items() if k != "new_version"}  # استئناف بعده على الإصدار الذي فتحه، لا إصدار آخر
            lines = [ln for ln in out.strip().splitlines() if ln.strip()]
            with self._lock:
                job.code, job.message = code, "\n".join(lines[-4:])[:800]
                if job.rerun:
                    job.rerun = False
                    job.message = (job.message + "\nوصل قرار أثناء التشغيل؛ يُستأنف الخط مرة أخرى.").strip()
                    continue
                job.ended, job.ended_at = _now(), time.monotonic()
                job.state = "stopped" if code in STOPPED_CODES else "done" if code in CODE_AR else "failed"
                return

    def snapshot(self) -> list[dict]:
        with self._lock:
            now = time.monotonic()
            for name in [n for n, j in self._jobs.items() if j.state in KEEP_S and now - j.ended_at > KEEP_S[j.state]]:
                del self._jobs[name]
            rows = [j.as_dict() for j in self._jobs.values()]
        if self._out and self._out.is_dir():
            known = {r["project"] for r in rows if r["state"] == "running"}
            for d in self._out.iterdir():
                h = holder(self._out, d.name) if d.is_dir() and d.name not in known else None
                if h:  # تشغيل حي لم تبدأه هذه المنصة: من الطرفية أو من منصة قبل إعادة تشغيلها
                    rows = [r for r in rows if r["project"] != d.name]
                    rows.append({"project": d.name, "state": "running", "code": None, "code_ar": "", "started": h.get("started", ""),
                                 "ended": "", "message": f"تشغيل خارج هذه المنصة (العملية {h.get('pid')}).", "rerun": False})
        return rows
