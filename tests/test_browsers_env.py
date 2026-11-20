"""متصفح التصيير من داخل المشروع: المنصة تعمل من طرفية المالك التي لا ترى ما ثُبّت في بيئة تطبيق مُحزَّم."""
from __future__ import annotations

from sima.adapters.playwright_renderer import browsers_env


def test_project_browsers_used_when_present(tmp_path):
    folder = tmp_path / "ms-playwright"
    (folder / "chromium_headless_shell-1").mkdir(parents=True)
    env: dict[str, str] = {}
    assert browsers_env(folder, env) == str(folder)
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(folder)


def test_owner_path_wins(tmp_path):
    folder = tmp_path / "ms-playwright"
    (folder / "chromium_headless_shell-1").mkdir(parents=True)
    env = {"PLAYWRIGHT_BROWSERS_PATH": "X:/mine"}
    assert browsers_env(folder, env) == "X:/mine"


def test_missing_or_empty_folder_keeps_default(tmp_path):
    env: dict[str, str] = {}
    assert browsers_env(tmp_path / "none", env) is None
    (tmp_path / "empty").mkdir()
    assert browsers_env(tmp_path / "empty", env) is None
    assert "PLAYWRIGHT_BROWSERS_PATH" not in env
