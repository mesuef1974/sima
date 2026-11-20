"""أداة البناء الهندسي: يصف الرسّام العلامة بناءً (أشكال على شبكة وعمليات بوليانية وإزاحة وتدوير زوايا وتكرار)،
وتحوّلها هذه الأداة حتميًا إلى SVG نظيف بمسارات مدموجة. لا يكتب النموذج إحداثيات مسارات معقدة بيده.

الصيغة في `.claude/skills/sima-design/references/41-construction.md`. الحساب بـ skia-pathops (مثبتة أصلًا للتشكيل).
"""
from __future__ import annotations

import math
import re
from html import escape

import yaml
from pathops import ArcSize, Direction, LineCap, LineJoin, Path, PathOp, PathVerb, op

MAX_DEFS = 80
MAX_DEPTH = 24
MAX_REPEAT = 72
LIMIT = 4096.0  # أي إحداثية أبعد من هذا خطأ في البناء لا تصميم
CAPS = {"butt": LineCap.BUTT_CAP, "round": LineCap.ROUND_CAP, "square": LineCap.SQUARE_CAP}
JOINS = {"miter": LineJoin.MITER_JOIN, "round": LineJoin.ROUND_JOIN, "bevel": LineJoin.BEVEL_JOIN}
BOOL = {"union": PathOp.UNION, "difference": PathOp.DIFFERENCE, "intersection": PathOp.INTERSECTION, "xor": PathOp.XOR}
SHAPES = ("circle", "ellipse", "rect", "polygon", "regular", "arc", "line", "curve", "path", "text")
OPS = (*BOOL, "offset", "round", "repeat")
TRANSFORMS = ("rotate", "about", "translate", "scale", "mirror")
OPTIONS = ("r", "width", "cap", "join", "from", "to", "d", "n", "step", "font", "weight", "size", "at", "part")


class ConstructError(ValueError):
    """خطأ في وصف البناء، برسالة عربية يقرؤها الرسّام في طلبه التالي."""


def _text(v, n: dict, where: str) -> Path:
    """حروف حقيقية من خطوط المشروع المرخّصة (fonts/) مشكّلة حتميًا، لتُعدَّل بعدها بالعمليات البوليانية."""
    from .font_shaper import shape_parts

    if not isinstance(v, str) or not v.strip() or len(v) > 40:
        raise ConstructError(f"{where}: نص من 1 إلى 40 حرفًا")
    font = str(n.get("font", ""))
    if not font or "/" in font or "\\" in font or ".." in font:
        raise ConstructError(f"{where}: font اسم ملف من fonts/ (مثل Cairo[slnt,wght].ttf)")
    x, base = _nums(n.get("at", [0, 200]), 2, where)
    try:
        p = shape_parts(v, font, int(_num(n.get("weight", 700), where)), _num(n.get("size", 160), where), x, base,
                        str(n.get("part", "all")))
    except (FileNotFoundError, ValueError) as exc:
        raise ConstructError(f"{where}: {exc}") from exc
    if p.area == 0:
        raise ConstructError(f"{where}: الجزء المطلوب فارغ في هذا النص")
    return p


# ----- أدوات المسار -----
def _copy(p: Path) -> Path:
    q = Path()
    q.addPath(p)
    return q


def _num(v, what: str) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError) as e:
        raise ConstructError(f"{what}: رقم مطلوب لا «{v}»") from e
    if not math.isfinite(x) or abs(x) > LIMIT:
        raise ConstructError(f"{what}: {v} خارج الحدود")
    return x


def _pt(v, what: str) -> tuple[float, float]:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ConstructError(f"{what}: نقطة [x, y] مطلوبة")
    return _num(v[0], what), _num(v[1], what)


def _nums(v, n: int, what: str) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise ConstructError(f"{what}: {n} أرقام مطلوبة")
    return [_num(x, what) for x in v]


def _quads(p: Path) -> Path:
    """arcTo يولّد مقاطع مخروطية لا تقبلها العمليات البوليانية؛ تُحوَّل إلى تربيعية."""
    p.convertConicsToQuads()
    return p


def _bool(a: Path, b: Path, kind: PathOp) -> Path:
    return op(_quads(_copy(a)), _quads(_copy(b)), kind, fix_winding=True, keep_starting_points=False)


