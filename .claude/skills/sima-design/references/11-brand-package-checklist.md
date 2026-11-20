# 11 — Brand = Full Package Checklist

> **اقرأ عند:** أي طلب brand identity كامل **بعد** logo approval من CEO. **لا تستخدمه قبل** trademark clearance + logo sign-off (راجع `00-azkia-gates.md`).
>
> **القاعدة الذهبية #6 (CEO directive 2026-04-25):** Brand identity = Full Package دائماً. لا partial. لا "نبدأ باللوجو ثم نرى". إن طُلب brand → جهّز ALL items أدناه (≥30 بنداً موزّعة على 6 مجموعات).
>
> **مستوى Bloom:** Apply → Create.

---

## التسلسل الإلزامي (Pre-Conditions)

قبل فتح هذا الملف، يجب أن يكون موثّقاً:
1. ✅ Trademark clearance: `clear` أو `clear-with-conditions` (موقَّع `advisor_qatar_corporate_law`).
2. ✅ Logo approval: 5 divergent concepts → CEO اختار → DEC-{PROJECT}-LOGO-001.md.
3. ✅ `advisory_input` من 3 مستشارين (advisor_brand + advisor_qatar_corporate_law + advisor_business_management).

**بدون هذه الثلاثة → STOP. ارجع للـ Gate 2.**

---

## المجموعة 1 — Logo System (5 variants)

| # | Item | Format(s) | Dimensions | Constraints |
|---|------|-----------|------------|-------------|
| 1.1 | Primary mark (combination: monogram + wordmark) | SVG + AI + PDF | scalable | `clear-space = x-height of "ن"` لو bilingual |
| 1.2 | Secondary mark (wordmark-only) | SVG + AI + PDF | scalable | استخدمه عند صغر المساحة الأفقية |
| 1.3 | Monogram / icon-only | SVG + AI + PDF | 1:1 ratio | min 16px digital |
| 1.4 | Reverse / dark-mode variant | SVG + AI + PDF | scalable | يُختبر على #000، #1B2A4E، gradient |
| 1.5 | Mono black + Mono white | SVG + AI + PDF | scalable | لا gradients، stroke فقط |

**Constraints عامة:**
- Source files in `brand/v1.0/source/` (.AI + .FIG)؛ exports في `brand/v1.0/exports/`.
- لا embedded raster داخل SVG.
- B&W test: كل variant يعمل بدون لون.
- Sibling-folder versioning (راجع `06-deliverables-and-versioning.md`).

---

## المجموعة 2 — Favicon System (5 sizes)

| # | Item | Format | Dimensions | Use |
|---|------|--------|------------|-----|
| 2.1 | favicon.ico (multi-res) | ICO | 16/32/48 px | browser tab classic |
| 2.2 | favicon-32 | PNG | 32×32 | modern browsers |
| 2.3 | apple-touch-icon | PNG | 180×180 | iOS home screen |
| 2.4 | android-chrome-192 | PNG | 192×192 | Android home screen |
| 2.5 | android-chrome-512 | PNG | 512×512 | PWA splash + manifest |

**Constraints:**
- Monogram-only (لا wordmark — لا يقرأ في 16px).
- Padding داخلي ≥ 12.5% (لا تلامس الحواف).
- مرفق `site.webmanifest` لـ PWA.

---

## المجموعة 3 — Icon System + Color Theory (5+ بنود)

| # | Item | Spec |
|---|------|------|
| 3.1 | Icon library (≥24 أيقونة أساسية) | SVG، stroke 1.5px، corners 2px rounded |
| 3.2 | Stroke weight ثابت | 1.5px (small) / 2px (large) |
| 3.3 | Corner radius ثابت | 2px أو 4px (لا تخلط) |
| 3.4 | Grid base | 24×24 (أو 16×16 للـ inline) |
| 3.5 | Color theory note | تطبيق نظرية اللون على الأيقونات (filled vs outlined ≠ نفس وزن بصري؛ راجع `03-color.md` §contrast) |
| 3.6 | Naming convention | `icon-{category}-{name}-{variant}.svg` (مثل `icon-action-edit-outline.svg`) |

---

## المجموعة 4 — Color Palette (4 tiers)

