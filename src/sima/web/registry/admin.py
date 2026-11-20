"""لوحة إدارة سِمة: تصفّح السجل للقراءة فقط. الكتابة كلها عبر خدمة السجل من قرارات المالك في المنصة، لا من هنا،
فلا إضافة ولا تعديل ولا حذف في اللوحة (سجلّ تدقيق لا يُمسّ)."""
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html, format_html_join

from .models import ApprovedIdentity, Asset, ConceptDecision, GateDecision, Project, Run

admin.site.site_header = "إدارة سِمة"
admin.site.site_title = "سِمة"
admin.site.index_title = "سجلّ الهوية: المشاريع والإصدارات والقرارات والهويات المعتمدة"


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class RunInline(ReadOnlyInline):
    model = Run
    fields = ("version", "key", "closed", "synced_at")
    readonly_fields = fields


@admin.register(Project)
class ProjectAdmin(ReadOnly):
    list_display = ("slug", "name_ar", "runs_count", "updated_at")
    search_fields = ("slug", "name_ar")
    inlines = (RunInline,)

    @admin.display(description="الإصدارات")
    def runs_count(self, obj: Project) -> int:
        return obj.runs.count()


class GateInline(ReadOnlyInline):
    model = GateDecision
    fields = ("decided_at", "gate", "verdict", "option", "reason", "digest")
    readonly_fields = fields


class ConceptInline(ReadOnlyInline):
    model = ConceptDecision
    fields = ("decided_at", "concept_id", "verdict", "medium", "reason")
    readonly_fields = fields


@admin.register(Run)
class RunAdmin(ReadOnly):
    list_display = ("project", "version", "key", "closed", "synced_at")
    list_filter = ("project", "closed")
    search_fields = ("key", "brief_hash")
    inlines = (GateInline, ConceptInline)


@admin.register(ConceptDecision)
class ConceptDecisionAdmin(ReadOnly):
    list_display = ("decided_at", "run", "concept_id", "verdict", "medium", "reason")
    list_filter = ("verdict", "medium", "run__project")
    date_hierarchy = "decided_at"


@admin.register(GateDecision)
class GateDecisionAdmin(ReadOnly):
    list_display = ("decided_at", "run", "gate", "verdict", "option", "reason")
    list_filter = ("gate", "verdict", "run__project")
    date_hierarchy = "decided_at"


class AssetInline(ReadOnlyInline):
    model = Asset
    fields = ("path", "kind", "size", "sha256")
    readonly_fields = fields


@admin.register(ApprovedIdentity)
class ApprovedIdentityAdmin(ReadOnly):
    list_display = ("run", "direction_id", "direction_name", "swatches", "checks", "approved_at")
    list_filter = ("run__project",)
    readonly_fields = ("swatches", "checks")
    inlines = (AssetInline,)

    @admin.display(description="الألوان")
    def swatches(self, obj: ApprovedIdentity) -> str:
        return format_html_join("", '<span title="{} {}" style="display:inline-block;inline-size:1.2em;block-size:1.2em;'
                                'border:1px solid #8886;margin-inline-end:2px;background:{}"></span>',
                                ((k, v, v) for k, v in (obj.colors or {}).items()))

    @admin.display(description="الفحوص")
    def checks(self, obj: ApprovedIdentity) -> str:
        return format_html("{} من {}", obj.checks_passed, obj.checks_total)


@admin.register(Asset)
class AssetAdmin(ReadOnly):
    list_display = ("path", "kind", "identity", "size", "media_type")
    list_filter = ("kind", "identity__run__project")
    search_fields = ("path", "sha256")
    exclude = ("content",)
    readonly_fields = ("preview",)

    @admin.display(description="المحتوى")
    def preview(self, obj: Asset) -> str:
        return format_html("<pre style='white-space:pre-wrap;max-block-size:30rem;overflow:auto' dir='ltr'>{}</pre>",
                           (obj.content or "ملف ثنائي؛ محفوظ ببصمته فقط")[:20000])