def _stroked(p: Path, width: float, cap=LineCap.ROUND_CAP, join=LineJoin.ROUND_JOIN) -> Path:
    q = _copy(p)
    q.stroke(width, cap, join, 4)
    q.convertConicsToQuads()
    q.simplify(fix_winding=True)
    return q


def _offset(p: Path, d: float, join=LineJoin.ROUND_JOIN) -> Path:
    """join=miter يبقي الزوايا حادة عند التثقيل (حروف كوفية ومضغوطة)؛ الافتراضي round يدوّرها."""
    if d == 0:
        return p
    ring = _stroked(p, 2 * abs(d), join=join)
    return _bool(p, ring, PathOp.UNION if d > 0 else PathOp.DIFFERENCE)


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> Path:
    p = Path()
    p.moveTo(cx + rx, cy)
    p.arcTo(rx, ry, 0, ArcSize.SMALL, Direction.CW, cx - rx, cy)
    p.arcTo(rx, ry, 0, ArcSize.SMALL, Direction.CW, cx + rx, cy)
    p.close()
    return p


def _polygon(pts: list[tuple[float, float]]) -> Path:
    if len(pts) < 3:
        raise ConstructError("polygon: ثلاث نقاط على الأقل")
    p = Path()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    p.close()
    return p


def _rect(x: float, y: float, w: float, h: float, r: float) -> Path:
    if w <= 0 or h <= 0:
        raise ConstructError("rect: العرض والارتفاع موجبان")
    r = max(0.0, min(r, w / 2, h / 2))
    if r == 0:
        return _polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    p = Path()
    p.moveTo(x + r, y)
    p.lineTo(x + w - r, y)
    p.arcTo(r, r, 0, ArcSize.SMALL, Direction.CW, x + w, y + r)
    p.lineTo(x + w, y + h - r)
    p.arcTo(r, r, 0, ArcSize.SMALL, Direction.CW, x + w - r, y + h)
    p.lineTo(x + r, y + h)
    p.arcTo(r, r, 0, ArcSize.SMALL, Direction.CW, x, y + h - r)
    p.lineTo(x, y + r)
    p.arcTo(r, r, 0, ArcSize.SMALL, Direction.CW, x + r, y)
    p.close()
    return p


def _arc_line(cx: float, cy: float, r: float, a0: float, a1: float) -> Path:
    """قوس مركزه (cx, cy) من الزاوية a0 إلى a1 بالدرجات؛ الصفر شرقًا والزيادة باتجاه عقارب الساعة (y إلى أسفل)."""
    span = a1 - a0
    if span <= 0 or span >= 360:
        raise ConstructError("arc: يلزم 0 < to - from < 360 (للدائرة الكاملة استعمل circle مع offset أو ring)")
    def at(a: float) -> tuple[float, float]:
        t = math.radians(a)
        return cx + r * math.cos(t), cy + r * math.sin(t)
    p = Path()
    p.moveTo(*at(a0))
    p.arcTo(r, r, 0, ArcSize.LARGE if span > 180 else ArcSize.SMALL, Direction.CW, *at(a1))
    return p


TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _parse_d(d: str) -> Path:
    toks = TOKEN.findall(d or "")
    if not toks or toks[0] not in "Mm":
        raise ConstructError("path: يبدأ المسار بـ M")
    p, i, cmd = Path(), 0, ""
    x = y = sx = sy = 0.0
    last_c: tuple[float, float] | None = None
    last_q: tuple[float, float] | None = None

    def nums(k: int) -> list[float]:
        nonlocal i
        out = []
        for _ in range(k):
            if i >= len(toks) or toks[i].isalpha():
                raise ConstructError(f"path: أرقام ناقصة بعد {cmd}")
            out.append(_num(toks[i], "path"))
            i += 1
        return out

    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        elif not cmd:
            raise ConstructError("path: رقم بلا أمر")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if c == "Z":
            p.close()
            x, y = sx, sy
            last_c = last_q = None
            continue
        if c == "M":
            a, b = nums(2)
            x, y = ox + a, oy + b
            sx, sy = x, y
            p.moveTo(x, y)
            cmd = "l" if rel else "L"
            last_c = last_q = None
        elif c == "L":
            a, b = nums(2)
            x, y = ox + a, oy + b
            p.lineTo(x, y)
            last_c = last_q = None
        elif c == "H":
            (a,) = nums(1)
            x = ox + a
            p.lineTo(x, y)
            last_c = last_q = None
        elif c == "V":
            (b,) = nums(1)
            y = oy + b
            p.lineTo(x, y)
            last_c = last_q = None
        elif c in "CS":
            if c == "C":
                x1, y1, x2, y2, ex, ey = nums(6)
                c1 = (ox + x1, oy + y1)
            else:
                x2, y2, ex, ey = nums(4)
                c1 = (2 * x - last_c[0], 2 * y - last_c[1]) if last_c else (x, y)
            c2 = (ox + x2, oy + y2)
            x, y = ox + ex, oy + ey
            p.cubicTo(*c1, *c2, x, y)
            last_c, last_q = c2, None
        elif c in "QT":
            if c == "Q":
                x1, y1, ex, ey = nums(4)
                q1 = (ox + x1, oy + y1)
            else:
                ex, ey = nums(2)
                q1 = (2 * x - last_q[0], 2 * y - last_q[1]) if last_q else (x, y)
            x, y = ox + ex, oy + ey
            p.quadTo(*q1, x, y)
            last_q, last_c = q1, None
        elif c == "A":
            rx, ry, rot, large, sweep, ex, ey = nums(7)
            x, y = ox + ex, oy + ey
            p.arcTo(abs(rx), abs(ry), rot, ArcSize.LARGE if large else ArcSize.SMALL,
                    Direction.CW if sweep else Direction.CCW, x, y)
            last_c = last_q = None
    return p