| Tier | Count | Examples | Constraint |
|------|-------|----------|------------|
| **Tier 1: Primary** | 1-2 | brand identity colors | يحدد العلامة فوراً؛ AAA-able as brand text |
| **Tier 2: Secondary** | 1-2 | accents | يكمّل Primary بـ 60-30-10 rule |
| **Tier 3: Neutral** | 4-6 | grays + paper + ink | warm vs cool consistent |
| **Tier 4: Semantic** | 4 | success / warning / danger / info | كل واحد ≥ 4.5:1 على Tier 3 paper |

**Deliverables:**
- `tokens.json` (راجع `templates/color-tokens.template.json`).
- لكل لون: HEX + RGB + CMYK + Pantone + OKLCH + contrast vs white/black.
- WCAG AA contrast pairs documented (راجع `scripts/check-contrast.py`).
- Reserved Government Colors **مُستثناة** (Qatar National Maroon #8A1538، MoEHE blue) — راجع `03-color.md`.

---

## المجموعة 5 — Typography (Arabic + Latin)

| # | Item | Spec |
|---|------|------|
| 5.1 | Latin display typeface | weight + license + fallback |
| 5.2 | Latin body typeface | weights 400/500/600 minimum |
| 5.3 | Arabic display typeface (Naskh أو Kufi حسب archetype) | راجع `04b-typography-arabic.md` |
| 5.4 | Arabic body typeface | x-height متوازن مع Latin (10-15% أكبر بصرياً) |
| 5.5 | Pairing rationale | لماذا هذا الـ pair؟ (مثال: IBM Plex Sans Arabic + IBM Plex Sans = نفس عائلة المصمم) |
| 5.6 | Hierarchy (type ladder) | H1/H2/H3/Body/Caption + sizes + line-heights + letter-spacing |
| 5.7 | RTL specifics | logical properties، Hindu vs Arabic-Indic numerals، kashida policy |
| 5.8 | License acquisition | شراء أو OFL؛ توثيق في `brand/v1.0/typography/LICENSE.md` |

---

## المجموعة 6 — Applications (8+ touchpoints)

| # | Touchpoint | Format | Dimensions |
|---|------------|--------|------------|
| 6.1 | Business card | PDF + AI | 85×55mm bilingual |
| 6.2 | Letterhead | PDF + DOCX | A4، logo position حسب RTL/LTR |
| 6.3 | Email signature | HTML + plain text + PNG | 600×200 max |
| 6.4 | Social templates | PSD/FIG + PNG | 1080×1080 + 1080×1920 stories + 1200×630 OG |
| 6.5 | Presentation template | PPTX + Google Slides | 16:9، title + content + section |
| 6.6 | Website header/footer | FIG + HTML snippet | responsive specs |
| 6.7 | Signage / storefront | PDF + DXF | scale 1:1 mockup + production specs |
| 6.8 | Packaging (لو منتج فيزيائي) | PDF + AI dieline | spec حسب المنتج |

**Optional touchpoints (+):**
- Vehicle wrap (لو B2B field service)
- Trade show booth (لو معارض)
- Merchandise (T-shirt، tote، mug)
- App icon + splash screen (لو منتج رقمي)

---

## Self-Check (Formative — per advisor_education_pedagogy)

قبل تسليم الحزمة، اسأل نفسك:
- [ ] هل كل الـ 5 logo variants مُختبرة B&W؟
- [ ] هل favicon-32 يقرأ من بُعد ذراع على شاشة 4K؟
- [ ] هل الـ color tokens تمر `check-contrast.py` بدون warnings حرجة؟
- [ ] هل الـ Arabic + Latin pair متوازنان بصرياً (x-height)؟
- [ ] هل كل application مُرفقة بـ source file + export قابل للطباعة؟
- [ ] هل الـ co-branding rules مكتوبة (لو B2G)؟
- [ ] هل decorative-vs-informational declaration موجودة في brand guide؟
- [ ] هل sibling-folder structure مطبَّق (لا destructive replace)؟

**إن أي [ ] فارغة → غير مكتمل. لا تسلّم.**

---

## مرجعية متقاطعة

- Trademark gate: `00-azkia-gates.md`
- Meeting workflow (متى نناقش brand): `12-meeting-workflow.md`
- Logo design depth: `02-logo.md`
- Color depth: `03-color.md`
- Typography: `04a-typography-latin.md` + `04b-typography-arabic.md`
- Brand guide structure: `05-brandbook.md` + `templates/brand-guide.template.md`
- Filled example: `templates/brand-guide.example.md` (Naseej)
- Versioning: `06-deliverables-and-versioning.md`
