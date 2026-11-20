"""حارس مصادر الإرث: كل موجز يرث علامة إصدار سابق (`inherit_mark`) يحتاج ذلك الإصدار على القرص.

`Pipeline._inherit_mark` ينسخ من المصدر `decisions.jsonl` ومجلد `work/` عند بناء إصدار جديد، فحذف المصدر
عند تنظيف `out/` يكسر الإصدار التالي للمشروع دون أن يظهر في شيء آخر (حذف 2026-11-20 كاد يُسقط ثلاثة مصادر).
"""

from __future__ import annotations

import pytest

from sima.config import OUT_DIR, ROOT
from sima.domain.brief import load_brief

BRIEFS = sorted((ROOT / "briefs").glob("*.yaml"))
INHERITING = [(p, b) for p in BRIEFS if (b := load_brief(p)).identity.inherit_mark]


def test_some_brief_inherits_a_mark():
    # بلا موجز وارث يمرّ الحارس فارغًا: هذا يثبت أنه يرى موجزات المشاريع فعلًا
    assert INHERITING


@pytest.mark.parametrize(("path", "brief"), INHERITING, ids=[p.stem for p, _ in INHERITING])
def test_inherit_mark_source_exists(path, brief):
    src = OUT_DIR / brief.project / brief.identity.inherit_mark
    assert (src / "decisions.jsonl").is_file(), f"{path.name}: مصدر inherit_mark بلا قرارات في {src}؛ لا يُحذف"
    assert (src / "work").is_dir(), f"{path.name}: مصدر inherit_mark بلا work/ في {src}؛ لا يُحذف"
