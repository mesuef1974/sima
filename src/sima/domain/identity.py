"""الهوية الكاملة: نطاقها في الموجز، والمنصة الاستراتيجية، والاتجاهات، وبوابات المالك. كيانات ثابتة بلا منطق ثقيل."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Scope(StrEnum):
    MARK = "mark"  # الشعار وحده (السلوك القديم)
    CORE = "core"  # + استراتيجية ولون وطباعة ولغة بصرية وtokens ودليل
    FULL = "full"  # + أيقونات وتطبيقات وحركة ودليل PDF


class PalettePolicy(StrEnum):
    RESPECT = "respect"
    EVOLVE = "evolve"
    NEW = "new"


class Gate(StrEnum):
    STRATEGY = "strategy"
    DIRECTIONS = "directions"
    BOOK = "book"


GATE_AR = {Gate.STRATEGY: "المنصة الاستراتيجية", Gate.DIRECTIONS: "اتجاه الهوية", Gate.BOOK: "دليل الهوية"}
SCOPE_AR = {Scope.MARK: "علامة", Scope.CORE: "هوية أساسية", Scope.FULL: "هوية كاملة"}


@dataclass(frozen=True)
class IdentitySpec:
    scope: Scope = Scope.MARK
    palette_policy: PalettePolicy = PalettePolicy.RESPECT
    inherit_mark: str | None = None
    icons: tuple[str, ...] = ()
    adopt: str | None = None  # بيان علامة واتجاه اعتمدهما المالك خارج خط الرسم (مسار نسبي إلى مجلد الموجز)
    designer: str | None = None  # "external": السكتشات والمتجه من مصمّم خارجي، وسِمة تفحص وتبني (services/designer.py)
    # "heading": العلامة المعتمدة من خارج الخط رمز بلا كتابة الاسم، فيُشكَّل الاسم من خط عناوين الاتجاه ويُقفل مع الرمز
    lockup_word: str | None = None
    # "three": علامة من خارج الخط تُعرض عليها ثلاثة اتجاهات يختار منها المالك (قراره 2026-11-14 على «أوراق»): اتجاه التسليم
    # كما هو، واتجاهان يكتبهما نموذج الخط فوق العلامة نفسها؛ بوابة الاتجاه تصير قراره لا قاعدة المسار.
    directions: str | None = None
    # خطّا الهوية يعلنهما المالك (قراره 2026-11-15: Tajawal) فيغلبان type في اتجاه التسليم المعتمد من خارج الخط:
    # {"heading": {"font": ملف, "weight": وزن}, "body": {...}}. المصمّم لا يعلنهما؛ ويلزمهما علامة من خارج الخط.
    fonts: dict | None = None
    # ليل الهوية من اتجاه معتمد آخر (قرار المالك 2026-11-17 على «مسك»: نهار عودي وليل v5): {"name": مصدره, "colors": الألوان
    # التسعة لذلك الاتجاه}. النهار والمقاييس من اتجاه الإصدار، وأدوار الليل وحدها تُشتق من هذه الألوان (`color_system.with_night`).
    night: dict | None = None

    @property
    def enabled(self) -> bool:
        return self.scope is not Scope.MARK

    @property
    def full(self) -> bool:
        return self.scope is Scope.FULL


@dataclass(frozen=True)
class Trait:
    trait: str
    means: str
    not_: str


@dataclass(frozen=True)
class Strategy:
    positioning: str
    promise: str
    personality: tuple[Trait, ...]
    voice_do: tuple[str, ...]
    voice_dont: tuple[str, ...]
    samples: dict[str, str]
    tagline: str
    imagery: str = ""


@dataclass(frozen=True)
class TypeChoice:
    font: str
    weight: int


@dataclass(frozen=True)
class Direction:
    id: str
    name: str
    idea: str
    colors: dict[str, str]  # paper, ink, brand, accent, neutral, success, warning, error, info
    accent_informational: bool
    heading: TypeChoice
    body: TypeChoice
    numerals: str  # arab | latn
    motif_file: str
    motif_rule: str
    radius: int = 4


@dataclass(frozen=True)
class IdentityDecision:
    gate: Gate
    digest: str
    verdict: str  # approved | revise | rejected
    option: str
    reason: str
    at: str


@dataclass
class Check:
    """نتيجة فحص حتمي واحد يُعرض في لوحة الاتجاه والدليل."""

    name: str
    ok: bool
    detail: str
    blocking: bool = True


@dataclass
class CheckReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, *, blocking: bool = True) -> None:
        self.checks.append(Check(name, ok, detail, blocking))

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.blocking)

    @property
    def failures(self) -> list[str]:
        return [f"{c.name}: {c.detail}" for c in self.checks if c.blocking and not c.ok]
