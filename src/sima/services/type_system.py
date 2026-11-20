"""نظام الطباعة: تغطية الخط للحروف المطلوبة، والوزن، والترخيص، وسلّم الأحجام. الخطوط محلية من fonts/ بترخيص OFL فقط."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont

from ..domain.identity import CheckReport, TypeChoice

ARABIC = [chr(c) for c in range(0x0621, 0x063B)] + [chr(c) for c in range(0x0641, 0x064B)]
ARABIC_DIGITS = [chr(c) for c in range(0x0660, 0x066A)]
LATIN = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [chr(c) for c in range(ord("a"), ord("z") + 1)]
DIGITS = [str(i) for i in range(10)]
PUNCT = ["،", "؛", "؟", ".", ":", "(", ")", "-", "«", "»"]
RATIO = 1.25
BASE_PX = 16
SCALE = {"caption": -2, "small": -1, "body": 0, "lead": 1, "h4": 2, "h3": 3, "h2": 4, "h1": 5, "display": 6}
SCALE_AR = {"caption": "تعليق", "small": "صغير", "body": "نص", "lead": "مقدّمة", "h4": "عنوان 4", "h3": "عنوان 3",
            "h2": "عنوان 2", "h1": "عنوان 1", "display": "عرض"}


@lru_cache(maxsize=16)
def _font(path: str) -> TTFont:
    return TTFont(path, lazy=True)


def cmap_chars(path: Path) -> set[str]:
    return {chr(c) for c in _font(str(path)).getBestCmap()}


def family_name(path: Path) -> str:
    name = _font(str(path))["name"]
    return str(name.getDebugName(16) or name.getDebugName(1) or path.stem)


def weight_range(path: Path) -> tuple[int, int]:
    tt = _font(str(path))
    if "fvar" in tt:
        for a in tt["fvar"].axes:
            if a.axisTag == "wght":
                return int(a.minValue), int(a.maxValue)
    w = int(tt["OS/2"].usWeightClass)
    return w, w


def license_file(fonts_dir: Path, font_file: str) -> Path | None:
    """ملف OFL المرافق: OFL-<العائلة>.txt حيث العائلة بادئة اسم الملف."""
    stem = font_file.split("[", maxsplit=1)[0].split("-", maxsplit=1)[0].split(".", maxsplit=1)[0]
    for p in fonts_dir.glob("OFL-*.txt"):
        if stem.lower().startswith(p.stem[4:].lower()) or p.stem[4:].lower().startswith(stem.lower()):
            return p
    return None


def check_type(fonts_dir: Path, role_ar: str, choice: TypeChoice, numerals: str, rep: CheckReport) -> None:
    path = fonts_dir / choice.font
    if not path.is_file() or "/" in choice.font or ".." in choice.font:
        rep.add(f"خط {role_ar}", False, f"غير موجود في fonts/: {choice.font}")
        return
    lic = license_file(fonts_dir, choice.font)
    rep.add(f"ترخيص خط {role_ar}", lic is not None, lic.name if lic else "لا ملف OFL مرافق")
    chars = cmap_chars(path)
    need = {"العربية": ARABIC, "علامات الترقيم": PUNCT, "اللاتينية": LATIN,
            "الأرقام": ARABIC_DIGITS if numerals == "arab" else DIGITS}
    for label, req in need.items():
        missing = [c for c in req if c not in chars]
        rep.add(f"تغطية {label} في خط {role_ar}", not missing, "كاملة" if not missing else "ينقص: " + " ".join(missing[:12]),
                blocking=label != "اللاتينية")
    lo, hi = weight_range(path)
    ok = lo <= choice.weight <= hi if lo != hi else abs(choice.weight - lo) <= 100
    rep.add(f"وزن خط {role_ar}", ok, f"{choice.weight} ضمن {lo}–{hi}" if ok else f"{choice.weight} خارج {lo}–{hi}")


def type_scale(base: int = BASE_PX, ratio: float = RATIO) -> dict[str, dict[str, float]]:
    """أحجام بالبكسل والـrem وارتفاع السطر: 1.7 للنص العربي و1.3 للعناوين."""
    out = {}
    for name, step in SCALE.items():
        px = max(12.0, round(base * ratio ** step, 1))  # لا نص عربي تحت 12 بكسل
        out[name] = {"px": px, "rem": round(px / base, 4), "line": 1.3 if step >= 2 else 1.7}
    return out
