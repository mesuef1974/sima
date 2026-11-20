"""كاشف الدمج من git: هل صار تسليم الفرع المحلي في فرع المشروع الرئيس؟ قراءة فقط ولا شبكة.

مسار الفرع المحلي (`BranchTarget`) بلا دفتر بطاقات، فلا يصل إلى سِمة حدث `merged`. الدمج بـ squash أو rebase يغيّر الرأس،
فلا يكفي أن يكون الرأس سلفًا: يُقبل أيضًا إيداع على الفرع الرئيس بعد وقت الرأس يمسّ ملفات التسليم ويحمل عنوان إيداع
التسليم سطرًا في رسالته (رسالة الـsquash تسرد عناوين إيداعات الطلب)."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REFS = ("origin/main", "main")
_SHA = re.compile(r"[0-9a-f]{7,40}")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          timeout=20, check=False, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if done.returncode != 0:
        raise OSError(done.stderr.strip() or f"git {args[0]} فشل")
    return done.stdout


def _first_ref(repo: Path) -> str | None:
    for ref in REFS:
        try:
            _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
            return ref
        except OSError:
            continue
    return None


def landed(manifest: dict) -> bool:
    """صحيح إن وُجد رأس التسليم أو عنوان إيداعه على الفرع الرئيس. أي تعذّر (مستودع غائب، رأس مجهول) يعني «لم يُعرف» لا خطأ."""
    repo, head = str(manifest.get("repo") or ""), str(manifest.get("head") or "")
    if not repo or not _SHA.fullmatch(head) or not (Path(repo) / ".git").exists():
        return False
    repo_path = Path(repo)
    try:
        ref = _first_ref(repo_path)
        if ref is None:
            return False
        _git(repo_path, "cat-file", "-e", f"{head}^{{commit}}")
        try:
            _git(repo_path, "merge-base", "--is-ancestor", head, ref)
            return True
        except OSError:
            pass  # ليس سلفًا: قد يكون دُمج بـsquash أو rebase
        subject, stamp = _git(repo_path, "log", "-1", "--format=%s%n%cI", head).splitlines()[:2]
        if not subject.strip():
            return False
        paths = [str(p) for p in manifest.get("changed") or manifest.get("paths") or [] if isinstance(p, str)]
        args = ["log", ref, f"--since={stamp}", "--fixed-strings", f"--grep={subject}", "--format=%H", "-1"]
        found = _git(repo_path, *args, *(["--", *paths] if paths else [])).strip()
        return bool(found)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
