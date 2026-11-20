"""tokens الهوية بأربع صيغ من مصدر واحد: CSS (فاتح وداكن)، وSCSS، وJSON بمعيار DTCG، وpreset لـTailwind."""
from __future__ import annotations

import json

from .type_system import type_scale

SPACE = {"0": 0, "1": 4, "2": 8, "3": 12, "4": 16, "5": 24, "6": 32, "7": 48, "8": 64}


def _kebab(k: str) -> str:
    return k.replace("_", "-")


def face_weight(fonts: dict[str, dict], role: str) -> str:
    """مدى وزن @font-face لخط الدور: عائلة بوجهين من ملفين ثابتين (Tajawal مثلًا) لكلٍّ وزنه، وإلا يطغى الأخير على الأوزان
    كلها؛ وملف واحد للعائلة (متغيّر أو ثابت) كما كان: 100 1000."""
    v = fonts[role]
    files = {x["file"] for x in fonts.values() if x["family"] == v["family"]}
    return str(v["weight"]) if len(files) > 1 else "100 1000"


def css(slug: str, system: dict, fonts: dict[str, dict], radius: int, numerals: str) -> str:
    """fonts: {"heading": {"family", "file", "weight"}, "body": {...}}؛ مسارات الخطوط نسبية إلى tokens/."""
    faces = []
    for f in sorted({(v["family"], v["file"], face_weight(fonts, role)) for role, v in fonts.items()}):
        faces.append(f'@font-face{{font-family:"{f[0]}";src:url("../fonts/{f[1]}") format("truetype");font-display:swap;'
                     f'font-weight:{f[2]}}}')
    lines = [f"/* tokens هوية {slug} — مولّدة من سِمة؛ لا تُعدَّل يدويًا. الأدوار فقط في الواجهة، والتدرجات للحالات الخاصة. */",
             *faces, ":root{", "  color-scheme:light;"]
    for k, v in system["light"].items():
        lines.append(f"  --{slug}-{_kebab(k)}:{v};")
    for name, sc in system["scales"].items():
        for step, v in sc.items():
            lines.append(f"  --{slug}-{name}-{step}:{v};")
    lines += [f'  --{slug}-font-heading:"{fonts["heading"]["family"]}",Tahoma,sans-serif;',
              f'  --{slug}-font-body:"{fonts["body"]["family"]}",Tahoma,sans-serif;',
              f"  --{slug}-weight-heading:{fonts['heading']['weight']};", f"  --{slug}-weight-body:{fonts['body']['weight']};",
              f"  --{slug}-numerals:{'arabic-indic' if numerals == 'arab' else 'decimal'};"]
    for name, v in type_scale().items():
        lines.append(f"  --{slug}-text-{name}:{v['rem']}rem;  --{slug}-leading-{name}:{v['line']};")
    for k, v in SPACE.items():
        lines.append(f"  --{slug}-space-{k}:{v}px;")
    lines += [f"  --{slug}-radius:{radius}px;", "}"]
    dark = [f"  --{slug}-{_kebab(k)}:{v};" for k, v in system["dark"].items()]
    lines += ['@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){', "  color-scheme:dark;", *dark, "}}",
              ':root[data-theme="dark"]{', "  color-scheme:dark;", *dark, "}", ""]
    return "\n".join(lines)


def scss(slug: str, system: dict) -> str:
    out = [f"// tokens هوية {slug} — مولّدة من سِمة"]
    out += [f"${slug}-{_kebab(k)}: {v};" for k, v in system["light"].items()]
    out += [f"${slug}-dark-{_kebab(k)}: {v};" for k, v in system["dark"].items()]
    for name, sc in system["scales"].items():
        out.append(f"${slug}-{name}: (" + ", ".join(f"{s}: {v}" for s, v in sc.items()) + ");")
    return "\n".join(out) + "\n"


def dtcg(slug: str, system: dict, fonts: dict[str, dict], radius: int) -> str:
    """Design Tokens Community Group: {"$type", "$value"}؛ تستورده Tokens Studio في Figma."""
    def col(v: str) -> dict:
        return {"$type": "color", "$value": v}
    doc = {
        "color": {name: {str(s): col(v) for s, v in sc.items()} for name, sc in system["scales"].items()},
        "role": {"light": {k: col(v) for k, v in system["light"].items()}, "dark": {k: col(v) for k, v in system["dark"].items()}},
        "font": {r: {"family": {"$type": "fontFamily", "$value": [v["family"], "Tahoma", "sans-serif"]},
                     "weight": {"$type": "fontWeight", "$value": v["weight"]}} for r, v in fonts.items()},
        "size": {k: {"$type": "dimension", "$value": f"{v['rem']}rem"} for k, v in type_scale().items()},
        "space": {k: {"$type": "dimension", "$value": f"{v}px"} for k, v in SPACE.items()},
        "radius": {"base": {"$type": "dimension", "$value": f"{radius}px"}},
    }
    return json.dumps({"$description": f"tokens هوية {slug} من سِمة", **doc}, ensure_ascii=False, indent=2) + "\n"


def tailwind(slug: str, system: dict, fonts: dict[str, dict]) -> str:
    colors = {name: {str(s): v for s, v in sc.items()} for name, sc in system["scales"].items()}
    roles = {_kebab(k): f"var(--{slug}-{_kebab(k)})" for k in system["light"]}
    sizes = {k: [f"{v['rem']}rem", {"lineHeight": str(v["line"])}] for k, v in type_scale().items()}
    preset = {"theme": {"extend": {"colors": {**colors, slug: roles},
                                   "fontFamily": {"heading": [fonts["heading"]["family"], "Tahoma", "sans-serif"],
                                                  "body": [fonts["body"]["family"], "Tahoma", "sans-serif"]},
                                   "fontSize": sizes}}}
    return (f"// preset لـTailwind من هوية {slug}: الأدوار تقرأ متغيرات tokens.css (فاتح وداكن)، والتدرجات قيم ثابتة.\n"
            f"module.exports = {json.dumps(preset, ensure_ascii=False, indent=2)};\n")
