"""واجهة API لمنصة سِمة (django-ninja): القراءة مفتوحة للأصل المحلي، والكتابة برمز التشغيل في `X-Sima-Token` وأصل محلي.

العقد كما كان في الخادم السابق: `{ok, message}` أو `{ok: false, error}`؛ القرار مربوط بالإصدار والمفتاح المعروضين،
وبعده يُستأنف `sima run` في الخلفية بلا نافذة.
"""
from __future__ import annotations

import hmac
import json
import threading
from datetime import UTC, datetime

from django.http import HttpRequest
from ninja import NinjaAPI, Schema, Status
from ninja.errors import AuthenticationError, ValidationError
from ninja.security import APIKeyHeader

from .. import config
from ..services import designer_box
from ..services.board import board_state, without_hidden
from ..services.inbox import (
    LIMITS,
    InboxError,
    brief_path,
    brief_unchanged,
    choose_sketch,
    choose_style,
    decide,
    develop_sketch,
    identity_decide,
    name_check,
    owner_inbox,
    reject_sketches,
    renew,
    renew_reason,
    resume,
    resume_args,
    return_vector,
    switch_medium,
)
from ..services.timeline import project_timeline
from ..services.workshop import workshop
from . import runtime


class PlatformToken(APIKeyHeader):
    """طلب من صفحة المنصة نفسها: الرأس المخصّص يفرض preflight يُرفض لأي أصل آخر، والأصل إن أُرسل محلي."""
    param_name = "X-Sima-Token"

    def authenticate(self, request: HttpRequest, key: str | None):
        origin = request.headers.get("Origin")
        if origin and origin not in runtime.origins():
            return None
        return True if key and hmac.compare_digest(key, runtime.TOKEN) else None


api = NinjaAPI(title="سِمة", version="1", docs_url=None, openapi_url=None, urls_namespace="sima-api")


@api.exception_handler(AuthenticationError)
def _forbidden(request, exc):
    return api.create_response(request, {"ok": False, "error": "طلب من خارج المنصة"}, status=403)


@api.exception_handler(ValidationError)
def _invalid(request, exc):
    return api.create_response(request, {"ok": False, "error": "طلب غير صالح"}, status=400)


class Target(Schema):
    project: str
    version: int
    key: str


class DecideIn(Target):
    verdict: str
    concept: str
    digest: str
    reason: str = ""


class MediumIn(Target):
    medium: str
    digest: str
    reason: str = ""


class IdentityIn(Target):
    gate: str
    digest: str
    verdict: str
    option: str = ""
    option_digest: str = ""
    reason: str = ""


class StyleIn(Target):
    digest: str
    styles: list[str] = []  # noqa: RUF012 — حقل مخطط pydantic لا سمة صنف
    note: str = ""


class SketchIn(Target):
    digest: str
    sketch: int
    note: str = ""


class SketchRejectIn(Target):
    digest: str
    reason: str = ""


class NameCheckIn(Target):
    status: str
    sources: list[str] = []  # noqa: RUF012 — حقل مخطط pydantic لا سمة صنف
    note: str = ""


class Reply(Schema):
    ok: bool
    message: str = ""
    error: str = ""


@api.get("/state")
def state(request: HttpRequest) -> dict:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    out = runtime.out_dir()
    inbox = owner_inbox(out)
    from ..adapters.git_landing import landed
    from ..adapters.ledger_runner import card_events

    full = board_state(runtime.repo(), out, now, card_events, landed) | {
        "inbox": inbox, "jobs": runtime.jobs().snapshot(), "workshop": workshop(out, inbox), "limits": LIMITS}
    return without_hidden(full, config.BOARD_HIDDEN)


