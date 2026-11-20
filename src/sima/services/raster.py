"""دوال حتمية على مصفوفات رمادية: قناع، تحويل مسافة، سماكة، تغطية، بصمات إدراكية.

كل الدوال نقية ولا تعتمد على مكتبات خارجية، فتُختبر بلا Chromium.
"""
from __future__ import annotations

import math
from collections import deque

from .ports import Gray

Mask = list[list[bool]]


def threshold(gray: Gray, cutoff: int = 160) -> Mask:
    """البكسل داكن إن كانت قيمته أقل من cutoff (الحبر على ورق فاتح)."""
    return [[v < cutoff for v in row] for row in gray]


def invert(gray: Gray) -> Gray:
    return [[255 - v for v in row] for row in gray]


def coverage(mask: Mask) -> float:
    total = sum(len(r) for r in mask)
    if total == 0:
        return 0.0
    return sum(1 for r in mask for v in r if v) / total


def distance_transform(mask: Mask) -> list[list[int]]:
    """مسافة شطرنجية من كل بكسل داكن إلى أقرب بكسل فاتح (BFS متعدد المصادر، جوار 8)."""
    h = len(mask)
    w = len(mask[0]) if h else 0
    INF = 10**9
    dist = [[INF] * w for _ in range(h)]
    q: deque[tuple[int, int]] = deque()
    for y in range(h):
        for x in range(w):
            if not mask[y][x]:
                dist[y][x] = 0
                q.append((y, x))
    # الحدود خارج الصورة تُعدّ فاتحة
    for y in range(h):
        for x in (0, w - 1):
            if mask[y][x] and dist[y][x] > 1:
                dist[y][x] = 1
                q.append((y, x))
    for x in range(w):
        for y in (0, h - 1):
            if mask[y][x] and dist[y][x] > 1:
                dist[y][x] = 1
                q.append((y, x))
    while q:
        y, x = q.popleft()
        d = dist[y][x] + 1
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and dist[ny][nx] > d:
                    dist[ny][nx] = d
                    q.append((ny, nx))
    return dist


def _edt_1d(f: list[float]) -> list[float]:
    """تحويل المسافة الإقليدي المربّع لبُعد واحد (Felzenszwalb وHuttenlocher)."""
    n = len(f)
    d = [0.0] * n
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    v[0] = 0
    z[0] = -math.inf
    z[1] = math.inf
    for q in range(1, n):
        while True:
            vk = v[k]
            s = ((f[q] + q * q) - (f[vk] + vk * vk)) / (2 * q - 2 * vk)
            if s <= z[k]:
                k -= 1
                if k < 0:
                    k = 0
                    break
            else:
                break
        k += 1
        v[k] = q
        z[k] = s if k > 0 else -math.inf
        z[k + 1] = math.inf
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        vk = v[k]
        d[q] = (q - vk) ** 2 + f[vk]
    return d


def euclidean_distance_sq(mask: Mask) -> list[list[float]]:
    """مربع المسافة الإقليدية من كل بكسل داكن إلى أقرب بكسل فاتح؛ حدود الصورة فاتحة."""
    h = len(mask)
    w = len(mask[0]) if h else 0
    INF = float(4 * (w * w + h * h) + 16)
    # نضيف إطارًا فاتحًا بعرض بكسل حول الصورة
    g = [[0.0] * (w + 2) for _ in range(h + 2)]
    for y in range(h):
        row = mask[y]
        grow = g[y + 1]
        for x in range(w):
            grow[x + 1] = INF if row[x] else 0.0
    # الأعمدة ثم الصفوف
    cols = [_edt_1d([g[y][x] for y in range(h + 2)]) for x in range(w + 2)]
    out = []
    for y in range(1, h + 1):
        out.append(_edt_1d([cols[x][y] for x in range(w + 2)])[1:w + 1])
    return out


def local_thickness(mask: Mask, centers: list[tuple[float, int, int]] | None = None) -> list[list[float]]:
    """السماكة المحلية لكل بكسل داكن: قطر أكبر قرص محتوى في الشكل يغطيه (تعريف Hildebrand وRüegsegger).

    مراكز الأقراص الأعظمية هي المحور الوسطي؛ نرسم كل قرص (بنصف قطر r + 0.5 ليغطي بكسلات الحافة) بقيمة
    عرضه 2r - 0.5 ونحتفظ بالأكبر.
    """
    h = len(mask)
    w = len(mask[0]) if h else 0
    if centers is None:
        centers = maximal_disc_centers(mask)
    thick = [[0.0] * w for _ in range(h)]
    for r, cy, cx in sorted(centers, reverse=True):
        width = max(1.0, 2 * r - 0.5)
        rr = r + 0.5
        rr2 = rr * rr
        ri = math.ceil(rr)
        for y in range(max(0, cy - ri), min(h, cy + ri + 1)):
            dy2 = (y - cy) ** 2
            trow = thick[y]
            mrow = mask[y]
            for x in range(max(0, cx - ri), min(w, cx + ri + 1)):
                if mrow[x] and trow[x] < width and dy2 + (x - cx) ** 2 <= rr2:
                    trow[x] = width
    return thick


