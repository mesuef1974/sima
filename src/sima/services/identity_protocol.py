"""بروتوكول ملفات الهوية بين الخط والنموذج: المنصة الاستراتيجية والاتجاهات والأنماط والأيقونات، وسجل بوابات المالك.

النموذج يكتب في work/identity/؛ الخط يقرأ ويتحقق تحققًا حتميًا ويكتب طلبًا مفصّلًا حين ينقص شيء أو يُطلب تعديل.
كل قرار للمالك مربوط بـsha256 ما عُرض عليه، فلا يُحتسب اعتماد على محتوى تغيّر بعده.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ..domain import Brief
from ..domain.identity import Direction, Gate, IdentityDecision, Strategy, Trait, TypeChoice
from . import svgtools
from .color_system import ROLES
from .workspace import Workspace

SAMPLES = ("headline", "button", "error", "empty_state")
SAMPLES_AR = {"headline": "عنوان", "button": "زر", "error": "رسالة خطأ", "empty_state": "حالة فارغة"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ICON_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
ARABIC = re.compile(r"[؀-ۿ]")
FORBIDDEN = {"text", "tspan", "linearGradient", "radialGradient", "filter", "image", "foreignObject", "script", "style", "use", "a"}
TAGLINE_MAX = 48


def idir(ws: Workspace) -> Path:
    return ws.work / "identity"


def digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes() if p.is_file() else b"<missing>")
    return h.hexdigest()[:16]


def _yaml(p: Path) -> tuple[dict | None, str]:
    if not p.is_file():
        return None, ""
    try:
        return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}), ""
    except yaml.YAMLError as e:
        return None, f"YAML غير صالح في {p.name}: {e}"


def _text(v, field: str, problems: list[str], *, arabic: bool = True, maxlen: int | None = None) -> str:
    s = str(v or "").strip()
    if not s:
        problems.append(f"{field}: فارغ")
    elif arabic and not ARABIC.search(s):
        problems.append(f"{field}: يجب أن يكون بالعربية")
    elif maxlen and len(s) > maxlen:
        problems.append(f"{field}: أطول من {maxlen} حرفًا")
    return s


# ---------- المنصة الاستراتيجية ----------
def strategy_path(ws: Workspace) -> Path:
    return idir(ws) / "strategy.yaml"


def _line(x: object) -> str:
    """بند قائمة نصي. إن كتب النموذج «مفتاح: قيمة» صار في YAML قاموسًا؛ يُعاد سطرًا واحدًا لا تمثيلًا برمجيًا."""
    if isinstance(x, dict):
        return "؛ ".join(f"{k}: {v}" for k, v in x.items())
    return str(x)


def read_strategy(ws: Workspace) -> tuple[Strategy | None, list[str]]:
    d, err = _yaml(strategy_path(ws))
    if d is None:
        return None, [err] if err else ["strategy.yaml غير موجود"]
    p: list[str] = []
    traits = []
    pers = d.get("personality") or []
    if not isinstance(pers, list) or len(pers) != 3:
        p.append("personality: ثلاث سمات بالضبط")
    else:
        for i, t in enumerate(pers, 1):
            t = t or {}
            traits.append(Trait(_text(t.get("trait"), f"السمة {i}", p), _text(t.get("means"), f"معنى السمة {i}", p),
                                _text(t.get("not"), f"ما ليست عليه السمة {i}", p)))
    voice = d.get("voice") or {}
    do, dont = [_line(x) for x in voice.get("do") or []], [_line(x) for x in voice.get("dont") or []]
    if len(do) < 3 or len(dont) < 3:
        p.append("voice: ثلاثة «نقول» وثلاثة «لا نقول» على الأقل")
    samples = {k: _text((voice.get("samples") or {}).get(k), f"مثال {SAMPLES_AR[k]}", p) for k in SAMPLES}
    s = Strategy(
        positioning=_text(d.get("positioning"), "التموضع", p), promise=_text(d.get("promise"), "الوعد", p),
        personality=tuple(traits), voice_do=tuple(do), voice_dont=tuple(dont), samples=samples,
        tagline=_text(d.get("tagline"), "الشعار اللفظي", p, maxlen=TAGLINE_MAX), imagery=str(d.get("imagery") or "").strip(),
    )
    return (s if not p else None), p


# ---------- الاتجاهات ----------
def directions_path(ws: Workspace) -> Path:
    return idir(ws) / "directions.yaml"


def svg_safety(svg: str) -> list[str]:
    """فحص أمان وأسلوب لأي SVG يكتبه النموذج: لا نص حي ولا تدرجات ولا مراجع خارجية ولا سكربت."""
    try:
        root = svgtools.parse(svg)
    except Exception as e:  # noqa: BLE001
        return [f"SVG غير صالح: {e}"]
    out = []
    for el in root.iter():
        tag = svgtools._local(el.tag)
        if tag in FORBIDDEN:
            out.append(f"عنصر ممنوع <{tag}>")
        for k, v in el.attrib.items():
            name = svgtools._local(k)
            if name.startswith("on") or (name == "href" and not str(v).startswith("#")):
                out.append(f"سمة ممنوعة {name}")
            if name in ("filter", "mask") or (name == "opacity" and v not in ("1", "1.0")):
                out.append(f"سمة ممنوعة {name}")
    if svgtools.view_box(root) is None:
        out.append("لا viewBox")
    return sorted(set(out))


def three_over_adopted(ws: Workspace) -> bool:
    """`identity.directions: three` في الموجز المجمَّد في الإصدار: علامة من خارج الخط تُعرض عليها ثلاثة اتجاهات يختار منها المالك."""
    try:
        data = json.loads((ws.root / "brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data.get("identity"), dict) and data["identity"].get("directions") == "three"


def directions_count(ws: Workspace) -> int:
    """ثلاثة اتجاهات يكتبها النموذج، أو اتجاه واحد اعتمده المالك خارج الخط (services/adopt.py) ما لم يطلب الموجز الثلاثة فوقه."""
    return 1 if ws.done("adopted") and not three_over_adopted(ws) else 3


def keep_adopted_direction(ws: Workspace, direction: dict, motif: str) -> None:
    """اتجاه التسليم المعتمد بين ثلاثة لا يُعدَّل: بنده أول القائمة وملف نمطه يُعادان كما في بيان الاعتماد إن غيّرهما النموذج
    أو حذفهما، فلا يُحاسَب النموذج على نسخه حرفًا بحرف ولا يتغيّر المعتمد بيده. متساوي الأثر: لا يكتب إن لم يختلف شيء."""
    path = directions_path(ws)
    data, _ = _yaml(path)
    if data is None or not isinstance(data.get("directions"), list):
        return
    items = data["directions"]
    fixed = [direction, *[x for x in items if not (isinstance(x, dict) and x.get("id") == direction["id"])]]
    if items != fixed:
        path.write_text(yaml.safe_dump({**data, "directions": fixed}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    mfile = idir(ws) / str(direction["motif"]["file"])
    if not mfile.is_file() or mfile.read_text(encoding="utf-8") != motif:
        mfile.parent.mkdir(parents=True, exist_ok=True)
        mfile.write_text(motif, encoding="utf-8")


def read_directions(ws: Workspace) -> tuple[list[Direction], list[str]]:
    d, err = _yaml(directions_path(ws))
    if d is None:
        return [], [err] if err else ["directions.yaml غير موجود"]
    p: list[str] = []
    items = d.get("directions") or []
    count = directions_count(ws)
    if not isinstance(items, list) or len(items) != count:
        return [], ["directions: ثلاثة اتجاهات بالضبط" if count == 3 else "directions: الاتجاه المعتمد وحده"]
    out, seen = [], set()
    for i, x in enumerate(items, 1):
        x = x or {}
        did = str(x.get("id") or "")
        if not re.match(r"^d[1-9]$", did) or did in seen:
            p.append(f"الاتجاه {i}: id بصيغة d1..d9 وغير مكرر")
        seen.add(did)
        colors = {k: str((x.get("colors") or {}).get(k) or "") for k in ROLES}
        bad = [k for k, v in colors.items() if not HEX.match(v)]
        if bad:
            p.append(f"{did}: ألوان ناقصة أو بغير صيغة #RRGGBB: {', '.join(bad)}")
        t = x.get("type") or {}
        try:
            heading = TypeChoice(str(t["heading"]["font"]), int(t["heading"]["weight"]))
            body = TypeChoice(str(t["body"]["font"]), int(t["body"]["weight"]))
        except (KeyError, TypeError, ValueError):
            p.append(f"{did}: type.heading وtype.body بخط ووزن")
            heading = body = TypeChoice("", 400)
        numerals = str(t.get("numerals") or "latn")
        if numerals not in ("arab", "latn"):
            p.append(f"{did}: numerals إما arab أو latn")
        motif = x.get("motif") or {}
        mfile = str(motif.get("file") or "")
        mpath = idir(ws) / mfile
        if not mfile.startswith("motifs/") or ".." in mfile or not mpath.is_file():
            p.append(f"{did}: motif.file في motifs/ وموجود")
        else:
            svg = mpath.read_text(encoding="utf-8")
            p += [f"{did} النمط: {e}" for e in svg_safety(svg)]
            cols = svgtools.colors_used(svgtools.parse(svg)) - {"#000000", "#FFFFFF"}
            if cols:
                p.append(f"{did} النمط: أسود وأبيض فقط، والتمييز بـdata-tone=\"accent\" (وُجد {', '.join(sorted(cols))})")
        out.append(Direction(
            id=did, name=_text(x.get("name"), f"{did} الاسم", p), idea=_text(x.get("idea"), f"{did} الفكرة", p),
            colors={k: v.upper() for k, v in colors.items()}, accent_informational=bool(x.get("accent_informational", False)),
            heading=heading, body=body, numerals=numerals, motif_file=mfile, motif_rule=_text(motif.get("rule"), f"{did} قاعدة النمط", p),
            radius=int(x.get("radius", 4)),
        ))
    if count > 1 and len({(o.heading.font, o.body.font) for o in out}) == 1 and len({o.colors["brand"] for o in out}) == 1:
        p.append("الاتجاهات الثلاثة متطابقة اللون والخط؛ يجب أن تتباعد")
    return (out if not p else []), p


def directions_digest(ws: Workspace) -> str:
    files = [directions_path(ws), *sorted((idir(ws) / "motifs").glob("*.svg"))]
    return digest(files)


# ---------- الأيقونات ----------
def icons_path(ws: Workspace) -> Path:
    return idir(ws) / "icons.yaml"


def read_icons(ws: Workspace, brief: Brief) -> tuple[list[dict], list[str]]:
    d, err = _yaml(icons_path(ws))
    if d is None:
        return [], [err] if err else ["icons.yaml غير موجود"]
    p: list[str] = []
    stroke = float(d.get("stroke", 0) or 0)
    if stroke < 1.5:
        p.append("stroke: سماكة موحّدة ≥ 1.5 على شبكة 24")
    items = d.get("icons") or []
    subjects = {str(i.get("subject")) for i in items if isinstance(i, dict)}
    missing = [s for s in brief.identity.icons if s not in subjects]
    if missing:
        p.append("أيقونات ناقصة لموضوعات الموجز: " + "، ".join(missing))
    out = []
    for i in items:
        iid, subj = str(i.get("id") or ""), str(i.get("subject") or "")
        if not ICON_ID.match(iid):
            p.append(f"{subj}: id لاتيني صغير بشرطات")
            continue
        f = idir(ws) / "icons" / f"{iid}.svg"
        if not f.is_file():
            p.append(f"{iid}: الملف icons/{iid}.svg غير موجود")
            continue
        p += [f"{iid}: {e}" for e in icon_problems(f.read_text(encoding="utf-8"), stroke)]
        out.append({"id": iid, "subject": subj, "svg": decorative(f.read_text(encoding="utf-8"))})
    return (out if not p else []), p


_TEXT_NODE = re.compile(r"\s*<(title|desc)\b[^>]*>.*?</\1>", re.DOTALL)
_ROOT = re.compile(r"<svg\b[^>]*>")


def decorative(svg: str) -> str:
    """أيقونة زخرفية من المصدر (قرار المالك 2026-11-20): بلا `<title>` ولا `<desc>`، وجذرها `aria-hidden="true" focusable="false"`.
    اسمها يحمله نص الواجهة بجانبها؛ عنوان «طلب» في أيقونة «مسك» دخل نص بلاطات لوحته. حتمي وidempotent."""
    svg = _TEXT_NODE.sub("", svg)
    root = _ROOT.search(svg)
    if not root:
        return svg
    tag = root.group(0)
    for attr, value in (("aria-hidden", "true"), ("focusable", "false")):
        if not re.search(rf"\s{attr}=", tag):
            tag = tag[:-1].rstrip("/").rstrip() + f' {attr}="{value}"' + ("/>" if tag.endswith("/>") else ">")
    return svg[:root.start()] + tag + svg[root.end():]


def icon_problems(svg: str, stroke: float) -> list[str]:
    out = svg_safety(svg)
    if out:
        return out
    root = svgtools.parse(svg)
    if svgtools.view_box(root) != (0.0, 0.0, 24.0, 24.0):
        out.append("viewBox يجب أن يكون 0 0 24 24")
    inherited = {k: root.get(k) for k in ("stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "fill")}
    widths, caps = set(), set()
    for el in root.iter():
        tag = svgtools._local(el.tag)
        if tag not in ("path", "line", "polyline", "polygon", "circle", "ellipse", "rect"):
            continue
        st = el.get("stroke") or inherited["stroke"]
        fill = el.get("fill") or inherited["fill"] or "black"
        if st not in (None, "none", "currentColor"):
            out.append(f"stroke بغير currentColor في <{tag}>")
        if fill not in ("none", "currentColor"):
            out.append(f"fill بغير none أو currentColor في <{tag}>")
        if st == "currentColor":
            widths.add(float(el.get("stroke-width") or inherited["stroke-width"] or 1))
            caps.add((el.get("stroke-linecap") or inherited["stroke-linecap"], el.get("stroke-linejoin") or inherited["stroke-linejoin"]))
    if widths and widths != {stroke}:
        out.append(f"سماكات مختلفة {sorted(widths)}؛ المطلوب {stroke:g} في كل الأيقونات")
    if len(caps) > 1:
        out.append("أطراف أو زوايا غير موحّدة")
    if not widths:
        out.append("لا خطوط مرسومة بـcurrentColor")
    return sorted(set(out))


# ---------- سجل البوابات ----------
class IdentityLedger:
    def __init__(self, path: Path):
        self._path = path

    def read(self) -> list[IdentityDecision]:
        if not self._path.is_file():
            return []
        out = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                out.append(IdentityDecision(Gate(d["gate"]), d["digest"], d["verdict"], d.get("option", ""), d.get("reason", ""), d["at"]))
        return out

    def record(self, gate: Gate, digest_: str, verdict: str, option: str = "", reason: str = "") -> IdentityDecision:
        dec = IdentityDecision(gate, digest_, verdict, option, reason, datetime.now(UTC).isoformat(timespec="seconds"))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"gate": gate.value, "digest": digest_, "verdict": verdict, "option": option, "reason": reason,
                                 "at": dec.at}, ensure_ascii=False) + "\n")
        return dec

    def latest(self, gate: Gate, digest_: str) -> IdentityDecision | None:
        """آخر قرار على هذا المحتوى بعينه؛ None يعني أنه لم يُعرض قرار عليه بعد."""
        for d in reversed(self.read()):
            if d.gate is gate and d.digest == digest_:
                return d
        return None

    def history(self, gate: Gate) -> list[IdentityDecision]:
        return [d for d in self.read() if d.gate is gate]


def ledger(ws: Workspace) -> IdentityLedger:
    return IdentityLedger(ws.root / "identity_decisions.jsonl")


REVISE_REQUEST = "REQUEST-revise.md"
# الطلب الذي يُكتب للنموذج حين يطلب المالك تعديلًا عند كل بوابة
GATE_REQUEST = {Gate.STRATEGY: "REQUEST-strategy.md", Gate.DIRECTIONS: "REQUEST-directions.md", Gate.BOOK: REVISE_REQUEST}


def revise_reply(ws: Workspace, dec: IdentityDecision | None, gate: Gate = Gate.BOOK) -> str | None:
    """جواب النموذج على طلب تعديل لم يغيّر المعروض (سؤال من المالك، أو خلل خارج `work/identity/`)، في أي بوابة هوية.
    القرار مربوط ببصمة المحتوى: إن أجاب النموذج بعد القرار وبقيت البصمة فلا تعديل يُنتظر منه، فتعود البوابة إلى المالك
    بجوابه بدل أن يعلق الإصدار بلا بطاقة. الجواب كاملًا (`reply`) إن سُجّل، وإلا خلاصته. None: لم يُجَب الطلب بعد، أو القرار
    اعتماد."""
    path = ws.root / "model_calls.jsonl"
    if dec is None or dec.verdict == "approved" or not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        call = json.loads(line)
        if call.get("request") == GATE_REQUEST[gate] and call.get("ok") and str(call.get("at", "")) >= dec.at:
            return str(call.get("reply") or call.get("summary") or "").strip()
    return None
