"""اللون على خلفيته الخافتة (قرار المالك 2026-11-14، ق4): اتجاه «أوراق» v6 اعتُمد وفيه أزواج نصية دون 4.5:1 (ليلًا لون العلامة
على خلفيته الخافتة 4.45 والنجاح والمعلومة 3.88، ونهارًا الذهبي نصًّا على خلفيته 4.35) لأن فحص سِمة لم يقس اللون إلا على
الخلفية؛ والتطبيق المستلم يضع النص على هذه الخلفيات فيردّه اختبار تباينه. الخلفيات الخافتة تُضبط حتى يبلغ نصّها عليها الحد،
والفحص يقيس الزوج، وحدود الحقول وحلقة التركيز تُقاس على السطح أيضًا."""
from __future__ import annotations

import pytest

from sima.domain.identity import PalettePolicy
from sima.services.color_system import SEMANTIC, SOFT_LIGHT, TEXT, UI, build_system, check_system, contrast_ratio, mix

D1 = {"paper": "#F7F4EE", "ink": "#1B1E23", "brand": "#7A1C3E", "accent": "#D9A441", "neutral": "#676B72",
      "success": "#2F6B4F", "warning": "#805A13", "error": "#B12F2B", "info": "#2C6187"}
D2 = {"paper": "#F4F5F2", "ink": "#16202B", "brand": "#6A1B44", "accent": "#BFA052", "neutral": "#5F6873",
      "success": "#2B6B58", "warning": "#7A5B12", "error": "#AE2E3A", "info": "#2A5F8C"}
D3 = {"paper": "#FBF3E4", "ink": "#2A1D1A", "brand": "#8E2433", "accent": "#DB943C", "neutral": "#6F655C",
      "success": "#3F6B3A", "warning": "#8A5510", "error": "#B5341F", "info": "#2F5E7D"}  # اتجاه «أوراق» v6 المعتمد
SOFT_PAIRS = (("brand_text", "brand_soft"), ("accent_text", "accent_soft"), *((k, f"{k}_soft") for k in SEMANTIC))


@pytest.mark.parametrize("colors", [D1, D2, D3], ids=["d1", "d2", "d3"])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_color_reads_as_text_on_its_own_soft_background(colors, mode):
    r = build_system(colors)[mode]
    for fg, bg in SOFT_PAIRS:
        assert contrast_ratio(r[fg], r[bg]) >= TEXT, (mode, fg, r[fg], r[bg])
    assert contrast_ratio(r["accent_text"], r["bg"]) >= TEXT  # الذهبي نصًّا يُقرأ على الخلفية نفسها أيضًا


@pytest.mark.parametrize("colors", [D1, D2, D3], ids=["d1", "d2", "d3"])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_field_borders_and_focus_ring_hold_on_the_surface_too(colors, mode):
    r = build_system(colors)[mode]
    for role in ("border_strong", "focus"):
        for bg in ("bg", "surface"):
            assert contrast_ratio(r[role], r[bg]) >= UI, (mode, role, bg, r[role], r[bg])


def test_a_soft_background_that_already_passes_is_left_as_it_was():
    """الضبط للساقط وحده: ما بلغ الحد يبقى بقيمته، فلا يتغيّر اتجاه سليم."""
    light = build_system(D3)["light"]
    assert light["brand_soft"] == mix(D3["paper"], D3["brand"], SOFT_LIGHT) == "#EED6C9"
    assert (light["success_soft"], light["error_soft"], light["info_soft"]) == ("#E3FEE0", "#FFF2EF", "#ECF7FF")
    assert (light["brand"], light["accent"], light["border_strong"], light["focus"]) == ("#8E2433", "#DB943C", "#8B8178", "#416E8D")
    dark = build_system(D3)["dark"]
    assert (dark["brand"], dark["accent"], dark["success"], dark["info"]) == ("#DC8084", "#DB943C", "#669061", "#5E89A7")  # النص كما هو


def test_checks_measure_the_soft_pairs_and_fail_a_system_below_the_bar():
    system = build_system(D3)
    kw = {"accent_informational": False, "policy": PalettePolicy.EVOLVE, "brief_palette": {k: D3[k] for k in ("paper", "ink", "brand", "accent")}}
    rep = check_system(D3, system, **kw)
    soft = [c for c in rep.checks if "على خلفيته الخافتة" in c.name]
    assert len(soft) == 2 * len(SOFT_PAIRS) and all(c.ok for c in soft) and rep.ok
    assert sum("على السطح" in c.name for c in rep.checks) >= 4  # حدود الحقول وحلقة التركيز في الوضعين
    system["dark"]["success_soft"] = "#0D3209"  # قيمة v6: النجاح عليها 3.88
    bad = check_system(D3, system, **kw)
    assert not bad.ok and any("النجاح على خلفيته الخافتة (داكن)" in c.name and not c.ok for c in bad.checks)


MARSAD = {"paper": "#F2EFE8", "ink": "#0D0C0B", "brand": "#089770", "accent": "#3EE6B0", "neutral": "#5F665F",
          "success": "#2A6D3E", "warning": "#8A5A12", "error": "#AC343B", "info": "#286694"}  # «مرصد» v2: الشعار 3.22:1


def test_brand_text_is_the_brand_itself_when_it_reads():
    """اتجاه يبلغ لونه حدّ النص لا يتغيّر فيه شيء: نص العلامة لونها، وخلفيتها الخافتة كما كانت."""
    for colors in (D1, D2, D3):
        for mode in ("light", "dark"):
            r = build_system(colors)[mode]
            assert r["brand_text"] == r["brand"]
    assert build_system(D3)["light"]["brand_soft"] == "#EED6C9"


def test_brand_below_text_bar_gets_a_darker_text_role_and_passes():
    """قرار المالك 2026-11-18 على «مرصد»: الشعار بلون العلامة كما هو، والنص والرابط بأقرب درجة أغمق من مقياسه تبلغ الحد."""
    system = build_system(MARSAD)
    light = system["light"]
    assert light["brand"] == "#089770" and contrast_ratio(light["brand"], light["bg"]) < TEXT
    assert light["brand_text"] != light["brand"] and contrast_ratio(light["brand_text"], light["bg"]) >= TEXT
    assert contrast_ratio(light["brand_text"], light["brand_soft"]) >= TEXT
    kw = {"accent_informational": False, "policy": PalettePolicy.RESPECT,
          "brief_palette": {k: MARSAD[k] for k in ("paper", "ink", "brand", "accent")}}
    rep = check_system(MARSAD, system, **kw)
    assert not [c for c in rep.checks if "لون العلامة" in c.name and not c.ok]
