# سِمة

خط إنتاج محلي بالكامل يحوّل موجز علامة (ملف YAML) إلى حزمة هوية معتمدة بأمر واحد. لا نوافذ ولا سحابة: Chromium بلا رأس، وخطوط عربية مفتوحة، ومكتبة مراجع محلية لفحص التشابه.

## التثبيت

```bash
uv sync --all-groups
uv run playwright install chromium
```

## الاستعمال

```bash
uv run sima run briefs/math_papers.yaml
```

الأمر idempotent: يتابع من حيث توقف، ويعود بالرمز 3 عندما ينتظر النموذج (جلسة Claude بمهارة `sima-design`) و4 عندما ينتظر المالك و0 عند اكتمال الحزمة. المخرجات في `out/<project>/v<n>/` ولا يُستبدل إصدار قديم؛ مفتاح كل تشغيل hash الموجز + seed.

## المراحل

1. الموجز: قراءة YAML وتثبيته في `brief.json`.
2. البحث: مسح فهرس مكتبة المراجع (1,400 شعار للدراسة فقط) وكتابة `work/research.md`.
3. التباعد: النموذج يكتب 8 إلى 12 فكرة وخمسة مفاهيم SVG أبيض وأسود تغطي العائلات الخمس (حرفي، استعاري، مجرد، طباعي، رمزي) بالوسيط الحالي.
4. التصيير والفحص: 16/32/48/256 بكسل، أحادي ومعكوس ومرآة ومشوّش؛ لا نص حي ولا تدرجات ولا فلاتر؛ أصغر سماكة ≥ 1.5 بكسل عند 16؛ تباين ≥ 3:1 و4.5:1؛ تشابه إدراكي ضد المكتبة.
5. النقد: النموذج يرى الصور وينقد حتى ثلاث جولات ويعدّل SVG.
6. المعاينة: `preview.html` واحدة بسياقات البوابة الفعلية (ترويسة، لسان متصفح، شريط داكن، طباعة، أيقونة هاتف).
7. القرار: `sima decide <brief> --approve|--reject|--revise <id> --reason "..."`. الرفض الثالث لوسيط يقفله ويفتح التالي: مجردة ← كلامية ← شارة ← نمط.
8. توافر الاسم: الأداة تكتب `NAME-CHECK.md` بروابط WIPO ووزارة التجارة والصناعة والنطاقات والمتاجر، والمالك يفحصها بنفسه ويسجّل `sima name-check <brief> --status clear --source ...`. لا استعلام شبكي آلي.
9. الحزمة: SVG أساسي وأحادي ومعكوس، أيقونات متعددة الدقة و`site.webmanifest`، `tokens.css`، `BrandMark.vue`، `USAGE.md` بقواعد الاستعمال بالعربية، في `out/<project>/v<n>/package/`.

10. التسليم: `sima deliver <brief> --repo <مستودع>` يكتب الرمز والأيقونات وsite.webmanifest ويرقّع tokens.css وspa.html في worktree على فرع `card/<id>` ويضع بطاقة ready في `automation/ledger`؛ المشغّل المجدوَل في المستودع يفحص ويدفع ويفتح الطلب.

## أوامر مساعدة

```bash
uv run sima status briefs/math_papers.yaml
uv run sima render briefs/math_papers.yaml
uv run sima audit path/to/mark.svg
uv run sima shape أوراق --font "ReemKufi[wght].ttf" --weight 700 -o out/word.svg
uv run pytest
```

## البنية

Clean Architecture: `domain/` (Brief، Concept، Mark، Palette، Package، Decision، NameCheck)، `services/` (Shaping، Render، Audit، Similarity، Preview، Export، Ledger، NameCheck، Pipeline)، `adapters/` (Playwright، HarfBuzz/fontTools، مكتبة المراجع، Recraft معطّل افتراضيًا)، و`cli.py` نقطة الدخول الوحيدة.

## الحقوق

شعارات `vendor/logo-design-skill` علامات تجارية لأصحابها: للدراسة وفحص التشابه فقط، لا تُنسخ ولا تُقتبس. الخطوط في `fonts/` برخصة OFL.
