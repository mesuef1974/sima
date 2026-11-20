"""إعداد مشترك: بوابة الطابع معطّلة في اختبارات الخط القديمة، وتُفعَّل صراحةً في اختباراتها (علامة style_gate)."""
import pytest

from sima import config as sima_config


def pytest_configure(config):
    config.addinivalue_line("markers", "style_gate: يفعّل بوابة الطابع البصري في الاختبار")


@pytest.fixture(autouse=True)
def _style_gate(request, monkeypatch):
    monkeypatch.setattr(sima_config, "STYLE_GATE", request.node.get_closest_marker("style_gate") is not None)
