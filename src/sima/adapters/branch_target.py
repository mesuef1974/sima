"""منفذ تسليم إلى مستودع بلا دفتر بطاقات (منصة المدرسة بعد خروج جلستي 0501 و0601): فرع محلي في worktree جانبي.

لا بطاقة ولا push ولا طلب دمج: التسليم فرع `claude/<معرّف>` من origin/main في `.claude/worktrees/<معرّف>` (عُرف المنصة)،
والمالك يقرر الدفع وفتح الطلب. شجرة المستودع الرئيسة وفرعها لا يُمسّان (قاعدة المنصة: لا تبديل فرع شجرة لست فيها)."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .ledger_runner import LedgerRunnerTarget


class BranchTarget(LedgerRunnerTarget):
    def __init__(self, repo: Path, card_id: str, co_authors: Sequence[str] = ()):
        self.repo = Path(repo).resolve()
        self.co_authors = tuple(co_authors)
        self._base_ref = None
        self.card_id = card_id
        if not (self.repo / ".git").exists():
            raise FileNotFoundError(f"ليس مستودع git: {self.repo}")

    def new_card(self, title: str, body: str, success: str) -> str:
        return self.card_id  # لا دفتر: المعرّف هو اسم الفرع والـworktree

    def make_worktree(self, card_id: str) -> tuple[Path, str]:
        branch = f"claude/{card_id}"
        path = self.repo / ".claude" / "worktrees" / card_id
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self._run(["git", "worktree", "add", "-b", branch, str(path), self._base()])
        return path, branch

    def ready(self, card_id: str) -> None:
        return None  # لا دفتر يُعلَّم