def _matrix(node: dict, center: tuple[float, float]) -> tuple[float, ...] | None:
    if not any(k in node for k in ("rotate", "translate", "scale", "mirror")):
        return None
    ax, ay = _pt(node["about"], "about") if "about" in node else center
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0

    def then(m: tuple[float, ...]) -> None:  # يطبّق m بعد التحويل الحالي
        nonlocal a, b, c, d, e, f
        a2, b2, c2, d2, e2, f2 = m
        a, b, c, d, e, f = (a2 * a + c2 * b, b2 * a + d2 * b, a2 * c + c2 * d, b2 * c + d2 * d,
                            a2 * e + c2 * f + e2, b2 * e + d2 * f + f2)

    def about(m: tuple[float, float, float, float]) -> tuple[float, ...]:
        m1, m2, m3, m4 = m
        return (m1, m2, m3, m4, ax - m1 * ax - m3 * ay, ay - m2 * ax - m4 * ay)

    if "scale" in node:
        s = node["scale"]
        sx, sy = (_num(s, "scale"),) * 2 if not isinstance(s, (list, tuple)) else _nums(s, 2, "scale")
        then(about((sx, 0.0, 0.0, sy)))
    if "mirror" in node:
        if node["mirror"] not in ("x", "y"):
            raise ConstructError("mirror: x (انعكاس أفقي) أو y (رأسي)")
        then(about((-1.0, 0.0, 0.0, 1.0) if node["mirror"] == "x" else (1.0, 0.0, 0.0, -1.0)))
    if "rotate" in node:
        t = math.radians(_num(node["rotate"], "rotate"))
        then(about((math.cos(t), math.sin(t), -math.sin(t), math.cos(t))))
    if "translate" in node:
        dx, dy = _pt(node["translate"], "translate")
        then((1.0, 0.0, 0.0, 1.0, dx, dy))
    return a, b, c, d, e, f


