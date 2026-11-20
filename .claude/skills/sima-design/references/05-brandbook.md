# 05 — Brand Book / Brand Guidelines

> **اقرأ هذا الملف فقط عند:** كتابة brand guidelines رسمية، أو مراجعة brand book موجود، أو إعداد decorative-vs-informational declaration.

## ما هو Brand Book؟

وثيقة حية تُحدّد قواعد استخدام كل عنصر بصري + voice. الهدف: الاتساق عبر كل touchpoints. الحجم: 20-150+ صفحة حسب التعقيد. **العلامات المتسقة تزيد الإيرادات 33% (Lucidpress)**.

## الهيكل الاحترافي (8 أقسام)

### 1. Introduction & Vision
- Mission, Vision, Core Values, Brand Story, Archetype.

### 2. Logo Usage
- Primary, Secondary, Mark only, Reverse, B&W.
- ✓ مسموح / ✗ ممنوع (تمديد، تدوير، تغيير ألوان، effects).
- Minimum size: 24px رقمي / 15mm طباعة.
- Clear space: عرض حرف X في الشعار.
- استخدم `templates/brand-guide.template.md` كهيكل بدء.

### 3. Color Palette
- لكل لون: name، HEX، RGB، CMYK، Pantone، OKLCH، usage، do-not.
- Primary / Secondary / Neutral / System (success/error/warning).

### 4. Typography
- Display / Body / Supporting fonts.
- Hierarchy + weights + spacing.
- ⚠️ مشاريع عربية: قسم منفصل لـ Arabic typography (راجع `04b-typography-arabic.md`).

### 5. Imagery & Illustration
- Photography style: lighting، angles، subject، processing.
- Icons: filled vs outlined، stroke width، corner style.
- Illustrations style guide.

### 6. Visual Elements
- Patterns، textures، graphic devices المميّزة.
- Motion guidelines (إن انطبق).

### 7. Voice & Tone
- كلمات تصفنا / لا تصفنا.
- Examples: "نقول / لا نقول".
- قواعد الكتابة بالعربي والإنجليزي.

### 8. Applications
- Business card، letterhead، envelope، email signature.
- Merchandise، vehicle، signage، digital banners، social.
- Presentation template.

## **WCAG 1.4.11 Decorative-vs-Informational Declaration (إلزامي)**

> هذا القسم يُغلق فجوة LL-2026-04-15-032 + LL-2026-04-15-035.

كل عنصر لوني في الـ brand asset لا يحقق 3:1 contrast **يجب أن يُصنَّف صراحة** كـ `decorative` أو `informational`.

استخدم `templates/decorative-vs-informational.template.md` كنموذج كامل.

### Sanity Test (proof of decorative)

> **"إذا حذفت هذا العنصر تماماً، هل الشعار يبقى مُتعرَّفاً عليه كالعلامة؟"**
> - YES → decorative → معفى من 1.4.11.
> - NO → informational → يجب 3:1 أو يُحذف.

### تصنيف نموذجي

| العنصر | التصنيف الافتراضي |
|--------|------------------|
| Wordmark النص | informational (4.5:1) |
| Icon silhouette الشكل | informational (3:1) |
| نقطة ذهبية decorative | decorative (معفى) |
| Grid lines | decorative |
| Star particles | decorative |
| Gradient background | decorative |
| Border حول CTA | informational (3:1) |
| دلالة حالة (نجاح/خطأ) | informational (3:1) |

### Default = informational (Fail-Safe)

غياب التصريح = افتراض الأسوأ في أي audit. غياب paragraph واحد في brand guide قد يكلّف إعادة تصميم 15+ ملف لاحقاً.

## معايير عالمية للدراسة

| العلامة | الدرس |
|--------|------|
| Airbnb | الارتباط العاطفي + Bélo + Rausch color name |
| Google | البساطة في التعقيد + adaptability |
| Spotify | حيوية، الموسيقى بصرياً |
| IBM | الانضباط الهندسي + Plex |
| NASA Graphics Standards Manual (1976) | المرجع الذهبي للـ identity systems |

## Sizes & Costs

```
Starter (small biz): 20-30 صفحة. $1.5K-5K
Standard (SME):     40-60 صفحة كل أقسام. $5K-20K
Enterprise:         60-150+ صفحة + Motion + Environmental. $25K-200K+
```

مرجع: BBC redesign كلّفت £1.8M. British Airways £60M.

## Anti-patterns

- ❌ غياب decorative-vs-informational declaration.
- ❌ أمثلة "ممنوع" بدون أمثلة "مسموح" مقابلة.
- ❌ Brand book PDF فقط بدون tokens.css/SVG قابلة للتطبيق.
- ❌ Minimum size غير محدد.
- ❌ Voice section بصيغ مبهمة ("ودود لكن احترافي" بلا أمثلة).
