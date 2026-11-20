"""بيان التبنّي (قرار المالك 2026-11-14): دليل الهوية يصل إلى المشروع ببيان آلي لا تخمين.

بعد تسليم v8 لـ«أوراق» سألت جلستها المالك عمّا لم يُطبَّق من أقسام الدليل (التطبيقات والحركة والملفات)، وطلبت جدول مطابقة
آليًا ومقتطع الحركة جاهزًا ومواصفات الشرائح. هنا `identity/ADOPTION.yaml` و`motion.css` يخرجان مع كل تسليم هوية كاملة،
والفجوة تُقاس على شجرة المشروع نفسها بإجراء لكل فحص، والبطاقة تذكرها.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from sima.domain import brief_from_dict
from sima.services import adoption
from sima.services import apply_identity as roles_map
from sima.services.deliver import DirFiles, plan_delivery

from .test_deliver import _package
from .test_delivery_stage6 import APP, IDENTITY, MAP
from .test_domain_ledger_workspace import BRIEF

MOTION_HTML = """<!doctype html><html><head><style>
body{margin:0}.mark{width:320px}
.mark>*{animation:sima-rise .6s cubic-bezier(.2,0,0,1) both;animation-delay:calc(var(--i,0) * 90ms)}
@keyframes sima-rise{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:reduce){.mark>*{animation:none}}
</style></head><body></body></html>"""
ICON = '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-2-1.5l-2 1.5Z"/>\n  <path d="M9 7h6"/></svg>'
ICON_D = "M6 3h12v18l-2-1.5l-2 1.5Z"
MOTIF = '<svg viewBox="0 0 120 60"><path d="M10 15 C40 5 80 5 110 15\n C80 23 40 23 10 15 Z" /></svg>'
RULES = roles_map.parse_rules(MAP)
ROLES = roles_map.identity_roles(IDENTITY, "p")


def _identity(tmp_path: Path, slug: str = "demo") -> Path:
    pkg = _package(tmp_path)
    ident = pkg / "identity"
    for sub, name, text in (("tokens", "tokens.css", IDENTITY.replace("--p-", f"--{slug}-")), ("motion", "mark-intro.html", MOTION_HTML),
                            ("fonts", "Cairo.ttf", "x"), ("icons", "print.svg", "<svg/>"), ("icons", "order.svg", ICON),
                            ("icons", "laser.svg", ICON.replace("M6 3", "M7 4")), ("patterns", "motif-soft.svg", MOTIF), ("applications", "slide-title.svg", "<svg/>"),
                            ("screens", "landing.html", "<html/>"), ("", "STRATEGY.md", "# منصة")):
        (ident / sub).mkdir(parents=True, exist_ok=True)
        (ident / sub / name).write_text(text, encoding="utf-8")
    return pkg


def _repo(tmp_path: Path, css: str = APP, extra: dict[str, str] | None = None) -> Path:
    repo = tmp_path / "proj"
    (repo / "frontend" / "src" / "styles").mkdir(parents=True)
    (repo / "frontend" / "src" / "styles" / "tokens.css").write_text(css, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    return repo


def _build(tmp_path: Path, repo: Path, css: str | None = None) -> adoption.Adoption:
    pkg = _identity(tmp_path)
    return adoption.build("demo", 8, "a1", pkg / "identity", RULES, ROLES, css, DirFiles(repo))


def _checks(a: adoption.Adoption) -> dict[str, adoption.Check]:
    return {c.id: c for c in a.checks}


def test_motion_snippet_is_embeddable_and_keeps_time_curve_stagger_and_reduced_motion():
    css = adoption.motion_css(MOTION_HTML)
    assert ".sima-mark-intro>*" in css and ".mark>*" not in css
    assert "cubic-bezier(.2,0,0,1)" in css and ".6s" in css and "90ms" in css
    assert "@keyframes sima-rise" in css and "prefers-reduced-motion:reduce" in css and "animation:none" in css
    assert "body{margin:0}" not in css  # قاعدة صفحة العرض التجريبية لا تدخل المشروع
    assert adoption.motion_css("<html>لا style</html>") == ""


def test_token_map_gives_role_variable_and_values_for_both_modes_and_marks_what_is_left():
    rows = {r["app_var"]: r for r in adoption.token_map(RULES, ROLES, "demo")}
    paper = rows["--color-paper"]
    assert paper["light"] == {"role": "bg", "var": "--demo-bg", "value": "#fbf3e4"}
    assert paper["dark"]["role"] == "bg"
    field = rows["--color-field"]  # {dark: bg}: نهارًا يبقى قيمة التطبيق
    assert field["light"] == "يُترك بقيمة التطبيق" and field["dark"]["var"] == "--demo-bg"
    md = rows["--radius-md"]
    assert md["light"]["value"] == "16px" and md["times"] == 2


def test_gaps_are_measured_on_the_project_tree_with_an_action_each(tmp_path):
    parity = adoption._first_value(APP, "color-brand")
    a = _build(tmp_path, _repo(tmp_path), APP)
    c = _checks(a)
    assert c["color-parity"].ok is False and f"--color-brand: {parity}" in c["color-parity"].detail  # التطبيق لم يُرقَّع بعد
    for gap in ("motion-included", "slide-templates", "splash-screen", "token-parity-test", "icons-used", "pattern-used",
                "screens-compared"):
        assert c[gap].ok is False and c[gap].action, gap
    assert "الحركة" not in a.summary() or "motion-included" in a.summary()
    assert a.summary().startswith("ADOPTION.yaml: ") and "الفجوات" in a.summary()


def test_checks_pass_when_the_project_has_what_the_book_asks_for(tmp_path):
    patched = roles_map.apply_roles(APP, RULES, ROLES, 8).css
    repo = _repo(tmp_path, patched, {
        "frontend/src/styles/motion.css": ".sima-mark-intro>*{animation:none}",
        "frontend/src/components/SlideTitle.vue": "<template/>", "frontend/src/components/AppSplash.vue": "<template/>",
        "frontend/src/tokens.spec.ts": "import m from 'brand/demo/identity/ADOPTION.yaml'",
        "frontend/src/styles/font.css": '@font-face{font-family:"Cairo"}',
        "frontend/src/data/icons.ts": f'export const order = "{ICON_D}"; export const laser = "{ICON_D.replace("M6 3", "M7 4")}"',
        "frontend/src/assets/band.svg": MOTIF, "frontend/src/pages/HomePage.vue": "<style>.hero{mask:url(@/assets/band.svg)}</style>",
        "frontend/tests/screens.spec.ts": "const SCREENS = 'brand/demo/identity/screens'",
    })
    roles = {**ROLES, "light": {**ROLES["light"], "font-heading": '"Cairo",Tahoma,sans-serif'}}
    a = adoption.build("demo", 8, "a1", _identity(tmp_path).joinpath("identity"), RULES, roles, patched, DirFiles(repo))
    assert a.gaps == (), [g.id for g in a.gaps]
    assert a.summary().endswith("يمرّ على مشروعك" + ".")


def test_yaml_is_valid_complete_and_carries_no_secret_looking_hash(tmp_path):
    a = _build(tmp_path, _repo(tmp_path), APP)
    doc = yaml.safe_load(a.yaml_text)
    assert doc["release"] == "demo/v8" and doc["concept"] == "a1"
    sections = {s["id"]: s for s in doc["sections"]}
    assert set(sections) == {"strategy", "color", "type", "pattern", "icons", "applications", "motion", "tokens", "book"}
    assert sections["motion"]["files"] == ["motion.css", "motion/mark-intro.html"]
    assert "applications/slide-title.svg" in sections["applications"]["files"] and "screens/landing.html" in sections["applications"]["files"]
    assert sections["color"]["status"] == "applied" and sections["icons"]["status"] == "provided"
    assert doc["gaps"] == [c.id for c in a.gaps] and doc["limits"]
    assert not any(len(tok) >= 32 and tok.isalnum() for tok in a.yaml_text.split())  # لا بصمة تقرؤها detect-secrets سرًّا


def test_plan_delivery_writes_the_manifest_and_motion_next_to_the_identity_and_tells_the_card(tmp_path):
    b = brief_from_dict(BRIEF)
    pkg = _identity(tmp_path, b.project)
    repo = _repo(tmp_path)
    plan = plan_delivery(b, pkg, repo, 8, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP)
    got = {w.path: w.content.decode("utf-8") for w in plan.writes if w.path.endswith((".yaml", ".css"))}
    base = f"brand/{b.project}/identity"
    assert f"{base}/{adoption.FILE_NAME}" in got and f"{base}/{adoption.MOTION_FILE}" in got
    doc = yaml.safe_load(got[f"{base}/{adoption.FILE_NAME}"])
    # التحقق يجري على tokens.css بعد ترقيعه: ألوان الهوية مطبَّقة فلا فجوة في color-parity
    assert next(c for c in doc["checks"] if c["id"] == "color-parity")["ok"] is True
    assert any(n.startswith("ADOPTION.yaml:") for n in plan.notes)
    # بلا خريطة لا بيان: التسليم القديم لا يتغيّر
    plain = plan_delivery(b, pkg, repo, 8, "a1", palette=("#7A1C3E", "#D9A441"))
    assert not any(w.path.endswith(adoption.FILE_NAME) for w in plain.writes)
    # تكرار التسليم لا يغيّر شيئًا (idempotent)
    again = plan_delivery(b, pkg, repo, 8, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP)
    assert [(w.path, w.content) for w in again.writes] == [(w.path, w.content) for w in plan.writes]


def test_icons_pattern_and_screens_are_measured_by_use_not_by_reference_files(tmp_path):
    """«مسك» v5: الأيقونات والنمط والشاشات وصلت مرجعًا ولم تدخل صفحة؛ الفحص يعدّ ما استُعمل ويسمّي ما لم يُستعمل."""
    assert adoption.signature(ICON) == ICON_D and adoption.signature("<svg/>") == ""
    repo = _repo(tmp_path, APP, {
        "frontend/src/components/OrderIcon.vue": f'<template><svg><path d="{ICON_D}"/></svg></template>',  # أيقونة واحدة مرسومة
        "frontend/src/static/brand/motif.svg": MOTIF.replace("\n", " "),  # نسخة النمط باسم آخر
        "frontend/src/static/brand/splash.css": ".splash-band{mask:url(motif.svg)}",  # تذكرها شاشة الافتتاح وحدها
        "tests/test_brand.py": "ADOPTION.yaml",
    })
    c = _checks(_build(tmp_path, repo, APP))
    assert c["icons-used"].ok is False and c["icons-used"].detail == "1 من 2 أيقونة مستعملة في الواجهة؛ غير المستعملة: laser"
    assert c["pattern-used"].ok is False and c["pattern-used"].detail == "النمط في شاشة الافتتاح وحدها" and c["pattern-used"].action
    assert c["screens-compared"].ok is False and "screens/landing.html" in c["screens-compared"].action
    # النمط في صفحة، والأيقونة الثانية، واختبار يذكر شاشات الدليل: تُغلق الفجوات الثلاث
    for rel, text in (("frontend/src/pages/HomePage.vue", "<style>.hero{mask:url('../static/brand/motif.svg')}</style>"),
                      ("frontend/src/components/LaserIcon.vue", f'<svg><path d="{ICON_D.replace("M6 3", "M7 4")}"/></svg>'),
                      ("frontend/tests/screens.spec.ts", "compare(page, 'brand/demo/identity/screens/landing.png')")):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    c = _checks(adoption.build("demo", 8, "a1", tmp_path / "pkg" / "identity", RULES, ROLES, APP, DirFiles(repo)))
    assert c["icons-used"].ok and c["pattern-used"].ok and c["screens-compared"].ok
    assert c["pattern-used"].detail == "النمط مستعمل في frontend/src/pages/HomePage.vue"


def test_a_package_without_icons_patterns_or_screens_adds_no_check(tmp_path):
    ident = tmp_path / "bare"
    ident.mkdir()
    ids = {c.id for c in adoption.build("demo", 8, "a1", ident, RULES, ROLES, APP, DirFiles(_repo(tmp_path))).checks}
    assert not ids & {"icons-used", "pattern-used", "screens-compared"}


def test_an_icon_component_that_takes_the_name_as_a_prop_counts_as_use(tmp_path):
    """«مسك» بعد v5: نسخ الأيقونات في مجلد يستورده مكوّن جملةً والصفحات تسمّي الأيقونة خاصيةً؛ غير المسمّاة تبقى غير مستعملة."""
    repo = _repo(tmp_path, APP, {
        "frontend/src/static/brand/icons/order.svg": ICON, "frontend/src/static/brand/icons/laser.svg": ICON.replace("M6 3", "M7 4"),
        "frontend/src/components/BrandIcon.vue": '<script setup>const s = import.meta.glob("../static/brand/icons/*.svg")</script>',
        "frontend/src/pages/OrdersPage.vue": '<template><BrandIcon name="order" /></template>',
        "docs/slides/slides.html": "<html/>",
    })
    c = _checks(_build(tmp_path, repo, APP))
    assert c["icons-used"].detail == "1 من 2 أيقونة مستعملة في الواجهة؛ غير المستعملة: laser"
    assert c["slide-templates"].ok  # الشرائح حيثما بناها المشروع، لا تحت frontend/src وحده


def test_delivery_writes_the_logo_components_without_the_fixed_size_of_the_source(tmp_path):
    """حزمة «مسك» v5 المعتمدة تحمل width="100mm" مع :width في وسم المكوّن؛ التسليم يحذف الثابت دون إعادة بناء الحزمة."""
    b = brief_from_dict(BRIEF)
    pkg = _identity(tmp_path, b.project)
    (pkg / "BrandMark.vue").write_text('<template><svg class="brand-mark" :width="size" width="100mm" height="65mm" viewBox="0 0 1 1">'
                                       '<path stroke-width="2"/></svg></template>', encoding="utf-8")
    plan = plan_delivery(b, pkg, _repo(tmp_path), 8, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP)
    mark = next(w.content.decode("utf-8") for w in plan.writes if w.path.endswith("BrandMark.vue"))
    assert '<svg class="brand-mark" :width="size" viewBox="0 0 1 1">' in mark and 'stroke-width="2"' in mark
