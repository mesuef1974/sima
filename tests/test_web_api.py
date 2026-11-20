"""منصة سِمة على Django: الصفحة تحقن رمز التشغيل وحزمة Vue، والكتابة لا تمر إلا برمز صحيح من أصل محلي،
وملفات المخرجات لا تخرج من out/. لا تحتاج قاعدة البيانات."""
from __future__ import annotations

import json

import pytest

from sima import config

pytest.importorskip("django")

HOST = "127.0.0.1:8766"
MANIFEST = config.ROOT / "src" / "sima" / "web" / "frontend_dist" / ".vite" / "manifest.json"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMA_OUT", str(tmp_path))
    monkeypatch.setenv("SIMA_BOARD_PORT", "8766")
    monkeypatch.delenv("SIMA_BOARD_REPO", raising=False)
    from sima.web import setup

    setup()
    from django.test import Client

    (tmp_path / "p" / "v1").mkdir(parents=True)
    (tmp_path / "p" / "v1" / "preview.html").write_text("<p>معاينة</p>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    return Client(HTTP_HOST=HOST)


def _token():
    from sima.web import runtime

    return runtime.TOKEN


def _post(client, path, body, **headers):
    return client.post(path, data=json.dumps(body), content_type="application/json", **headers)


BODY = {"project": "p", "version": 1, "key": "k", "verdict": "approved", "concept": "c1", "digest": "d"}


@pytest.mark.skipif(not MANIFEST.is_file(), reason="واجهة Vue غير مبنية")
def test_index_injects_token_and_vue_bundle(client):
    r = client.get("/")
    html = r.content.decode("utf-8")
    assert r.status_code == 200
    assert f'name="sima-token" content="{_token()}"' in html
    assert "/static/assets/main-" in html and 'dir="rtl"' in html
    assert "default-src 'self'" in r["Content-Security-Policy"] and r["Cache-Control"] == "no-store"


def test_state_is_json_with_inbox_and_jobs(client):
    r = client.get("/api/state")
    data = r.json()
    assert r.status_code == 200
    assert {"now", "sima", "cards", "inbox", "jobs", "runner", "workshop"} <= data.keys() and data["workshop"] == []


def test_write_requires_token(client):
    r = _post(client, "/api/decide", BODY)
    assert r.status_code == 403 and r.json() == {"ok": False, "error": "طلب من خارج المنصة"}
    r = _post(client, "/api/decide", BODY, HTTP_X_SIMA_TOKEN="wrong")
    assert r.status_code == 403


def test_write_rejects_foreign_origin_even_with_token(client):
    r = _post(client, "/api/identity", BODY, HTTP_X_SIMA_TOKEN=_token(), HTTP_ORIGIN="http://evil.test")
    assert r.status_code == 403


def test_trusted_write_reaches_inbox_rules(client):
    r = _post(client, "/api/decide", BODY, HTTP_X_SIMA_TOKEN=_token(), HTTP_ORIGIN=f"http://{HOST}")
    assert r.status_code == 409 and r.json()["ok"] is False
    r = _post(client, "/api/decide", {"project": "p"}, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 400 and r.json()["error"] == "طلب غير صالح"


def test_resume_restarts_the_line_on_the_shown_open_version_only(client, tmp_path, monkeypatch):
    """زر الاستئناف (م1): برمز التشغيل، على آخر إصدار مفتوح بالمفتاح المعروض، ولا يُقبل وتشغيل المشروع جارٍ."""
    from sima.web import runtime

    v = tmp_path / "p" / "v1"
    run = {"project": "p", "key": "h-s1", "brief_hash": "h", "seed": 1, "version": 1, "brief_source": "briefs/p.yaml", "closed": False}
    (v / "run.json").write_text(json.dumps(run), encoding="utf-8")
    started, state = [], {"running": False}

    class Jobs:
        def start(self, project, brief, **kw):
            assert kw == {"seed": 1, "expect_key": "h-s1"}  # يُستأنف الإصدار المعروض بعينه (م2)
            started.append((project, brief.as_posix().rsplit("/", 2)[-2:]))
            return True

        def snapshot(self):
            return [{"project": "p", "state": "running"}] if state["running"] else []

    monkeypatch.setattr(runtime, "jobs", Jobs)
    body = {"project": "p", "version": 1, "key": "h-s1"}
    assert _post(client, "/api/resume", body).status_code == 403
    r = _post(client, "/api/resume", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 200 and "يُستأنف الخط على p v1" in r.json()["message"] and started == [("p", ["briefs", "p.yaml"])]
    assert _post(client, "/api/resume", {**body, "key": "old"}, HTTP_X_SIMA_TOKEN=_token()).status_code == 409
    state["running"] = True
    r = _post(client, "/api/resume", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 409 and "تشغيل جارٍ" in r.json()["error"] and len(started) == 1
    state["running"] = False
    (v / "run.json").write_text(json.dumps({**run, "closed": True}), encoding="utf-8")
    r = _post(client, "/api/resume", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 409 and "مكتمل" in r.json()["error"] and len(started) == 1


def test_out_files_stay_inside_out_dir(client):
    assert client.get("/out/p/v1/preview.html").status_code == 200
    assert client.get("/out/../secret.txt").status_code == 404
    assert client.get("/out/p/v1/work/REQUEST.md").status_code == 404
    assert client.get("/fonts/..%5Csecret.ttf").status_code == 404
    assert client.get("/out/p/v1/WORK/REQUEST.md").status_code == 404


def test_out_documents_are_sandboxed_away_from_the_token(client, tmp_path):
    concepts = tmp_path / "p" / "v1" / "work" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "c1.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', encoding="utf-8")
    model = client.get("/out/p/v1/work/concepts/c1.svg")["Content-Security-Policy"]
    assert model.startswith("sandbox;") and "script-src" not in model
    doc = client.get("/out/p/v1/preview.html")["Content-Security-Policy"]
    assert doc.startswith("sandbox ") and "allow-same-origin" not in doc and "connect-src 'none'" in doc
    assert "5173" not in client.get("/")["Content-Security-Policy"]


def test_registry_never_breaks_the_page(client):
    r = client.get("/api/registry")
    assert r.status_code == 200 and "online" in r.json()


def test_admin_requires_login_and_serves_its_assets(client):
    r = client.get("/admin/")
    assert r.status_code == 302 and "/admin/login/" in r["Location"]
    login = client.get("/admin/login/")
    assert login.status_code == 200 and 'dir="rtl"' in login.content.decode("utf-8")
    assert client.get("/static/admin/css/base.css").status_code == 200


def test_registry_admin_is_read_only():
    from django.contrib import admin
    from django.test import RequestFactory

    from sima.web.registry.models import ApprovedIdentity, GateDecision

    req = RequestFactory().get("/admin/")
    for model in (GateDecision, ApprovedIdentity):
        ma = admin.site._registry[model]
        assert not ma.has_add_permission(req) and not ma.has_change_permission(req) and not ma.has_delete_permission(req)


def test_refresh_manifest_resets_loader_only_when_manifest_changes(tmp_path, monkeypatch):
    from django_vite.core.asset_loader import DjangoViteAssetLoader

    from sima.web import views

    m = tmp_path / "manifest.json"
    m.write_text("{}", encoding="utf-8")
    monkeypatch.setitem(views._MANIFEST_SEEN, "mtime", None)
    assert views.refresh_manifest(m) is True  # أول رؤية
    assert views.refresh_manifest(m) is False  # لم يتغيّر
    DjangoViteAssetLoader._instance = object()  # محمّل مخزَّن
    m.write_text('{"a": 1}', encoding="utf-8")
    import os

    os.utime(m, ns=(m.stat().st_atime_ns, m.stat().st_mtime_ns + 5_000_000))
    assert views.refresh_manifest(m) is True and DjangoViteAssetLoader._instance is None
    assert views.refresh_manifest(tmp_path / "missing.json") is False


def test_unknown_project_timeline_is_404_and_tool_folders_are_not_projects(client, tmp_path):
    """مجلدات الأدوات المؤقتة في out/ (_probe، _calibration) ليست مشاريع، وصندوق حالة مشروع غير موجود 404 لا 500."""
    r = client.get("/api/timeline/nope")
    assert r.status_code == 404 and r.json()["ok"] is False
    from sima.services.board import sima_state
    from sima.services.inbox import owner_inbox
    from sima.web import runtime

    out = runtime.out_dir()
    (out / "_calibration" / "v1" / "work").mkdir(parents=True)
    assert all(not p["project"].startswith("_") for p in sima_state(out))
    assert all(not i["project"].startswith("_") for i in owner_inbox(out))


def test_designer_box_lists_the_pending_request_and_takes_a_reply_larger_than_the_general_limit(client, tmp_path, monkeypatch):
    """صندوق المصمّم: القراءة مفتوحة للأصل المحلي، والاستلام برمز التشغيل؛ جسمه بصورته يتجاوز السقف العام (8 ك.ب) ويُقبل بسقفه."""
    import base64

    import yaml

    from sima.adapters.font_shaper import HarfBuzzShaper
    from sima.domain.brief import load_brief
    from sima.services import designer
    from sima.services.pipeline import AWAIT_DESIGNER, Pipeline
    from sima.services.shaping import ShapingService
    from sima.web import api as web_api

    from .fakes import FakeRenderer
    from .test_designer import TRACK
    from .test_designer_box import LIST
    from .test_domain_ledger_workspace import BRIEF

    brief_file = tmp_path / "demo.yaml"
    brief_file.write_text(yaml.safe_dump({**BRIEF, "identity": TRACK}, allow_unicode=True), encoding="utf-8")
    out = Pipeline(FakeRenderer(), ShapingService(HarfBuzzShaper()), None, tmp_path, catalog=[]).run(load_brief(brief_file))
    assert out.code == AWAIT_DESIGNER
    [item] = client.get("/api/designer-box").json()["items"]
    assert item["kind"] == "sketches" and item["project"] == "demo" and len(item["sha256"]) == 64 and "سكتش" in item["text"]

    started = []
    monkeypatch.setattr(web_api, "_start", lambda project, version: started.append((project, version)) or True)
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 80  # نحو 20 ك.ب: فوق السقف العام
    body = {"project": "demo", "version": 1, "key": item["key"], "text": LIST, "image": "data:image/png;base64," + base64.b64encode(png).decode()}
    assert _post(client, "/api/designer-box/intake", body).status_code == 403
    assert _post(client, "/api/designer-box/intake", body, HTTP_X_SIMA_TOKEN=_token(), HTTP_ORIGIN="http://evil.test").status_code == 403
    assert not designer.sheet_path(out.workspace).is_file() and started == []
    bad = _post(client, "/api/designer-box/intake", {**body, "image": "data:image/svg+xml;base64,PHN2Zz4="}, HTTP_X_SIMA_TOKEN=_token())
    assert bad.status_code == 409 and "PNG أو JPEG" in bad.json()["error"]
    assert client.post("/api/designer-box/intake", data="ليس JSON", content_type="application/json", HTTP_X_SIMA_TOKEN=_token()).status_code == 400
    r = _post(client, "/api/designer-box/intake", body, HTTP_X_SIMA_TOKEN=_token(), HTTP_ORIGIN=f"http://{HOST}")
    assert r.status_code == 200 and "16 سكتشًا" in r.json()["message"] and started == [("demo", 1)]
    assert (designer.ddir(out.workspace) / "sketches.png").read_bytes() == png
    assert client.get("/api/designer-box").json()["items"] == []  # استُلمت الصفحة: الدور للمالك ولا شيء يُرسل


def test_stopped_database_does_not_break_pages_for_a_browser_with_session_cookie(client, monkeypatch):
    """متصفح يحمل كعكة جلسة لوحة الإدارة والقاعدة متوقفة: صفحات المنصة لا تقرأ الجلسة فلا تسقط (انقطاع 2026-11-17)."""
    from django.conf import settings
    from django.contrib.sessions.backends.db import SessionStore
    from django.db import OperationalError

    def down(self):
        raise OperationalError("connection timeout expired")

    monkeypatch.setattr(SessionStore, "load", down)
    client.cookies[settings.SESSION_COOKIE_NAME] = "stale-session-key"
    assert client.get("/api/state").status_code == 200
    assert client.get("/").status_code == 200


def test_cluster_start_flags_keep_a_private_console():
    """القاعدة تبدأ بطرفية خاصة بلا نافذة: لا DETACHED_PROCESS (يفتح ويندوز لابن pg_ctl طرفية خارج تحكّمنا فتسقط القاعدة)."""
    import subprocess
    import sys

    from sima.adapters import registry

    if sys.platform != "win32":
        pytest.skip("أعلام ويندوز")
    for flags in registry._detach_flags():
        assert flags & subprocess.CREATE_NO_WINDOW and flags & subprocess.CREATE_NEW_PROCESS_GROUP
        assert not flags & subprocess.DETACHED_PROCESS


@pytest.mark.skipif(not MANIFEST.is_file(), reason="واجهة Vue غير مبنية")
def test_new_version_opens_after_the_shown_closed_version_with_the_flag(client, tmp_path, monkeypatch):
    """زر «إصدار جديد» (قرار المالك 2026-11-20): برمز التشغيل، بعد إصدار مغلق تغيّر بعده بيان اعتماده، بـ`--new-version`."""
    from types import SimpleNamespace

    from sima.services import inbox
    from sima.web import runtime

    v = tmp_path / "p" / "v1"
    (v / "stages").mkdir()
    run = {"project": "p", "key": "h-s1", "brief_hash": "h", "seed": 1, "version": 1, "brief_source": "pyproject.toml", "closed": True}
    (v / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (v / "stages" / "adopted.json").write_text(json.dumps({"digest": "old"}), encoding="utf-8")
    monkeypatch.setattr(inbox, "load_brief", lambda p: SimpleNamespace(hash=lambda: "h"))
    monkeypatch.setattr(inbox.adopt, "load", lambda b: SimpleNamespace(digest="new"))
    started = []

    class Jobs:
        def start(self, project, brief, **kw):
            started.append((project, kw))
            return True

        def snapshot(self):
            return []

    monkeypatch.setattr(runtime, "jobs", Jobs)
    body = {"project": "p", "version": 1, "key": "h-s1"}
    assert _post(client, "/api/new-version", body).status_code == 403
    assert "بيان الاعتماد" in client.get("/api/timeline/p").json()["now"]["renew"]
    r = _post(client, "/api/new-version", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 200 and "يُفتح v2" in r.json()["message"] and started == [("p", {"new_version": True})]
    monkeypatch.setattr(inbox.adopt, "load", lambda b: SimpleNamespace(digest="old"))
    r = _post(client, "/api/new-version", body, HTTP_X_SIMA_TOKEN=_token())
    assert r.status_code == 409 and len(started) == 1
