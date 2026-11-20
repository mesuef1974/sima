# منصة سِمة (Django + Vue)

`uv run sima board [--repo <مستودع>] [--port 8766]` يشغّل المنصة على 127.0.0.1 فقط: Django يخدم الصفحة والـAPI وملفات المخرجات للقراءة، وواجهة Vue تعرض اليوم والمشاريع والقرارات والأتمتة.

## الطبقات

| المكان | الدور |
|---|---|
| `src/sima/web/api.py` | API بـ django-ninja: `GET /api/state`، `GET /api/registry`، و`POST /api/decide | identity | name-check` |
| `src/sima/web/views.py` | الصفحة (قالب يحقن رمز التشغيل ويحمّل الحزمة عبر django-vite)، و`/out/` و`/fonts/` للقراءة فقط |
| `src/sima/web/runtime.py` | رمز التشغيل لكل عملية، ومجلد المخرجات، والتشغيلات الخلفية |
| `src/sima/web/server.py` | wsgiref متعدد الخيوط بلا حزمة خادم إضافية |
| `frontend/` | Vue 3 + TypeScript + Vite + Pinia + vue-router (تاريخ hash، صفحات كسولة) |

## الأمان

- الكتابة تتطلب رمز التشغيل في رأس `X-Sima-Token`، والرأس المخصّص يفرض preflight يرفضه أي أصل آخر، والأصل إن أُرسل يجب أن يكون محليًا. الرمز يُولَّد لكل تشغيل ولا يُخزَّن في المتصفح.
- القرار مربوط بالإصدار والمفتاح وبصمة المعروض؛ القرار على معروض قديم يُرفض (409).
- `/out/` لا يخرج من مجلد المخرجات ولا يخدم من `work/` إلا رسوم المفاهيم.
- الصفحة بسياسة CSP تمنع أي مصدر خارجي، وبلا ذاكرة مؤقتة، وحجم الطلب محدود بـ 8 KB.
- تفضيل السمة وحده في localStorage (راحة عرض، لا بيانات).

## التطوير

```bash
cd frontend
npm install
npm run build      # vue-tsc ثم vite build إلى src/sima/web/frontend_dist
npm test           # vitest
```

للتطوير الحي: `npm run dev` في `frontend/` مع `SIMA_VITE_DEV=1` عند تشغيل `sima board`.
