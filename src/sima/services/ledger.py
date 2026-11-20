"""سجل قرارات المالك (JSONL) وقفل الوسيط. الإضافة فقط، لا تعديل."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..domain import Decision, Medium, MediumLock, Verdict


class Ledger:
    def __init__(self, path: Path):
        self._path = path

    def read(self) -> list[Decision]:
        if not self._path.is_file():
            return []
        out = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(Decision(
                concept_id=d.get("concept_id"), verdict=Verdict(d["verdict"]), medium=Medium(d["medium"]),
                reason=d.get("reason", ""), at=d["at"], round=int(d.get("round", 0)),
            ))
        return out

    def append(self, decision: Decision) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "concept_id": decision.concept_id, "verdict": decision.verdict.value, "medium": decision.medium.value,
            "reason": decision.reason, "at": decision.at, "round": decision.round,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def record(self, concept_id: str | None, verdict: Verdict, medium: Medium, reason: str = "", round_: int = 0) -> Decision:
        d = Decision(concept_id=concept_id, verdict=verdict, medium=medium, reason=reason,
                     at=datetime.now(UTC).isoformat(timespec="seconds"), round=round_)
        self.append(d)
        return d

    def lock(self) -> MediumLock:
        return MediumLock.from_decisions(self.read())

    def approved(self) -> Decision | None:
        for d in reversed(self.read()):
            if d.verdict is Verdict.APPROVED:
                return d
        return None
