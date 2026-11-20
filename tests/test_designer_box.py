"""صندوق المصمّم: ما ينتظر الإرسال يُقرأ من الخط بنصّه وبصمته، وردّ المصمّم (صورة وقائمة، أو كتل شيفرة بأسماء ملفاتها) يدخل
`designer/` من الإصدار الذي ينتظره وحده، ثم يفحصه الخط كعادته. لا اتصال شبكي ولا نموذج في هذه الاختبارات."""
from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace

import pytest
import yaml

from sima.services import designer, designer_box
from sima.services.identity_protocol import strategy_path
from sima.services.inbox import InboxError, choose_sketch, owner_inbox, reject_sketches
from sima.services.pipeline import AWAIT_DESIGNER, AWAIT_MODEL, AWAIT_OWNER, Pipeline

from .test_adopt import MARK, MOTIF, WORD, _manifest
from .test_designer import track  # noqa: F401  (التجهيزة نفسها: موجز على المسار الخارجي وخط بلا نموذج)
from .test_identity import STRATEGY

PNG = b"\x89PNG\r\n\x1a\n" + b"sheet-bytes"
LIST = "\n".join([f"{i}. **فكرة {i}:** وصف السكتش {i}." for i in range(1, 17)]
                 + ["", "أقوى ثلاثة عندي: 14 لربطه الاسم بالناتج، و4، و15؛ ولم يُختبر وضوحها عند 16 بكسل."])
NOW = "2026-11-13 12:00"


def _reply(files: dict[str, str]) -> str:
    parts = ["هذا هو التسليم كاملًا: logo.svg وicon.svg وmotif.svg وdirection.yaml وconcept.yaml.", ""]
    for i, (name, body) in enumerate(files.items(), 1):
        parts += [f"{i}. `{name}`", "", "```" + name.rsplit(".", 1)[1], body.rstrip("\n"), "```", ""]
    return "\n".join([*parts, "نظّفت المنحنيات. أقرب قراءة خاطئة: سهم."])


def _files() -> dict[str, str]:
    return {"logo.svg": WORD, "icon.svg": MARK, "motif.svg": MOTIF,
            "direction.yaml": yaml.safe_dump(_manifest()["direction"], allow_unicode=True),
            "concept.yaml": yaml.safe_dump({"name": "وتد مائل", "sentence": "خط يثبت ما حوله", "construction": "شبكة 8"}, allow_unicode=True)}


def test_outbox_carries_the_sent_text_and_a_sheet_reply_enters_the_line(track):  # noqa: F811
    tmp, brief, pipe = track
    out_dir = tmp / "out"
    ws = pipe.run(brief).workspace
    [item] = designer_box.outbox(out_dir)
    sent = (ws.work / designer.REQ_SKETCHES).read_text(encoding="utf-8").split(designer.SENT, 1)[1].strip()
    assert (item["project"], item["version"], item["kind"], item["invoke"]) == ("demo", 1, "sketches", False)
    assert item["text"] == sent and item["sha256"] == hashlib.sha256(sent.encode("utf-8")).hexdigest() and item["chars"] == len(sent)
    assert str(tmp) not in item["text"] and designer_box.outbox(out_dir, hidden=("demo",)) == []
    key = item["key"]

    with pytest.raises(InboxError, match="لم تصل صورة"):
        designer_box.intake(out_dir, "demo", 1, key, LIST, None, NOW)
    with pytest.raises(InboxError, match="PNG أو JPEG"):
        designer_box.intake(out_dir, "demo", 1, key, LIST, b"<svg/>", NOW)
    with pytest.raises(InboxError, match="قائمة مرقّمة"):
        designer_box.intake(out_dir, "demo", 1, key, "1. واحدة فقط", PNG, NOW)
    for project, version, k in (("demo", 2, key), ("demo", 1, "other-s1"), ("../demo", 1, key), ("none", 1, key)):
        with pytest.raises(InboxError):
            designer_box.intake(out_dir, project, version, k, LIST, PNG, NOW)
    assert not designer.sheet_path(ws).is_file()  # المرفوض لم يكتب شيئًا يُعرض

    msg = designer_box.intake(out_dir, "demo", 1, key, LIST, PNG, NOW)
    assert "16 سكتشًا" in msg and (designer.ddir(ws) / "sketches.png").read_bytes() == PNG
    sheet, problems = designer.read_sheet(ws)
    assert not problems and sheet.picks == (14, 4, 15) and sheet.sketches[0] == (1, "فكرة 1: وصف السكتش 1.") and NOW in sheet.source
    assert pipe.run(brief).code == AWAIT_OWNER and owner_inbox(out_dir)[0]["kind"] == "sketches"
    assert designer_box.outbox(out_dir) == []  # الدور للمالك: لا شيء يُرسل
    with pytest.raises(InboxError, match="لا ينتظر المصمّم"):
        designer_box.intake(out_dir, "demo", 1, key, LIST, PNG, NOW)

    [card] = owner_inbox(out_dir)
    reject_sketches(out_dir, "demo", 1, key, card["digest"], "اشرح المنصة بشكل أوضح")
    pipe.run(brief)
    [again] = designer_box.outbox(out_dir)  # رفض المالك يعيد طلب الصفحة إلى الصندوق بسببه
    assert again["kind"] == "sketches" and "اشرح المنصة بشكل أوضح" in again["text"] and again["sha256"] != item["sha256"]


