"""تسليم الهوية إلى تطبيق Django (قرار المالك 2026-11-15، منصة المدرسة): مرحلة الألوان وحدها على ملفات static/css.

يثبّت ثلاثة أمور: الكتلة الليلية `html.dark` تُقرأ ليلية، والسطر ذو التعريفين يُعالَج كله، وخطة Django تكتب الأنماط المسمّاة
وحدها بلا شعار ولا أيقونات ولا قوالب، وتوقف التسليم باسم الناقص."""
from __future__ import annotations

from pathlib import Path

import pytest

from sima.domain import brief_from_dict
from sima.services import apply_identity as roles_map
from sima.services.deliver import DirFiles
from sima.services.deliver_django import card_text_django, plan_delivery_django

from .test_domain_ledger_workspace import BRIEF

ROLES_CSS = """:root{
  --shahaniya-bg:#FFF8F1;
  --shahaniya-surface:#F9F3F7;
  --shahaniya-text:#24202A;
  --shahaniya-brand:#8A1538;
}
:root[data-theme="dark"]{
  --shahaniya-bg:#1B171A;
  --shahaniya-surface:#2C272B;
  --shahaniya-text:#F9F3F7;
  --shahaniya-brand:#DD7E8D;
}
"""
APP_CSS = """:root {
  --page-bg:   #d7dee8;
  --surface:   #ffffff;
  --status-warning-bg:    #fef3c7;  --status-warning-border: #f59e0b;
  --text-primary: #111827;
}
html.dark {
  --page-bg:   #0f172a;
  --surface:   #1e293b;
  --status-warning-bg:    #3a2a08;  --status-warning-border: #92400e;
  --text-primary: #f1f5f9;
}
html.dark body { color: var(--text-primary); }
"""
MAP = {"page-bg": "bg", "surface": "surface", "text-primary": "text"}
RULES = roles_map.parse_rules(MAP)
ROLES = roles_map.identity_roles(ROLES_CSS, "shahaniya")


def test_html_dark_block_is_read_as_dark():
    res = roles_map.apply_roles(APP_CSS, RULES, ROLES, 4)
    got = {(c.var, c.mode): c.new for c in res.changes}
    assert got[("page-bg", "light")] == "#fff8f1"
    assert got[("page-bg", "dark")] == "#1b171a"
    assert got[("text-primary", "dark")] == "#f9f3f7"


def test_two_declarations_on_one_line_are_both_handled():
    rules = roles_map.parse_rules({**MAP, "status-warning-bg": "surface", "status-warning-border": "text"})
    res = roles_map.apply_roles(APP_CSS, rules, ROLES, 4)
    assert "--status-warning-bg:    #f9f3f7;  --status-warning-border: #24202a;" in res.css
    assert "--status-warning-bg:    #2c272b;  --status-warning-border: #f9f3f7;" in res.css


def test_second_declaration_alone_is_mapped_and_first_is_kept():
    rules = roles_map.parse_rules({"status-warning-border": "text"})
    res = roles_map.apply_roles(APP_CSS, rules, ROLES, 4)
    assert "--status-warning-bg:    #fef3c7;  --status-warning-border: #24202a;" in res.css
    assert "--status-warning-bg" in "".join(res.unmapped)


def test_apply_roles_is_idempotent_on_django_styles():
    once = roles_map.apply_roles(APP_CSS, RULES, ROLES, 4).css
    assert roles_map.apply_roles(once, RULES, ROLES, 4).changes == ()


def _package(tmp_path: Path) -> Path:
    tokens = tmp_path / "pkg" / "identity" / "tokens"
    tokens.mkdir(parents=True)
    (tokens / "tokens.css").write_text(ROLES_CSS, encoding="utf-8")
    return tmp_path / "pkg"


def _repo(tmp_path: Path) -> Path:
    css = tmp_path / "repo" / "static" / "css" / "custom"
    css.mkdir(parents=True)
    (css / "10-foundation.css").write_text(APP_CSS, encoding="utf-8")
    (tmp_path / "repo" / "templates").mkdir()
    (tmp_path / "repo" / "templates" / "base.html").write_text("<html></html>", encoding="utf-8")
    return tmp_path / "repo"


def test_plan_writes_only_the_named_styles(tmp_path):
    brief = brief_from_dict({**BRIEF, "project": "shahaniya"})
    repo = _repo(tmp_path)
    plan = plan_delivery_django(brief, _package(tmp_path), DirFiles(repo), 4, "a1", ["static/css/custom/10-foundation.css"], MAP)
    assert plan.paths == ("static/css/custom/10-foundation.css",)
    text = plan.writes[0].content.decode("utf-8")
    assert "--page-bg:   #fff8f1;" in text and "--page-bg:   #1b171a;" in text
    assert any("لا شعار ولا أيقونات" in n for n in plan.notes)
    title, body, success = card_text_django(brief, plan)
    assert "مرحلة الألوان" in title and "static/css/custom/10-foundation.css" in body and success


@pytest.mark.parametrize("styles, mapping, fragment", [
    ([], MAP, "styles:"),
    (["static/css/custom/10-foundation.css"], None, "apply_identity"),
    (["static/css/custom/missing.css"], MAP, "missing.css"),
])
def test_plan_stops_naming_what_is_missing(tmp_path, styles, mapping, fragment):
    brief = brief_from_dict({**BRIEF, "project": "shahaniya"})
    with pytest.raises(RuntimeError, match=fragment):
        plan_delivery_django(brief, _package(tmp_path), DirFiles(_repo(tmp_path)), 4, "a1", styles, mapping)


def test_plan_stops_without_full_identity(tmp_path):
    brief = brief_from_dict({**BRIEF, "project": "shahaniya"})
    with pytest.raises(RuntimeError, match="هوية كاملة"):
        plan_delivery_django(brief, tmp_path, DirFiles(_repo(tmp_path)), 4, "a1", ["static/css/custom/10-foundation.css"], MAP)
