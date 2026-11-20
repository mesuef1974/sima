"""تطبيق الاتجاه المعتمد كاملًا على رموز التطبيق المستلم (قرار المالك ق1، 2026-11-14؛ ت2 من مراجعة الأتمتة).

التسليم كان يبدّل الشعار ولون العلامة النهاري وحدهما، فيبقى التطبيق هجينًا بين هوية قديمة وجديدة والبطاقة لا تذكر الفرق.
هنا خريطة لكل هدف في `deliver_targets.yaml` (`apply_identity:` اسم متغير التطبيق ثم دور الهوية) تُطبَّق على `tokens.css`
التطبيق بحسب وضع الكتلة (نهارية أو ليلية)، وتعيد كل ما تغيّر بقيمتيه وكل متغير لوني لم تشمله. دوال صافية بلا آثار جانبية.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

DARK = re.compile(r"prefers-color-scheme:\s*dark|data-theme=[\"']dark[\"']|(?<![\w-])html\.dark(?![\w-])")
_DECL = re.compile(r"^(\s*)--([A-Za-z0-9_-]+)(\s*:\s*)([^;]+);(.*)$")
_ONE = re.compile(r"(\s*)--([A-Za-z0-9_-]+)(\s*:\s*)([^;]+);")
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_RGB = re.compile(r"(rgba?\(\s*)(\d{1,3})(\s*,\s*|\s+)(\d{1,3})(\s*,\s*|\s+)(\d{1,3})\b")
_HEADER = re.compile(r"(هوية\s+«[^»]*»\s+v)\d+(\s+من سِمة)")
_PX = re.compile(r"^(\d+(?:\.\d+)?)px$")
_ARG = r"(?:[^,()]|\([^()]*\))+?"  # قيمة مفردة أو دالة بقوسين غير متداخلين (`var(--day-ink)`)
_PAIR = re.compile(rf"^light-dark\(\s*({_ARG})\s*,\s*({_ARG})\s*\)$")
_REF = re.compile(r"^var\(\s*--[A-Za-z0-9_-]+\s*(?:,[^()]*)?\)$")
MODES = ("light", "dark")
MODE_AR = {"light": "نهارًا", "dark": "ليلًا"}


@dataclass(frozen=True)
class Rule:
    """متغير في التطبيق يأخذ دورًا من الهوية؛ دور فارغ لوضعٍ يترك قيمة التطبيق فيه كما هي، و`times` مضاعِف للأبعاد."""
    var: str
    light: str = ""
    dark: str = ""
    times: float = 1


@dataclass(frozen=True)
class Change:
    var: str
    mode: str  # light | dark
    old: str
    new: str


@dataclass(frozen=True)
class Applied:
    css: str
    changes: tuple[Change, ...] = ()  # كل متغير تغيّرت قيمته، مرة لكل وضع (الكتلتان الليليتان المتطابقتان مرة واحدة)
    unmapped: tuple[str, ...] = ()  # متغيرات لونية في رموز التطبيق لم تشملها الخريطة
    unfollowed: tuple[str, ...] = ()  # ثلاثيات rgb تحمل قيمة قديمة ولم تُتبع لأن أكثر من متغير يحملها بقيم جديدة مختلفة


def parse_rules(raw: Mapping) -> tuple[Rule, ...]:
    """خريطة الهدف كما في YAML: `var: role`، أو `var: {light: role, dark: role}` لما يختلف بين الوضعين (الغائب يُترك)،
    أو `var: {role: role, times: 2}` للأبعاد. الخطأ في الصيغة يُرفع بنصّه: خريطة معطوبة لا تُطبَّق نصفها."""
    rules: list[Rule] = []
    for key, value in raw.items():
        var = str(key).lstrip("-")
        if isinstance(value, str):
            rules.append(Rule(var, value.strip(), value.strip()))
            continue
        if not isinstance(value, Mapping) or not value or set(value) - {"light", "dark", "role", "times"}:
            raise ValueError(f"apply_identity: صيغة غير مفهومة للمتغير {var}: {value!r}")
        both = str(value.get("role") or "").strip()
        light, dark = (str(value.get(m) or both).strip() for m in MODES)
        try:
            times = float(value.get("times", 1))
        except (TypeError, ValueError):
            raise ValueError(f"apply_identity: مضاعِف غير رقمي للمتغير {var}: {value.get('times')!r}") from None
        if not (light or dark) or times <= 0:
            raise ValueError(f"apply_identity: المتغير {var} بلا دور أو بمضاعِف غير موجب: {value!r}")
        rules.append(Rule(var, light, dark, times))
    return tuple(rules)


def identity_roles(tokens_css: str, slug: str) -> dict[str, dict[str, str]]:
    """أدوار الهوية من `package/identity/tokens/tokens.css`: النهارية من كتلة `:root` الأولى، والليلية فوقها من كتلة
    `:root[data-theme="dark"]` (ما لم تُعِد تعريفه الليلية يبقى بقيمته النهارية، كما يقرؤه المتصفح)."""
    def block(opening: str) -> dict[str, str]:
        start = tokens_css.find(opening)
        if start < 0:
            return {}
        body = tokens_css[start + len(opening): tokens_css.find("}", start)]
        return {m.group(1): m.group(2).strip() for m in re.finditer(rf"--{re.escape(slug)}-([A-Za-z0-9-]+)\s*:\s*([^;]+);", body)}

    light = block(":root{")
    return {"light": light, "dark": {**light, **block(':root[data-theme="dark"]{')}}


def light_dark(value: str) -> tuple[str, str] | None:
    """قيمتا `light-dark(نهارية, ليلية)` إن كُتب المتغير بهما في تعريف واحد (رموز «مسك»)، أو None لقيمة مفردة."""
    m = _PAIR.match(value.strip())
    return (m.group(1), m.group(2)) if m else None


def is_ref(value: str) -> bool:
    """قيمة تحيل إلى متغير آخر (`var(--day-ink)`): اختيار المشروع (سماته العشر في «مسك»)، فلا يكتب التسليم فوقها لونًا خامًا."""
    return bool(_REF.match(value.strip()))


def line_decls(line: str) -> list[re.Match]:
    """كل تعريفات المتغيرات المتتالية في سطر يبدأ بتعريف (`--a: 1; --b: 2;`)؛ يقف عند أول ما ليس تعريفًا (تعليق مثلًا)."""
    out: list[re.Match] = []
    if not line.lstrip().startswith("--"):
        return out
    pos = 0
    while (m := _ONE.match(line, pos)):
        out.append(m)
        pos = m.end()
    return out


def _value(rule: Rule, role: str, roles: Mapping[str, str], mode: str) -> str:
    if role not in roles:
        raise ValueError(f"apply_identity: الدور «{role}» للمتغير --{rule.var} ({MODE_AR[mode]}) ليس في رموز الهوية المعتمدة.")
    value = roles[role]
    if rule.times != 1:
        m = _PX.match(value)
        if not m:
            raise ValueError(f"apply_identity: المضاعِف للمتغير --{rule.var} يلزمه دور ببُعد px، والدور «{role}» قيمته {value}.")
        return f"{float(m.group(1)) * rule.times:g}px"
    return value.lower() if _HEX.fullmatch(value) else value


def _triple(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def apply_roles(css: str, rules: tuple[Rule, ...], roles: Mapping[str, Mapping[str, str]], version: int) -> Applied:
    """يكتب قيمة الدور في كل تعريف لمتغير مذكور في الخريطة، بوضع كتلته (ليلية إن حملت ترويستها أو ترويسة ما يحيط بها
    `prefers-color-scheme: dark` أو `data-theme="dark"`)، وتعريف بـ`light-dark(أ, ب)` تأخذ قيمتاه دورَي الوضعين، وثلاثية `rgb` لقيمة قديمة في الكتلة نفسها تتبعها (الشبكة والظلال)،
    وترويسة «هوية «…» vN من سِمة» تأخذ رقم الإصدار. حتمي وidempotent: تطبيقه على ناتجه لا يغيّر شيئًا."""
    by_var = {r.var: r for r in rules}
    for r in rules:  # دور غائب عن الهوية خطأ في الخريطة ولو لم يرد متغيره في الملف: يُرفع قبل أي كتابة
        for mode in MODES:
            if getattr(r, mode):
                _value(r, getattr(r, mode), roles[mode], mode)
    lines = css.split("\n")
    stack: list[tuple[int, bool]] = []  # الكتل المفتوحة: (رقمها، هل هي ليلية)
    block_of: list[int] = []  # رقم الكتلة الداخلية لكل سطر (0 خارج الكتل)
    dark_of: list[bool] = []  # هل السطر داخل كتلة ليلية
    swaps: dict[int, dict[str, set[str]]] = {}  # لكل كتلة: القيمة القديمة ← القيم الجديدة لمن يحملها من متغيرات الخريطة
    changes: list[Change] = []
    seen_vars: list[str] = []
    counter = 0
    for i, line in enumerate(lines):
        block_of.append(stack[-1][0] if stack else 0)
        dark_of.append(bool(stack) and stack[-1][1])
        decls = line_decls(line) if stack else []
        if decls:
            mode = "dark" if stack[-1][1] else "light"
            new_line = line
            for m in reversed(decls):  # من الآخر حتى لا تنزاح مواضع ما قبله
                var, old = m.group(2), m.group(4).strip()
                if var not in seen_vars:
                    seen_vars.append(var)
                rule = by_var.get(var)
                pair = light_dark(old) if rule else None
                if rule and pair:  # تعريف واحد بقيمتين: كل قيمة تأخذ دور وضعها، وما لا دور له في وضعه أو أحال إلى متغير يبقى
                    parts = list(pair)
                    for k, md in enumerate(MODES):
                        if not getattr(rule, md) or is_ref(parts[k]):
                            continue
                        new = _value(rule, getattr(rule, md), roles[md], md)
                        if new.lower() != parts[k].lower():
                            if (c := Change(var, md, parts[k], new)) not in changes:
                                changes.append(c)
                            parts[k] = new
                    if tuple(parts) != pair:
                        new_line = new_line[:m.start(4)] + f"light-dark({parts[0]}, {parts[1]})" + new_line[m.end(4):]
                    continue
                role = getattr(rule, mode) if rule else ""
                if rule and role:
                    new = _value(rule, role, roles[mode], mode)
                    if _HEX.fullmatch(old):
                        swaps.setdefault(stack[-1][0], {}).setdefault(old.lower(), set()).add(new)
                    if new.lower() != old.lower():
                        new_line = new_line[:m.start(4)] + new + new_line[m.end(4):]
                        if (c := Change(var, mode, old, new)) not in changes:
                            changes.append(c)
            lines[i] = new_line
        delta = line.count("{") - line.count("}")
        for _ in range(delta):
            counter += 1
            stack.append((counter, bool(DARK.search(line)) or any(d for _, d in stack)))
        for _ in range(-delta):
            if stack:
                stack.pop()

    unfollowed: list[str] = []
    for i, line in enumerate(lines):
        decls = line_decls(line)
        if not decls or any(m.group(2) in by_var for m in decls) or block_of[i] not in swaps:
            continue
        fixed, ambiguous = _follow(line, swaps[block_of[i]])
        if ambiguous:
            for m in decls:
                if f"--{m.group(2)}" not in unfollowed:
                    unfollowed.append(f"--{m.group(2)}")
        if fixed != line:
            for before, after in zip(decls, line_decls(fixed), strict=True):
                if before.group(4).strip() != after.group(4).strip():
                    c = Change(before.group(2), "dark" if dark_of[i] else "light", before.group(4).strip(), after.group(4).strip())
                    if c not in changes:
                        changes.append(c)
            lines[i] = fixed

    out = "\n".join(lines)
    out = _HEADER.sub(lambda h: f"{h.group(1)}{version}{h.group(2)}", out, count=1)
    unmapped = tuple(f"--{v}" for v in seen_vars if v not in by_var and not v.startswith("color-mark-") and _is_color(css, v)
                     and not any(c.var == v for c in changes))
    return Applied(out, tuple(changes), unmapped, tuple(unfollowed))


def _follow(line: str, table: Mapping[str, set[str]]) -> tuple[str, bool]:
    """ثلاثيات `rgb` في السطر التي تحمل قيمة قديمة لمتغير من الخريطة تأخذ قيمته الجديدة؛ ما حمله أكثر من متغير بقيم جديدة
    مختلفة يبقى ويُبلَّغ (الثاني في الناتج)."""
    ambiguous = False

    def swap(t: re.Match) -> str:
        nonlocal ambiguous
        old = "#{:02x}{:02x}{:02x}".format(*(int(t.group(k)) for k in (2, 4, 6)))
        news = table.get(old, set())
        if len(news) != 1:
            ambiguous = ambiguous or len(news) > 1
            return t.group(0)
        new = next(iter(news))
        if not _HEX.fullmatch(new) or new.lower() == old:
            return t.group(0)
        r, g, b = _triple(new)
        return f"{t.group(1)}{r}{t.group(3)}{g}{t.group(5)}{b}"

    return _RGB.sub(swap, line), ambiguous


def _is_color(css: str, var: str) -> bool:
    return any(_HEX.search(m.group(1)) or _RGB.search(m.group(1))
               for m in re.finditer(rf"--{re.escape(var)}\s*:\s*([^;]+);", css))


def diff_note(applied: Applied, version: int) -> str:
    """سطر البطاقة: كل متغير تغيّر بقيمتيه في وضعه، وما لم تشمله الخريطة، وما لم يُتبع؛ لا «المطلوب التحقق فقط» وقيم التطبيق تغيّرت."""
    if not applied.changes:
        head = f"tokens.css: رموز التطبيق تطابق الاتجاه المعتمد (v{version}) بحسب خريطة apply_identity؛ لا قيمة تغيّرت."
    else:
        head = (f"tokens.css: طُبّق الاتجاه المعتمد (v{version}) على رموز التطبيق بقرار المالك (خريطة apply_identity في سِمة)؛ "
                f"{len(applied.changes)} قيمة تغيّرت:")
    rows = [f"  - {MODE_AR[c.mode]} `--{c.var}`: {c.old} صار {c.new}" for c in applied.changes]
    if applied.unmapped:
        rows.append("  - متغيرات لونية لم تشملها الخريطة وبقيت بقيمها: " + "، ".join(f"`{v}`" for v in applied.unmapped))
    if applied.unfollowed:
        rows.append("  - ثلاثيات rgb لم تُتبع (قيمتها القديمة يحملها أكثر من متغير): " + "، ".join(f"`{v}`" for v in applied.unfollowed))
    if applied.changes:
        rows.append("  - راجع تعليقات tokens.css التي تذكر قيمًا قديمة، وشغّل اختبار التباين (styles/contrast.test.ts).")
    return "\n".join([head, *rows])


# ---------- الورق: print.css وثوابت مولّد Word (ما طلبه المالك بعد دمج «أوراق» v7) ----------
# الورقة المطبوعة تثبّت ألوانها بنفسها (متغيرات `.sheet` وثوابت `ooxml.py`) فلا تتبع tokens.css؛ تسليم v7 غيّر رموز التطبيق وحدها
# فسقطت ستة اختبارات طباعة في «أوراق» وأصلحتها جلستها بيدها. هنا تتبع الورقة الاتجاه بالخريطة نفسها نهارًا دائمًا.
_PAPER_KEYS = {"css", "constants", "skip"}


@dataclass(frozen=True)
class PaperMap:
    css: tuple[str, ...] = ()  # ملفات CSS تطبَّق عليها خريطة apply_identity بقيم الوضع النهاري
    constants: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()  # (ملف، ((ثابت، دور)، ...)): `NAME = "RRGGBB"`
    skip: tuple[str, ...] = ()  # متغيرات الورقة التي تبقى بقيمتها: الورقة بيضاء بقصد فلا تتبع ورق الاتجاه وسطوحه


@dataclass(frozen=True)
class PaperCss:
    css: str
    changes: tuple[Change, ...] = ()
    literals: tuple[Change, ...] = ()  # ألوان ثابتة خارج المتغيرات تبعت متغيرًا تغيّر (var = القيمة القديمة نفسها)
    stray: tuple[str, ...] = ()  # ألوان ثابتة لا تطابق قيمة أي متغير في الملف: لا تتبع الاتجاه ويقرّرها مشروعها


def parse_paper(raw: Mapping) -> PaperMap:
    """`apply_paper:` في deliver_targets.yaml: `css: [مسار]` و`constants: {مسار: {ثابت: دور}}`. الخطأ في الصيغة يُرفع بنصّه."""
    if not isinstance(raw, Mapping) or set(raw) - _PAPER_KEYS:
        raise ValueError(f"apply_paper: صيغة غير مفهومة: {raw!r}")
    css = raw.get("css") or []
    if not isinstance(css, list) or not all(isinstance(p, str) and p for p in css):
        raise ValueError(f"apply_paper: css قائمة مسارات: {css!r}")
    skip = raw.get("skip") or []
    if not isinstance(skip, list) or not all(isinstance(v, str) and v for v in skip):
        raise ValueError(f"apply_paper: skip قائمة أسماء متغيرات: {skip!r}")
    consts = raw.get("constants") or {}
    if not isinstance(consts, Mapping):
        raise ValueError(f"apply_paper: constants خريطة مسار إلى ثوابت: {consts!r}")
    out = []
    for path, table in consts.items():
        if not isinstance(table, Mapping) or not table or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in table.items()):
            raise ValueError(f"apply_paper: ثوابت {path} خريطة اسم إلى دور: {table!r}")
        out.append((str(path), tuple((str(k), v.strip()) for k, v in table.items())))
    return PaperMap(tuple(css), tuple(out), tuple(v.lstrip('-') for v in skip))


def apply_paper_css(css: str, rules: tuple[Rule, ...], roles: Mapping[str, Mapping[str, str]], version: int,
                    skip: tuple[str, ...] = ()) -> PaperCss:
    """متغيرات الورقة بقيم الوضع النهاري من الخريطة نفسها (الورقة لا تتبع الوضع الداكن)، وكل لون ثابت خارج المتغيرات يحمل القيمة
    القديمة لمتغير تغيّر يأخذ قيمته الجديدة؛ وما لا يطابق قيمة أي متغير يُسرد ولا يُمسّ. `skip` متغيرات تبقى بقيمتها. حتمي وidempotent."""
    light_only = tuple(Rule(r.var, r.light, "", r.times) for r in rules if r.light and r.var not in skip)
    applied = apply_roles(css, light_only, {"light": roles["light"], "dark": roles["light"]}, version)
    table: dict[str, set[str]] = {}
    for c in applied.changes:
        if _HEX.fullmatch(c.old) and _HEX.fullmatch(c.new):
            table.setdefault(c.old.lower(), set()).add(c.new.lower())
    lines = applied.css.split("\n")
    literals: list[Change] = []
    for i, line in enumerate(lines):
        if _DECL.match(line):
            continue

        def swap(h: re.Match) -> str:
            news = table.get(h.group(0).lower(), set())
            if len(news) != 1:
                return h.group(0)
            new = next(iter(news))
            if (c := Change(h.group(0).lower(), "light", h.group(0).lower(), new)) not in literals:
                literals.append(c)
            return new

        lines[i] = _HEX.sub(swap, line)
    out = "\n".join(lines)
    held = {m.group(1).strip().lower() for m in re.finditer(r"--[A-Za-z0-9_-]+\s*:\s*([^;]+);", out) if _HEX.fullmatch(m.group(1).strip())}
    stray: list[str] = []
    for line in out.split("\n"):
        if _DECL.match(line):
            continue
        for h in _HEX.findall(line):
            if h.lower() not in held and h.lower() not in stray:
                stray.append(h.lower())
    return PaperCss(out, applied.changes, tuple(literals), tuple(stray))


def apply_constants(text: str, table: tuple[tuple[str, str], ...], roles_light: Mapping[str, str]) -> tuple[str, tuple[Change, ...]]:
    """ثوابت الألوان في ملف بايثون (`NAME = "RRGGBB"`) تأخذ قيم أدوارها النهارية بحروف كبيرة بلا `#`. ثابت غائب عن الملف أو دور غائب
    عن الهوية يوقف التسليم باسمه: خريطة معطوبة لا تُطبَّق نصفها."""
    changes: list[Change] = []
    for name, role in table:
        if role not in roles_light or not _HEX.fullmatch(roles_light[role]):
            raise ValueError(f"apply_paper: الدور «{role}» للثابت {name} ليس لونًا سداسيًا في رموز الهوية المعتمدة.")
        new = roles_light[role].lstrip("#").upper()
        pat = re.compile(rf'^({re.escape(name)}\s*=\s*")([0-9A-Fa-f]{{6}})(")', re.MULTILINE)
        m = pat.search(text)
        if not m:
            raise ValueError(f"apply_paper: الثابت {name} غير موجود في الملف.")
        if m.group(2).upper() != new:
            changes.append(Change(name, "light", m.group(2).upper(), new))
            text = pat.sub(lambda x, v=new: f"{x.group(1)}{v}{x.group(3)}", text, count=1)
    return text, tuple(changes)


def paper_note(path: str, changes: tuple[Change, ...], literals: tuple[Change, ...] = (), stray: tuple[str, ...] = ()) -> str:
    if not changes and not literals:
        head = f"{path}: ألوان الورق تطابق الاتجاه المعتمد بحسب خريطة apply_paper؛ لا قيمة تغيّرت."
    else:
        head = f"{path}: طُبّق الاتجاه المعتمد على ألوان الورق بخريطة apply_paper (نهاريًا دائمًا)؛ {len(changes) + len(literals)} قيمة تغيّرت:"
    rows = [f"  - `{c.var}`: {c.old} صار {c.new}" for c in changes]
    rows += [f"  - لون ثابت خارج المتغيرات {c.old} صار {c.new}" for c in literals]
    if stray:
        rows.append("  - ألوان ثابتة لا تطابق قيمة أي متغير فلا تتبع الاتجاه (ثبّتها مشروعك على متغير أو بدّلها بيده): " + "، ".join(f"`{h}`" for h in stray))
    return "\n".join([head, *rows])
