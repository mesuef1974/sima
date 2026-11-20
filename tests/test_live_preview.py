"""عين الرسّام: معاينة حية لما يكتبه النموذج أثناء الاستدعاء."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sima import config
from sima.adapters.proc import run_tree
from sima.services import live_preview
from sima.services.autopilot import ModelResult, run_until_owner
from sima.services.live_preview import LivePreview, preview_path, sheet_svg
from sima.services.pipeline import AWAIT_MODEL, AWAIT_OWNER, Outcome

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 256"><title>t</title><path d="M0 0h10v10z"/></svg>'


class FakeRenderer:
    def __init__(self):
        self.calls: list[tuple[str, int, str | None]] = []

    def render_png(self, svg, size, background=None):
        self.calls.append((svg, size, background))
        return b"PNG" + str(len(self.calls)).encode()


def build(text: str, title: str) -> str:
    if "bad" in text:
        raise ValueError("شكل غير معروف")
    return SVG


def touch(p: Path, text: str, t: int) -> None:
    p.write_text(text, encoding="utf-8")
    os.utime(p, ns=(t, t))


def test_sheet_nests_mark_at_real_small_sizes():
    sheet = sheet_svg(SVG, "c1 #2")
    assert sheet.count('viewBox="0 0 512 256"') == 5  # كبيرة ومعكوسة وثلاثة مقاسات
    assert 'height="16"' in sheet and 'height="48"' in sheet and "invert(1)" in sheet
    assert "c1 #2" in sheet and "<title>" in sheet


def test_first_call_is_snapshot_then_stable_change_renders(tmp_path):
    d = tmp_path / "concepts"
    d.mkdir()
    spec = d / "c1.mark.yaml"
    touch(spec, "a", 1_000)
    r = FakeRenderer()
    lp = LivePreview(r, build)
    assert lp(tmp_path) == [] and not r.calls  # لقطة البداية: ما كان قبل الاستدعاء لا يُصيَّر
    assert lp(tmp_path) == []
    preview_path(spec).write_bytes(b"old")
    touch(spec, "ab", 2_000)
    assert lp(tmp_path) == [] and not preview_path(spec).exists()  # تغيّر: تُحذف المعاينة القديمة ويُنتظر ثبات الملف
    assert lp(tmp_path) == ["concepts/c1"]
    assert preview_path(spec).read_bytes() == b"PNG1" and r.calls[0][1:] == (768, "#FFFFFF")
    assert "c1 #1" in r.calls[0][0]
    assert lp(tmp_path) == [] and len(r.calls) == 1  # idempotent
    assert not (d / "c1.svg").exists()  # المعاينة لا تكتب SVG المعتمد


def test_file_still_changing_is_not_built(tmp_path):
    d = tmp_path / "styles"
    d.mkdir()
    lp = LivePreview(FakeRenderer(), build)
    lp(tmp_path)
    spec = d / "s1.mark.yaml"
    touch(spec, "a", 1_000)
    assert lp(tmp_path) == []
    touch(spec, "abc", 2_000)
    assert lp(tmp_path) == []
    assert lp(tmp_path) == ["styles/s1"]


def test_build_error_written_and_cleared(tmp_path):
    d = tmp_path / "concepts"
    d.mkdir()
    lp = LivePreview(FakeRenderer(), build)
    lp(tmp_path)
    spec = d / "c2.mark.yaml"
    touch(spec, "bad", 1_000)
    lp(tmp_path)
    lp(tmp_path)
    err = d / "c2.mark.error.txt"
    assert err.read_text(encoding="utf-8") == "شكل غير معروف" and not preview_path(spec).exists()
    touch(spec, "good", 2_000)
    lp(tmp_path)
    lp(tmp_path)
    assert not err.exists() and preview_path(spec).is_file()


def test_clear_and_lines(tmp_path, monkeypatch):
    (tmp_path / "c1.preview.png").write_bytes(b"x")
    (tmp_path / "c1.svg").write_text("s", encoding="utf-8")
    live_preview.clear(tmp_path)
    assert not (tmp_path / "c1.preview.png").exists() and (tmp_path / "c1.svg").exists()
    assert any("work/styles/<id>.preview.png" in ln for ln in live_preview.lines("styles"))
    monkeypatch.setattr(config, "LIVE_PREVIEW", False)
    assert live_preview.lines() == []


def test_run_tree_ticks_while_process_runs(tmp_path):
    n = []
    p = run_tree([sys.executable, "-c", "import time; time.sleep(0.8); print('ok')"], tmp_path, 20, tick=lambda: n.append(1), every=0.1)
    assert p.returncode == 0 and p.stdout.strip() == "ok" and len(n) >= 2


def test_run_tree_tick_error_does_not_stop_and_timeout_kills(tmp_path):
    def boom():
        raise RuntimeError("x")

    p = run_tree([sys.executable, "-c", "import time; time.sleep(0.4); print('ok')"], tmp_path, 20, tick=boom, every=0.1)
    assert p.stdout.strip() == "ok"
    with pytest.raises(subprocess.TimeoutExpired):
        run_tree([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 0.5, tick=lambda: None, every=0.1)


def test_autopilot_passes_watch_to_model(tmp_path):
    class WS:
        root = tmp_path
        work = tmp_path / "work"

    WS.work.mkdir()
    (WS.work / "REQUEST-diverge.md").write_text("r", encoding="utf-8")
    seen: list[Path] = []
    outs = iter([Outcome(AWAIT_MODEL, "m", WS), Outcome(AWAIT_OWNER, "o", WS)])

    class Model:
        def run(self, request, version_root, *, cap_usd, tick=None):
            (WS.work / "x.txt").write_text("1", encoding="utf-8")
            tick()
            return ModelResult(True, 0.1, 1.0, "تم")

    out = run_until_owner(lambda: next(outs), Model(), 3, watch=seen.append)
    assert out.code == AWAIT_OWNER and seen == [WS.work] * 3  # قبل الاستدعاء، وأثناءه، وبعده
