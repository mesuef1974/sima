# 06 — Deliverables + Versioning (Sibling-Folder Pattern)

> **اقرأ هذا الملف فقط عند:** تجهيز حزمة تسليم نهائية، أو استبدال/تحديث logo asset سابق، أو إعداد brand asset structure لمشروع جديد.

## Source Files (للمصمم)

```
.AI / .SKETCH / .FIG    — قابل للتعديل
.EPS                    — متوافق universal
.PDF (PDF/X-1a or X-4)  — للطباعة
```

## Print-Ready

```
.PDF بدقة 300 DPI + bleed 3-5mm + crop marks
نموذج لوني: CMYK
Outline text (تحويل الخطوط لمسارات)
.EPS للمطابع الكبيرة
```

## Digital / Web

```
.SVG  — primary للشعارات (vector، يُكبر بلا حد)
.PNG  — 1x + 2x retina + 3x mobile، خلفية شفافة
.JPG  — صور بخلفية بيضاء فقط
.WebP — أداء ويب
.ICO  — favicon (16/32/48px multi-resolution)
```

## Social Sizes (مرجع 2026)

```
Square post:     1080×1080
Banner 16:9:     1920×1080
Profile:         400×400
Instagram Story: 1080×1920 (9:16)
LinkedIn Banner: 1584×396
X/Twitter Header: 1500×500
YouTube Thumbnail: 1280×720
```

## Full Delivery Matrix

| Asset | Formats | استخدام |
|-------|---------|---------|
| Primary logo color | AI, SVG, PNG (1x/2x/3x) | كل شيء |
| Logo white | AI, SVG, PNG | خلفيات داكنة |
| Logo black | AI, SVG, PNG | ضمان طباعة |
| Icon mark | SVG, PNG, ICO | App icon, Favicon |
| Color palette | PDF, ASE, JSON | توثيق |
| Fonts (مرخصة) | OTF, TTF, WOFF2 | تطبيق |
| Brand guide | PDF + MD source | مرجع الفريق |
| Template presentation | PPTX, PDF | عروض |
| `tokens.css` (drop-in) | CSS | dev integration |

> **Pro tip (LL-027):** `tokens.css` كـ drop-in replacement يختصر أسابيع تطبيق إلى ساعات. سعّر الـ brand package ليشمله افتراضياً.

## Quality Checklist (قبل التسليم)

- [ ] جميع الخطوط محوّلة Outline في source.
- [ ] CMYK لكل ملف طباعي، RGB لكل ملف رقمي.
- [ ] 300 DPI للطباعة، 72-96 DPI للشاشة (raster).
- [ ] لا layers مخفية أو objects خارج artboard.
- [ ] أسماء ملفات منظّمة بنمط: `{brand}-{variant}-{state}-{size}.{ext}`.
  - مثال: `livesky-primary-light-1x.png`
- [ ] WCAG contrast verified (راجع `scripts/check-contrast.py`).
- [ ] decorative-vs-informational declared (راجع `05-brandbook.md`).
- [ ] sibling folder structure مُجهَّز لـ versioning مستقبلي (انظر أدناه).

## **Sibling-Folder Versioning Pattern (LL-2026-04-15-029)**

### القاعدة الحاسمة

> **لا تستبدل أي brand asset مُعتمد في مكانه مطلقاً. أنشئ folder sibling جديد (`<family>/<version>/`) تحت نفس الـ brand root، وأبقِ الإصدار القديم حتى بعد التعطيل الرسمي. التحويل إلى "archived" يكون بتحريك المجلد القديم إلى `brand/archive/` بعد dual-run period ≥ 30 يوم، لا بحذفه.**

### لماذا destructive replace خطير؟

1. **Broken references**: docs، README، presentations، contracts، tweets — كلها قد تشير للمسار القديم.
2. **No rollback**: لو trademark clearance فشل بعد الدفع → لا نسخة سليمة للعودة.
3. **Lost institutional memory**: كل شعار يحمل قصة مرحلية. الحذف = حذف تاريخ.
4. **Git history غير كافٍ**: binary assets يصعب استرجاعها لـ non-engineers، ولا تُظهر السبب التصميمي.

### الـ Pattern

```
docs/brand/
├── v1/                          # legacy (kept)
│   └── logo/
│       └── azkia-wordmark/
├── v2/                          # current production
│   └── logo/
│       ├── sightline/           # previous primary (kept for rollback)
│       │   ├── livesky-sightline-primary.svg
│       │   └── README.md        # "Active until 2026-05-15 dual-run end"
│       └── night-dome/          # NEW primary (DEC-LIVESKY-BRAND-002)
│           ├── livesky-primary.svg
│           ├── livesky-primary-reversed.svg
│           ├── livesky-mono.svg
│           └── ... 12 more variants
└── archive/
    └── (moved after dual-run completes)
```

### متى يُسمح بـ destructive replace؟

- **نص فقط**: تصحيح إملائي داخل `<desc>` SVG (لا الشعار نفسه).
- **metadata**: عناوين، تعليقات، license headers.
- **فنية بحتة**: export settings (precision، decimal places) بدون تغيير pixels.

أي تغيير يؤثر على **الشكل المرئي** = folder sibling جديد، بدون استثناء.

### Cutover Checklist

1. ✅ folder sibling جديد موجود ومُختَبَر (rendering، a11y، alignment).
2. ✅ قرار CEO موثق (DEC-{PROJECT}-BRAND-###) يحدد "new primary".
3. ✅ جميع refs نشطة تُحدَّث (docs, site, README) في PR واحد.
4. ⏳ dual-run period ≥ 30 يوم (كلاهما متاح).
5. ⏳ trademark clearance للـ new asset (إن انطبق).
6. 🔄 move old → `brand/archive/` فقط بعد 1-5 ✅.

## Anti-patterns

- ❌ overwrite logo SVG في مكانه = LL-029 violation.
- ❌ تسليم بدون tokens.css/JSON drop-in.
- ❌ ملفات raster فقط بدون vectors.
- ❌ أسماء ملفات عشوائية (`logo-final-v3-FINAL-USE-THIS.png`).
- ❌ نسيان favicon multi-resolution.
