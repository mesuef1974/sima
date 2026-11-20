"""الهوية الكاملة: نظام اللون وفحوصه، والتشكيل ثنائي الاتجاه، وبروتوكول ملفات النموذج، وبوابات المالك المربوطة بالمحتوى."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sima.config import ROOT
from sima.domain.brief import load_brief
from sima.domain.identity import Gate, PalettePolicy
from sima.domain.run import RunKey
from sima.services.color_system import ROLES, base_step, build_system, check_system, contrast_ratio, hex_to_oklch, mix, ramp
from sima.services.compose import visual_runs
from sima.services.design_tokens import css, dtcg
from sima.services.identity_protocol import digest, icon_problems, ledger, read_strategy, strategy_path, svg_safety
from sima.services.inbox import InboxError, identity_decide, owner_inbox
from sima.services.workspace import Workspace

AWRAQ = {"paper": "#F7F4EE", "ink": "#1B1E23", "brand": "#7A1C3E", "accent": "#D9A441", "neutral": "#6E6A63",
         "success": "#2F7A4D", "warning": "#B26B00", "error": "#B3261E", "info": "#2C5D8C"}
BRIEF_PAL = {"paper": "#F7F4EE", "ink": "#1B1E23", "brand": "#7A1C3E", "accent": "#D9A441"}


def test_ramp_keeps_base_at_its_step():
    r = ramp("#7A1C3E")
    assert r[base_step("#7A1C3E")] == "#7A1C3E"
    assert len(r) == 11
    ls = [hex_to_oklch(r[s])[0] for s in sorted(r)]
    assert ls == sorted(ls, reverse=True)  # 50 أفتح من 950


def test_system_roles_pass_contrast_in_both_modes():
    s = build_system(AWRAQ)
    for mode in ("light", "dark"):
        r = s[mode]
        assert contrast_ratio(r["text"], r["bg"]) >= 4.5
        assert contrast_ratio(r["text_muted"], r["bg"]) >= 4.5
        assert contrast_ratio(r["brand"], r["bg"]) >= 4.5
        assert contrast_ratio(r["border_strong"], r["bg"]) >= 3
    rep = check_system(AWRAQ, s, accent_informational=False, policy=PalettePolicy.EVOLVE, brief_palette=BRIEF_PAL)
    assert rep.ok, rep.failures


def test_soft_roles_are_mixed_into_paper_not_taken_from_ramp():
    s = build_system(AWRAQ)
    soft = s["light"]["brand_soft"]
    assert soft == mix(AWRAQ["paper"], AWRAQ["brand"], 0.14)
    assert hex_to_oklch(soft)[1] < hex_to_oklch(ramp(AWRAQ["brand"])[100])[1]  # أقل تشبعًا من الوردي
    assert mix("#FFFFFF", "#000000", 0) == "#FFFFFF" and mix("#FFFFFF", "#000000", 1) == "#000000"


def test_evolve_policy_rejects_hue_drift():
    c = {**AWRAQ, "brand": "#1C4A7A"}  # أزرق بدل العنابي
    rep = check_system(c, build_system(c), accent_informational=False, policy=PalettePolicy.EVOLVE, brief_palette=BRIEF_PAL)
    assert not rep.ok and any("brand" in f for f in rep.failures)


def test_respect_policy_requires_exact_colors():
    c = {**AWRAQ, "accent": "#D9A442"}
    rep = check_system(c, build_system(c), accent_informational=False, policy=PalettePolicy.RESPECT, brief_palette=BRIEF_PAL)
    assert not rep.ok


def test_visual_runs_reverses_numbers_inside_arabic_only():
    assert visual_runs("ولّد ١٢ مسألة") == "ولّد ٢١ مسألة"  # تُعكس قبل التشكيل RTL فتظهر ١٢
    assert visual_runs("Reem Kufi 700 للعناوين").startswith("007 ifuK meeR")
    assert visual_runs("2026") == "2026"


def test_tokens_have_dark_mode_and_dtcg_types():
    s = build_system(AWRAQ)
    fonts = {"heading": {"family": "Reem Kufi", "file": "ReemKufi[wght].ttf", "weight": 700},
             "body": {"family": "IBM Plex Sans Arabic", "file": "IBMPlexSansArabic-Regular.ttf", "weight": 400}}
    out = css("awraq", s, fonts, 4, "arab")
    assert "--awraq-brand:#7A1C3E;" in out and "prefers-color-scheme:dark" in out and ':root[data-theme="dark"]' in out
    doc = json.loads(dtcg("awraq", s, fonts, 4))
    assert doc["role"]["light"]["brand"] == {"$type": "color", "$value": "#7A1C3E"}


def test_svg_safety_and_icon_rules():
    assert svg_safety('<svg xmlns="http://www.w3.org/2000/svg"><text>x</text></svg>')
    assert svg_safety('<svg xmlns="http://www.w3.org/2000/svg"><linearGradient id="g"/></svg>')
    good = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v16H4z"/></svg>')
    assert icon_problems(good, 1.75) == []
    assert icon_problems(good.replace('stroke-width="1.75"', 'stroke-width="2"'), 1.75)
    assert icon_problems(good.replace('fill="none"', 'fill="#7A1C3E"'), 1.75)


def test_icons_are_decorative_from_the_source():
    from sima.services.identity_protocol import decorative
    titled = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"><title>طلب</title>'
              '<desc>ورقة</desc><path d="M6 2h12"/></svg>')
    out = decorative(titled)
    assert "<title" not in out and "<desc" not in out and "طلب" not in out
    assert out.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">')
    assert '<path d="M6 2h12"/>' in out and decorative(out) == out
    assert icon_problems(out, 1.75) == icon_problems(titled, 1.75)


# ---------- البوابات ----------
STRATEGY = """positioning: لمعلمي الرياضيات أداة تولّد أوراقًا أصلية
promise: ورقة صحيحة من أول مرة
personality:
  - {trait: دقيق, means: مصطلحات المنهج, not: متحذلق}
  - {trait: هادئ, means: واجهة قليلة الكلام, not: باهت}
  - {trait: صانع, means: يولّد الجديد, not: استعراضي}
