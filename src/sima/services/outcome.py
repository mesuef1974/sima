"""علامة النتيجة: ما أعاده الخط آخر مرة على الإصدار، في ملف واحد يقرؤه الوارد وصندوق المصمّم والسجل.

كانت كل خدمة تستنتج «من يُنتظر» بمنطقها من ملفات الإصدار، وحيث اختلف استنتاجها عمّا أعاده `Pipeline.run` وقف الإصدار
بلا بطاقة (مراجعة 2026-11-14، البنود ب1 وب2 وب10 وب13 وم1). الآن يكتب الخط نتيجته هنا: من يُنتظر، وعند أي بوابة، وببصمة أي
محتوى، وأي طلب، ولماذا توقف التشغيل الآلي إن توقف. والعلامة «سارية» ما لم يكتب المالك أو المصمّم الخارجي شيئًا بعدها
(قرار، تحقق اسم، استلام): عندها ينتظر الإصدار استئناف الخط، ولا تُقرأ العلامة حالًا.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

FILE = "outcome.json"
STOPPED = 6  # رمز خروج `sima run` حين يتوقف التشغيل الآلي والخط ما زال ينتظر النموذج (سقف، تكرار، فشل استدعاء، لا كتابة)
WHO = {0: "done", 1: "error", 3: "model", 4: "owner", 5: "designer", STOPPED: "model"}
# ما يكتبه المالك والمصمّم الخارجي في الإصدار. قراراتهما تغيّر ما ينتظره الخط، فتُبطل العلامة حتى يُستأنف
OWNER_FILES = ("decisions.jsonl", "identity_decisions.jsonl", "designer_decisions.jsonl", "style_decisions.jsonl", "name_check.yaml")
DESIGNER_DIR = "designer"


def inputs(root: Path) -> str:
    """بصمة مدخلات المالك والمصمّم: أسماء ملفاتها وأحجامها وأوقات كتابتها (لا محتواها: تُحسب عند كل قراءة للمنصة)."""
    rows = []
    files = [root / n for n in OWNER_FILES]
    d = root / DESIGNER_DIR
    if d.is_dir():
        files += sorted(p for p in d.rglob("*") if p.is_file())
    for p in files:
        try:
            st = p.stat()
        except OSError:
            continue
        rows.append(f"{p.relative_to(root).as_posix()}:{st.st_size}:{st.st_mtime_ns}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def write(root: Path, *, code: int, message: str, gate: str = "", digest: str = "", request: str = "", stopped: str = "") -> dict:
    """تُكتب في نهاية كل تشغيل للخط، وعند توقف التشغيل الآلي. الكتابة ذرّية: المنصة تقرأ والخط يكتب."""
    rec = {"code": code, "who": WHO.get(code, "error"), "gate": gate, "digest": digest, "request": request, "message": message,
           "stopped": stopped, "inputs": inputs(root), "at": datetime.now(UTC).isoformat(timespec="seconds")}
    tmp = root / (FILE + ".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, root / FILE)
    return rec


def read(root: Path) -> dict | None:
    """العلامة كما كُتبت، أو None إن لم يكتبها الخط بعد (إصدار أقدم منها) أو تعذّرت قراءتها."""
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "code" not in data:
        return None
    return {"code": int(data["code"]), "who": str(data.get("who") or WHO.get(int(data["code"]), "error")), "gate": str(data.get("gate") or ""),
            "digest": str(data.get("digest") or ""), "request": str(data.get("request") or ""), "message": str(data.get("message") or ""),
            "stopped": str(data.get("stopped") or ""), "inputs": str(data.get("inputs") or ""), "at": str(data.get("at") or "")}


def current(root: Path) -> dict | None:
    """العلامة إن كانت سارية: لم يُكتب بعدها قرار ولا تحقق اسم ولا استلام من المصمّم. غير السارية تعني أن الخط لم يُستأنف
    بعد ما كُتب، فلا يُعرف منها من يُنتظر."""
    rec = read(root)
    return rec if rec is not None and rec["inputs"] == inputs(root) else None


def superseded(root: Path) -> bool:
    """كتب الخط نتيجته ثم كُتب بعدها قرار أو استلام ولم يُستأنف: الإصدار ينتظر تشغيل الخط لا أحدًا."""
    rec = read(root)
    return rec is not None and rec["inputs"] != inputs(root)