def test_vector_and_fix_replies_become_the_delivery_as_received(track, monkeypatch):  # noqa: F811
    tmp, brief, pipe = track
    out_dir = tmp / "out"
    ws = pipe.run(brief).workspace
    key = designer_box.outbox(out_dir)[0]["key"]
    designer_box.intake(out_dir, "demo", 1, key, LIST, PNG, NOW)
    pipe.run(brief)
    choose_sketch(out_dir, "demo", 1, key, owner_inbox(out_dir)[0]["digest"], 5, "")
    assert pipe.run(brief).code == AWAIT_DESIGNER
    [item] = designer_box.outbox(out_dir)
    assert item["kind"] == "vector" and item["invoke"] and "السكتش رقم 5" in item["text"]

    files = _files()
    with pytest.raises(InboxError, match="كتلة شيفرة"):
        designer_box.intake(out_dir, "demo", 1, key, "سأسلّم لاحقًا.", None, NOW)
    with pytest.raises(InboxError, match="ناقص"):  # ثلاثة من خمسة: لا بيان اعتماد
        designer_box.intake(out_dir, "demo", 1, key, _reply({n: files[n] for n in ("logo.svg", "icon.svg", "motif.svg")}), None, NOW)
    assert not designer.manifest_path(ws).is_file()
    msg = designer_box.intake(out_dir, "demo", 1, key, _reply(files), None, NOW)
    intake_dir = designer.ddir(ws) / designer_box.INTAKE_DIR
    assert "بيان الاعتماد" in msg and (intake_dir / "icon.svg").read_text(encoding="utf-8") == MARK.rstrip("\n") + "\n"
    assert yaml.safe_load(designer.manifest_path(ws).read_text(encoding="utf-8"))["sketch"] == 5
    assert designer_box.outbox(out_dir) == []  # استُلم: لا طلب معلّق حتى يفحصه الخط

    why = "أصغر سماكة عند 16 بكسل = 0.97 أقل من 1.5"

    def rejected(self, ws, brief, concepts, svgs, smalls, small_base=16, min_stroke=None, **_):
        ok, bad = SimpleNamespace(passed=True, findings=[]), SimpleNamespace(passed=False, findings=[why])
        return {concepts[0].id: ok, concepts[0].id + "-small": bad}

    monkeypatch.setattr(Pipeline, "_stage_render", rejected)
    assert pipe.run(brief).code == AWAIT_MODEL
    strategy_path(ws).write_text(STRATEGY, encoding="utf-8")
    assert pipe.run(brief).code == AWAIT_DESIGNER
    [fix] = designer_box.outbox(out_dir)  # ما ردّه الفحص يظهر في الصندوق بسببه
    assert fix["kind"] == "fix" and fix["invoke"] and why in fix["text"]
    # ب5: إعادة تسليم مطابقة أثناء حلقة التصحيح. البيان يُعاد كتابته والطلب المطابق لا يُمسّ؛ كان الصندوق يقارن وقتيهما
    # فيعمى والخط ما زال ينتظر المصمّم. الآن يقرأ ما وقف عنده الخط.
    designer_box.intake(out_dir, "demo", 1, key, _reply({"icon.svg": MARK}), None, NOW)
    old = (ws.work / designer.REQ_FIX).stat().st_mtime - 60
    os.utime(ws.work / designer.REQ_FIX, (old, old))
    assert pipe.run(brief).code == AWAIT_DESIGNER
    [again] = designer_box.outbox(out_dir)
    assert again["kind"] == "fix" and again["sha256"] == fix["sha256"]
    fixed = MARK.replace("<svg", "<svg data-round=\"2\"", 1)
    designer_box.intake(out_dir, "demo", 1, key, _reply({"icon.svg": fixed}), None, NOW)
    assert (intake_dir / "icon.svg").read_text(encoding="utf-8") == fixed.rstrip("\n") + "\n"
    assert (intake_dir / "logo.svg").read_text(encoding="utf-8") == WORD.rstrip("\n") + "\n"  # غير المردود كما هو
    assert designer_box.outbox(out_dir) == []


