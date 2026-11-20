# 04a — Typography (Latin)

> **اقرأ هذا الملف فقط عند:** اختيار/نقد خط لاتيني، pairing، أو ضبط hierarchy لمحتوى لاتيني.
> **مكمّل:** `04b-typography-arabic.md` لأي محتوى عربي/ثنائي اللغة.

## Type Anatomy (مختصر)

```
Baseline | Cap Height | X-Height | Ascender | Descender | Serif | Bowl | Counter
```

X-Height = أهم مقياس للقابلية للقراءة على الشاشات.

## Classifications

| الفئة | الصفات | استخدام | أمثلة |
|------|--------|--------|------|
| Serif | كلاسيكي، موثوق | نشر، قانون، مال، فخامة | Garamond, Bodoni, Playfair |
| Sans-Serif | حديث، نظيف | تقنية، تعليم، digital | Helvetica, Inter, Futura |
| Slab Serif | جريء، صناعي | شعارات قوية، editorial | Rockwell, Roboto Slab |
| Script | يدوي، عاطفي | أزياء، أعراس | Pacifico, Sacramento |
| Display | لافت، فريد | عناوين فقط | Impact, Bebas Neue |
| Monospace | تقني، رمزي | كود، تكنولوجيا | JetBrains Mono, Fira Code |

## Pairing Rules

```
القاعدة الذهبية: ≤ 2 خطوط في مشروع واحد

الصيغ الناجحة:
  Serif H + Sans-Serif Body
  Sans H + Sans Body خفيف (وزن مختلف)

أزواج مُجرَّبة:
  Playfair Display + Lato
  Merriweather + Open Sans
  Bebas Neue + Roboto
  IBM Plex Serif + IBM Plex Sans (نفس الفصيلة)
```

**خطأ فادح:** زوجان من نفس الفصيلة بلا تباين.

## Hierarchy

```
H1: 48-72px / weight 700-900 / leading 1.1-1.2
H2: 32-40px
H3: 24-32px
Body: 16-18px (الحد الأدنى المطلق 16px)
Caption: 12-14px
```

## Fine Tuning

- **Kerning** (بين حرفين): يدوي للـ wordmarks. AV, To, Wa = pairs مشكلة.
- **Tracking** (إجمالي): negative للعناوين الكبيرة، positive للـ ALL CAPS.
- **Leading** (بين السطور): 1.4× الحد الأدنى للـ body، 1.5-1.6× مُفضَّل، 1.1-1.2× للعناوين.

## Variable Fonts (2016+)

ملف واحد، محاور متعددة (Weight 100-900، Width Condensed-Expanded، Slant). أداء أفضل + مرونة أعلى. أمثلة: Inter, Recursive, Decovar, Amstelvar.

## Brand Custom Fonts (المؤسسات الكبرى)

- Apple → San Francisco
- Google → Google Sans / Product Sans
- Netflix → Netflix Sans (وفّر ملايين ترخيص)
- Airbnb → Cereal
- IBM → IBM Plex (مفتوح المصدر — مرشح ممتاز للـ B2B)
- Coca-Cola → script منذ 1887

## Anti-patterns

- ❌ Comic Sans / Papyrus / Curlz MT.
- ❌ خطّ مجاني بترخيص personal-only في commercial.
- ❌ kerning تلقائي للـ wordmark النهائي.
- ❌ Body < 16px على الشاشات.
- ❌ Display font لـ body text.
