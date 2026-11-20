"""ليل الهوية من اتجاه معتمد آخر (قرار المالك 2026-11-17 على «مسك»: نهار عودي وليل v5): `identity.night` يبقي نهار اتجاه
الإصدار ومقاييسه ويأخذ أدوار الوضع الداكن كلها من ألوان الاتجاه المسمّى. لا اتصال شبكي ولا نموذج."""
from __future__ import annotations

import pytest

from sima import config
from sima.domain import brief_from_dict
from sima.domain.identity import Direction, TypeChoice
from sima.services.color_system import build_system, with_night
from sima.services.identity_flow import IdentityFlow

from .test_domain_ledger_workspace import BRIEF

DAY = {"paper": "#F8F2E9", "ink": "#35242C", "brand": "#68112F", "accent": "#D6B68C", "neutral": "#6C5C61",
       "success": "#3E6954", "warning": "#8A5A14", "error": "#B0363F", "info": "#2D6387"}
NIGHT = {"paper": "#F5F3EE", "ink": "#17201D", "brand": "#1E4D43", "accent": "#C4785A", "neutral": "#5E6763",
         "success": "#3B7A3A", "warning": "#8A5A14", "error": "#B0363F", "info": "#2D6387"}
SPEC = {"name": "v5 d3 «مسك الليل»", "colors": NIGHT}


def _brief(**identity):
    return brief_from_dict({**BRIEF, "identity": {"scope": "core", **identity}})


def test_night_parses_and_enters_the_key():
    plain, declared = _brief(), _brief(night=SPEC)
    assert plain.identity.night is None and declared.identity.night == SPEC
    assert plain.hash() != declared.hash()  # الإعلان مدخل للمفتاح: إصدار جديد
    assert brief_from_dict({**BRIEF, "identity": {"scope": "core"}}).hash() == plain.hash()  # الغياب لا يغيّر
    assert _brief(night={**SPEC, "colors": {**NIGHT, "brand": "#1e4d43"}}).identity.night == SPEC  # الحالة لا تغيّر
    for bad in ("v5", {"name": "x"}, {"colors": NIGHT}, {"name": " ", "colors": NIGHT}, {**SPEC, "x": 1},
                {"name": "x", "colors": {k: v for k, v in NIGHT.items() if k != "info"}},
                {"name": "x", "colors": {**NIGHT, "extra": "#000000"}},
                {"name": "x", "colors": {**NIGHT, "brand": "green"}}):
        with pytest.raises(ValueError, match=r"identity\.night"):
            _brief(night=bad)


def test_night_roles_come_from_the_named_direction_and_day_stays():
    day, night = build_system(DAY), build_system(NIGHT)
    mixed = with_night(day, NIGHT)
    assert mixed["dark"] == night["dark"] and mixed["dark"] != day["dark"]
    assert mixed["light"] == day["light"] and mixed["scales"] == day["scales"]
    assert day["dark"] == build_system(DAY)["dark"]  # النظام الأصلي لا يُمسّ


def test_the_flow_checks_the_borrowed_night_and_says_so():
    d = Direction("d1", "شريط الإهداء", "", DAY, False, TypeChoice("IBMPlexSansArabic-Medium.ttf", 500),
                  TypeChoice("IBMPlexSansArabic-Regular.ttf", 400), "latn", "", "")
    flow = IdentityFlow(None, None, config.FONTS_DIR)  # type: ignore[arg-type]  # evaluate لا يصيّر
    system, rep, _ = flow.evaluate(_brief(palette_policy="new", night=SPEC), d)
    assert system["dark"] == build_system(NIGHT)["dark"] and system["light"]["brand"] == "#68112F"
    note = [c for c in rep.checks if c.name == "ليل الهوية من اتجاه معتمد آخر"]
    assert len(note) == 1 and "مسك الليل" in note[0].detail and not note[0].blocking
    plain, plain_rep, _ = flow.evaluate(_brief(palette_policy="new"), d)
    assert plain["dark"] == build_system(DAY)["dark"] and not [c for c in plain_rep.checks if "ليل الهوية" in c.name]
