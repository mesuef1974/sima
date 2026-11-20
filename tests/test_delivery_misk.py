"""ألوان تطبيق «مسك» تتبع الاتجاه المعتمد (أمر المالك 2026-11-17): رموزه في ملف واحد بـ`light-dark()` خارج المسار المعتاد،
وإصداره سُلّم قبل أن تُكتب خريطته، فيُعاد تسليمه ببطاقة تحلّ محلّ التي لم تُلتقط."""
from __future__ import annotations

import shutil
from pathlib import Path

from sima.adapters.auto_deliver import options, targets
from sima.services import adoption
from sima.services import apply_identity as roles_map
from sima.services.color_system import contrast_ratio
from sima.services.deliver import deliver, patch_tokens_css, plan_delivery

from .test_deliver import FakeTarget, _delivery_setup

TOKENS_PATH = "frontend/src/static/brand/tokens.css"
# رموز تطبيق «مسك» كما في أساس فرعه (origin/main، 2026-11-17)
MISK_TOKENS = """/* ألوان المنصة، مصدر واحد */
:root, html[data-theme] {
  --bg: light-dark(#f6f4ef, #14181a);
  --surface: light-dark(#ffffff, #1d2326);
  --ink: light-dark(#1d2327, #eceff0);
  --muted: light-dark(#5b656c, #a3adb2);
  --line: light-dark(#e0dcd2, #333b3f);
  --accent: light-dark(#0f6b5c, #5cc7b2);
  --risk: light-dark(#a23a2e, #ee9c90);
  --font-ui: "Segoe UI", "Noto Sans Arabic", Tahoma, Arial, sans-serif;
}
"""
# أدوار الاتجاه المعتمد d3 كما كانت في `out/misk/v5/package/identity/tokens/tokens.css` (حُذف الإصدار 2026-11-20 وبقي في git قبل 069af89)
ROLES_CSS = """:root{
  --misk-bg:#F5F3EE;
  --misk-surface:#F1F7F4;
  --misk-border:#CFD6D3;
  --misk-text:#17201D;
  --misk-text-muted:#5E6763;
  --misk-brand:#1E4D43;
  --misk-brand-strong:#013128;
  --misk-error:#76021A;
}
:root[data-theme="dark"]{
  --misk-bg:#141A17;
  --misk-surface:#242B28;
  --misk-border:#4C5551;
  --misk-text:#F1F7F4;
  --misk-text-muted:#B5BDB9;
  --misk-brand:#668D83;
  --misk-brand-strong:#84A79E;
  --misk-error:#FF9A99;
}
"""
ROLES = roles_map.identity_roles(ROLES_CSS, "misk")
MISK = targets()["misk"]
RULES = roles_map.parse_rules(MISK["apply_identity"])
# ما يقرؤه المستعمل في واجهة «مسك» (styles/base.css): نص على الأرضية والسطح، والزر الأساسي أرضيةٌ على لون التمييز
PAIRS = (("ink", "bg"), ("ink", "surface"), ("muted", "bg"), ("muted", "surface"), ("accent", "bg"), ("accent", "surface"),
         ("bg", "accent"), ("risk", "bg"), ("risk", "surface"))


