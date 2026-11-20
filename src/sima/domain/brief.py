"""موجز العلامة: كيان ثابت يُقرأ من YAML ويُهشَّر لمفتاح التشغيل."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .identity import IdentitySpec, PalettePolicy, Scope


@dataclass(frozen=True)
class Taste:
    feeling: str
    likes: tuple[str, ...] = ()
    dislikes: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class PaletteSpec:
    paper: str = "#FFFFFF"
    ink: str = "#000000"
    brand: str = "#000000"
    accent: str | None = None
    extra: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CloudSpec:
    """إذن المشروع بما يخرج من الجهاز. الغياب منع: مشروع لم يأذن موجزه لا يُستدعى له شيء سحابي ولو فُعّل الاستدعاء في .env.
    إذن لا مُدخل تصميم: لا يدخل مفتاح التشغيل، فتبديله لا يفتح إصدارًا جديدًا."""
    model: bool = False  # الاستدعاء الآلي للنموذج (`claude -p`) حين ينتظره الخط


@dataclass(frozen=True)
class Brief:
    project: str
    name_ar: str
    name_short: str | None
    name_latin: str | None
    sector: str
    audience: str
    purpose: str
    archetype: str
    three_words: tuple[str, ...]
    taste: Taste
    palette: PaletteSpec
    contexts: tuple[str, ...]
    wordmark_font: str = "ReemKufi[wght].ttf"
    wordmark_weight: int = 700
    seed: int = 1
    language: str = "ar"
    source_path: str | None = None
    identity: IdentitySpec = field(default_factory=IdentitySpec)
    cloud: CloudSpec = field(default_factory=CloudSpec)
    product: str | None = None  # شرح المنتج بالتفصيل (ما يفعله ولمن وما ليس هو) لمن يرسم من خارج الخط؛ مُدخل تصميم يدخل المفتاح

    def hash(self) -> str:
        data = asdict(self)
        if self.product is None:  # الحقل أُضيف لاحقًا: غيابه لا يغيّر مفاتيح الإصدارات القائمة
            data.pop("product", None)
        data.pop("source_path", None)
        data.pop("seed", None)
        data.pop("cloud", None)
        if self.identity == IdentitySpec():  # موجزات الشعار وحده تحتفظ بمفاتيحها القديمة
            data.pop("identity", None)
        elif self.identity.adopt is None:  # الحقل أُضيف لاحقًا: غيابه لا يغيّر مفاتيح الإصدارات القائمة
            data["identity"].pop("adopt", None)
        if "identity" in data and self.identity.designer is None:  # كذلك: غيابه لا يغيّر مفاتيح الإصدارات القائمة
            data["identity"].pop("designer", None)
        if "identity" in data and self.identity.lockup_word is None:  # كذلك
            data["identity"].pop("lockup_word", None)
        if "identity" in data and self.identity.directions is None:  # كذلك
            data["identity"].pop("directions", None)
        if "identity" in data and self.identity.fonts is None:  # كذلك
            data["identity"].pop("fonts", None)
        if "identity" in data and self.identity.night is None:  # كذلك
            data["identity"].pop("night", None)
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]

    @property
    def wordmark_text(self) -> str:
        return self.name_short or self.name_ar


def _tuple(v) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return (v,)
    return tuple(str(x) for x in v)


def brief_from_dict(d: dict, source: str | None = None) -> Brief:
    taste = d.get("taste", {}) or {}
    pal = d.get("palette", {}) or {}
    raw_extra = pal.get("extra") or {}
    pairs = raw_extra.items() if isinstance(raw_extra, dict) else (tuple(x) for x in raw_extra)  # موجز YAML أو brief.json المجمّد
    extra = tuple((str(k), str(v)) for k, v in sorted(pairs))
    return Brief(
        project=str(d["project"]),
        name_ar=str(d["name_ar"]),
        name_short=d.get("name_short"),
        name_latin=d.get("name_latin"),
        sector=str(d.get("sector", "")),
        audience=str(d.get("audience", "")),
        purpose=str(d.get("purpose", "")),
        archetype=str(d.get("archetype", "")),
        three_words=_tuple(d.get("three_words")),
        taste=Taste(
            feeling=str(taste.get("feeling", "")),
            likes=_tuple(taste.get("likes")),
            dislikes=_tuple(taste.get("dislikes")),
            avoid=_tuple(taste.get("avoid")),
        ),
        palette=PaletteSpec(
            paper=str(pal.get("paper", "#FFFFFF")),
            ink=str(pal.get("ink", "#000000")),
            brand=str(pal.get("brand", "#000000")),
            accent=pal.get("accent"),
            extra=extra,
        ),
        contexts=_tuple(d.get("contexts")),
        wordmark_font=str(d.get("wordmark_font", "ReemKufi[wght].ttf")),
        wordmark_weight=int(d.get("wordmark_weight", 700)),
        seed=int(d.get("seed", 1)),
        language=str(d.get("language", "ar")),
        source_path=source,
        identity=_identity(d.get("identity")),
        cloud=_cloud(d.get("cloud")),
        product=(" ".join(str(d["product"]).split()) or None) if d.get("product") else None,
    )


def _cloud(d: object) -> CloudSpec:
    """`cloud: {model: true}` وحدها تأذن؛ أي صيغة أخرى (نص، رقم، `cloud: true`) تبقى منعًا فلا يُفتح الإذن بخطأ كتابة."""
    return CloudSpec(model=isinstance(d, dict) and d.get("model") is True)


def _fonts(d: object) -> dict | None:
    """`identity.fonts`: خطّا الهوية المعلنان، لكلٍّ ملف في fonts/ ووزنه؛ كلاهما لازم، وما سواهما خطأ يُرفض."""
    if d is None:
        return None
    if not isinstance(d, dict) or set(d) != {"heading", "body"}:
        raise ValueError("identity.fonts: heading وbody معًا، لكلٍّ {font, weight}")
    out: dict[str, dict] = {}
    for role in ("heading", "body"):
        spec = d[role]
        try:
            font, weight = str(spec["font"]), int(spec["weight"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"identity.fonts.{role}: font (اسم ملف) وweight (عدد)") from e
        if not font.endswith(".ttf") or "/" in font or "\\" in font or ".." in font:
            raise ValueError(f"identity.fonts.{role}: اسم ملف .ttf من fonts/ بلا مسار")
        if not 100 <= weight <= 1000:
            raise ValueError(f"identity.fonts.{role}: وزن بين 100 و1000")
        out[role] = {"font": font, "weight": weight}
    return out


NIGHT_KEYS = ("paper", "ink", "brand", "accent", "neutral", "success", "warning", "error", "info")
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def _night(d: object) -> dict | None:
    """`identity.night`: ليل الهوية من اتجاه معتمد آخر؛ اسم مصدره وألوانه التسعة كلها، وما سواها خطأ يُرفض."""
    if d is None:
        return None
    if not isinstance(d, dict) or set(d) != {"name", "colors"} or not str(d["name"]).strip() or not isinstance(d["colors"], dict):
        raise ValueError("identity.night: name (مصدر الليل) وcolors (ألوان اتجاهه التسعة) معًا")
    colors = d["colors"]
    if set(colors) != set(NIGHT_KEYS):
        raise ValueError(f"identity.night.colors: المفاتيح التسعة كلها: {', '.join(NIGHT_KEYS)}")
    for k in NIGHT_KEYS:
        if not _HEX.fullmatch(str(colors[k])):
            raise ValueError(f"identity.night.colors.{k}: لون بصيغة #RRGGBB")
    return {"name": str(d["name"]).strip(), "colors": {k: str(colors[k]).upper() for k in NIGHT_KEYS}}


def _identity(d: dict | None) -> IdentitySpec:
    if not d:
        return IdentitySpec()
    inherit, adopt, designer = d.get("inherit_mark"), d.get("adopt"), d.get("designer")
    if designer not in (None, "external"):
        raise ValueError("identity.designer: القيمة الوحيدة المقبولة external")
    word = d.get("lockup_word")
    if word not in (None, "heading"):
        raise ValueError("identity.lockup_word: القيمة الوحيدة المقبولة heading (خط عناوين الاتجاه)")
    if word and not (adopt or designer):
        raise ValueError("identity.lockup_word يلزمه علامة من خارج الخط (identity.designer أو identity.adopt)")
    three = d.get("directions")
    if three not in (None, "three"):
        raise ValueError("identity.directions: القيمة الوحيدة المقبولة three (ثلاثة اتجاهات يختار منها المالك)")
    if three and not (adopt or designer):
        raise ValueError("identity.directions يلزمه علامة من خارج الخط (identity.designer أو identity.adopt)؛ الخط المرسوم يعرض ثلاثة دائمًا")
    fonts = _fonts(d.get("fonts"))
    if fonts and not (adopt or designer):
        raise ValueError("identity.fonts يلزمه علامة من خارج الخط (identity.designer أو identity.adopt)")
    return IdentitySpec(
        designer=designer,
        lockup_word=word,
        directions=three,
        fonts=fonts,
        night=_night(d.get("night")),
        scope=Scope(str(d.get("scope", "mark"))),
        palette_policy=PalettePolicy(str(d.get("palette_policy", "respect"))),
        inherit_mark=str(inherit) if inherit else None,
        icons=_tuple(d.get("icons")),
        adopt=str(adopt) if adopt else None,
    )


def load_frozen_brief(version_root: str | Path) -> Brief:
    """الموجز كما جُمّد في الإصدار (brief.json) لحظة تشغيله: ما اعتمده المالك فعلًا، لا ما عُدّل في briefs/ بعده."""
    import json

    data = json.loads((Path(version_root) / "brief.json").read_text(encoding="utf-8"))
    return brief_from_dict(data, source=data.get("source_path"))


def load_brief(path: str | Path) -> Brief:
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return brief_from_dict(data, source=str(p))