def test_reply_parsers_keep_only_what_matches_the_format():
    rows, picks = designer_box.parse_sheet("مقدمة\n1) الأولى\n2) الثانية\n7. شاردة\n3) الثالثة\n4- الرابعة\n5: الخامسة\n6. السادسة\nالأقوى 6 ثم 2 ثم 6 ثم 99 ثم 1 ثم 3")
    assert [i for i, _ in rows] == [1, 2, 3, 4, 5, 6] and rows[2] == (3, "الثالثة") and picks == [6, 2, 1]
    sheet = "\n".join(f"{i}) فكرة {i}" for i in range(1, 17))
    _, picks = designer_box.parse_sheet(sheet + "\nكلها تُقرأ عند 16 بكسل و32px و16×16 وبسماكة 1.5 ونسبة 80%.\nالأقوى: 4 ثم 11 ثم 16")
    assert picks == [4, 11, 16]  # المقاس ليس اختيارًا، والرقم نفسه اختيار حين يُذكر رقمًا
    _, picks = designer_box.parse_sheet(sheet + "\nكلها تُقرأ عند 16 وتبقى واضحة عند 12.\nأقوى 3 سكتشات عندي: 5 و9\nثم 14\n\nوالسكتش 2 ضعيف عند 16.")
    assert picks == [5, 9, 14]  # رقم بلا وحدة في النثر حول سطر الاختيار ليس اختيارًا، ولا عدد السكتشات
    _, picks = designer_box.parse_sheet(sheet + "\nأرشّح:\n- 7\n- 3\n- 12")
    assert picks == [7, 3, 12]  # سطر الإعلان بلا أرقام: القائمة تحته حتى السطر الفارغ
    with pytest.raises(InboxError, match="وجدت 0"):
        designer_box.parse_sheet("لا قائمة هنا")
    text = "\n".join(["```svg", "<svg>بلا اسم</svg>", "```", "ثم `direction.yaml` بلا كتلة، وهذه بلا اسم:", "",
                      "وأخيرًا icon.svg ثم logo.svg:", "```", "<svg>logo</svg>", "```", "```yaml", "sentence: جملة", "```",
                      "```yaml", "colors: {}", "```"])
    got = designer_box.parse_files(text)
    assert got == {"logo.svg": "<svg>logo</svg>\n", "concept.yaml": "sentence: جملة\n", "direction.yaml": "colors: {}\n"}
    import base64

    assert designer_box.image_bytes("data:image/png;base64," + base64.b64encode(PNG).decode()) == PNG and designer_box.image_bytes(None) is None
    for bad in ("data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,@@@", "http://x/y.png", "data:image/png;base64,QQ"):
        with pytest.raises(InboxError, match="PNG أو JPEG"):
            designer_box.image_bytes(bad)