class Builder:
    def __init__(self, spec: dict):
        if not isinstance(spec, dict):
            raise ConstructError("ملف البناء قاموس YAML")
        self.w = _num(spec.get("width", spec.get("canvas", 256)), "width")
        self.h = _num(spec.get("height", spec.get("canvas", 256)), "height")
        self.center = (self.w / 2, self.h / 2)
        defs = spec.get("defs") or {}
        if not isinstance(defs, dict) or len(defs) > MAX_DEFS:
            raise ConstructError(f"defs: قاموس أسماء بحد أقصى {MAX_DEFS}")
        self.defs: dict[str, Path] = {}
        for name, node in defs.items():
            self.defs[str(name)] = self.node(node, 0, f"defs.{name}")
        if "mark" not in spec:
            raise ConstructError("mark: الشكل النهائي مطلوب")
        self.mark = self.node(spec["mark"], 0, "mark")
        self.accent = self.node(spec["accent"], 0, "accent") if spec.get("accent") is not None else None

    def node(self, n, depth: int, where: str) -> Path:
        if depth > MAX_DEPTH:
            raise ConstructError(f"{where}: تداخل أعمق من {MAX_DEPTH}")
        if isinstance(n, str):
            if n not in self.defs:
                raise ConstructError(f"{where}: اسم غير معرّف قبله «{n}»")
            return _copy(self.defs[n])
        if not isinstance(n, dict):
            raise ConstructError(f"{where}: عقدة غير مفهومة")
        kinds = [k for k in (*SHAPES, *OPS) if k in n]
        if len(kinds) != 1:
            raise ConstructError(f"{where}: مفتاح شكل أو عملية واحد بالضبط من {', '.join((*SHAPES, *OPS))}")
        unknown = set(n) - {*kinds, *TRANSFORMS, *OPTIONS}
        if unknown:
            raise ConstructError(f"{where}: مفاتيح غير معروفة {sorted(unknown)}")
        k = kinds[0]
        p = _quads(self._make(k, n, depth, f"{where}.{k}"))
        m = _matrix(n, self.center)
        if m is not None and k != "repeat":
            p = p.transform(*m)
        return p

    def _make(self, k: str, n: dict, depth: int, where: str) -> Path:
        v = n[k]
        if k == "text":
            return _text(v, n, where)
        if k == "circle":
            cx, cy, r = _nums(v, 3, where)
            return _ellipse(cx, cy, r, r)
        if k == "ellipse":
            cx, cy, rx, ry = _nums(v, 4, where)
            return _ellipse(cx, cy, rx, ry)
        if k == "rect":
            x, y, w, h = _nums(v, 4, where)
            return _rect(x, y, w, h, _num(n.get("r", 0), where))
        if k == "polygon":
            p = _polygon([_pt(q, where) for q in v or []])
            r = _num(n.get("r", 0), where)
            return self._round(p, r) if r else p
        if k == "regular":
            cx, cy, r, sides = _nums(v, 4, where)
            if not 3 <= sides <= 64:
                raise ConstructError(f"{where}: عدد الأضلاع بين 3 و64")
            pts = [(cx + r * math.cos(math.radians(-90 + 360 * i / sides)), cy + r * math.sin(math.radians(-90 + 360 * i / sides)))
                   for i in range(int(sides))]
            p = _polygon(pts)
            rr = _num(n.get("r", 0), where)
            return self._round(p, rr) if rr else p
        if k in ("arc", "line", "curve"):
            width = _num(n.get("width", 0), where)
            if width <= 0:
                raise ConstructError(f"{where}: width (سماكة الخط) مطلوبة وموجبة")
            cap = CAPS.get(str(n.get("cap", "butt")))
            join = JOINS.get(str(n.get("join", "round")))
            if cap is None or join is None:
                raise ConstructError(f"{where}: cap من {list(CAPS)} وjoin من {list(JOINS)}")
            if k == "arc":
                cx, cy, r = _nums(v, 3, where)
                line = _arc_line(cx, cy, r, _num(n.get("from", 0), where), _num(n.get("to", 0), where))
            elif k == "line":
                pts = [_pt(q, where) for q in v or []]
                if len(pts) < 2:
                    raise ConstructError(f"{where}: نقطتان على الأقل")
                line = Path()
                line.moveTo(*pts[0])
                for q in pts[1:]:
                    line.lineTo(*q)
            else:
                line = _parse_d(str(v))
            return _stroked(line, width, cap, join)
        if k == "path":
            p = _quads(_parse_d(str(v)))
            p.close()
            p.simplify(fix_winding=True)
            return p
        if k in BOOL:
            if not isinstance(v, list) or len(v) < 2:
                raise ConstructError(f"{where}: قائمة من عقدتين على الأقل")
            parts = [self.node(x, depth + 1, f"{where}[{i}]") for i, x in enumerate(v)]
            acc = parts[0]
            for q in parts[1:]:
                acc = _bool(acc, q, BOOL[k])
            return acc
        if k == "offset":
            join = JOINS.get(str(n.get("join", "round")))
            if join is None:
                raise ConstructError(f"{where}: join من {list(JOINS)}")
            return _offset(self.node(v, depth + 1, where), _num(n.get("d", 0), where), join)
        if k == "round":
            return self._round(self.node(v, depth + 1, where), _num(n.get("r", 0), where))
        # repeat: نسخ دورانية حول نقطة
        count = int(_num(n.get("n", 0), where))
        if not 2 <= count <= MAX_REPEAT:
            raise ConstructError(f"{where}: n بين 2 و{MAX_REPEAT}")
        step = _num(n.get("step", 360 / count), where)
        base = self.node(v, depth + 1, where)
        pre = _matrix({kk: n[kk] for kk in ("scale", "mirror", "translate", "about") if kk in n} | {"rotate": 0}, self.center)
        if pre is not None:
            base = base.transform(*pre)
        ax, ay = _pt(n["about"], where) if "about" in n else self.center
        acc = base
        for i in range(1, count):
            t = math.radians(_num(n.get("rotate", 0), where) + step * i)
            c, s = math.cos(t), math.sin(t)
            acc = _bool(acc, base.transform(c, s, -s, c, ax - c * ax + s * ay, ay - s * ax - c * ay), PathOp.UNION)
        return acc

    @staticmethod
    def _round(p: Path, r: float) -> Path:
        """r موجب يدوّر الزوايا البارزة (تقليص ثم تمديد)، وسالب يدوّر الزوايا الداخلة (تمديد ثم تقليص)."""
        return _offset(_offset(p, -r), r)  # الصيغة نفسها للحالتين: إشارة r تقلب ترتيب التقليص والتمديد


