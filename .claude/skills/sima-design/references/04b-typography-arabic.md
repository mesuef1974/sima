# 04b — Typography (Arabic + Bilingual)

> **اقرأ هذا الملف فقط عند:** أي مشروع يحتوي محتوى عربي، أو ثنائي اللغة (عربي/إنجليزي)، أو سوق قطري/خليجي/عربي.
> **مكمّل:** `04a-typography-latin.md` للجزء اللاتيني.

## الفصائل العربية الكلاسيكية

| الفصيلة | الصفات | متى | المرجع التاريخي |
|---------|--------|------|----------------|
| **نسخ (Naskh)** | تقليدي، رسمي، مقروء | كتب، صحف، PDF رسمي، نصوص طويلة | المعتمد في طباعة المصاحف منذ ابن مقلة |
| **ثلث (Thuluth)** | فنّي، خطّاطي، احتفالي | شعارات فاخرة، عناوين تذكارية، architectural | يُعتبر "ملك الخطوط" |
| **كوفي (Kufi)** | هندسي، تراثي، صلب | شعارات تكنولوجية/مؤسسية، بنّاءة | أقدم خط عربي، مرتبط بالمعمار |
| **ديواني (Diwani)** | رشيق، أنيق، متحرك | دعوات، علامات فاخرة، فنّ خطاطة | Ottoman court script |
| **رقعة (Ruqʿa)** | يومي، سريع، عملي | محادثات، signage عام | الخط الأشيع في الكتابة اليدوية |
| **مغربي/أندلسي** | منحنيات حادة، تراث | علامات maghrebi/أندلسية | شمال أفريقيا تاريخياً |

## خطوط رقمية موصى بها (2026)

### للشاشات (Sans-style Arabic)
- **IBM Plex Arabic** — مفتوح المصدر، يطابق IBM Plex Sans لاتيني، ممتاز B2B/Enterprise
- **Almarai** — Google Fonts، نظيف، 8 أوزان، شاشات
- **Cairo** — حديث، 9 أوزان، popular في الويب القطري
- **Tajawal** — أنيق تجاري، 7 أوزان
- **Noto Sans Arabic** — Google، يدعم 100% من الحروف

### للنشر/الفخامة (Naskh/Serif-equivalent)
- **Noto Naskh Arabic** — للمصاحف والكتب
- **Amiri** — كلاسيكي خطّاطي، ممتاز للنشر الديني/الأدبي
- **Aref Ruqaa** — ديواني/ثلث modernized، فاخر للعناوين

### للشعارات/Display
- **Reem Kufi** — كوفي حديث للـ wordmarks
- **Lateef** — Naskh decorative
- **Lalezar** — display نيون-modern

⚠️ **Comic Sans Arabic-equivalent:** تجنّب AdvertisingBold، Andalus default، أي خط Windows 95 افتراضي.

## RTL Considerations

```
1. Mirror الـ layout كاملاً — ليس فقط النص (icons، arrows، margins).
2. CSS: dir="rtl"، logical properties (margin-inline-start بدل margin-left).
3. الأرقام: اختر بين Arabic-Indic (٠١٢٣) أو Hindu-Arabic (0123) — كن متّسقاً.
4. punctuation: ، ؛ ؟ تختلف عن , ; ? — لا تخلط.
5. Mixed content (عربي + إنجليزي + أرقام): استخدم Unicode bidi marks (LRM/RLM) عند الحاجة.
```

## Arabic-Latin Pairing (ثنائي اللغة)

**القاعدة الذهبية:** اختر زوجاً مصمّماً معاً (أو بنفس "الصوت" البصري).

| Latin | Arabic match | الاستخدام |
|-------|-------------|----------|
| IBM Plex Sans | IBM Plex Arabic | B2B/Enterprise (مصمّمان معاً) ⭐ |
| Inter | Almarai or Cairo | Digital products، startups |
| Roboto | Tajawal | Material Design products |
| Noto Sans | Noto Sans Arabic | International/multilingual |
| Playfair Display | Amiri | Editorial، publishing فاخر |
| Lato | Cairo | عام، corporate |

**اختبارات التطابق:**
- [ ] X-height (عربي: ارتفاع جسم الحرف بدون النقاط) متطابق visually
- [ ] Stroke weight متشابه (لا Arabic رفيع + Latin سميك)
- [ ] العصر (عتيق + عتيق، حديث + حديث)
- [ ] لا Script Arabic + Sans Latin (تنافر)

## Kerning + Spacing للعربي

- **لا تطبّق tracking سالب على الأبجدية العربية** — يكسر الاتصال بين الحروف.
- **Letter-spacing موجب على ALL-CAPS عربي** غير ذي معنى — العربي ليس له upper/lower case.
- **Justification:** العربي يدعم Kashida (تمديد الحرف) — استخدمه باعتدال للنصوص الطويلة.
- **Kerning يدوي للـ wordmarks العربية**: ركّز على لام-ألف (لا)، الحاء/الجيم/الخاء، النقاط فوق التاء/الياء/الشين.

## السياق القطري/الخليجي

- **رسمياً (حكومة، PDPPL، أكاديمي):** Naskh-style الافتراضي. Noto Naskh Arabic أو Amiri للنشر، Almarai/Cairo للويب.
- **B2B/Enterprise قطري:** IBM Plex Arabic شائع (Qatar Foundation، QF entities).
- **B2C تجاري:** Cairo / Tajawal.
- **تراثي/فاخر (luxury Qatar):** Aref Ruqaa أو Reem Kufi أو خط مخصّص (custom calligraphy).
- **حذار من خطوط مكلفة الترخيص بدون ميزانية واضحة:** FF Shamel, 29LT, Boutros — عالية الجودة لكن expensive.

## Anti-patterns

- ❌ خط لاتيني افتراضي + خط عربي مختلف الشخصية تماماً.
- ❌ Tracking سالب للنص العربي (يكسر الاتصال).
- ❌ خلط Arabic-Indic و Hindu-Arabic أرقام في نفس الواجهة.
- ❌ tag dir="ltr" في صفحة عربية بـ inline overrides.
- ❌ Kashida مفرطة (≥3 مدّات في سطر = bloat).
- ❌ استخدام Andalus/Traditional Arabic كافتراضي (Windows legacy، تبدو غير احترافية).
