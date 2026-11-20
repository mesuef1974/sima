import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

// حارس الهوية: الألوان تُعرَّف في tokens.css وحدها، وكل متغير مستعمل معرَّف هناك.
const SRC = join(process.cwd(), "src"); // vitest يعمل من مجلد frontend
const STYLES = join(SRC, "styles");

function files(dir: string, ext: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path, ext);
    return path.endsWith(ext) ? [path] : [];
  });
}

const tokens = readFileSync(join(STYLES, "tokens.css"), "utf-8");
const defined = new Set([...tokens.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
const sheets = [...files(SRC, ".vue"), ...files(STYLES, ".css").filter((path) => !path.endsWith("tokens.css"))];
const RAW_COLOR = /#[0-9a-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\(/i;
// المتغيرات التي يضبطها المكوّن نفسه بالسمة style (تتبع بيانات التشغيل لا الهوية)
const LOCAL = new Set(["--p", "--n", "--node"]);

describe("رموز الهوية", () => {
  it("لا لون خامًا خارج tokens.css", () => {
    const offenders = sheets.filter((path) => RAW_COLOR.test(readFileSync(path, "utf-8")));
    expect(offenders.map((p) => p.replace(SRC, ""))).toEqual([]);
  });

  it("كل var(--x) مستعمل معرَّف في tokens.css", () => {
    const missing = new Set<string>();
    for (const path of sheets) {
      for (const m of readFileSync(path, "utf-8").matchAll(/var\((--[a-z0-9-]+)/g)) {
        if (!defined.has(m[1]) && !LOCAL.has(m[1])) missing.add(`${m[1]} في ${path.replace(SRC, "")}`);
      }
    }
    expect([...missing]).toEqual([]);
  });

  it("الوضع الداكن يعرّف كل ما يعرّفه الفاتح من ألوان الأدوار", () => {
    const block = (re: RegExp) => new Set([...(tokens.match(re)?.[0] ?? "").matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
    const dark = block(/:root\[data-theme="dark"\]\{[^}]*\}/);
    const auto = block(/@media \(prefers-color-scheme:dark\)\{[\s\S]*?\}\}/);
    expect([...dark].filter((k) => !auto.has(k))).toEqual([]);
    expect([...auto].filter((k) => !dark.has(k))).toEqual([]);
    for (const k of ["--bg", "--surface", "--ink", "--brand", "--on-brand", "--bad", "--good"]) expect(dark.has(k)).toBe(true);
  });
});
