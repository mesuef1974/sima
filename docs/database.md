# قاعدة سِمة (Django + PostgreSQL)

القرص يبقى المصدر بإصدارات لا تُستبدل (`out/<project>/v<n>`)، والقاعدة هي السجل العلائقي الدائم المستعلَم. كل كتابة فيها idempotent عبر `sima.web.registry.service`، والنماذج نحيلة بلا منطق.

## الجداول

| الجدول | المحتوى |
|---|---|
| `sima_project` | المشروع (slug، الاسم العربي) |
| `sima_run` | الإصدار: رقمه ومفتاح التشغيل (hash الموجز + seed) ومصدر الموجز وإغلاقه |
| `sima_concept_decision` | قرارات المالك في المفاهيم (من `decisions.jsonl`) |
| `sima_gate_decision` | قرارات بوابات الهوية مربوطة ببصمة المعروض (من `identity_decisions.jsonl`) |
| `sima_approved_identity` | الهوية المعتمدة: الاتجاه، الألوان، أدوار الفاتح والداكن، السلالم، الخطوط، المنصة الاستراتيجية، نتيجة الفحوص، بصمة الدليل، وقرار الاعتماد نفسه |
| `sima_asset` | كل ملف في الحزمة ببصمة sha256 وحجمه ونوعه؛ النص حتى 512 KB يُحفظ كاملًا |

## متى تُكتب الهوية المعتمدة

عند اعتماد المالك لدليل الهوية يكمل `sima run` الإصدار ويستدعي منفذ السجل (`on_identity_approved`) فيحفظ الهوية بأصولها. النواة لا تعرف Django؛ المنفذ يُحقن من `cli.py`. إن كانت القاعدة متوقفة لا يُبطَل الاعتماد المسجّل على القرص، ويظهر تنبيه بإعادة المزامنة.

لا تُحفظ هوية إلا إذا وُجد في `identity_decisions.jsonl` اعتماد على بصمة الدليل نفسها المكتوبة في علامة المرحلة.

## الأوامر

```bash
uv run sima db start      # العنقود المحلي على 127.0.0.1 بلا نافذة
uv run sima db status
uv run sima db migrate
uv run sima db sync       # يستورد كل الإصدارات والقرارات، ويسجّل الهويات المعتمدة
uv run sima db stop
```

## الإيقاف النظيف عند إيقاف ويندوز

postgres خارج الخدمات يُقطع حين تنتهي جلسة ويندوز، فيبدأ كل إقلاع باستعادة. `sima db start` يبدأ معه حارسًا بلا نافذة (`adapters/db_guard.py`، واحد لكل عنقود): يُبلَّغ بانتهاء الجلسة قبل غيره فيرسل إلى postmaster طلب الإيقاف السريع عبر أنبوب إشاراته وينتظر زوال `postmaster.pid`؛ وإن أُلغي الإيقاف أعاد تشغيل القاعدة. يخرج حين تتوقف القاعدة بغيره (`sima db stop`). سجله `var/db_guard.log`، و`SIMA_DB_GUARD=0` يوقفه. التحقق بعد إقلاع: في `var/pg.log` سطر «database system was shut down at» لا «was interrupted».

## الإعداد

العنقود في `var/pgdata` (خارج git) على 127.0.0.1 فقط بمصادقة scram-sha-256. المفاتيح في `.env` (خارج git ولا تُطبع):
`SIMA_DB_NAME`، `SIMA_DB_USER`، `SIMA_DB_PASSWORD`، `SIMA_DB_HOST`، `SIMA_DB_PORT`، `DJANGO_SECRET_KEY`.

لإنشاء العنقود أول مرة: `initdb -D var/pgdata -U postgres --auth=scram-sha-256 --pwfile=<ملف مؤقت>` ثم إنشاء الدور `sima` بصلاحية CREATEDB (تحتاجها الاختبارات) وقاعدة `sima` يملكها، ثم `sima db migrate`.

اختبارات `tests/test_registry.py` تنشئ قاعدة `test_sima` مؤقتة وتحذفها، وتُتخطّى إن لم تكن القاعدة تعمل.
