"""كاشف الدمج من git لتسليم الفرع المحلي: السلف، والـsquash بعنوان الإيداع، وغير المدموج، وغياب المعلومة."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sima.adapters.git_landing import landed
from sima.services.timeline import progress, reached, steps_for

SUBJECT = "هوية «س» من سِمة: مرحلة الألوان (v9)"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return done.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "school"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "a.css").write_text("a{color:red}\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "أساس")
    git(repo, "checkout", "-b", "claude/card")
    (repo / "a.css").write_text("a{color:blue}\n", encoding="utf-8")
    git(repo, "commit", "-am", SUBJECT)
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "main")
    return repo, head


def manifest(repo: Path, head: str) -> dict:
    return {"repo": str(repo), "head": head, "branch": "claude/card", "changed": ["a.css"]}


def test_unmerged_branch_is_not_landed(tmp_path):
    repo, head = make_repo(tmp_path)
    assert landed(manifest(repo, head)) is False


def test_ancestor_is_landed(tmp_path):
    repo, head = make_repo(tmp_path)
    git(repo, "merge", "--ff-only", "claude/card")
    assert landed(manifest(repo, head)) is True


def test_squash_with_subject_in_message_is_landed(tmp_path):
    repo, head = make_repo(tmp_path)
    git(repo, "merge", "--squash", "claude/card")
    (repo / "a.css").write_text("a{color:green}\n", encoding="utf-8")  # الطلب غيّر الملف نفسه بعد الإيداع: لا يطابق الـblob
    git(repo, "commit", "-am", f"هوية v9 (#1)\n\n* {SUBJECT}\n\n* إيداع آخر")
    assert landed(manifest(repo, head)) is True


def test_unrelated_commit_with_other_subject_is_not_landed(tmp_path):
    repo, head = make_repo(tmp_path)
    (repo / "a.css").write_text("a{color:green}\n", encoding="utf-8")
    git(repo, "commit", "-am", "تغيير آخر")
    assert landed(manifest(repo, head)) is False


def test_subject_on_other_paths_only_is_not_landed(tmp_path):
    repo, head = make_repo(tmp_path)
    (repo / "b.css").write_text("b{}\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", f"شيء ما\n\n* {SUBJECT}")
    assert landed(manifest(repo, head)) is False


def test_unknown_head_or_missing_repo_is_not_landed(tmp_path):
    repo, _ = make_repo(tmp_path)
    assert landed(manifest(repo, "deadbeefdeadbeef")) is False
    assert landed({"repo": str(tmp_path / "none"), "head": "deadbeef"}) is False
    assert landed({}) is False


def test_reached_marks_landed_only_through_the_injected_check(tmp_path):
    v = tmp_path / "out" / "p" / "v1"
    (v / "stages").mkdir(parents=True)
    (v / "brief.json").write_text(json.dumps({"identity": {}}), encoding="utf-8")
    (v / "stages" / "deliver.json").write_text(json.dumps({"repo": "r", "head": "abcdef12", "card_id": "c"}), encoding="utf-8")
    assert "landed" not in reached(v)
    assert "landed" not in reached(v, None, lambda m: False)
    assert "landed" in reached(v, None, lambda m: m["head"] == "abcdef12")
    assert "landed" not in reached(v, None, lambda m: (_ for _ in ()).throw(OSError("x")))
    steps = progress(v, reached(v, None, lambda m: True))["steps"]
    assert steps_for(v)[-1] == "landed" and steps[-1]["status"] == "done"