@api.get("/timeline/{project}", response={200: dict, 404: dict})
def project_log(request: HttpRequest, project: str):
    """صندوق حالة المشروع: ماذا جرى، وأين يقف الآن ومن ينتظر، والتقدم."""
    if project in config.BOARD_HIDDEN:  # المخفي من العرض مخفي من سجله أيضًا (م7)
        return Status(404, {"ok": False, "error": "مشروع غير موجود"})
    out = runtime.out_dir()
    waiting = next((i for i in owner_inbox(out) if i["project"] == project), None)
    job = next((j for j in runtime.jobs().snapshot() if j["project"] == project), None)
    from ..adapters.git_landing import landed
    from ..adapters.ledger_runner import all_cards, card_events

    t = project_timeline(out, project, waiting, job, card_events, all_cards, landed)
    if t is None:
        return Status(404, {"ok": False, "error": "مشروع غير موجود"})
    if not (job and job.get("state") == "running"):  # زر «إصدار جديد»: إصدار مغلق تغيّر بعده موجزه أو بيان اعتماده
        version = int(str(t["version"]).lstrip("v") or 0)
        t["now"]["renew"] = renew_reason(out, config.ROOT, project, version)
    ap = t["now"].pop("approval", None)
    if ap:  # المالك يراجع الطلب ثم يشغّل الأمر بنفسه؛ السكربت يرفض إن تغيّر الرأس عمّا يُعرض هنا
        script = config.ROOT / "scripts" / "approve_pr.ps1"
        t["now"]["command"] = f"& '{script}' -Repo {ap['repo']} -Pr {ap['pr']} -Head {ap['head']}"
        t["now"]["pr_url"] = f"https://github.com/{ap['repo']}/pull/{ap['pr']}"
    return t


@api.get("/registry")
def registry(request: HttpRequest) -> dict:
    """الهويات المعتمدة المحفوظة في قاعدة سِمة؛ إن تعذّر الاتصال تُعاد حالة القاعدة بلا إسقاط الصفحة."""
    try:
        from .registry.models import ApprovedIdentity, GateDecision, Run

        items = [{"project": i.run.project.slug, "name_ar": i.run.project.name_ar, "version": i.run.version, "direction": i.direction_id,
                  "direction_name": i.direction_name, "colors": i.colors, "checks": f"{i.checks_passed}/{i.checks_total}",
                  "assets": i.assets.count(), "approved_at": i.approved_at.isoformat(), "book_digest": i.book_digest}
                 for i in ApprovedIdentity.objects.select_related("run__project")]
        return {"online": True, "runs": Run.objects.count(), "gate_decisions": GateDecision.objects.count(), "identities": items}
    except Exception as e:  # noqa: BLE001 — القاعدة متوقفة أو غير مهيأة: تُعرض الحالة للمالك
        return {"online": False, "error": type(e).__name__, "runs": 0, "gate_decisions": 0, "identities": []}


_WRITE = threading.Lock()


def _start(project: str, version: int) -> bool:
    """يستأنف `sima run` على الإصدار المعروض نفسه: ببذرته ومفتاحه المتوقع، فلا يفتح الموجز الحي إصدارًا آخر (م2)."""
    out = runtime.out_dir()
    return runtime.jobs().start(project, brief_path(out, config.ROOT, project, version), **resume_args(out, project, version))


def _decision(project: str, version: int, record) -> dict:
    """قرار أو استلام يستأنف الخط: يُرفض قبل تسجيله إن عُدّل موجز الإصدار بعد فتحه، ثم يُسجَّل ويُستأنف الخط عليه."""
    brief_unchanged(runtime.out_dir(), config.ROOT, project, version)
    msg = record()
    started = _start(project, version)
    return {"ok": True, "message": msg + (" يُستأنف الخط في الخلفية." if started else
                                          " تشغيل جارٍ للمشروع الآن؛ سُجّل قرارك ويُستأنف الخط به فور انتهاء الجاري.")}


def _guard(fn):
    try:
        with _WRITE:  # قرار واحد في كل لحظة: الفحص ثم التسجيل ذريّان
            return Status(200, fn())
    except InboxError as e:
        return Status(409, {"ok": False, "error": str(e)})
    except (ValueError, KeyError, TypeError):
        return Status(400, {"ok": False, "error": "طلب غير صالح"})


def _resume(project: str, version: int, key: str) -> dict:
    """زر الاستئناف: يعيد تشغيل الخط حيث وقف على الإصدار المعروض، بلا قرار. لا يُقبل وتشغيل المشروع جارٍ."""
    msg = resume(runtime.out_dir(), project, version, key)
    brief_unchanged(runtime.out_dir(), config.ROOT, project, version)
    if any(j["project"] == project and j["state"] == "running" for j in runtime.jobs().snapshot()):
        raise InboxError("تشغيل جارٍ لهذا المشروع الآن؛ انتظر انتهاءه.")
    _start(project, version)
    return {"ok": True, "message": msg}