def _themes(css: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    for line in css.splitlines():
        for m in roles_map.line_decls(line):
            pair = roles_map.light_dark(m.group(4))
            if pair:
                out["light"][m.group(2)], out["dark"][m.group(2)] = pair
    return out


def test_each_value_of_a_light_dark_declaration_takes_the_role_of_its_mode():
    applied = roles_map.apply_roles(MISK_TOKENS, RULES, ROLES, 5)
    assert "--bg: light-dark(#f5f3ee, #141a17);" in applied.css
    assert "--accent: light-dark(#1e4d43, #84a79e);" in applied.css  # ليلًا brand-strong لا brand
    assert "--font-ui:" in applied.css and "html[data-theme]" in applied.css
    assert len(applied.changes) == 14 and not applied.unmapped
    assert roles_map.Change("risk", "dark", "#ee9c90", "#ff9a99") in applied.changes
    assert roles_map.apply_roles(applied.css, RULES, ROLES, 5).css == applied.css


def test_a_mode_without_a_role_keeps_the_value_of_the_app():
    rules = roles_map.parse_rules({"accent": {"light": "brand"}})
    assert "--accent: light-dark(#1e4d43, #5cc7b2);" in roles_map.apply_roles(MISK_TOKENS, rules, ROLES, 5).css


def test_the_misk_map_passes_the_contrast_pairs_of_the_app_in_both_modes():
    themes = _themes(roles_map.apply_roles(MISK_TOKENS, RULES, ROLES, 5).css)
    for mode, theme in themes.items():
        for fg, bg in PAIRS:
            assert contrast_ratio(theme[fg], theme[bg]) >= 4.5, (mode, fg, theme[fg], bg, theme[bg])


def test_the_mark_ink_is_written_as_one_light_dark_declaration_in_such_a_file():
    out = patch_tokens_css(MISK_TOKENS, "#1E4D43", None)
    assert "--color-mark-ink: light-dark(#1e4d43, #ffffff);" in out and "--color-mark-accent" not in out
    assert patch_tokens_css(out, "#1E4D43", None) == out


def test_color_parity_reads_the_light_value_of_a_light_dark_declaration():
    css = roles_map.apply_roles(MISK_TOKENS, RULES, ROLES, 5).css
    assert adoption._first_value(css, "accent") == "#1e4d43"


# رموز «مسك» بعد سماته العشر (origin/main، 2026-11-20): النهار يحيل إلى متغير السمة، والليل لون خام أو متغير
THEMED_TOKENS = """:root {
  --day-color: #68112f;
  --day-bg: #f8f2e9;
  --day-ink: #35242c;
  --night-bg: #1f1518;
}
:root, html[data-theme] {
  --bg: light-dark(var(--day-bg), var(--night-bg));
  --ink: light-dark(var(--day-ink), #fdf2f5);
  --risk: light-dark(#76021a, #ff9a99);
}

:root {
  --color-mark-ink: light-dark(var(--day-color), #ffffff);
  --color-ink: var(--ink);
}
"""


def test_a_value_that_refers_to_a_theme_variable_is_kept():
    # بطاقة v9 الأولى كتبت فوقها ألوانًا نهارية خامًا فأسقطت ليل السمات كلها (ردّ جلسة «مسك» 2026-11-20)
    rules = roles_map.parse_rules({"bg": {"light": "bg", "dark": "bg"}, "ink": {"light": "text", "dark": "text"},
                                   "risk": {"light": "error", "dark": "error"}})
    applied = roles_map.apply_roles(THEMED_TOKENS, rules, ROLES, 9)
    assert "--bg: light-dark(var(--day-bg), var(--night-bg));" in applied.css
    assert "--ink: light-dark(var(--day-ink), #f1f7f4);" in applied.css  # الليل الخام يأخذ دوره
    assert "--risk: light-dark(#76021a, #ff9a99);" in applied.css
    assert roles_map.Change("ink", "dark", "#fdf2f5", "#f1f7f4") in applied.changes
    assert not [c for c in applied.changes if c.mode == "light" and c.var in ("bg", "ink")]
    assert roles_map.apply_roles(applied.css, rules, ROLES, 9).css == applied.css


def test_the_mark_ink_keeps_its_theme_reference():
    out = patch_tokens_css(THEMED_TOKENS, "#68112F", None)
    assert "--color-mark-ink: light-dark(var(--day-color), #ffffff);" in out and "--color-mark-accent" not in out
    assert patch_tokens_css(out, "#68112F", None) == out


def test_color_parity_follows_a_theme_reference_to_its_value():
    assert adoption._first_value(THEMED_TOKENS, "ink") == "#35242c"
    assert adoption._first_value(THEMED_TOKENS, "bg") == "#f8f2e9"


def test_a_file_that_only_names_the_accent_variable_does_not_use_it(tmp_path):
    from sima.services.deliver import DirFiles, accent_in_use
    pkg, repo = tmp_path / "pkg", tmp_path / "repo"
    pkg.mkdir()
    (pkg / "BrandMark.vue").write_text('<path fill="var(--color-mark-ink)"/>', encoding="utf-8")
    src = repo / "frontend" / "src" / "styles"
    src.mkdir(parents=True)
    (src / "designTokens.test.ts").write_text('for (const old of ["--color-mark-accent"]) {}', encoding="utf-8")
    assert accent_in_use(pkg, DirFiles(repo)) == (False, [])
    (src / "x.css").write_text(".a { color: var(--color-mark-accent); }", encoding="utf-8")
    assert accent_in_use(pkg, DirFiles(repo)) == (False, ["frontend/src/styles/x.css"])


def _misk_repo(repo: Path) -> None:
    shutil.rmtree(repo / "frontend" / "src" / "styles")
    target = repo / TOKENS_PATH
    target.parent.mkdir(parents=True)
    target.write_text(MISK_TOKENS, encoding="utf-8")


def test_the_target_names_its_tokens_file_and_the_plan_writes_it(tmp_path):
    b, ws, repo = _delivery_setup(tmp_path)
    _misk_repo(repo)
    opts = options(MISK)
    assert opts["tokens_path"] == TOKENS_PATH
    plan = plan_delivery(b, ws.package_dir, repo, 5, "a1", tokens_path=opts["tokens_path"])
    assert TOKENS_PATH in plan.paths and "frontend/src/styles/tokens.css" not in plan.paths
    assert any(TOKENS_PATH in n for n in plan.notes)


class LedgerTarget(FakeTarget):
    """دفتر وهمي: كل بطاقة جديدة بمعرّف، و`supersede` يلغي ما لم يُلتقط ويعيد حالته قبل ذلك."""

    def __init__(self, root: Path, state: str = "ready"):
        super().__init__(root)
        self.state, self.cancelled, self.count = state, [], 0

    def new_card(self, title, body, success):
        self.count += 1
        self.body = body
        return f"card-{self.count}"

    def supersede(self, card_id, note):
        if self.state in ("created", "ready"):
            self.cancelled.append(card_id)
        return self.state


def test_redelivery_opens_a_new_card_and_cancels_the_unclaimed_one(tmp_path):
    b, ws, repo = _delivery_setup(tmp_path)
    target = LedgerTarget(repo)
    first = deliver(ws, b, target, repo)
    assert deliver(ws, b, target, repo).card_id == first.card_id == "card-1" and target.count == 1  # بلا أمر: لا بطاقة ثانية
    again = deliver(ws, b, target, repo, redeliver=True)
    assert again.card_id == "card-2" and target.cancelled == ["card-1"]
    assert "محلّ البطاقة card-1" in target.body
    marker = ws.read_marker("deliver")
    assert marker["card_id"] == "card-2" and [p["card_id"] for p in marker["previous"]] == ["card-1"]


def test_redelivery_leaves_a_claimed_card_alone_and_says_its_state(tmp_path):
    b, ws, repo = _delivery_setup(tmp_path)
    target = LedgerTarget(repo, state="merged")
    deliver(ws, b, target, repo)
    again = deliver(ws, b, target, repo, redeliver=True)
    assert again.card_id == "card-2" and not target.cancelled
    assert "card-1" in target.body and "merged" in target.body
