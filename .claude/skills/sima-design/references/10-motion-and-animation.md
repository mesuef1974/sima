# 10 — Motion & Animation for Brand

> **اقرأ هذا الملف فقط عند:** تصميم logo animation، brand intro motion، interactive brand element، أو تعريف motion principles ضمن brand guidelines.
> **مستوى Bloom المتوقع:** Apply → Analyze (تطبيق مبادئ + تحليل خيارات easing).

---

## 1. متى تحتاج motion في brand؟

| سياق | استخدمه | تجنّبه |
|------|---------|--------|
| Logo reveal (intro video، splash screen) | ✓ | ❌ على signage ثابت |
| Hover state على primary CTA | ✓ | ❌ على نص body |
| Loading / progress indicator | ✓ | ❌ كل scroll trigger |
| Brand pattern (background ambient) | ✓ بـ reduced-motion fallback | ❌ بدون pause control |
| Page transitions داخل website | ✓ بـ ≤300ms | ❌ ≥600ms (يبطئ الإحساس) |

**القاعدة الذهبية:** motion يخدم القراءة، لا يستعرض المصمم.

---

## 2. Motion Principles (Disney-12 المختزلة لـ brand)

5 من أصل 12 تنطبق على brand motion:

1. **Anticipation** — قبل الحركة الرئيسية، حركة معاكسة صغيرة (logo يصغر ثم يكبر = أكثر "حياة" من النمو المباشر).
2. **Follow-Through** — العنصر لا يتوقف فجأة؛ overshoot 5-10% ثم استقرار.
3. **Easing** — لا linear للـ brand motion. linear = روبوتي.
4. **Staging** — حركة واحدة تجذب الانتباه، لا 3 معاً.
5. **Slow-In / Slow-Out** — البداية بطيئة + النهاية بطيئة، السرعة في المنتصف.

---

## 3. Easing Curves (cheat sheet)

| Curve | CSS | متى |
|-------|-----|------|
| `ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | الافتراضي لـ enter (شيء يدخل المشهد) |
| `ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | exit (شيء يخرج) |
| `ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | حركة بين موضعين (move) |
| `spring(0.5, 100, 10, 0)` | (Framer Motion) | brand reveal، logo bounce |
| ❌ `linear` | `linear` | لا تستخدمه إلا لـ infinite progress (loader spinner) |

**Material Design Standard:** Standard easing = `cubic-bezier(0.4, 0.0, 0.2, 1)` لـ 95% من الحالات.

---

## 4. Duration Guide

| الحركة | المدة المثالية | المبرر |
|--------|---------------|--------|
| Hover state | 150ms | تحت 100ms = غير محسوس، فوق 200ms = بطيء |
| Button press / tap feedback | 100-150ms | فوري لكن مرئي |
| Logo reveal (intro) | 600-1200ms | مساحة لقراءة الفكرة |
| Page transition | 200-300ms | لا يتعب المستخدم |
| Modal enter / exit | 250ms enter / 200ms exit | exit أسرع من enter دائماً |
| Brand pattern loop | 4-8s | لا يلفت الانتباه عن المحتوى |
| Loader spinner | 800ms-1.2s rotation | فوقها = إحساس بالتعليق |

**قاعدة عامة:** ≤300ms للتفاعلات، 600-1200ms للـ brand statements.

---

## 5. Logo Reveal — مثال عملي (CSS)

```css
@keyframes logo-reveal {
  0%   { opacity: 0; transform: scale(0.85) translateY(8px); }
  60%  { opacity: 1; transform: scale(1.03) translateY(0); }   /* anticipation overshoot */
  100% { opacity: 1; transform: scale(1) translateY(0); }       /* follow-through settle */
}

.brand-logo {
  animation: logo-reveal 800ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .brand-logo { animation: none; opacity: 1; }
}
```

3 ملاحظات:
- **overshoot عند 60%** = anticipation/follow-through معاً.
- **`both`** يحفظ الحالة النهائية (لا يعود لـ 0% بعد الانتهاء).
- **`prefers-reduced-motion`** إلزامي — WCAG 2.3.3 + احترام الإعدادات.

---

## 6. Brand Intro Motion (After Effects / Lottie)

عند تصميم logo animation للـ video / Lottie:

| المرحلة | المدة | التقنية |
|---------|-------|---------|
| Build-up | 0-400ms | عناصر تدخل واحداً تلو الآخر (stagger 50-80ms) |
| Hero moment | 400-700ms | الشعار كامل + لون + spring scale |
| Settle | 700-900ms | overshoot ثم استقرار + (اختياري) tagline يظهر |

**Lottie tips:**
- صدِّر بـ 30fps لا 60 (الفرق غير محسوس على الـ brand، الحجم نصف).
- استخدم expressions بدل keyframes لكل frame (ملف أصغر).
- اختبر على Android low-end — Lottie ثقيل أحياناً.

---

## 7. Reduced Motion (WCAG 2.3.3 + 1.4.13)

**إلزامي لكل brand motion يخرج للمستخدم النهائي:**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

ضع هذا قبل أي brand animation. المستخدمون ذوو الحساسية الدهليزية (vestibular sensitivity) يحتاجونه.

---

## 8. Brand Motion Checklist (قبل التسليم)

- [ ] كل animation له `prefers-reduced-motion` fallback.
- [ ] لا motion على نص body طويل (≥3 أسطر).
- [ ] Easing ليس `linear` (إلا للـ infinite loaders).
- [ ] Duration ضمن المجال (150-300ms للتفاعل، 600-1200ms للـ brand reveal).
- [ ] لا 3+ حركات متزامنة على نفس الشاشة.
- [ ] Lottie/After Effects: تم اختبار الأداء على mobile متوسط الأداء.
- [ ] Pause control موجود لأي ambient loop.
- [ ] Motion يخدم hierarchy (يجذب للعنصر الأهم) لا يشتت.

---

## 9. Anti-patterns

- ❌ Logo يدور 360° لا سبب — gimmick بلا معنى.
- ❌ Parallax مفرط على every section.
- ❌ Hover effect يؤخر فهم الزر (>200ms).
- ❌ Auto-play video كـ brand intro بدون mute + pause.
- ❌ Spring مفرط (bounce 10×) — يبدو رخيصاً.
- ❌ نسيان `prefers-reduced-motion` (فشل WCAG + إساءة accessibility).

---

## 10. مراجع

- Material Design — Motion: https://m3.material.io/styles/motion
- Apple HIG — Motion: https://developer.apple.com/design/human-interface-guidelines/motion
- Val Head — *Designing Interface Animation* (2016).
- Rachel Nabors — *Animation at Work* (2017).
- WCAG 2.3.3 (Animation from Interactions) + 1.4.13 (Content on Hover).

---

**Self-check قبل المتابعة:** هل أعرف الفرق بين `ease-out` و `ease-in`؟ متى أستخدم كلاً منهما؟ (إجابة: ease-out للداخل، ease-in للخارج).
