import { readFileSync } from "node:fs";
import { join } from "node:path";

// تباين WCAG: النص ≥ 4.5:1 والمعلوماتي (حدود الأزرار والتركيز) ≥ 3:1، في الوضعين.
const tokens = readFileSync(join(process.cwd(), "src", "styles", "tokens.css"), "utf-8");

function vars(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b/g)].map((m) => [m[1], m[2]]));
}
const light = vars(tokens.match(/:root\{[^}]*\}/)?.[0] ?? "");
const darkOnly = vars(tokens.match(/:root\[data-theme="dark"\]\{[^}]*\}/)?.[0] ?? "");
const dark = { ...light, ...darkOnly };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT: [string, string][] = [
  ["--ink", "--bg"], ["--ink", "--surface"], ["--ink", "--raised"], ["--ink2", "--bg"], ["--ink2", "--surface"], ["--ink2", "--raised"],
  ["--ink3", "--surface"], ["--ink3", "--bg"],
  ["--brand-ink", "--bg"], ["--brand-ink", "--surface"], ["--brand-ink", "--brand-soft"], ["--on-brand", "--brand"],
  ["--good", "--good-soft"], ["--bad", "--bad-soft"], ["--warn", "--warn-soft"], ["--good", "--surface"], ["--bad", "--surface"],
  ["--paper-ink", "--paper"],
];
const INFO: [string, string][] = [["--line-strong", "--surface"], ["--focus", "--surface"], ["--focus", "--bg"]];

describe.each([["الفاتح", light], ["الداكن", dark]] as const)("التباين في الوضع %s", (_name, theme) => {
  it.each(TEXT)("نص %s على %s ≥ 4.5", (fg, bg) => {
    expect(theme[fg], fg).toBeDefined();
    expect(theme[bg], bg).toBeDefined();
    expect(ratio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
  });
  it.each(INFO)("معلوماتي %s على %s ≥ 3", (fg, bg) => {
    expect(ratio(theme[fg], theme[bg])).toBeGreaterThanOrEqual(3);
  });
});