voice:
  do: [نخاطب المعلم زميلًا, نقول ما سيحدث, نشرح الخطأ بسببه]
  dont: [لا نبالغ, لا عامية, لا نلوم]
  samples: {headline: درسك اليوم, button: ولّد الورقة, error: تعذّر التوليد, empty_state: لا أوراق بعد}
tagline: ورقة أصلية لكل درس
imagery: الورقة المطبوعة بطلًا
"""


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    v = tmp_path / "proj" / "v2"
    (v / "work" / "identity").mkdir(parents=True)
    (v / "run.json").write_text(json.dumps({"project": "proj", "key": "abc123-s1", "brief_hash": "abc123", "seed": 1, "version": 2,
                                            "brief_source": "briefs/math_papers.yaml", "closed": False}), encoding="utf-8")
    return Workspace(root=v, key=RunKey(project="proj", brief_hash="abc123", seed=1), version=2)


def test_strategy_parses_and_validates(ws):
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    s, problems = read_strategy(ws)
    assert s is not None and not problems and len(s.personality) == 3
    strategy_path(ws).write_text(STRATEGY.replace("tagline: ورقة أصلية لكل درس", "tagline: " + "ك" * 60), encoding="utf-8")
    s, problems = read_strategy(ws)
    assert s is None and problems


def test_ledger_binds_decision_to_content_digest(ws):
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    dg = digest([strategy_path(ws)])
    led = ledger(ws)
    led.record(Gate.STRATEGY, dg, "approved")
    assert led.latest(Gate.STRATEGY, dg).verdict == "approved"
    strategy_path(ws).write_text(STRATEGY + "\n# تعديل\n", encoding="utf-8")
    assert led.latest(Gate.STRATEGY, digest([strategy_path(ws)])) is None  # المحتوى تغيّر: يعود القرار للمالك


def test_inbox_strategy_gate_and_stale_digest(ws):
    out = ws.root.parent.parent
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    [item] = owner_inbox(out)
    assert item["kind"] == "identity" and item["gate"] == "strategy" and item["strategy"]["tagline"] == "ورقة أصلية لكل درس"
    assert "_ledger" not in item
    with pytest.raises(InboxError):
        identity_decide(out, "proj", 2, "abc123-s1", "strategy", "0" * 16, "approved", "", "")
    with pytest.raises(InboxError):
        identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "revise", "", "قصير"[:1])
    msg = identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "", "")
    assert "المنصة الاستراتيجية" in msg
    assert owner_inbox(out) == []  # قُرّر؛ لا شيء ينتظر حتى يتقدّم الخط


def test_brief_identity_block_and_stable_hash_without_it():
    # الموجز الحي: v8 على مسار المصمّم الخارجي يرث علامة v7 (شعار v4 كما هو) ويقفلها بكلمة من خط الاتجاه (قرار المالك 2026-11-13)،
    # وبثلاثة اتجاهات يختار منها (قراره 2026-11-14)
    now = load_brief(ROOT / "briefs" / "math_papers.yaml")
    assert now.identity.full and now.identity.palette_policy is PalettePolicy.EVOLVE
    assert now.identity.designer == "external" and now.identity.inherit_mark == "v7" and now.identity.lockup_word == "heading"
    assert now.identity.directions == "three"
    assert set(ROLES) >= {"paper", "ink", "brand", "accent"}
    from dataclasses import replace

    from sima.domain import brief_from_dict
    from sima.domain.identity import IdentitySpec

    # المفاتيح القائمة تُحسب من الموجز المجمّد في الإصدار، فلا يكسرها تعديل الموجز الحي
    b = brief_from_dict(json.loads((Path(__file__).parent / "data" / "awraq_brief_v2.json").read_text(encoding="utf-8")))
    assert b.identity.inherit_mark == "v1" and b.hash() == "a62970b5dfc8" and now.hash() != b.hash()
    assert replace(b, identity=IdentitySpec()).hash() == "77963c7428b0"  # مفتاح v1 لم يتغيّر بإضافة الحقل


def test_strategy_card_carries_visuals_when_board_is_fresh(ws):
    out = ws.root.parent.parent
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    [item] = owner_inbox(out)
    assert item["visuals"] == {"mark": "", "reveal": "", "preview": "", "board": "", "options": []}  # لا لوحة بعد: لا روابط مكسورة
    (ws.root / "preview.html").write_text("<html></html>", encoding="utf-8")
    (ws.root / "directions.html").write_text("<html></html>", encoding="utf-8")
    ws.mark_done("directions_board", {"digest": "قديم"})
    [item] = owner_inbox(out)
    assert item["visuals"]["preview"].endswith("v2/preview.html") and item["visuals"]["board"] == ""  # لوحة لمحتوى سابق لا تُعرض


def test_reveal_cmyk_and_screens_use_identity_roles():
    from sima.services.product_screens import SIZES, ScreenKit, screens
    from sima.services.reveal import cmyk, rgb
    assert cmyk("#000000") == (0, 0, 0, 100) and cmyk("#FFFFFF") == (0, 0, 0, 0) and rgb("#7A1C3E") == (122, 28, 62)
    s = build_system(AWRAQ)
    fonts = {"heading": {"family": "Reem Kufi", "file": "ReemKufi[wght].ttf", "weight": 700},
             "body": {"family": "IBM Plex Sans Arabic", "file": "IBMPlexSansArabic-Regular.ttf", "weight": 400}}
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    k = ScreenKit(name_ar="أوراق", tagline="ورقة لكل درس", samples={"headline": "درسك اليوم", "button": "ولّد الورقة", "error": "خطأ", "empty_state": "فارغ"},
                  traits=(("دقيق", "مصطلحات المنهج"),), light=s["light"], dark=s["dark"], fonts=fonts, mark=svg, mark_white=svg, lockup=svg,
                  lockup_white=svg, lockup_mono=svg, motif_soft=svg, nav=("ورقة عمل",))
    out = screens(k, "../fonts/")
    assert set(out) == set(SIZES)
    assert "--brand:#7A1C3E" in out["landing"] and f"--bg:{s['dark']['bg']}" in out["app-dark"] and "ولّد الورقة" in out["mobile"]
    assert 'url("../fonts/ReemKufi[wght].ttf")' in out["landing"]


def test_strategy_approval_can_choose_direction_in_one_step(ws, monkeypatch):
    """المنصة تُعتمد مع اتجاه من لوحة الاطلاع فيُسجَّل القراران، بشرط أن تكون الاتجاهات المعروضة هي الحالية."""
    import sima.services.inbox as inbox_mod

    out = ws.root.parent.parent
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    opts = [{"id": d, "name": d, "idea": "", "swatches": [], "img": "", "slide": ""} for d in ("d1", "d2", "d3")]
    monkeypatch.setattr(inbox_mod, "_visuals", lambda _ws, _rel: {"mark": "", "reveal": "", "preview": "", "board": "b", "options": opts})
    monkeypatch.setattr(inbox_mod, "directions_digest", lambda _ws: "f" * 16)
    [item] = owner_inbox(out)
    assert item["directions_digest"] == "f" * 16
    with pytest.raises(InboxError):  # لوحة قديمة
        identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "d2", "", option_digest="0" * 16)
    with pytest.raises(InboxError):  # اتجاه ليس من المعروض
        identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "d9", "", option_digest="f" * 16)
    msg = identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "d2", "", option_digest="f" * 16)
    assert "d2" in msg
    led = ledger(ws)
    assert led.latest(Gate.STRATEGY, item["digest"]).verdict == "approved"
    d = led.latest(Gate.DIRECTIONS, "f" * 16)
    assert d.verdict == "approved" and d.option == "d2"


def test_intent_guard_blocks_choice_hidden_in_note(ws, monkeypatch):
    """«d2» في ملاحظة اعتماد المنصة بلا اختيار لا يمرّ صامتًا: يُطلب الاختيار صراحة (ما حدث فعلًا في v2)."""
    import sima.services.inbox as inbox_mod

    out = ws.root.parent.parent
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    opts = [{"id": d, "name": d, "idea": "", "swatches": [], "img": "", "slide": ""} for d in ("d1", "d2", "d3")]
    monkeypatch.setattr(inbox_mod, "_visuals", lambda _ws, _rel: {"mark": "", "reveal": "", "preview": "", "board": "b", "options": opts})
    monkeypatch.setattr(inbox_mod, "directions_digest", lambda _ws: "f" * 16)
    [item] = owner_inbox(out)
    assert item["title"] and "الدليل" in item["after"]
    with pytest.raises(InboxError, match="d2"):
        identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "", "d2")
    with pytest.raises(InboxError, match="d3"):
        identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "d2", "d3 أوضح", option_digest="f" * 16)
    assert inbox_mod.mentioned_ids("نريد D2 لا sd2", {"d1", "d2"}) == ["d2"]
    identity_decide(out, "proj", 2, "abc123-s1", "strategy", item["digest"], "approved", "d2", "d2 أوضح", option_digest="f" * 16)


def test_status_colors_are_separated_for_color_blindness():
    from sima.services.color_system import DISTINCT, build_system, status_gap

    # نجاح وخطأ متقاربا الإضاءة: الوضع الذي أسقط d2 سابقًا
    colors = {"paper": "#FAF7F0", "ink": "#1C1B19", "brand": "#2F4B7C", "accent": "#C8892B", "neutral": "#77736B",
              "success": "#2E7D4F", "warning": "#B7791F", "error": "#B3402F", "info": "#2B6CB0"}
    system = build_system(colors)
    for mode in ("light", "dark"):
        assert status_gap(system[mode]["success"], system[mode]["error"]) >= DISTINCT


def test_project_timeline_tells_what_happened_and_who_waits(ws):
    from sima.services.timeline import project_timeline

    out = ws.root.parent.parent
    (ws.root / "brief.json").write_text(json.dumps({"identity": {"scope": "full"}}), encoding="utf-8")
    ws.mark_done("brief", {"hash": "abc123"})
    ws.mark_done("strategy", {"digest": "x"})
    ledger(ws).record(Gate.STRATEGY, "x", "approved", reason="d2")
    (ws.root / "work" / "REQUEST-directions.md").write_text("طلب", encoding="utf-8")
    t = project_timeline(out, "proj")
    texts = [e["text"] for e in t["events"]]
    assert any("ملاحظتك: d2" in x for x in texts) and any("ثلاثة اتجاهات" in x for x in texts)
    assert t["progress"]["total"] == 14 and t["progress"]["done"] == 2
    assert project_timeline(out, "../etc") is None


def test_delivery_is_not_done_until_project_merges_the_card(ws, tmp_path):
    from sima.adapters.ledger_runner import card_events
    from sima.services.timeline import project_timeline

    out = ws.root.parent.parent
    repo = tmp_path / "repo"
    (repo / "automation" / "ledger").mkdir(parents=True)
    book = repo / "automation" / "ledger" / "c1.jsonl"
    book.touch()

    def add(event: str, **extra) -> None:
        with book.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"card": "c1", "event": event, "at": "2026-11-09T16:49:51+00:00", **extra}) + "\n")

    add("created")
    add("ready")
    from sima.services.timeline import flow

    for stage in flow(False)[:-2]:
        ws.mark_done(stage, {})
    ws.mark_done("deliver", {"card_id": "c1", "repo": str(repo)})
    t = project_timeline(out, "proj", read_card=card_events)
    assert t["progress"]["current"] == "landed" and t["now"]["who"] == "project" and "لم يلتقطها" in t["now"]["text"]
    add("pr_opened", url="https://x/pull/2")
    t = project_timeline(out, "proj", read_card=card_events)
    assert t["now"]["who"] == "owner" and any("pull/2" in e["text"] for e in t["events"])
    add("merged")
    t = project_timeline(out, "proj", read_card=card_events)
    assert next(s for s in t["progress"]["steps"] if s["key"] == "landed")["status"] == "done"
    assert card_events(repo, "../c1") == [] and card_events(tmp_path / "none", "c1") == []


def test_marker_rewrite_with_same_content_keeps_its_time(ws):
    import os

    ws.mark_done("preview", {"digest": "a"})
    os.utime(ws.marker("preview"), (1_000_000, 1_000_000))
    ws.mark_done("preview", {"digest": "a"})
    assert ws.marker("preview").stat().st_mtime == 1_000_000
    ws.mark_done("preview", {"digest": "b"})
    assert ws.marker("preview").stat().st_mtime > 1_000_000


def test_marker_keeps_its_own_time_and_inherited_events_are_labelled(ws):
    import os

    from sima.services.timeline import timeline

    ws.mark_done("diverge", {"digest": "a"})
    at = json.loads(ws.marker("diverge").read_text(encoding="utf-8"))["at"]
    os.utime(ws.marker("diverge"), (1_000_000, 1_000_000))  # نسخ أو وراثة غيّرا وقت الملف
    ws.mark_done("diverge", {"digest": "a"})
    assert ws.read_marker("diverge") == {"digest": "a"}
    (ws.root / "brief.json").write_text("{}", encoding="utf-8")
    ws.marker("brief").write_text(json.dumps({"hash": "h", "at": "2026-11-09T12:00:00+00:00"}), encoding="utf-8")
    (ws.root / "stages" / "critique.json").write_text(json.dumps({"at": "2026-11-08T10:00:00+00:00"}), encoding="utf-8")
    texts = {e["text"]: e["at"] for e in timeline(ws.root)["events"]}
    assert texts["رسم النموذج المفاهيم المتباعدة"] == at
    assert texts["اكتملت جولات النقد (من الإصدار السابق)"] == "2026-11-08T10:00:00+00:00"
    req = ws.write_request("REQUEST-x.md", "طلب")
    os.utime(req, (1_000_000, 1_000_000))
    ws.write_request("REQUEST-x.md", "طلب")
    assert req.stat().st_mtime == 1_000_000  # الاستئناف بالطلب نفسه لا يصفّر «ينتظر منذ»


def test_follow_up_cards_show_and_owner_gets_an_approval_command(ws, tmp_path):
    from sima.services.timeline import approval, flow, project_timeline

    out = ws.root.parent.parent
    (ws.root / "brief.json").write_text(json.dumps({"name_ar": "أوراق"}), encoding="utf-8")
    for stage in flow(False)[:-2]:
        ws.mark_done(stage, {})
    ws.mark_done("deliver", {"card_id": "c1", "repo": "R"})
    cards = {
        "c1": [{"card": "c1", "event": "created", "at": "2026-11-09T16:00:00+00:00"},
               {"card": "c1", "event": "merged", "at": "2026-11-09T17:00:00+00:00"}],
        "c2": [{"card": "c2", "event": "created", "at": "2026-11-09T18:00:00+00:00", "title": "تطبيق هوية «أوراق»"},
               {"card": "c2", "event": "pr_opened", "at": "2026-11-09T18:30:00+00:00",
                "note": "https://github.com/o/r/pull/5 الرأس 1793da6"}],
        "c3": [{"card": "c3", "event": "created", "at": "2026-11-09T18:00:00+00:00", "title": "إصلاح CI"}],
        "c4": [{"card": "c4", "event": "created", "at": "2026-11-09T18:40:00+00:00", "title": "توحيد لوحة الإدارة مع الهوية"}],
        "c0": [{"card": "c0", "event": "created", "at": "2026-11-01T10:00:00+00:00", "title": "هوية «أوراق» قديمة"}],
    }
    t = project_timeline(out, "proj", read_card=lambda repo, cid: cards[cid], read_cards=lambda repo: cards)
    texts = " | ".join(e["text"] for e in t["events"])
    assert "بطاقة لاحقة c2" in texts and "بطاقة لاحقة c4" in texts and "c3" not in texts and "c0" not in texts
    assert t["progress"]["current"] is None and t["now"]["who"] == "owner"
    assert t["now"]["approval"] == {"repo": "o/r", "pr": 5, "head": "1793da6"}
    assert approval(cards["c1"]) is None
