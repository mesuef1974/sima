<!--
WCAG 1.4.11 decorative-vs-informational declaration.
Insert into Section 9 of brand-guide.template.md, OR keep as standalone document inside docs/brand/.
Closes lessons L-2026-04-15-032 and L-2026-04-15-035.
-->

# {Brand Name} — WCAG 2.2 AA Color Contrast & Accessibility Declarations

**Standard:** WCAG 2.2 AA
**Audit-ready as of:** {YYYY-MM-DD}
**Owner:** {brand owner}
**Linked decision:** {DEC-id}

---

## Sanity Test Reminder

> **"If I remove this element entirely, is the logo still recognizable as the brand?"**
> - **YES** → element is **decorative** → exempt from 1.4.11.
> - **NO** → element is **informational** → must meet contrast threshold.

The default for any unclassified element is **informational** (fail-safe). Without this document, an external auditor will assume the strictest interpretation.

---

## Informational Elements (must meet contrast thresholds)

| Element | WCAG criterion | Required contrast | Verified-on backgrounds |
|---------|---------------|-------------------|------------------------|
| Primary wordmark "{brand}" | 1.4.3 (text) | 4.5:1 | white, neutral-light, neutral-dark |
| Icon silhouette (mark) | 1.4.11 (non-text) | 3:1 | white, brand-primary, brand-secondary |
| Horizon/baseline lines (if present) | 1.4.11 | 3:1 | all approved bgs |
| Semantic UI (success/error/warning) | 1.4.1 (color not sole means) | 3:1 + iconography | adjacent surfaces |
| Active/focused border | 1.4.11 | 3:1 | container surface |

---

## Decorative Accents (EXEMPT from WCAG 1.4.11)

For each item below, the sanity test passed: removing it does NOT impair brand recognition. Therefore exempt per WCAG 2.2 SC 1.4.11 "Non-text Contrast" decorative-exception clause.

| Element | Coordinates / location | Rationale | Sanity-test result |
|---------|----------------------|-----------|-------------------|
| {e.g., gold accent dot} | {cx=82 cy=62 r=8} | Pure ornament; carries no information | Logo recognizable without it ✓ |
| {Subtle radial gradient behind mark} | background layer | Atmospheric/decorative effect | Logo identical without it ✓ |
| {Star particles / sparkles} | scattered | Decorative; no info carried | Removed → still on-brand ✓ |
| {Grid lines (e.g., 120×120)} | construction guides | Layout aid; never displayed in production | N/A (not user-facing) |

---

## Testing Protocol (for every new variant)

1. All "Informational Elements" verified ≥ 3:1 (1.4.11) or 4.5:1 (1.4.3) on the target background — use `scripts/check-contrast.py`.
2. Logo remains recognizable without decorative accents (run sanity test).
3. Colorblind simulations (protanopia, deuteranopia, tritanopia) do not render informational elements invisible.
4. Print + screen + small-size renders all checked.

---

## Why This Document Exists

- **Brand-guide declaration > SVG edits.** One paragraph here saves 15+ file edits later.
- **Legal evidence.** In a11y disputes, brand guides are treated as evidence of declared intent. Git history of an SVG is not.
- **Audit-proofing.** Without this declaration, any auditor defaults to "informational" assumption.

## References

- WCAG 2.2 SC 1.4.1 (Use of Color)
- WCAG 2.2 SC 1.4.3 (Contrast Minimum — text)
- WCAG 2.2 SC 1.4.11 (Non-text Contrast)
- LL-2026-04-15-032 (decorative-vs-informational — Azkia)
- LL-2026-04-15-035 (decorative exemption needs explicit docs — Azkia)
