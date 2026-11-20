"""مساحة العمل: out/<project>/v<n>/ لكل تشغيل؛ لا يُستبدل إصدار قديم. علامات المراحل تجعل التشغيل idempotent."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..domain import Brief, RunKey

_V_RE = re.compile(r"^v(\d+)$")


@dataclass(frozen=True)
class Workspace:
    root: Path  # out/<project>/v<n>
    key: RunKey
    version: int

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def concepts_dir(self) -> Path:
        return self.work / "concepts"

    @property
    def render_dir(self) -> Path:
        return self.work / "render"

    @property
    def critique_dir(self) -> Path:
        return self.work / "critique"

    @property
    def package_dir(self) -> Path:
        return self.root / "package"

    @property
    def ledger_path(self) -> Path:
        return self.root / "decisions.jsonl"

    @property
    def preview_path(self) -> Path:
        return self.root / "preview.html"

    @property
    def name_check_path(self) -> Path:
        return self.root / "name_check.yaml"

    def marker(self, stage: str) -> Path:
        return self.root / "stages" / f"{stage}.json"

    def done(self, stage: str) -> bool:
        return self.marker(stage).is_file()

    def mark_done(self, stage: str, payload: dict | None = None) -> None:
        """idempotent: لا يُعاد كتابة علامة بالمحتوى نفسه. ووقت اكتمال المرحلة يُحفظ داخلها (at)، فلا يعتمد سجلّ المشروع
        على وقت الملف الذي يتغيّر بالنسخ أو الوراثة."""
        m = self.marker(stage)
        m.parent.mkdir(parents=True, exist_ok=True)
        data = dict(payload or {"ok": True})
        data.pop("at", None)
        if m.is_file():
            try:
                old = json.loads(m.read_text(encoding="utf-8"))
            except ValueError:
                old = None
            if isinstance(old, dict) and {k: v for k, v in old.items() if k != "at"} == data:
                return
        data["at"] = datetime.now(UTC).isoformat(timespec="seconds")
        m.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_request(self, name: str, text: str) -> Path:
        """طلب للنموذج في work/، لا يُعاد كتابته إن لم يتغيّر محتواه: يبقى «ينتظر منذ» صادقًا عبر الاستئنافات."""
        p = self.work / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if not (p.is_file() and p.read_text(encoding="utf-8") == text):
            p.write_text(text, encoding="utf-8")
        return p

    def read_marker(self, stage: str) -> dict:
        if not self.done(stage):
            return {}
        data = json.loads(self.marker(stage).read_text(encoding="utf-8"))
        data.pop("at", None)  # الوقت للسجل وحده؛ المستهلكون يقرؤون الحمولة كما كُتبت
        return data

    def ensure(self) -> None:
        """ومعها مجلدا الحَكَم والقارئ الأعمى: وجودهما من البداية يُدخلهما في قفل الرسّام منذ أول استدعاء."""
        for p in (self.work, self.concepts_dir, self.render_dir, self.critique_dir, self.root / "stages",
                  self.work / "judge", self.work / "blind"):
            p.mkdir(parents=True, exist_ok=True)


def _versions(project_dir: Path) -> list[tuple[int, Path]]:
    if not project_dir.is_dir():
        return []
    out = []
    for p in project_dir.iterdir():
        m = _V_RE.match(p.name)
        if m and p.is_dir():
            out.append((int(m.group(1)), p))
    return sorted(out)


def run_key(brief: Brief) -> RunKey:
    return RunKey(project=brief.project, brief_hash=brief.hash(), seed=brief.seed)


def find_workspace(out_dir: Path, brief: Brief) -> Workspace | None:
    """الإصدار المطابق لمفتاح الموجز إن وُجد، ولا يُنشأ شيء. لكل أمر عدا `sima run`: أمر قراءة أو قرار على موجز عُدّل
    كان يفتح إصدارًا فارغًا ويسجّل فيه (مراجعة 2026-11-14، خ9 وت5)."""
    key = run_key(brief)
    for n, p in reversed(_versions(out_dir / brief.project)):
        run = p / "run.json"
        if run.is_file() and json.loads(run.read_text(encoding="utf-8")).get("key") == key.key:
            return Workspace(root=p, key=key, version=n)
    return None


def last_version(out_dir: Path, project: str) -> int:
    """رقم آخر إصدار للمشروع، أو 0 إن لم يُفتح له إصدار."""
    versions = _versions(out_dir / project)
    return versions[-1][0] if versions else 0


def open_workspace(out_dir: Path, brief: Brief, *, new_version: bool = False) -> Workspace:
    """يعيد الإصدار المطابق لمفتاح التشغيل إن وُجد ولم يُطلب جديد، وإلا ينشئ v<n+1>. الإنشاء لـ`sima run` وحده
    (وتقييم الرسّام في مجلده)؛ غيره يبحث بـ`find_workspace`."""
    key = run_key(brief)
    project_dir = out_dir / brief.project
    versions = _versions(project_dir)
    if not new_version:
        found = find_workspace(out_dir, brief)
        if found is not None:
            return found
    n = (versions[-1][0] + 1) if versions else 1
    root = project_dir / f"v{n}"
    ws = Workspace(root=root, key=key, version=n)
    ws.ensure()
    (root / "run.json").write_text(json.dumps({
        "project": brief.project, "key": key.key, "brief_hash": key.brief_hash, "seed": brief.seed,
        "brief_source": brief.source_path, "version": n, "closed": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return ws


def workspace_of(root: Path) -> Workspace:
    """إصدار قائم من run.json فيه، دون موجز (للسجل والمنصة)."""
    data = json.loads((root / "run.json").read_text(encoding="utf-8"))
    key = RunKey(project=str(data["project"]), brief_hash=str(data["brief_hash"]), seed=int(data["seed"]))
    return Workspace(root=root, key=key, version=int(data["version"]))


def close_workspace(ws: Workspace) -> None:
    run = ws.root / "run.json"
    data = json.loads(run.read_text(encoding="utf-8"))
    data["closed"] = True
    run.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
