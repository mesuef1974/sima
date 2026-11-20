"""سجلّ سِمة العلائقي: المشاريع، وإصدارات التشغيل، وقرارات المالك، والهويات المعتمدة وأصولها.

نماذج نحيلة: لا منطق أعمال هنا؛ الكتابة كلها عبر خدمة السجل (sima.web.registry.service) وبشكل idempotent.
الملفات تبقى على القرص بإصدارات لا تُستبدل؛ القاعدة تحفظ المرجع والبصمة، ونص الأصول النصية الصغيرة.
"""
from __future__ import annotations

from django.db import models


class Project(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    name_ar = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sima_project"
        ordering = ("slug",)

    def __str__(self) -> str:
        return self.slug


class Run(models.Model):
    """إصدار تشغيل واحد: out/<project>/v<n>، مفتاحه hash الموجز مع seed."""
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="runs")
    version = models.PositiveIntegerField()
    key = models.CharField(max_length=64)
    brief_hash = models.CharField(max_length=64)
    seed = models.IntegerField()
    brief_source = models.CharField(max_length=300, blank=True)
    closed = models.BooleanField(default=False)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sima_run"
        ordering = ("project", "version")
        constraints = (models.UniqueConstraint(fields=("project", "version"), name="uniq_run_project_version"),)
        indexes = (models.Index(fields=("key",)),)

    def __str__(self) -> str:
        return f"{self.project.slug} v{self.version}"


class Verdict(models.TextChoices):
    APPROVED = "approved", "اعتُمد"
    REVISE = "revise", "طُلب تعديل"
    REJECTED = "rejected", "رُفض"
    SWITCH_MEDIUM = "switch_medium", "غُيّر الوسيط"  # قرار المالك بتغيير الوسيط (decisions.jsonl)


class ConceptDecision(models.Model):
    """قرار المالك في مفهوم شعار (سجلّ decisions.jsonl)."""
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="concept_decisions")
    concept_id = models.CharField(max_length=20, blank=True)
    verdict = models.CharField(max_length=20, choices=Verdict.choices)
    medium = models.CharField(max_length=30)
    reason = models.TextField(blank=True)
    decided_at = models.DateTimeField()
    round = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "sima_concept_decision"
        ordering = ("run", "decided_at")
        constraints = (models.UniqueConstraint(fields=("run", "concept_id", "verdict", "decided_at"), name="uniq_concept_decision"),)


class Gate(models.TextChoices):
    STRATEGY = "strategy", "المنصة الاستراتيجية"
    DIRECTIONS = "directions", "اتجاه الهوية"
    BOOK = "book", "دليل الهوية"
    DESIGNER = "designer", "سكتش المصمّم الخارجي"  # designer_decisions.jsonl: البصمة بصمة صفحة السكتشات والخيار `sN`


class GateDecision(models.Model):
    """قرار المالك في بوابة هوية، مربوط ببصمة ما عُرض عليه (identity_decisions.jsonl، ومسار المصمّم designer_decisions.jsonl)."""
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="gate_decisions")
    gate = models.CharField(max_length=12, choices=Gate.choices)
    digest = models.CharField(max_length=64)
    verdict = models.CharField(max_length=20, choices=Verdict.choices)
    option = models.CharField(max_length=10, blank=True)
    reason = models.TextField(blank=True)
    decided_at = models.DateTimeField()

    class Meta:
        db_table = "sima_gate_decision"
        ordering = ("run", "decided_at")
        constraints = (models.UniqueConstraint(fields=("run", "gate", "digest", "decided_at"), name="uniq_gate_decision"),)


class ApprovedIdentity(models.Model):
    """الهوية المعتمدة لإصدار: تُكتب مرة عند اعتماد المالك للدليل، ولا تُعدَّل بعده إلا بإعادة المزامنة نفسها."""
    run = models.OneToOneField(Run, on_delete=models.PROTECT, related_name="identity")
    approval = models.OneToOneField(GateDecision, on_delete=models.PROTECT, related_name="identity")
    concept_id = models.CharField(max_length=20)
    direction_id = models.CharField(max_length=10)
    direction_name = models.CharField(max_length=200)
    direction_idea = models.TextField()
    colors = models.JSONField()          # ألوان الاتجاه الأصلية
    roles_light = models.JSONField()
    roles_dark = models.JSONField()
    scales = models.JSONField()
    fonts = models.JSONField()
    numerals = models.CharField(max_length=4)
    radius = models.PositiveSmallIntegerField()
    strategy = models.JSONField()
    checks_passed = models.PositiveSmallIntegerField()
    checks_total = models.PositiveSmallIntegerField()
    book_digest = models.CharField(max_length=64)
    package_path = models.CharField(max_length=400)
    approved_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sima_approved_identity"
        ordering = ("-approved_at",)
        verbose_name_plural = "approved identities"

    def __str__(self) -> str:
        return f"{self.run} · {self.direction_id}"


class AssetKind(models.TextChoices):
    MARK = "mark", "العلامة"
    TOKENS = "tokens", "tokens"
    FONT = "font", "خط"
    PATTERN = "pattern", "نمط"
    ICON = "icon", "أيقونة"
    APPLICATION = "application", "تطبيق"
    SCREEN = "screen", "شاشة منتج"
    REVEAL = "reveal", "عرض الكشف"
    BOOK = "book", "دليل الهوية"
    MOTION = "motion", "حركة"
    DOC = "doc", "وثيقة"


class Asset(models.Model):
    """ملف من حزمة الهوية المعتمدة ببصمته؛ النص الصغير (≤ 512 KB) يُحفظ كاملًا ليبقى في القاعدة حتى لو ضاع الملف."""
    identity = models.ForeignKey(ApprovedIdentity, on_delete=models.CASCADE, related_name="assets")
    path = models.CharField(max_length=300)
    kind = models.CharField(max_length=12, choices=AssetKind.choices)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    media_type = models.CharField(max_length=80)
    content = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "sima_asset"
        ordering = ("identity", "path")
        constraints = (models.UniqueConstraint(fields=("identity", "path"), name="uniq_asset_path"),)
