"""ملف التسليم Django (قرار المالك 2026-11-15: نقل الهوية إلى منصة المدرسة D:\\shschool_mvp).

المنصة تطبيق Django بقوالب وstatic/css لا واجهة Vue ولا دفتر بطاقات، فلا ينطبق عليها `plan_delivery` (BrandMark.vue وfrontend/).
هنا مرحلة الألوان وحدها: خريطة `apply_identity` من `deliver_targets.yaml` تُطبَّق على ملفات الأنماط المسمّاة في `styles:`
بالمحرك نفسه (`apply_identity.apply_roles`): الكتلة الليلية `html.dark` تُقرأ ليلية، والأسطر المتعددة التعريف تُعالَج كلها.
الشعار والأيقونات والزوايا والخطوط مراحل لاحقة بقرارات منفصلة، فلا تكتبها هذه الدالة. دالة صافية على شجرة تُقرأ ولا تُكتب."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ..domain.brief import Brief
from ..domain.delivery import DeliveryPlan, FileWrite
from . import apply_identity as roles_map


def plan_delivery_django(brief: Brief, package_dir: Path, files, version: int, concept_id: str,
                         styles: Sequence[str], apply_identity: Mapping | None) -> DeliveryPlan:
    """خطة كتابة ملفات الأنماط بأدوار الاتجاه المعتمد. غياب الخريطة أو الهوية الكاملة أو أحد الملفات خطأ يوقف التسليم باسمه."""
    slug = brief.project
    tokens = package_dir / "identity" / "tokens" / "tokens.css"
    if not apply_identity:
        raise RuntimeError(f"تسليم {slug} إلى تطبيق Django يلزمه apply_identity في deliver_targets.yaml.")
    if not styles:
        raise RuntimeError(f"تسليم {slug} إلى تطبيق Django يلزمه styles: في deliver_targets.yaml (ملفات الأنماط).")
    if not tokens.is_file():
        raise RuntimeError("لا هوية كاملة في الحزمة (identity/tokens/tokens.css): اعتمد دليل الهوية أولًا.")
    rules = roles_map.parse_rules(apply_identity)
    roles = roles_map.identity_roles(tokens.read_text(encoding="utf-8"), slug)
    writes: list[FileWrite] = []
    notes = ["مرحلة الألوان وحدها: لا شعار ولا أيقونات ولا خطوط ولا زوايا هنا (مراحل لاحقة بقرارات منفصلة من المالك)."]
    for rel in styles:
        css = files.read_text(rel)
        if css is None:
            raise RuntimeError(f"ملف الأنماط غير موجود أو ليس نصًّا في المستودع الهدف: {rel}")
        applied = roles_map.apply_roles(css, rules, roles, version)
        notes.append(roles_map.diff_note(applied, version).replace("tokens.css:", f"{rel}:", 1))
        if applied.css != css:
            writes.append(FileWrite(rel, applied.css.encode("utf-8")))
    return DeliveryPlan(project=slug, version=version, concept_id=concept_id, writes=tuple(writes), notes=tuple(notes), deletes=())


def card_text_django(brief: Brief, plan: DeliveryPlan) -> tuple[str, str, str]:
    title = f"هوية «{brief.wordmark_text}» من سِمة: مرحلة الألوان (المفهوم {plan.concept_id}، الإصدار v{plan.version})"
    body = ("الملفات مكتوبة ومودَعة في هذا الفرع بأداة سِمة؛ لا يُعدَّل لون يدويًا قبل مراجعة المالك. ما تغيّر:\n"
            + "\n".join(f"- {n}" for n in plan.notes)
            + "\n- شغّل اختبارات التباين والتكافؤ الليلي في المنصة (test_dark_parity وما يقيس التباين) وأصلح ما سقط بقرار المالك.")
    success = "اختبارات التباين والتكافؤ الليلي تمرّ في المنصة، ولا متغير لوني خارج الخريطة إلا ما ذكرته البطاقة."
    return title, body, success
