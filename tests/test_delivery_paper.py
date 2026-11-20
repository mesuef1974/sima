"""الورقة المطبوعة تتبع الاتجاه المعتمد (طلب المالك 2026-11-14 بعد دمج «أوراق» v7): تسليم v7 غيّر رموز التطبيق وحدها فسقطت ستة
اختبارات طباعة في «أوراق» وأصلحتها جلستها بيدها. هنا `apply_paper` يطبّق خريطة apply_identity على print.css بقيم النهار، ويتبع
اللونَ الثابتَ المتغيّرَ، ويطبّق أدوارًا على ثوابت `ooxml.py`. الأساس نسخ حقيقية من v6 في «أوراق» وهوية v7 المعتمدة."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from sima.domain import brief_from_dict
from sima.services import apply_identity as roles_map
from sima.services.deliver import card_text, plan_delivery

from .test_deliver import _package, _repo
from .test_delivery_stage6 import APP, IDENTITY, MAP
from .test_domain_ledger_workspace import BRIEF

DATA = Path(__file__).parent / "data"
TARGET = yaml.safe_load((Path(__file__).parents[1] / "deliver_targets.yaml").read_text(encoding="utf-8"))["math_papers"]
RULES = roles_map.parse_rules(TARGET["apply_identity"])
ROLES = roles_map.identity_roles((DATA / "awraq_identity_v7.css").read_text(encoding="utf-8"), "math_papers")
PAPER = roles_map.parse_paper(TARGET["apply_paper"])
V6_CSS = (DATA / "awraq_print_v6.css").read_text(encoding="utf-8")
V6_CONSTS = (DATA / "awraq_ooxml_constants_v6.txt").read_text(encoding="utf-8")


def _sheet(css: str) -> dict[str, str]:
    start = css.index("\n.sheet {")
    block = css[start: css.index("\n}", start)]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"--([a-z0-9-]+):\s*([^;]+);", block)}


def test_v6_sheet_variables_become_the_v7_values_as_jalsat_awraq_set_them_by_hand():
    """القيم المتوقعة هي ما كتبته جلسة «أوراق» بيدها في إيداع المطابقة (فرق v6 إلى v7 في print.css)."""
    res = roles_map.apply_paper_css(V6_CSS, RULES, ROLES, 7, PAPER.skip)
    sheet = _sheet(res.css)
    expected = {"color-ink": "#2a1d1a", "color-ink-soft": "#6f655c", "color-line": "#dbd3cb", "color-line-strong": "#8b8178",
                "color-brand-strong": "#740a21", "color-brand-soft": "#eed6c9", "color-sand": "#935a00", "color-sand-soft": "#f7e4ca",
                "color-accent": "#db943c", "color-danger": "#740f00", "color-success": "#3f6b3a", "color-success-soft": "#e3fee0",
                "color-info": "#2f5e7d", "color-info-soft": "#ecf7ff", "color-level-k": "#3f6b3a", "color-level-a": "#2f5e7d",
                "color-level-r-soft": "#eed6c9", "color-focus": "#416e8d"}
    for var, value in expected.items():
        assert sheet[var] == value, var


def test_the_paper_stays_white_and_light_whatever_the_dark_roles_say():
    """الورقة المعروضة بيضاء بقصد (`color-sheet: {dark: surface}`) ولا يتسرب إليها دور ليلي."""
    res = roles_map.apply_paper_css(V6_CSS, RULES, ROLES, 7, PAPER.skip)
    sheet = _sheet(res.css)
    assert sheet["color-sheet"] == "#ffffff" and sheet["color-field"] == "#ffffff"
    # ورق الاتجاه وسطوحه لا تلوّن الورقة المطبوعة: skip في خريطة الهدف
    assert sheet["color-paper"] == "#ffffff" and sheet["color-surface"] == "#ffffff" and sheet["color-surface-sunken"] == "#f4eef0"
    assert "#1d1711" not in res.css.lower() and "#1d" not in "".join(c.new for c in res.changes)


def test_a_hard_coded_color_follows_the_variable_that_held_it_and_stray_ones_are_listed():
    """@page يحمل في v6 `#4c535c` و`#14171c` (حبر الورقة) ثابتين: يتبعان متغيرهما إن تغيّر، وما لا يطابق متغيرًا يُسرد ولا يُمسّ."""
    res = roles_map.apply_paper_css(V6_CSS, RULES, ROLES, 7, PAPER.skip)
    page = res.css[: res.css.index(".sheet {")]
    assert "color: #6f655c;" in page and "color: #2a1d1a;" in page  # كانا #4c535c و#14171c
    assert "#4c535c" not in page and "#14171c" not in page
    assert {c.old for c in res.literals} >= {"#4c535c", "#14171c"}
    assert "#8e2433" not in res.stray  # لون العلامة يطابق متغير --color-brand فليس شاردًا


def test_a_stale_hard_coded_color_with_no_changed_variable_is_reported_not_guessed():
    """حال «أوراق» بعد مطابقتها اليدوية: متغيراتها v7 و@page ما زال #4c535c: لا متغير تغيّر فلا تبديل، لكنه يُسرد في البطاقة."""
    synced = roles_map.apply_paper_css(V6_CSS, RULES, ROLES, 7, PAPER.skip).css
    stale = synced.replace("color: #6f655c;", "color: #4c535c;", 1)
    assert stale != synced
    res = roles_map.apply_paper_css(stale, RULES, ROLES, 7, PAPER.skip)
    assert res.css == stale and res.changes == () and "#4c535c" in res.stray
    assert "`#4c535c`" in roles_map.paper_note("print.css", res.changes, res.literals, res.stray)


