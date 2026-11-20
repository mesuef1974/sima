"""خدمة الفحص: ثابت (بنية SVG) + نقطي (سماكة وتغطية عند 16) + تباين + تشابه. المخرج تقرير قابل للتسلسل."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .. import config
from . import contrast, raster, svgtools
from .ports import Renderer
from .similarity import SimilarityService


@dataclass
class AuditReport:
    concept_id: str
    passed: bool
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class AuditService:
    def __init__(self, renderer: Renderer, similarity: SimilarityService | None = None):
        self._r = renderer
        self._sim = similarity

    def raster_metrics(self, svg: str, base: int = 16) -> dict:
        """يقيس عند الحجم الصغير base بتكبير فائق ويقارن التغطية بينه وبين 256."""
        ss = config.SUPERSAMPLE if base <= 32 else max(2, config.SUPERSAMPLE // 2)
        big = self._r.render_gray(svg, base * ss, "#FFFFFF")
        small = self._r.render_gray(svg, base, "#FFFFFF")
        ref = self._r.render_gray(svg, 256, "#FFFFFF")
        m_big = raster.threshold(big)
        m_small = raster.threshold(small)
        m_ref = raster.threshold(ref)
        thick = raster.min_thickness(m_big) / ss
        cov16, cov256 = raster.coverage(m_small), raster.coverage(m_ref)
        comp16, comp256 = raster.components(m_small), raster.components(m_ref)
        bb = raster.bbox(m_ref)
        pad = None
        if bb:
            x0, y0, x1, y1 = bb
            pad = {
                "left": x0 / 256, "top": y0 / 256, "right": (255 - x1) / 256, "bottom": (255 - y1) / 256,
            }
        return {
            "base_size": base,
            "supersample": ss,
            "min_stroke_px": round(thick, 2),
            "coverage_small": round(cov16, 4),
            "coverage_256": round(cov256, 4),
            "components_small": comp16,
            "components_256": comp256,
            "padding_256": pad,
            "centroid_offset_256": (None if (c := raster.centroid(m_ref)) is None
                                    else {"x": round((c[0] - 127.5) / 256, 3), "y": round((c[1] - 127.5) / 256, 3)}),
        }

    def audit(self, concept_id: str, svg: str, *, stage: str = "bw", paper: str = "#FFFFFF", ink: str = "#000000",
              brand: str | None = None, base_size: int = 16, min_stroke: float | None = None) -> AuditReport:
        rep = AuditReport(concept_id=concept_id, passed=True)
        allowed = {"#000000", "#FFFFFF"} if stage == "bw" else None
        st = svgtools.static_audit(svg, allowed_colors=allowed, max_colors=2 if stage == "bw" else 3)
        rep.metrics.update({"shapes": st.shapes, "anchors": st.anchors, "colors": sorted(st.colors)})
        rep.findings.extend(st.findings)
        if not st.ok:
            rep.passed = False
            if any("غير صالح" in f for f in st.findings):
                return rep
        try:
            rm = self.raster_metrics(svg, base_size)
        except Exception as exc:  # noqa: BLE001 — خطأ التصيير يُبلَّغ كنتيجة لا كانهيار
            rep.passed = False
            rep.findings.append(f"تعذّر التصيير: {exc}")
            return rep
        rep.metrics.update(rm)
        floor = config.MIN_STROKE_AT_16 if min_stroke is None else min_stroke  # حدّ يعلنه المالك يغلب الافتراضي
        if rm["min_stroke_px"] < floor - 0.5 / rm["supersample"]:  # تسامح نصف بكسل عند التكبير
            rep.passed = False
            rep.findings.append(
                f"أصغر سماكة عند {base_size} بكسل = {rm['min_stroke_px']} أقل من {floor:g}"
            )
        if rm["coverage_256"] == 0:
            rep.passed = False
            rep.findings.append("العلامة فارغة بعد التصيير")
        else:
            ratio = rm["coverage_small"] / rm["coverage_256"] if rm["coverage_256"] else 0
            rep.metrics["coverage_ratio"] = round(ratio, 3)
            if ratio < 0.55 or ratio > 1.8:
                rep.warnings.append(f"تغطية الحبر عند {base_size} تختلف كثيرًا عن 256 (نسبة {ratio:.2f}): تفاصيل تضيع أو تلتحم")
            if base_size <= 32 and rm["components_small"] > 4:
                rep.warnings.append(f"{rm['components_small']} مكوّنات منفصلة عند {base_size} بكسل؛ قد تُقرأ ضجيجًا")
            if rm["coverage_256"] > 0.6:
                rep.warnings.append("كتلة الحبر تتجاوز 60% من المساحة: ثقيلة")
        pad = rm.get("padding_256")
        if pad:
            mn = min(pad.values())
            if mn < config.MIN_PADDING:
                rep.warnings.append(f"هامش العلامة {mn:.1%} من أضيق حافة؛ اترك هامشًا {config.MIN_PADDING:.0%} إلى 8% على الأقل")
        off = rm.get("centroid_offset_256")
        if off and max(abs(off["x"]), abs(off["y"])) > config.MAX_CENTROID_OFFSET:
            side_x = "يمين" if off["x"] > 0 else "يسار"
            side_y = "أسفل" if off["y"] > 0 else "أعلى"
            rep.warnings.append(f"مركز كتلة الحبر منحرف عن مركز اللوحة ({off['x']:+.0%} أفقيًا نحو {side_x}، {off['y']:+.0%} رأسيًا نحو {side_y}): "
                                "أعد التمركز على حدود الحبر الفعلية")
        if st.anchors > 400:
            rep.warnings.append(f"{st.anchors} نقطة ارتكاز: أعلى من المئين 95 للمكتبة (379)")
        # التباين
        c_ink = contrast.contrast_ratio(ink, paper)
        rep.metrics["contrast_ink_on_paper"] = c_ink
        if c_ink < config.CONTRAST_INFO:
            rep.passed = False
            rep.findings.append(f"تباين الحبر على الورق {c_ink}:1 أقل من {config.CONTRAST_INFO}:1")
        if brand:
            c_b = contrast.contrast_ratio(brand, paper)
            rep.metrics["contrast_brand_on_paper"] = c_b
            if c_b < config.CONTRAST_INFO:
                rep.findings.append(f"تباين لون العلامة على الورق {c_b}:1 أقل من {config.CONTRAST_INFO}:1")
                rep.passed = False
            c_bt = contrast.contrast_ratio("#FFFFFF", brand)
            rep.metrics["contrast_white_text_on_brand"] = c_bt
            if c_bt < config.CONTRAST_TEXT:
                rep.warnings.append(f"نص أبيض على لون العلامة {c_bt}:1 أقل من {config.CONTRAST_TEXT}:1")
        # التشابه
        if self._sim is not None:
            sim = self._sim.nearest(svg, top=3)
            rep.metrics["similarity"] = sim
            if sim and sim[0]["distance"] <= config.SIMILARITY_WARN:
                rep.warnings.append(
                    f"تشابه إدراكي مقلق مع {sim[0]['brand']} (مسافة {sim[0]['distance']} من 64)"
                )
        return rep
