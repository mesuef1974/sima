"""بحث تمهيدي حتمي: ماذا تفعل الفئة في المكتبة المرجعية، وما يجب تجنّبه. مخرجه ملف عربي واحد."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..domain import Brief

_RELATED = {
    "education": ("education", "edtech", "e-learning", "school", "university", "learning", "tutoring", "kids-stem"),
    "math": ("math", "science", "analytics", "data", "statistics", "research"),
    "publishing": ("publishing", "print", "documents", "productivity", "office", "notes"),
}


def _match(industry: str | None, keys: tuple[str, ...]) -> bool:
    if not industry:
        return False
    ind = industry.lower()
    return any(k in ind for k in keys)


def research(brief: Brief, catalog: list[dict], out_dir: Path) -> dict:
    groups: dict[str, list[dict]] = {g: [] for g in _RELATED}
    for e in catalog:
        for g, keys in _RELATED.items():
            if _match(e.get("industry"), keys):
                groups[g].append(e)
    summary: dict = {"groups": {}}
    lines = [f"# بحث تمهيدي: {brief.name_ar}", "",
             f"القطاع: {brief.sector}. الجمهور: {brief.audience}. الكلمات الثلاث: {'، '.join(brief.three_words)}.", "",
             "المكتبة المرجعية (علامات لأصحابها، للدراسة فقط): ما تفعله الفئات القريبة، لنعرف ما نتجنّبه.", ""]
    for g, items in groups.items():
        if not items:
            continue
        mark_types = Counter(e.get("mark_type") for e in items)
        subjects = Counter(e.get("subject") for e in items if e.get("subject"))
        techniques = Counter(t for e in items for t in (e.get("techniques") or []))
        fams = Counter(e.get("primary_family") for e in items if e.get("primary_family"))
        summary["groups"][g] = {
            "count": len(items),
            "mark_types": mark_types.most_common(5),
            "subjects": subjects.most_common(8),
            "techniques": techniques.most_common(8),
            "color_families": fams.most_common(5),
        }
        lines += [f"## {g} ({len(items)} علامة)",
                  "أنواع العلامات: " + "، ".join(f"{k} {v}" for k, v in mark_types.most_common(5)),
                  "موضوعات شائعة (تجنّبها): " + "؛ ".join(f"{k}" for k, _ in subjects.most_common(8)),
                  "تقنيات شائعة: " + "، ".join(f"{k} {v}" for k, v in techniques.most_common(8)),
                  "عائلات لونية: " + "، ".join(f"{k} {v}" for k, v in fams.most_common(5)), ""]
    avoid = list(brief.taste.avoid) + list(brief.taste.dislikes)
    lines += ["## ما يُمنع في هذا الموجز", *[f"- {a}" for a in avoid], "",
              "## الاتجاه", f"الإحساس المطلوب: {brief.taste.feeling}",
              f"النموذج الأصلي: {brief.archetype}. الغرض: {brief.purpose}", ""]
    summary["avoid"] = avoid
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "research.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "research.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
