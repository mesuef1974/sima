from __future__ import annotations

from django.contrib import admin
from django.contrib.staticfiles.views import serve as static_serve
from django.urls import path, re_path

from . import views
from .api import api

urlpatterns = [
    path("", views.index, name="board"),
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    re_path(r"^out/(?P<rel>.+)$", views.out_file, name="out"),
    re_path(r"^fonts/(?P<name>[^/\\]+)$", views.font, name="font"),
    # حزمة Vue المبنية وملفات لوحة الإدارة عبر finders؛ خادم محلي لمستخدم واحد فلا حاجة إلى خادم ملفات منفصل
    re_path(r"^static/(?P<path>.+)$", static_serve, {"insecure": True}),
]