def maximal_disc_centers(mask: Mask) -> list[tuple[float, int, int]]:
    """مراكز الأقراص الأعظمية (المحور الوسطي) مع نصف قطر كل منها."""
    h = len(mask)
    w = len(mask[0]) if h else 0
    d2 = euclidean_distance_sq(mask)
    out: list[tuple[float, int, int]] = []
    sqrt2 = math.sqrt(2)
    for y in range(h):
        for x in range(w):
            v = d2[y][x]
            if v <= 0:
                continue
            r = math.sqrt(v)
            maximal = True
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        step = sqrt2 if dy and dx else 1.0
                        if math.sqrt(d2[ny][nx]) >= r + step - 1e-9:
                            maximal = False
                            break
                if not maximal:
                    break
            if maximal:
                out.append((r, y, x))
    return out


def stroke_widths(mask: Mask, taper_tolerance: float = 0.1) -> list[float]:
    """عرض الضربة عند بكسلات المحور الوسطي المستوية.

    بكسل المحور الذي يملك جارًا داكنًا بنصف قطر أكبر منه بأكثر من taper_tolerance يقع على تدرّج
    (قطر مربع أو منصّف زاوية مثلث) لا على ضربة ثابتة العرض، فيُستبعد. العرض المأخوذ هو السماكة
    المحلية عند المركز، فنتوءات التعرّج على حافة شكل سميك تأخذ سماكة الشكل، وتبقى الشعرة بعرضها.
    """
    h = len(mask)
    w = len(mask[0]) if h else 0
    d2 = euclidean_distance_sq(mask)
    centers = maximal_disc_centers(mask)
    thick = local_thickness(mask, centers)
    widths: list[float] = []
    for r, y, x in centers:
        if r < 1.6:
            continue  # نتوءات التعرّج على الحواف المائلة والمنحنية، لا ضربات
        tapered = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and math.sqrt(d2[ny][nx]) >= r + taper_tolerance:
                    tapered = True
                    break
            if tapered:
                break
        if not tapered:
            widths.append(thick[y][x])
    return widths


def min_thickness(mask: Mask, percentile: float = 0.02) -> float:
    """السماكة الدنيا المعتبرة: المئين الثاني لعروض الضربات على المحور الوسطي المستوي."""
    vals = sorted(stroke_widths(mask))
    if not vals:
        return 0.0
    idx = min(len(vals) - 1, math.floor(percentile * (len(vals) - 1)))
    return round(vals[idx], 2)


def components(mask: Mask) -> int:
    """عدد المكوّنات المتصلة الداكنة (جوار 8)."""
    h = len(mask)
    w = len(mask[0]) if h else 0
    seen = [[False] * w for _ in range(h)]
    n = 0
    for y in range(h):
        for x in range(w):
            if mask[y][x] and not seen[y][x]:
                n += 1
                stack = [(y, x)]
                seen[y][x] = True
                while stack:
                    cy, cx = stack.pop()
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w and mask[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                stack.append((ny, nx))
    return n


def resample(gray: Gray, w: int, h: int) -> Gray:
    """تصغير بمتوسط الصناديق (box filter) إلى w×h."""
    sh = len(gray)
    sw = len(gray[0]) if sh else 0
    out: list[list[int]] = []
    for j in range(h):
        y0 = j * sh // h
        y1 = max(y0 + 1, (j + 1) * sh // h)
        row: list[int] = []
        for i in range(w):
            x0 = i * sw // w
            x1 = max(x0 + 1, (i + 1) * sw // w)
            acc = 0
            n = 0
            for y in range(y0, y1):
                r = gray[y]
                for x in range(x0, x1):
                    acc += r[x]
                    n += 1
            row.append(acc // n if n else 0)
        out.append(row)
    return out


def dhash(gray: Gray) -> str:
    """بصمة الفروق 9×8 → 64 بتًا سداسيًا."""
    g = resample(gray, 9, 8)
    bits = 0
    for row in g:
        for x in range(8):
            bits = (bits << 1) | (1 if row[x] > row[x + 1] else 0)
    return f"{bits:016x}"


def _dct_1d(v: list[float]) -> list[float]:
    n = len(v)
    out = []
    for k in range(n):
        s = 0.0
        for i in range(n):
            s += v[i] * math.cos(math.pi * (i + 0.5) * k / n)
        out.append(s)
    return out


def phash(gray: Gray) -> str:
    """بصمة DCT: تصغير إلى 32×32 ثم أخذ 8×8 الترددات الدنيا ومقارنتها بالوسيط."""
    g = resample(gray, 32, 32)
    rows = [_dct_1d([float(v) for v in r]) for r in g]
    cols = [_dct_1d([rows[y][x] for y in range(32)]) for x in range(32)]
    low = [cols[x][y] for y in range(8) for x in range(8)]
    vals = low[1:]  # نتجاهل مكوّن DC
    med = sorted(vals)[len(vals) // 2]
    bits = 0
    for v in low:
        bits = (bits << 1) | (1 if v > med else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def bbox(mask: Mask) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1) شامل لآخر بكسل داكن، أو None إن كانت الصورة فارغة."""
    xs = [x for row in mask for x, v in enumerate(row) if v]
    if not xs:
        return None
    ys = [y for y, row in enumerate(mask) if any(row)]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(mask: Mask) -> tuple[float, float] | None:
    """مركز كتلة الحبر (x, y) بالبكسل، أو None إن كانت الصورة فارغة."""
    n = sx = sy = 0
    for y, row in enumerate(mask):
        for x, v in enumerate(row):
            if v:
                n += 1
                sx += x
                sy += y
    return (sx / n, sy / n) if n else None