def _d(p: Path) -> str:
    q = _copy(p)
    q.convertConicsToQuads()

    def f(v: float) -> str:
        s = f"{round(v, 2):.2f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s

    out: list[str] = []
    for verb, pts in q:  # الأفعال الخام: لا تجميع تربيعيات بنقاط ضمنية (None) كما في segments
        if verb is PathVerb.MOVE:
            out.append(f"M{f(pts[0][0])} {f(pts[0][1])}")
        elif verb is PathVerb.LINE:
            out.append(f"L{f(pts[0][0])} {f(pts[0][1])}")
        elif verb is PathVerb.QUAD:
            out.append("Q" + " ".join(f"{f(x)} {f(y)}" for x, y in pts))
        elif verb is PathVerb.CUBIC:
            out.append("C" + " ".join(f"{f(x)} {f(y)}" for x, y in pts))
        elif verb is PathVerb.CLOSE:
            out.append("Z")
        else:
            raise ConstructError(f"فعل مسار غير متوقع {verb}")
    return "".join(out)


def _empty(p: Path) -> bool:
    q = _copy(p)
    q.convertConicsToQuads()
    return not any(v in (PathVerb.LINE, PathVerb.QUAD, PathVerb.CUBIC) for v, _ in q) or abs(q.area) < 1


def build_svg(spec_text: str, title: str) -> str:
    """يحوّل نص YAML للبناء إلى SVG أسود على أبيض؛ عنصر accent (إن وُجد) مسار منفصل بـ data-tone="accent"."""
    try:
        spec = yaml.safe_load(spec_text)
    except yaml.YAMLError as e:
        raise ConstructError(f"YAML غير صالح: {e}") from e
    b = Builder(spec)
    mark = _copy(b.mark)
    mark.simplify(fix_winding=True)
    if _empty(mark):
        raise ConstructError("mark: الشكل النهائي فارغ (طرح أكل كل شيء؟)")
    width, height, accent = b.w, b.h, b.accent
    if spec.get("fit") is not None:
        # اللوحة تُقصّ على حدود الحبر بهامش نسبته fit من أصغر بُعدي المحتوى (للكلمة العريضة؛ المربع يبقى 256)
        pad = _num(spec["fit"], "fit")
        if not 0 <= pad <= 0.25:
            raise ConstructError("fit: نسبة الهامش بين 0 و0.25")
        x0, y0, x1, y1 = mark.bounds
        m = pad * min(x1 - x0, y1 - y0)
        mark = mark.transform(1, 0, 0, 1, m - x0, m - y0)
        accent = accent.transform(1, 0, 0, 1, m - x0, m - y0) if accent is not None else None
        width, height = round(x1 - x0 + 2 * m, 2), round(y1 - y0 + 2 * m, 2)
    paths = []
    if accent is not None:
        acc = _bool(mark, accent, PathOp.INTERSECTION)
        ink = _bool(mark, accent, PathOp.DIFFERENCE)
        if not _empty(ink):
            paths.append(f'<path d="{_d(ink)}" fill="#000000"/>')
        if not _empty(acc):
            paths.append(f'<path data-tone="accent" d="{_d(acc)}" fill="#000000"/>')
    else:
        paths.append(f'<path d="{_d(mark)}" fill="#000000"/>')
    w, h = (f"{v:g}" for v in (width, height))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><title>{escape(title)}</title>'
            + "".join(paths) + "</svg>")
