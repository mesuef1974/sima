"""التسليم والتصدير بعد مراجعة الأتمتة (2026-11-14، المرحلة 6): نقطة git الآلية لا تفشل بصمت (ت6)، والأمر البديل يُطبع بمسار
مقتبس (ت11). لا اتصال شبكي ولا نموذج في هذه الاختبارات."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from sima.adapters import auto_deliver
from sima.adapters.auto_deliver import commit_outputs
from sima.adapters.ledger_runner import GitRefFiles, LedgerRunnerTarget
from sima.domain import Concept, Family, Medium, brief_from_dict
from sima.services import apply_identity as roles_map
from sima.services import design_tokens, designer, export
from sima.services.color_system import build_system, contrast_ratio
from sima.services.deliver import card_text, deliver, plan_delivery, replace_color_light
from sima.services.pipeline import Pipeline
from sima.services.workspace import open_workspace

from .fakes import FakeRenderer, rect_svg
from .test_color_pairs import D3
from .test_deliver import FakeTarget, _delivery_setup, _package, _styled_repo
from .test_deliver import _repo as _plain_repo
from .test_designer import track  # noqa: F401
from .test_designer_track import _to_book
from .test_domain_ledger_workspace import BRIEF


def _repo(tmp_path):
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    v = tmp_path / "out" / "p" / "v1"
    v.mkdir(parents=True)
    (v / "run.json").write_text(json.dumps({"project": "p", "version": 1, "brief_source": "briefs/p.yaml"}), encoding="utf-8")
    return v, git


# ---------- ت6 ----------
def test_a_failed_git_add_is_reported_not_taken_for_nothing_new(tmp_path):
    """فهرس مقفل (`index.lock`) يُفشل `git add`؛ كان يُهمل رمزه فيعود الأمر فارغًا كأن لا جديد، والمخرجات المعتمدة بلا نقطة."""
    v, git = _repo(tmp_path)
    lock = tmp_path / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    line = commit_outputs(v, tmp_path)
    assert line.startswith("تنبيه: تعذّرت نقطة git") and "git add" in line
    lock.unlink()
    assert "أُودعت" in commit_outputs(v, tmp_path)  # زال القفل: النقطة تُسجَّل
    assert git("show", "--name-only", "--format=").split() == ["out/p/v1/run.json"]


# ---------- ت11 ----------
def test_the_fallback_command_quotes_a_repo_path_with_a_space(tmp_path, monkeypatch):
    """مستودع «أوراق» مساره فيه فراغ: الأمر البديل المطبوع عند تعذّر التسليم الآلي يُنسخ ويُشغَّل كما هو."""
    v, _ = _repo(tmp_path)
    repo = tmp_path / "مستودع بفراغ"
    monkeypatch.setattr(auto_deliver, "targets", lambda: {"p": {"repo": str(repo)}})
    line = auto_deliver.deliver_if_configured(v)  # لا موجز مجمَّد في الإصدار: يتعذّر التسليم ويُطبع البديل
    assert line.startswith("تنبيه: تعذّر التسليم الآلي") and f'--repo "{repo.resolve()}"' in line


# ---------- ت2: التطبيق يتبع الاتجاه المعتمد كاملًا (ق1) ----------
APP = """/* مصدر الهوية الوحيد: هوية «أوراق» v2 من سِمة. */
:root {
  --color-paper: #ffffff;
  --color-field: #ffffff;
  --color-ink: #14171c;
  --color-grid: rgb(142 36 51 / 5%);
  --color-brand: #8e2433;
  --color-on-brand: #ffffff;
  --color-glow: rgb(255 255 255 / 40%);
  --color-other: #123456;
  --radius-sm: 2px;
  --radius-md: 4px;
  --shadow-sm: 0 1px 2px rgb(20 23 28 / 6%);
}
@media screen and (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-paper: #14191f;
    --color-field: #14191f;
    --color-brand: #d58298;
    --color-grid: rgb(213 130 152 / 6%);
  }
}
"""
IDENTITY = """:root{
  --p-bg:#FBF3E4;
  --p-text:#2A1D1A;
  --p-brand:#7A1C3E;
  --p-on-brand:#FFFFFF;
  --p-radius:8px;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --p-bg:#1D1711;
}}
:root[data-theme="dark"]{
  --p-bg:#1D1711;
  --p-brand:#DC8084;
}
"""
MAP = {"color-paper": "bg", "color-field": {"dark": "bg"}, "color-ink": "text", "color-brand": "brand",
       "color-on-brand": "on-brand", "radius-sm": "radius", "radius-md": {"role": "radius", "times": 2}}


def _applied(css: str = APP, version: int = 7):
    return roles_map.apply_roles(css, roles_map.parse_rules(MAP), roles_map.identity_roles(IDENTITY, "p"), version)


def test_every_mapped_variable_takes_its_role_in_the_mode_of_its_block():
    """تسليم v6 غيّر العنابي النهاري وحده فبقي التطبيق هجينًا؛ الخريطة تطبّق كل دور في وضع كتلته وتسرد ما تغيّر بقيمتيه."""
    a = _applied()
    light, dark = a.css.split("@media")
    assert "--color-paper: #fbf3e4;" in light and "--color-ink: #2a1d1a;" in light and "--color-brand: #7a1c3e;" in light
    assert "--color-field: #ffffff;" in light  # نهارًا خارج الخريطة بقصد
    assert "--color-paper: #1d1711;" in dark and "--color-field: #1d1711;" in dark and "--color-brand: #dc8084;" in dark
    assert "--radius-sm: 8px;" in light and "--radius-md: 16px;" in light
    assert "هوية «أوراق» v7 من سِمة" in a.css
    assert roles_map.Change("color-paper", "light", "#ffffff", "#fbf3e4") in a.changes
    assert roles_map.Change("color-brand", "dark", "#d58298", "#dc8084") in a.changes
    assert not any(c.var == "color-on-brand" for c in a.changes)  # بقيمته: لا يُعدّ تغييرًا


def test_an_rgb_triple_of_an_old_value_follows_it_unless_two_variables_share_it():
    a = _applied()
    assert "--color-grid: rgb(122 28 62 / 5%);" in a.css and "--color-grid: rgb(220 128 132 / 6%);" in a.css
    assert "--shadow-sm: 0 1px 2px rgb(42 29 26 / 6%);" in a.css
    assert "--color-glow: rgb(255 255 255 / 40%);" in a.css and a.unfollowed == ("--color-glow",)  # الأبيض ورقٌ وحبرُ علامة
    assert a.unmapped == ("--color-glow", "--color-other")
    assert roles_map.Change("color-grid", "dark", "rgb(213 130 152 / 6%)", "rgb(220 128 132 / 6%)") in a.changes


def test_applying_the_map_to_its_own_output_changes_nothing():
    once = _applied()
    again = _applied(once.css)
    assert again.css == once.css and again.changes == ()


def test_a_role_the_identity_does_not_carry_stops_the_delivery_with_its_name():
    with pytest.raises(ValueError, match="accent-text"):
        roles_map.apply_roles(APP, roles_map.parse_rules({"color-sand": "accent-text"}), roles_map.identity_roles(IDENTITY, "p"), 7)
    with pytest.raises(ValueError, match="color-x"):
        roles_map.parse_rules({"color-x": {"lihgt": "bg"}})


# أزواج اختبار تباين التطبيق المستلم (`D:/أوراق الرياضيات/frontend/src/styles/contrast.test.ts`): يُحاكى على الخريطة قبل التسليم
APP_TEXT = [("ink", "paper"), ("ink", "surface"), ("ink", "surface-sunken"), ("ink", "sheet"), ("ink", "field"), ("ink-soft", "paper"),
            ("ink-soft", "surface"), ("ink-soft", "surface-sunken"), ("ink-soft", "sheet"), ("brand", "paper"), ("brand", "surface"),
            ("brand", "field"), ("brand", "brand-soft"), ("brand-strong", "brand-soft"), ("ink", "brand-soft"), ("on-brand", "brand"),
            ("on-brand", "brand-strong"), ("danger", "danger-soft"), ("danger", "paper"), ("danger", "surface"),
            ("success", "success-soft"), ("success", "paper"), ("info", "info-soft"), ("info", "paper"), ("ink", "info-soft"),
            ("level-k", "level-k-soft"), ("level-a", "level-a-soft"), ("level-r", "level-r-soft"), ("sand", "paper"),
            ("sand", "surface"), ("sand", "sand-soft"), ("ink", "sand-soft")]
APP_NON_TEXT = [("line-strong", "field"), ("line-strong", "surface"), ("focus", "paper"), ("focus", "surface"), ("brand", "paper")]


def _awraq():
    font = {"family": "Cairo", "file": "Cairo[slnt,wght].ttf", "weight": 700}
    identity = design_tokens.css("math_papers", build_system(D3), {"heading": font, "body": {**font, "weight": 400}}, 8, "latn")
    app = (Path(__file__).parent / "data" / "awraq_app_tokens.css").read_text(encoding="utf-8")
    rules = roles_map.parse_rules(auto_deliver.targets()["math_papers"]["apply_identity"])
    return roles_map.apply_roles(app, rules, roles_map.identity_roles(identity, "math_papers"), 7), rules


def _vars(css: str, opening: str) -> dict[str, str]:
    start = css.index(opening)
    return {m.group(1): m.group(2).lower()
            for m in re.finditer(r"--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b", css[start:css.index("}", start)])}


def test_the_awraq_map_passes_the_contrast_pairs_of_the_receiving_app_in_both_modes():
    """ق1: التطبيق يتبع الاتجاه كاملًا. رموز «أوراق» كما هي في مستودعها (نسخة في tests/data) تأخذ اتجاه d3 بخريطة هدفها،
    وأزواج اختبار تباينها تُقاس على الناتج: ما يردّه اختبار التطبيق يُردّ هنا قبل أن تُكتب بطاقة."""
    applied, rules = _awraq()
    light = _vars(applied.css, ":root {")
    auto, manual = _vars(applied.css, ':root:not([data-theme="light"]) {'), _vars(applied.css, ':root[data-theme="dark"] {')
    assert auto == manual  # الكتلتان الليليتان متطابقتان كما يفرض اختبار التطبيق
    for name, theme in (("نهارًا", light), ("ليلًا", {**light, **auto})):
        for pairs, floor in ((APP_TEXT, 4.5), (APP_NON_TEXT, 3.0)):
            for fg, bg in pairs:
                assert contrast_ratio(theme[fg], theme[bg]) >= floor, (name, fg, theme[fg], bg, theme[bg])
    assert (light["paper"], light["accent"], light["brand-strong"], auto["brand"]) == ("#fbf3e4", "#db943c", "#740a21", "#dc8084")
    assert (light["sheet"], light["field"]) == ("#ffffff", "#ffffff")
    assert "هوية «أوراق» v7 من سِمة" in applied.css and "--radius-sm: 8px;" in applied.css and "--radius-lg: 16px;" in applied.css
    assert applied.unmapped == () and applied.unfollowed == ()
    assert {r.var for r in rules} >= {f"color-{k}" for k in light if not k.startswith("mark-") and k != "grid"}


def test_the_card_lists_every_changed_value_instead_of_asking_for_verification_only(tmp_path):
    """البطاقة كانت تقول «المطلوب التحقق فقط» والتطبيق تغيّرت قيمه: الآن فرق القيم فيها، وما خرج عن الخريطة مذكور."""
    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _plain_repo(tmp_path)
    (pkg / "identity" / "tokens").mkdir(parents=True)
    (pkg / "identity" / "tokens" / "tokens.css").write_text(IDENTITY.replace("--p-", f"--{b.project}-"), encoding="utf-8")
    (repo / "frontend" / "src" / "styles" / "tokens.css").write_text(APP, encoding="utf-8")
    plan = plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP)
    tokens = next(w.content.decode("utf-8") for w in plan.writes if w.path.endswith("styles/tokens.css"))
    assert "--color-paper: #fbf3e4;" in tokens and "--color-mark-ink: #7a1c3e;" in tokens
    _, body, _ = card_text(b, plan)
    assert "المطلوب التحقق فقط" not in body
    assert "نهارًا `--color-paper`: #ffffff صار #fbf3e4" in body and "ليلًا `--color-brand`: #d58298 صار #dc8084" in body
    assert "`--color-other`" in body and "contrast.test.ts" in body
    plain = plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"))
    assert "--color-paper: #ffffff;" in next(w.content.decode("utf-8") for w in plain.writes if w.path.endswith("styles/tokens.css"))


# ---------- ت3 ----------
def test_the_old_brand_color_left_outside_the_unified_roots_is_listed_in_the_card(tmp_path):
    """`unify_brand` يبدّل `#rrggbb` في الواجهة والقوالب؛ ثابت بلا `#` في مولّد Word (`BRAND = "842447"`) كان يبقى بلا ذكر
    فأصلحه مشروع «أوراق» بيده. الآن يُسرد بمساره وسطره، ومرجع الهوية `brand/` وملفات القفل والمجلدات المخفية خارج المسح."""
    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _styled_repo(tmp_path)
    (repo / "apps" / "word").mkdir(parents=True)
    (repo / "apps" / "word" / "ooxml.py").write_text('X = 1\nBRAND = "842447"\nHASH = "a842447f"\n', encoding="utf-8")
    (repo / "docs.md").write_text("لون العلامة rgb(132, 36, 71) في الوثيقة\n", encoding="utf-8")
    (repo / "frontend" / "package-lock.json").write_text('{"integrity": "842447"}', encoding="utf-8")
    (repo / "brand" / b.project).mkdir(parents=True)
    (repo / "brand" / b.project / "old.md").write_text("#842447", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / ".git" / "packed").write_text("#842447", encoding="utf-8")
    plan = plan_delivery(b, pkg, repo, 4, "a1", palette=("#7A1C3E", "#D9A441"), unify_brand=True)
    note = next(n for n in plan.notes if "بقي لون العلامة القديم" in n)
    assert "apps/word/ooxml.py:2" in note and "docs.md:1" in note
    assert "ooxml.py:3" not in note and "package-lock" not in note and "old.md" not in note and ".git" not in note
    assert "tokens.css" not in note  # ما وُحّد لا يُسرد، والقيم الليلية ليست «باقيًا»
    assert not any("بقي لون العلامة القديم" in n for n in plan_delivery(b, pkg, repo, 4, "a1", palette=("#7A1C3E", "#D9A441")).notes)


def test_unifying_the_light_brand_never_touches_a_dark_block_that_carries_the_same_value():
    """«القيم الليلية لا تُمسّ» كانت تصدق مصادفةً: الاستبدال على الملف كله، فقيمة ليلية تساوي العنابي النهاري القديم تُبدَّل."""
    css = (":root {\n  --color-brand: #842447;\n}\n@media (prefers-color-scheme: dark) {\n  :root {\n    --color-frame: #842447;\n  }\n}\n"
           ':root[data-theme="dark"] {\n  --color-frame: rgb(132 36 71 / 50%);\n}\n.x { color: #842447; }\n')
    out = replace_color_light(css, "#842447", "#7A1C3E", css=True)
    assert "--color-brand: #7a1c3e;" in out and ".x { color: #7a1c3e; }" in out
    assert "--color-frame: #842447;" in out and "rgb(132 36 71 / 50%)" in out
    assert replace_color_light(css, "#842447", "#7A1C3E", css=False).count("#842447") == 0  # غير CSS: الملف كله


# ---------- ت7 ----------
def test_the_card_describes_the_base_the_branch_opens_from_not_the_main_checkout(tmp_path):
    """نص البطاقة كان يُحسب من النسخة الرئيسة (بفرعها وتعديلاتها) والإيداع من شجرة البطاقة: النسخة الرئيسة هنا بلا قالب
    spa.html وبلا print.css، وorigin/main فيه القالب وورقة الطباعة؛ البطاقة تصف ما سيودَع فعلًا."""
    b, ws, repo = _delivery_setup(tmp_path)
    origin = tmp_path / "origin"
    shutil.copytree(repo, origin)
    (repo / "templates" / "spa.html").unlink()
    (origin / "frontend" / "src" / "styles" / "print.css").write_text(":root { --color-mark-ink: #000000; }", encoding="utf-8")
    target = FakeTarget(repo, origin)
    rc = deliver(ws, b, target, repo)
    assert "templates/spa.html: روابط" in target.body and "templates/spa.html" in rc.paths
    assert "print.css: --color-mark-ink" in target.body and "frontend/src/styles/print.css" in rc.changed


def test_git_ref_files_read_a_commit_without_a_checkout(tmp_path):
    """منفذ الأساس في المحوّل: شجرة مرجع git تُقرأ من أرشيف واحد، بأسماء عربية، وغير النصي None، والنسخة العاملة لا تُقرأ."""
    _, git = _repo(tmp_path)
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "أنماط.css").write_text(":root{}", encoding="utf-8")
    (tmp_path / "frontend" / "logo.png").write_bytes(b"\x89PNG\xff\xfe")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "frontend" / "src" / "أنماط.css").write_text("LOCAL", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")
    files = GitRefFiles(tmp_path, "HEAD")
    assert files.read_text("frontend/src/أنماط.css") == ":root{}" and files.read_text("frontend/logo.png") is None
    assert files.read_text("untracked.txt") is None and files.walk("frontend/src") == ["frontend/src/أنماط.css"]
    assert "out/p/v1/run.json" in files.walk()


# ---------- ت8 ----------
def test_identity_files_of_an_earlier_delivery_that_the_approved_identity_dropped_are_deleted(tmp_path):
    """التسليم كان يكتب ولا يحذف: ملف هوية من إصدار سابق يبقى بجوار الجديدة تحت brand/<slug>/identity/. الآن يُحذف ويُعدّ في
    الإيصال ويُذكر في البطاقة، وما خارج مجلد الهوية لا يُمسّ؛ ومحاولة تعثّرت بعد الحذف تودِع الحذف في الثانية."""
    b, ws, repo = _delivery_setup(tmp_path)
    ident = ws.package_dir / "identity"
    (ident / "tokens").mkdir(parents=True)
    (ident / "tokens" / "tokens.css").write_text(":root{}", encoding="utf-8")
    old = repo / "brand" / b.project / "identity"
    (old / "motifs").mkdir(parents=True)
    (old / "motifs" / "d1.svg").write_text("<svg/>", encoding="utf-8")
    (old / "tokens").mkdir()
    (old / "tokens" / "tokens.css").write_text(":root{--old:1}", encoding="utf-8")
    (repo / "brand" / b.project / "notes-by-project.md").write_text("للمشروع", encoding="utf-8")
    target = FakeTarget(repo, fail_commit=True)
    with pytest.raises(RuntimeError):
        deliver(ws, b, target, repo)
    rc = deliver(ws, b, target, repo)
    stale = f"brand/{b.project}/identity/motifs/d1.svg"
    wt = Path(rc.worktree)
    assert not (wt / stale).exists() and (wt / "brand" / b.project / "notes-by-project.md").is_file()
    assert rc.deleted == (stale,) and stale in rc.changed and stale in target.gone and stale in target.committed
    assert "حُذف ما ليس في الهوية المعتمدة" in target.body and "motifs/d1.svg" in target.body
    assert deliver(ws, b, target, repo).deleted == (stale,)  # من العلامة


def test_the_runner_adapter_commits_a_planned_deletion_and_skips_an_untracked_one(tmp_path):
    """المحوّل الفعلي: ما حذفته الخطة يُودَع حذفًا مع ما كُتب، ومسار غائب لم يُتتبَّع قط لا يُفشل الإيداع."""
    _, git = _repo(tmp_path)
    (tmp_path / "automation").mkdir()
    (tmp_path / "automation" / "ledger.py").write_text("", encoding="utf-8")
    (tmp_path / "old.svg").write_text("<svg/>", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "old.svg").unlink()
    (tmp_path / "new.svg").write_text("<svg/>", encoding="utf-8")
    head = LedgerRunnerTarget(tmp_path).commit(tmp_path, ("new.svg", "old.svg", "never-there.svg"), "تسليم")
    assert git("rev-parse", "HEAD").strip() == head
    shown = git("show", "--no-renames", "--name-status", "--format=")
    assert sorted(x for x in shown.splitlines() if x) == ["A\tnew.svg", "D\told.svg"]


# ---------- ت4 ----------
def test_the_package_is_rebuilt_when_any_export_input_changes_not_only_the_palette(tmp_path):
    """مخبأ الحزمة كان الألوان وحدها: خط عناوين الاتجاه يغيّر كلمة القفل والألوان كما هي، فتعود حزمة بقفل قديم. الآن بصمة كل
    المدخلات؛ علامة قديمة بلا بصمة تُقبل كما كانت، وإصدار اعتُمد دليله لا تُبنى حزمته من جديد."""
    b = brief_from_dict(BRIEF)
    ws = open_workspace(tmp_path / "out", b)
    c = Concept("c1", "مربع", Family.ABSTRACT, Medium.ABSTRACT_MARK, "فكرة بجملة")
    pipe = Pipeline.__new__(Pipeline)
    pipe._export = export.ExportService(FakeRenderer())
    svg, lock_a, lock_b = rect_svg(32, 32, 192, 192), rect_svg(16, 16, 100, 100), rect_svg(24, 24, 100, 100)
    lockup, kept = ws.package_dir / f"{b.project}-lockup-mono.svg", ws.package_dir / "kept-from-first-build"

    pipe._stage_package(ws, b, c, svg, None, None, lock_a)
    first = lockup.read_text(encoding="utf-8")
    kept.write_text("x", encoding="utf-8")
    pipe._stage_package(ws, b, c, svg, None, None, lock_a)
    assert kept.is_file()  # المدخلات نفسها: لا بناء
    pipe._stage_package(ws, b, c, svg, None, None, lock_b)
    assert not kept.exists() and lockup.read_text(encoding="utf-8") != first  # القفل تغيّر والألوان كما هي: تُبنى
    pipe._stage_package(ws, b, replace(c, name="اسم آخر"), svg, None, None, lock_b)
    assert "اسم آخر" in (ws.package_dir / "USAGE.md").read_text(encoding="utf-8")

    legacy = {k: v for k, v in ws.read_marker("package").items() if k != "inputs"}
    ws.mark_done("package", legacy)
    kept.write_text("x", encoding="utf-8")
    pipe._stage_package(ws, b, c, svg, None, None, lock_a)
    assert kept.is_file()  # علامة قبل هذه المرحلة: تُقبل بألوانها فلا يُعاد بناء إصدار جارٍ
    ws.mark_done("package", {**legacy, "inputs": "0" * 16})
    ws.mark_done("identity")
    pipe._stage_package(ws, b, c, svg, None, None, lock_a)
    assert kept.is_file()  # دليل معتمد: الإصدار مغلق


# ---------- ت9 والملاحظة 2 ----------
def test_the_package_documents_say_what_the_delivery_does(tmp_path):
    """`tokens.css` الحزمة كان يقول «الشعار ثابت في الوضعين» والتسليم يعكس حبره في الداكن، و`USAGE.md` يسرد ملفات ليست بجواره
    في المشروع وخطوات ربط يدوي أنجزها التسليم. ورمز بلون واحد لا يُذكر له لون تمييز كأنه يستعمله."""
    b = brief_from_dict(BRIEF)
    c = Concept("c1", "مربع", Family.ABSTRACT, Medium.ABSTRACT_MARK, "فكرة بجملة")
    export.ExportService(FakeRenderer()).export(export.ExportInputs(b, c, rect_svg(32, 32, 192, 192), None, None, None, None), tmp_path / "p", 1)
    tokens, usage = ((tmp_path / "p" / n).read_text(encoding="utf-8") for n in ("tokens.css", "USAGE.md"))
    assert "ثابت في الوضعين" not in tokens and "على الداكن" in tokens
    assert "--color-mark-accent" not in tokens and "--brand-accent" in tokens  # الرمز بلون واحد؛ لون التمييز دور في الهوية
    assert "ربطُه منجز" in usage and f"brand/{b.project}/" in usage and "frontend/public/" in usage
    assert "أدرج `tokens.css` في `styles/index.css`" not in usage
    assert "الرمز بلون واحد لا يستعمله" in usage and 'data-tone="accent"' not in usage
    two = rect_svg(32, 32, 192, 192).replace("<rect", '<rect data-tone="accent"', 1)
    assert "--color-mark-accent" in export.tokens_css(b, b.project, export.mark_uses_accent(two))
    assert "| التمييز |" in export.usage_md(b, c, b.project, [], None, mark_accent=True)


def test_a_single_color_mark_gets_no_accent_variable_unless_the_project_uses_it(tmp_path):
    """الملاحظة 2 على تسليم «أوراق» v6: `--color-mark-accent` كُتب بلا شرط في tokens.css وprint.css والرمز بلون واحد، والبطاقة
    تقول إنه يستعمله."""
    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _styled_repo(tmp_path)
    (pkg / "BrandMark.vue").write_text('<template><svg fill="var(--color-mark-ink, #7a1c3e)"/></template>', encoding="utf-8")
    styles = repo / "frontend" / "src" / "styles"
    (styles / "print.css").write_text(":root {\n  --color-mark-ink: #842447;\n  --color-mark-accent: #e3ab3c;\n}\n", encoding="utf-8")
    plan = plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"))
    got = {w.path: w.content.decode("utf-8") for w in plan.writes if w.path.endswith(".css")}
    assert "--color-mark-accent" not in got["frontend/src/styles/tokens.css"] + got["frontend/src/styles/print.css"]
    assert "--color-mark-ink: #7a1c3e;" in got["frontend/src/styles/tokens.css"] + got["frontend/src/styles/print.css"]
    assert got["frontend/src/styles/print.css"] == ":root {\n  --color-mark-ink: #7a1c3e;\n}\n"
    assert any("بلون واحد: يستعمل --color-mark-ink وحده" in n for n in plan.notes)
    assert not any("--color-mark-accent فقط" in n for n in plan.notes)

    (repo / "frontend" / "src" / "Badge.vue").write_text("<style>.b { color: var(--color-mark-accent); }</style>", encoding="utf-8")
    kept = plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"))
    assert "--color-mark-accent: #d9a441;" in next(w.content.decode("utf-8") for w in kept.writes if w.path.endswith("tokens.css"))
    assert any("frontend/src/Badge.vue" in n for n in kept.notes)


# ---------- ت10 وق2 ----------
def test_shown_name_is_the_title_of_the_sketch_the_owner_chose():
    sheet = designer.Sheet("s.jpg", "", ((11, "التراكب الأفقي: تتّسع الأوراق الخلفية نحو اليسار."), (12, "فكرة بلا عنوان")), (), "d")
    assert designer.shown_name(sheet, 11) == "التراكب الأفقي (السكتش 11)"
    assert designer.shown_name(sheet, 12) == "السكتش 12"


def test_documents_name_the_mark_by_its_sketch_and_carry_the_run_key(track):  # noqa: F811
    """ق2: الاسم الذي وضعه المصمّم لم يُسأل عنه المالك، فلا يُعرض: الوثائق تسمّي العلامة بالسكتش الذي اختاره، واسم المصمّم يبقى
    في البيان. وت10: `concept.json` كان يحمل بصمة موجز بُدّلت ألوانه بالاتجاه فلا تطابق تشغيلًا."""
    _, _, _, ws, _ = _to_book(track)
    concept = json.loads((ws.package_dir / "concept.json").read_text(encoding="utf-8"))
    usage = (ws.package_dir / "USAGE.md").read_text(encoding="utf-8")
    assert concept["name"] == "السكتش 5" and "«السكتش 5»" in usage and "وتد مائل" not in usage
    assert "وتد مائل" in designer.manifest_path(ws).read_text(encoding="utf-8")  # حقل تتبّع في البيان وبصمته
    assert concept["brief_hash"] == ws.key.brief_hash and concept["run_key"] == ws.key.key
    assert ws.read_marker("package")["inputs"]


# ---------- ت11: القاعدة ----------
def test_registry_keeps_the_lockup_as_a_mark_and_reads_designer_decisions_as_gate_decisions(tmp_path):
    """`BrandLockup.vue` كان يُحفظ وثيقة، وقرارات مسار المصمّم (أي سكتش اختار المالك ولماذا ردّ متجهًا) لم تكن تدخل القاعدة."""
    from sima.web import setup

    setup()
    from sima.web.registry.models import AssetKind
    from sima.web.registry.service import _kind, designer_decisions

    assert _kind("BrandLockup.vue") == AssetKind.MARK and _kind("BrandMark.vue") == AssetKind.MARK
    ws = open_workspace(tmp_path / "out", brief_from_dict(BRIEF))
    rows = [{"sketch": 14, "note": "طوّره", "digest": "aa", "at": "2026-11-13T09:40:49+00:00", "develop": True},
            {"rejected": True, "reason": "لا شيء منها", "digest": "aa", "at": "2026-11-13T10:00:00+00:00"},
            {"sketch": 11, "note": "", "digest": "bb", "at": "2026-11-13T14:48:03+00:00"},
            {"sketch": 11, "note": "", "rebuild": True, "reason": "ليس هذا الشعار", "digest": "bb", "at": "2026-11-13T19:04:22+00:00"}]
    designer.decisions_path(ws).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    assert designer_decisions(ws) == [
        ("aa", "revise", "s14", "طوّره", "2026-11-13T09:40:49+00:00"), ("aa", "rejected", "", "لا شيء منها", "2026-11-13T10:00:00+00:00"),
        ("bb", "approved", "s11", "", "2026-11-13T14:48:03+00:00"), ("bb", "rejected", "s11", "ليس هذا الشعار", "2026-11-13T19:04:22+00:00")]


def test_sync_all_reports_a_broken_version_and_goes_on(tmp_path, monkeypatch):
    """أول إصدار معطوب كان يُسقط `sima db sync` كله فلا يُسجَّل ما بعده."""
    from sima.web import setup

    setup()
    from sima.web.registry import service

    for name in ("a/v1", "b/v1"):
        (tmp_path / name).mkdir(parents=True)
        (tmp_path / name / "run.json").write_text("{}", encoding="utf-8")
    synced: list[str] = []

    def sync_run(root):
        if root.parent.name == "a":
            raise KeyError("project")
        synced.append(root.parent.name)

    monkeypatch.setattr(service, "sync_run", sync_run)
    monkeypatch.setattr(service, "_workspace", lambda root: (type("W", (), {"done": staticmethod(lambda _stage: False)})(), {}))
    out = service.sync_all(tmp_path)
    assert synced == ["b"] and out["runs"] == 1 and len(out["failed"]) == 1 and out["failed"][0].startswith("a/v1: KeyError")
