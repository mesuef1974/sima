# 03 — Color (Theory + Application + Culture + WCAG)

> **اقرأ هذا الملف فقط عند:** بناء/مراجعة لوحة لونية لعلامة، اختيار HEX/RGB/CMYK، أو فحص contrast.

## Color Wheel + Schemes

```
Primary:   🔴 أحمر  🔵 أزرق  🟡 أصفر
Secondary: 🟠 برتقالي  🟢 أخضر  🟣 بنفسجي
```

| Scheme | متى | قاعدة |
|--------|------|------|
| Monochromatic | فخامة، تماسك | لون + tints/shades |
| Complementary | طاقة، تباين قوي | 80/20 (لا 50/50) |
| Analogous | طبيعة، هدوء | 3-5 ألوان متجاورة |
| Triadic | حيوية متوازنة | 60/30/10 |
| Split-Complementary | تباين بدون صدام | لون + جارَي متمّمه |
| Tetradic | للمحترفين فقط | 4 ألوان متساوية |

## Brand Color Psychology (مختصر)

- 🔴 أحمر: طاقة، إلحاح، شغف. (Coca-Cola, Netflix, YouTube)
- 🔵 أزرق: ثقة، احترافية، هدوء. (Facebook, IBM, PayPal)
- 🟡 أصفر: تفاؤل، انتباه. (McDonald's, IKEA, DHL)
- 🟢 أخضر: طبيعة، نمو، ثروة. (Starbucks, Spotify, Whole Foods)
- 🟠 برتقالي: حماس، إبداع، أسعار معقولة. (Amazon, Fanta)
- 🟣 بنفسجي: فخامة، غموض، إبداع. (Cadbury, Hallmark)
- ⚫ أسود: قوة، أناقة، فخامة. (Chanel, Apple)
- ⚪ أبيض: نقاء، نظافة، (في آسيا = حداد).
- 🟡 ذهبي: رفاهية، حصرية. (Rolex, MasterCard)

## Cultural Color Codes (حرج للسوق العربي)

| اللون | الغرب | الصين | الشرق الأوسط | الهند |
|------|------|------|------------|------|
| أحمر | خطر/عشق | حظ/سعادة | خطر | نقاء/عروس |
| أبيض | نقاء/عروس | حداد/موت | نقاء | سلام |
| أخضر | طبيعة | تجارة | إسلام/حياة | خصوبة |
| أصفر | سعادة | إمبراطورية | سعادة | تجارة |
| أزرق | ثقة | خلود | حماية | كريشنا |
| أسود | أناقة/حداد | ثروة | حداد | شر/حداد |

⚠️ القبعة الخضراء في الصين = خيانة زوجية. الأحمر محظور في الجنازات الصينية.

## Technical Systems

```
RGB    (شاشات): 0-255 لكل قناة. #FFFFFF, #000000
CMYK   (طباعة): 0-100% لكل قناة. لا تطبع بدون proof
Pantone: نظام مرجع عالمي (PMS 485 C = أحمر Coca-Cola)
HEX    (ويب): #RRGGBB
OKLCH  (حديث): perceptual، أفضل لـ tints/shades الحاسوبية
```

## 60-30-10 Rule

```
60%  السائد (خلفيات، مساحات كبيرة)
30%  الثانوي (أزرار، عناوين)
10%  التمييز (CTAs، نقاط جذب)
```

## WCAG Contrast (إلزامي)

```
نص عادي: 4.5:1 (AA)، 7:1 (AAA)
نص كبير (≥18pt أو 14pt-bold): 3:1 (AA)، 4.5:1 (AAA)
عناصر بصرية informational (أيقونات، حدود): 3:1 (1.4.11)
عناصر decorative: معفاة (لكن يجب التصريح — راجع 05)
أداة: webaim.org/resources/contrastchecker/
سكريبت داخلي: scripts/check-contrast.py
```

83.6% من المواقع تفشل في التباين — لا تكن منهم.

## Brand Palette Build (الخطوات)

1. اللون الأساسي حسب الـ archetype + cultural fit.
2. حدّد HEX + RGB + CMYK + Pantone + OKLCH للمصدر الواحد.
3. أنشئ Tints (+50%) و Shades (-30%).
4. اختر ثانوياً متناسقاً (راجع Schemes).
5. اختر Accent عالي الطاقة.
6. أضِف Neutrals (gray scale + white + black).
7. تحقّق من contrast لكل combination قبل الاعتماد.
8. صدِّر إلى `templates/color-tokens.template.json`.

## Output Schema (لكل لون)

```
name           # Brand-named (e.g. "Sahla Teal")
role           # primary | secondary | accent | neutral | system
hex, rgb, cmyk, pantone, oklch
contrast_on_white   # ratio
contrast_on_black   # ratio
usage          # "buttons-primary, headings-h1"
do_not         # "نص عادي على bg-white إن ratio < 4.5:1"
```

## Anti-patterns

- ❌ RGB فقط لعلامة ستُطبع — التزم Pantone.
- ❌ contrast < 4.5:1 للنص — فشل WCAG AA.
- ❌ تجاهل cultural codes للسوق المستهدف.
- ❌ 4+ ألوان رئيسية في v1.
- ❌ Complementary 50/50 (يُتعب العين).