def test_applying_it_to_its_own_output_changes_nothing():
    once = roles_map.apply_paper_css(V6_CSS, RULES, ROLES, 7, PAPER.skip)
    again = roles_map.apply_paper_css(once.css, RULES, ROLES, 7, PAPER.skip)
    assert again.css == once.css and again.changes == () and again.literals == ()


def test_word_constants_take_the_light_roles_of_the_identity():
    table = dict(dict(PAPER.constants)["apps/papers/word/ooxml.py"])
    text, changes = roles_map.apply_constants(V6_CONSTS, tuple(table.items()), ROLES["light"])
    for name, value in {"SOFT": "6F655C", "RULE": "8B8178", "LINE": "DBD3CB", "BRAND_STRONG": "740A21", "SHADE": "EED6C9", "ACCENT": "DB943C"}.items():
        assert f'{name} = "{value}"' in text, name
    assert 'BRAND = "8E2433"' in text and 'INK = "000000"' in text and 'WHITE = "FFFFFF"' in text  # خارج الخريطة
    assert "# العنابي الخفيف" in text  # التعليق بعد القيمة يبقى
    assert {c.var for c in changes} == set(table)
    assert roles_map.apply_constants(text, tuple(table.items()), ROLES["light"])[1] == ()


def test_a_broken_paper_map_stops_the_delivery_with_its_name():
    with pytest.raises(ValueError, match="NOPE"):
        roles_map.apply_constants(V6_CONSTS, (("NOPE", "border"),), ROLES["light"])
    with pytest.raises(ValueError, match="no-such-role"):
        roles_map.apply_constants(V6_CONSTS, (("SOFT", "no-such-role"),), ROLES["light"])
    with pytest.raises(ValueError, match="صيغة"):
        roles_map.parse_paper({"cs": []})
    with pytest.raises(ValueError, match="skip"):
        roles_map.parse_paper({"skip": "color-paper"})
    with pytest.raises(ValueError, match="ثوابت"):
        roles_map.parse_paper({"constants": {"a.py": {}}})


def test_the_real_target_map_covers_every_word_constant_that_the_awraq_session_pinned():
    """الثوابت الستة التي طابقتها جلسة «أوراق» بيدها مذكورة كلها في خريطة الهدف الفعلية."""
    names = {n for n, _ in dict(PAPER.constants)["apps/papers/word/ooxml.py"]}
    assert names == {"SOFT", "RULE", "LINE", "BRAND_STRONG", "SHADE", "ACCENT"}
    assert PAPER.css == ("frontend/src/styles/print.css",)
    assert set(PAPER.skip) == {"color-paper", "color-surface", "color-surface-sunken", "color-sheet", "color-field"}


# ---------- التسليم الكامل ----------
PRINT = """@page {
  @bottom-center { content: var(--print-footer); color: #14171c; }
}
.sheet {
  --color-ink: #14171c;
  --color-brand: #8e2433;
  --color-mark-ink: #8e2433;
}
"""
CONSTS = 'INK = "000000"\nSOFT = "4C535C"\nBRAND = "8E2433"\n'
PAPER_MAP = {"css": ["frontend/src/styles/print.css"], "constants": {"apps/word/ooxml.py": {"SOFT": "text"}}}


def _delivery_repo(tmp_path):
    repo = _repo(tmp_path)
    (repo / "frontend" / "src" / "styles" / "tokens.css").write_text(APP, encoding="utf-8")
    (repo / "frontend" / "src" / "styles" / "print.css").write_text(PRINT, encoding="utf-8")
    (repo / "apps" / "word").mkdir(parents=True)
    (repo / "apps" / "word" / "ooxml.py").write_text(CONSTS, encoding="utf-8")
    return repo


def test_a_delivery_writes_the_paper_files_and_the_card_lists_what_changed(tmp_path):
    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _delivery_repo(tmp_path)
    (pkg / "identity" / "tokens").mkdir(parents=True)
    (pkg / "identity" / "tokens" / "tokens.css").write_text(IDENTITY.replace("--p-", f"--{b.project}-"), encoding="utf-8")
    plan = plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP, apply_paper=PAPER_MAP)
    out = {w.path: w.content.decode("utf-8") for w in plan.writes}
    assert "--color-ink: #2a1d1a;" in out["frontend/src/styles/print.css"] and "color: #2a1d1a; }" in out["frontend/src/styles/print.css"]
    assert 'SOFT = "2A1D1A"' in out["apps/word/ooxml.py"] and 'INK = "000000"' in out["apps/word/ooxml.py"]
    _, body, _ = card_text(b, plan)
    assert "print.css: طُبّق الاتجاه المعتمد على ألوان الورق" in body and "apps/word/ooxml.py: طُبّق الاتجاه المعتمد" in body
    assert "`SOFT`: 4C535C صار 2A1D1A" in body
    # بلا apply_paper لا يُمسّ شيء من الورق غير ما كان
    plain = {w.path for w in plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP).writes}
    assert "apps/word/ooxml.py" not in plain


def test_without_a_full_identity_the_paper_map_is_reported_and_nothing_is_written(tmp_path):
    b = brief_from_dict(BRIEF)
    pkg, repo = _package(tmp_path), _delivery_repo(tmp_path)
    plan = plan_delivery(b, pkg, repo, 7, "a1", palette=("#7A1C3E", "#D9A441"), apply_identity=MAP, apply_paper=PAPER_MAP)
    assert "apps/word/ooxml.py" not in {w.path for w in plan.writes}
    assert any("apply_paper لم تُطبَّق" in n for n in plan.notes)
