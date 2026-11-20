// تنسيق الوقت والمسارات بأرقام لاتينية كما في بقية منصات المالك.
const LOC = "ar-QA-u-nu-latn";

function date(iso?: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export const hm = (iso?: string | null): string => date(iso)?.toLocaleTimeString(LOC, { hour: "2-digit", minute: "2-digit" }) ?? "—";
export const full = (iso?: string | null): string => date(iso)?.toLocaleString(LOC, { dateStyle: "short", timeStyle: "short" }) ?? "—";
export const clock = (iso?: string | null): string => date(iso)?.toLocaleTimeString(LOC) ?? "—";

export function dur(a?: string | null, b?: string | null): string {
  const x = date(a), y = date(b);
  if (!x || !y) return "—";
  let m = Math.max(0, Math.round((y.getTime() - x.getTime()) / 6e4));
  const h = Math.floor(m / 60);
  m %= 60;
  return h ? `${h} س ${m} د` : `${m} د`;
}

export const cardKind = (s: string): string =>
  ["prepush_failed", "blocked", "cancelled"].includes(s) ? "bad" : ["deployed", "merged", "approved"].includes(s) ? "good" : "";

export const verdictKind = (v: string): string => (v === "approved" || v === "اعتُمد" ? "good" : v === "rejected" || v === "رُفض" ? "bad" : "warn");

/** رابط ملف مخرجات: كل مقطع مرمَّز على حدة فلا يخرج المسار من out/. */
export const out = (p?: string): string => (p ? "/out/" + p.split("/").map(encodeURIComponent).join("/") : "");

/** نص فيه `رمز` يُقسَّم إلى أجزاء تُعرض بلا HTML خام. */
export function codeParts(t: string): { code: boolean; text: string }[] {
  return t.split(/`([^`]+)`/).map((text, i) => ({ code: i % 2 === 1, text })).filter((x) => x.text);
}

/** حارس نية القرار (مرآة الخدمة): معرّفات الخيارات المذكورة في الملاحظة وليست المختار. */
export function strayIds(reason: string, ids: string[], chosen: string): string[] {
  const esc = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return ids.filter((i) => i && i.toLowerCase() !== chosen.toLowerCase() && new RegExp(`(?<![A-Za-z0-9])${esc(i)}(?![A-Za-z0-9])`, "i").test(reason));
}

export function intentProblem(reason: string, ids: string[], chosen: string): string {
  const other = strayIds(reason, ids, chosen);
  return other.length ? `ذكرتَ ${other.join("، ")} في الملاحظة ولم تختره. اختره من الخيارات المعروضة، أو احذفه من الملاحظة إن لم تقصد اختياره.` : "";
}

export const WHO_AR: Record<string, string> = { owner: "أنت", model: "النموذج", script: "الخط", project: "المشروع", designer: "المصمّم الخارجي" };
