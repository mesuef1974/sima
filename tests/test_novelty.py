"""جِدّة الأفكار: لا عودة إلى فكرة رفضها المالك."""
from __future__ import annotations

import json

import pytest

from sima import config
from sima.adapters.local_embed import LocalEmbedder
from sima.domain import Concept, Family, Medium
from sima.services import novelty
from sima.services.workspace import workspace_of

RUN = {"key": "k-s1", "brief_hash": "k", "seed": 1, "version": 1, "project": "p"}


class FakeEmbedder:
    model = "fake"

    def __init__(self, table: dict[str, list[float]] | None = None, down: bool = False):
        self.table, self.down, self.calls = table or {}, down, 0

    def embed(self, texts):
        self.calls += 1
        if self.down:
            return None
        return [next((v for k, v in self.table.items() if k in t), [0.0, 0.0, 1.0]) for t in texts]


def concept(cid: str, name: str, sentence: str) -> Concept:
    return Concept(cid, name, Family.LITERAL, Medium.WORDMARK, sentence)


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "p" / "v1"
    (root / "work" / "history" / "medium-wordmark").mkdir(parents=True)
    (root / "stages").mkdir()
    (root / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    (root / "work" / "history" / "medium-wordmark" / "concepts.yaml").write_text(
        "concepts:\n  - {id: c1, name: ميسم, sentence: الكلمة كتلة ختم تُقرأ حروفها بيضاء}\n"
        "  - {id: c2, name: الميسم, sentence: الاسم محفور في رأس ميسم حديدي}\n", encoding="utf-8")
    (root / "work" / "history" / "judge-owner-1").mkdir()
    return workspace_of(root)


def test_rejected_from_archives_and_log_grouped_in_request(ws):
    c = concept("c3", "الكسرة", "الكسرة محفورة في خط الأساس")
    assert novelty.record(ws, c, "يوجد أفضل", "2026-11-10T15:21:29+00:00") is True
    assert novelty.record(ws, c, "يوجد أفضل", "2026-11-10T15:21:29+00:00") is False  # idempotent
    got = novelty.rejected(ws)
    assert [(r.name, r.source) for r in got] == [("ميسم", "medium-wordmark"), ("الميسم", "medium-wordmark"),
                                                 ("الكسرة", "رفض المالك 2026-11-10")]
    lines = novelty.lines(ws)
    assert lines[0].startswith("## أفكار رفضها المالك")
    assert any("«الميسم» (رُسمت 2 مرات)" in ln for ln in lines) and any("«الكسرة»:" in ln for ln in lines)


def test_no_rejected_no_lines_no_check(tmp_path):
    root = tmp_path / "p" / "v1"
    (root / "work").mkdir(parents=True)
    (root / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    w = workspace_of(root)
    e = FakeEmbedder()
    assert novelty.lines(w) == [] and novelty.check(w, [concept("c1", "a", "b")], e) == [] and e.calls == 0


def test_check_flags_return_to_rejected_idea_and_caches(ws):
    e = FakeEmbedder({"ميسم": [1.0, 0.0, 0.0], "بوصلة": [0.0, 1.0, 0.0]})
    cs = [concept("c1", "بوصلة", "اتجاه يهدي"), concept("c2", "وسم", "أثر ميسم على الجلد")]
    problems = novelty.check(ws, cs, e)
    assert len(problems) == 1 and "المفهوم c2 «وسم»" in problems[0] and "ميسم»" in problems[0]
    mk = ws.read_marker("novelty")
    assert mk["nearest"]["c1"]["sim"] == 0.0 and mk["nearest"]["c2"]["sim"] == 1.0
    assert novelty.check(ws, cs, e) == problems and e.calls == 1  # المحتوى نفسه: من العلامة بلا استدعاء
    cs[1] = concept("c2", "جسر", "بوصلة تعبر")
    assert novelty.check(ws, cs, e) == [] and e.calls == 2


def test_embedder_down_skips_without_marking(ws):
    e = FakeEmbedder(down=True)
    assert novelty.check(ws, [concept("c1", "ميسم", "x")], e) == [] and not ws.done("novelty")
    assert novelty.check(ws, [concept("c1", "ميسم", "x")], None) == []


def test_threshold_from_config(ws, monkeypatch):
    e = FakeEmbedder({"ميسم": [1.0, 0.0, 0.0], "قريب": [0.7, 0.714, 0.0]})
    cs = [concept("c1", "قريب", "شيء")]
    assert novelty.check(ws, cs, e) == []  # 0.70 دون 0.72
    monkeypatch.setattr(config, "NOVELTY_MAX_SIM", 0.69)
    assert len(novelty.check(ws, cs, e)) == 1


def test_local_embedder_loopback_only_and_down_server():
    with pytest.raises(ValueError, match="هذا الجهاز"):
        LocalEmbedder(url="http://192.168.1.5:1234/v1")
    with pytest.raises(ValueError):
        LocalEmbedder(url="https://api.example.com/v1")
    e = LocalEmbedder(url="http://127.0.0.1:9/v1", model="m", timeout_s=1)
    assert e.embed([]) == [] and e.embed(["نص"]) is None  # خادم متوقف: None لا استثناء


def test_repeated_return_is_waived_after_max_tries(ws):
    """كل ردّ يكلّف استدعاء رسم كاملًا: بعد NOVELTY_MAX_TRIES ردودًا متتالية لمفهوم يُقبل أقرب ما رُسم ولا تدور الأتمتة بلا نهاية."""
    e = FakeEmbedder({"ميسم": [1.0, 0.0, 0.0]})
    for k in range(config.NOVELTY_MAX_TRIES):
        assert len(novelty.check(ws, [concept("c1", f"وسم{k}", f"أثر ميسم {k}")], e)) == 1
    assert novelty.check(ws, [concept("c1", "وسم9", "أثر ميسم 9")], e) == []
    mk = ws.read_marker("novelty")
    assert mk["waived"] == ["c1"] and mk["problems"] == []
    assert novelty.check(ws, [concept("c1", "بوصلة", "اتجاه يهدي")], e) == [] and ws.read_marker("novelty")["tries"] == {}
    assert len(novelty.check(ws, [concept("c1", "وسم", "أثر ميسم جديد")], e)) == 1  # العدّ يبدأ من جديد


def test_request_separates_brief_meaning_from_exhausted_image(ws):
    """مجاز مرفوض ورد في نص الموجز نفسه: الطلب يقول إن المرفوض صورته لا معناه، فلا يتناقض الموجز مع قائمة المرفوض."""
    assert any("صورته المرسومة لا معناه" in ln for ln in novelty.lines(ws))
