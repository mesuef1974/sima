---
paths:
  - "src/sima/cli.py"
  - "src/sima/web/**"
  - "src/sima/config.py"
  - "src/sima/env.py"
  - "pyproject.toml"
  - "tests/**"
  - "briefs/**"
  - "frontend/package.json"
  - "frontend/src/**"
---
## أوامر
```bash
uv sync --all-groups
uv run pytest
uv run sima run briefs/math_papers.yaml
uv run sima decide briefs/math_papers.yaml --approve w1 --reason "..."
uv run sima name-check briefs/math_papers.yaml --status clear --source WIPO --source MOCI
uv run sima identity-decide briefs/math_papers.yaml --gate directions --approve d1   # أو --revise/--reject --reason "..."
uv run sima deliver briefs/math_papers.yaml --repo "D:/أوراق الرياضيات"
uv run sima db start   # ثم: db migrate | db sync | db status | db stop
cd frontend && npm run lint && npm run build && npm test   # الواجهة: eslint وبناء وفحص أنواع واختبارات vitest
uv run sima designer briefs/<project>.yaml --pick 5   # مسار المصمّم الخارجي: اختيار السكتش؛ --intake <مجلد> يستلم المتجه بيانَ اعتماد
uv run sima eval list   # حالات تقييم الرسّام؛ run [--case eval_watad] [--until thumbs] [--label ...] مدفوع بأمر المالك، compare <أ> <ب>، و--no-model تجريبي بلا كلفة
uv run sima board   # منصة سِمة على 127.0.0.1:8766 وحدها؛ --repo <مستودع> يضيف بطاقات دفتر ذلك المستودع (قرار المالك 2026-11-11: بلا)
```
