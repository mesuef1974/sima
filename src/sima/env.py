"""قارئ البيئة الوحيد: `.env` في جذر المشروع ثم متغيرات البيئة، والثانية تغلب.

كل مفتاح `SIMA_*` يُقرأ من حصيلته (`config.ENV`): مفاتيح الإيقاف كانت تُقرأ من متغيرات البيئة وحدها ومفاتيح النموذج من `.env`
أيضًا، فكان `SIMA_THUMBS=0` في `.env` بلا أثر (مراجعة 2026-11-14، خ10). وبلا Django: أمر لا يحتاج القاعدة لا يحتاج أسرارها.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def read_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def load(path: Path, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    return {**read_file(path), **(os.environ if environ is None else environ)}
