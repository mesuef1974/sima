"""محوّل «المشغّل»: مستودع فيه automation/ledger.py (دفتر بطاقات JSONL) وrunner.py يلتقط بطاقة ready.

يُنشئ البطاقة، وworktree على فرع card/<id> من origin/main (كما يفعل runner.make_worktree)، ويودع محليًا ويضع
البطاقة ready. لا push ولا gh: المشغّل في المستودع الهدف هو من يفعلهما. لا نافذة ظاهرة على ويندوز.
"""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

BASE_NOTE = "أساس الفرع origin/main كما جُلب لحظة التسليم (git fetch من مستودع المشروع: الاتصال الشبكي الوحيد في التسليم)."
TEXT_MAX = 1_000_000


class GitRefFiles:
    """شجرة مرجع git للقراءة بلا سحب: أرشيف واحد (`git archive`) يُقرأ في الذاكرة عند أول طلب. منفذ `RepoFiles` لنص البطاقة."""

    def __init__(self, repo: Path, ref: str):
        self.repo, self.ref = Path(repo), ref
        self._members: dict[str, bytes | None] | None = None

    def _load(self) -> dict[str, bytes | None]:
        if self._members is None:
            import io
            import tarfile

            proc = subprocess.run(["git", "archive", "--format=tar", self.ref], cwd=self.repo, capture_output=True, check=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._members = {}
            with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
                for m in tar:
                    if m.isfile():
                        self._members[m.name] = tar.extractfile(m).read() if m.size <= TEXT_MAX else None
        return self._members

    def read_text(self, rel: str) -> str | None:
        data = self._load().get(rel)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def walk(self, sub: str = "") -> list[str]:
        prefix = sub.rstrip("/") + "/" if sub else ""
        return sorted(p for p in self._load() if p.startswith(prefix))


class LedgerRunnerTarget:
    def __init__(self, repo: Path, python: str | None = None, co_authors: Sequence[str] = ()):
        """co_authors: سطور نسبة نقطة التسليم، وهي النماذج التي عملت في الإصدار فعلًا (`auto_deliver.co_authors`)، لا اسم
        ثابت (م10)؛ إصدار بلا استدعاء نموذج نقطته بلا سطر."""
        self.repo = Path(repo).resolve()
        self.co_authors = tuple(co_authors)
        self._base_ref: str | None = None
        self.ledger = self.repo / "automation" / "ledger.py"
        self.python = python or sys.executable
        if not self.ledger.is_file():
            raise FileNotFoundError(f"لا دفتر بطاقات في {self.ledger}")
        if not (self.repo / ".git").exists():
            raise FileNotFoundError(f"ليس مستودع git: {self.repo}")

    def _run(self, cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=cwd or self.repo, text=True, encoding="utf-8", errors="replace", capture_output=True,
                              check=check, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def new_card(self, title: str, body: str, success: str) -> str:
        proc = self._run([self.python, "-I", str(self.ledger), "new", title, "--body", body, "--success", success])
        card = proc.stdout.strip().splitlines()[-1].strip()
        if not card:
            raise RuntimeError("الدفتر لم يُعد معرّف بطاقة: " + proc.stderr)
        return card

    def _base(self) -> str:
        """أساس فرع البطاقة: `origin/main` كما يُجلب مرة واحدة لكل تسليم (الاتصال الشبكي الوحيد فيه، ومعلن في `BASE_NOTE`)، أو
        `HEAD` لمستودع بلا origin. نص البطاقة والفرع من الأساس نفسه."""
        if self._base_ref is None:
            self._run(["git", "fetch", "origin", "main"], check=False)
            found = self._run(["git", "rev-parse", "--verify", "--quiet", "origin/main^{commit}"], check=False)
            self._base_ref = found.stdout.strip() if found.returncode == 0 and found.stdout.strip() else "HEAD"
        return self._base_ref

    def base_files(self) -> GitRefFiles:
        return GitRefFiles(self.repo, self._base())

    def make_worktree(self, card_id: str) -> tuple[Path, str]:
        branch = f"card/{card_id}"
        path = self.repo / ".worktrees" / card_id
        path.parent.mkdir(exist_ok=True)
        base = self._base()
        if not path.exists():
            self._run(["git", "worktree", "add", "-b", branch, str(path), base])
        return path, branch

    def commit(self, worktree: Path, paths: tuple[str, ...], message: str) -> str:
        present = [p for p in paths if (worktree / p).exists()]
        gone = [p for p in paths if not (worktree / p).exists()]
        for i in range(0, len(present), 200):  # دفعات: سطر أمر ويندوز محدود الطول
            self._run(["git", "add", "--", *present[i:i + 200]], cwd=worktree)
        for i in range(0, len(gone), 200):  # ما حذفته الخطة: يُسقط من الفهرس (غير المتتبَّع يُتجاوز)
            self._run(["git", "rm", "-q", "--cached", "--ignore-unmatch", "--", *gone[i:i + 200]], cwd=worktree)
        staged = self._run(["git", "diff", "--cached", "--quiet"], cwd=worktree, check=False).returncode != 0
        if staged:
            trailer = "\n\n" + "\n".join(self.co_authors) if self.co_authors else ""
            self._run(["git", "commit", "-q", "-m", message + trailer], cwd=worktree)
        return self._run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()

    def ready(self, card_id: str) -> None:
        self._run([self.python, "-I", str(self.ledger), "ready", card_id])

    def supersede(self, card_id: str, note: str) -> str:
        """حالة البطاقة في الدفتر (آخر حدث)، وإن لم يلتقطها المشغّل بعد (created أو ready) يُضاف لها حدث `cancelled` بأمر الدفتر
        نفسه؛ بطاقة التُقطت أو دُمجت لا تُمسّ. فرعها وشجرتها يبقيان لمشروعها."""
        events = card_events(self.repo, card_id)
        was = str(events[-1].get("event", "")) if events else ""
        if was in ("created", "ready"):
            self._run([self.python, "-I", str(self.ledger), "event", card_id, "cancelled", "--note", note])
        return was


def all_cards(repo: str | Path) -> dict[str, list[dict]]:
    """كل بطاقات دفتر المشروع بأحداثها، قراءة فقط."""
    folder = Path(repo) / "automation" / "ledger"
    return {p.stem: card_events(repo, p.stem) for p in sorted(folder.glob("*.jsonl"))} if folder.is_dir() else {}


def card_events(repo: str | Path, card_id: str) -> list[dict]:
    """أحداث بطاقة من دفتر المشروع، قراءة فقط ولا شبكة. فارغة إن غاب الدفتر أو كان المعرّف غير صالح."""
    import json
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]+", card_id or ""):
        return []
    path = Path(repo) / "automation" / "ledger" / f"{card_id}.jsonl"
    if not path.is_file():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("card") == card_id:
            events.append(row)
    return events