def _renew(project: str, version: int, key: str) -> dict:
    """زر «إصدار جديد» (قرار المالك 2026-11-20): يفتح بعد الإصدار المغلق المعروض إصدارًا بـ`sima run --new-version`."""
    out = runtime.out_dir()
    msg = renew(out, config.ROOT, project, version, key)
    if any(j["project"] == project and j["state"] == "running" for j in runtime.jobs().snapshot()):
        raise InboxError("تشغيل جارٍ لهذا المشروع الآن؛ انتظر انتهاءه.")
    if not runtime.jobs().start(project, brief_path(out, config.ROOT, project, version), new_version=True):
        raise InboxError("تشغيل جارٍ لهذا المشروع الآن؛ انتظر انتهاءه.")
    return {"ok": True, "message": msg}


@api.post("/new-version", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_new_version(request: HttpRequest, body: Target):
    return _guard(lambda: _renew(body.project, body.version, body.key))


@api.post("/resume", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_resume(request: HttpRequest, body: Target):
    return _guard(lambda: _resume(body.project, body.version, body.key))


@api.post("/decide", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_decide(request: HttpRequest, body: DecideIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:decide(
        runtime.out_dir(), body.project, body.version, body.key, body.verdict, body.concept, body.reason, body.digest)))


@api.post("/medium", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_medium(request: HttpRequest, body: MediumIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:switch_medium(
        runtime.out_dir(), body.project, body.version, body.key, body.medium, body.reason, body.digest)))


@api.post("/identity", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_identity(request: HttpRequest, body: IdentityIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:identity_decide(
        runtime.out_dir(), body.project, body.version, body.key, body.gate, body.digest, body.verdict, body.option, body.reason,
        body.option_digest)))


@api.post("/style", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_style(request: HttpRequest, body: StyleIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:choose_style(
        runtime.out_dir(), body.project, body.version, body.key, body.digest, body.styles[:4], body.note)))


@api.post("/sketch", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_sketch(request: HttpRequest, body: SketchIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:choose_sketch(
        runtime.out_dir(), body.project, body.version, body.key, body.digest, body.sketch, body.note)))


@api.post("/sketch-develop", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_sketch_develop(request: HttpRequest, body: SketchIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:develop_sketch(
        runtime.out_dir(), body.project, body.version, body.key, body.digest, body.sketch, body.note)))


@api.post("/sketch-reject", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_sketch_reject(request: HttpRequest, body: SketchRejectIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:reject_sketches(
        runtime.out_dir(), body.project, body.version, body.key, body.digest, body.reason)))


@api.post("/vector-return", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_vector_return(request: HttpRequest, body: SketchRejectIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:return_vector(
        runtime.out_dir(), body.project, body.version, body.key, body.digest, body.reason)))


BOX_MAX_BODY = 12 * 1024 * 1024  # ردّ المصمّم بصورته؛ سقف Django العام (8 ك.ب) يبقى لبقية المنافذ


@api.get("/designer-box")
def get_box(request: HttpRequest) -> dict:
    """ما ينتظر الإرسال إلى المصمّم الخارجي: النص المرسل وحده وبصمته (صندوق المصمّم)."""
    return {"items": designer_box.outbox(runtime.out_dir(), config.BOARD_HIDDEN)}


@api.post("/designer-box/intake", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_box_intake(request: HttpRequest):
    """ردّ المصمّم الخارجي من صفحة الصندوق. الجسم يُقرأ من المجرى بسقفه الخاص لأن الصورة تتجاوز السقف العام؛ وما فيه بيانات
    تُفحص في الخدمة ولا يُكتب منها إلا ما يطابق الصيغة."""
    def work() -> dict:
        size = int(request.headers.get("Content-Length") or 0)
        if not 0 < size <= BOX_MAX_BODY:
            raise ValueError("size")
        body = json.loads(request.read(size).decode("utf-8"))
        project, version, key, text = str(body["project"]), int(body["version"]), str(body["key"]), str(body["text"])
        now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        return _decision(project, version, lambda: designer_box.intake(
            runtime.out_dir(), project, version, key, text, designer_box.image_bytes(body.get("image")), now))
    return _guard(work)


@api.post("/name-check", auth=PlatformToken(), response={200: Reply, 400: Reply, 409: Reply})
def post_name_check(request: HttpRequest, body: NameCheckIn):
    return _guard(lambda: _decision(body.project, body.version, lambda:name_check(
        runtime.out_dir(), config.ROOT, body.project, body.version, body.key, body.status, body.sources[:10], body.note)))
