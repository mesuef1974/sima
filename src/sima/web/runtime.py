"""حالة تشغيل منصة سِمة لعملية الخادم: رمز التشغيل، ومجلد المخرجات، ومستودع الدفتر، والتشغيلات الخلفية.

الرمز يُولَّد لكل تشغيل ويُحقن في الصفحة فقط؛ لا يُخزَّن ولا يُطبع. الإعداد يأتي من متغيرات يضبطها `sima board`.
"""
from __future__ import annotations

import os
import secrets
from functools import cache
from pathlib import Path

from .. import config
from ..adapters.pipeline_jobs import PipelineJobs

TOKEN = secrets.token_urlsafe(24)


def out_dir() -> Path:
    return Path(os.environ.get("SIMA_OUT") or config.OUT_DIR)


def repo() -> Path | None:
    r = os.environ.get("SIMA_BOARD_REPO")
    return Path(r) if r else None


def port() -> int:
    return int(os.environ.get("SIMA_BOARD_PORT", "8766"))


def origins() -> set[str]:
    p = port()
    return {f"http://127.0.0.1:{p}", f"http://localhost:{p}"}


@cache
def jobs() -> PipelineJobs:
    return PipelineJobs(config.ROOT, out_dir=out_dir())
