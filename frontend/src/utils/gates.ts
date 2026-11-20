import type { BoardState, InboxItem, Limits } from "@/types";
import { out } from "@/utils/format";

/** حدود الخادم لكل ملاحظة أو سبب إن لم ترسلها اللقطة (خادم أقدم): الزائد يُرفض هناك، فيقف الحقل عنده هنا. */
export const DEFAULT_LIMITS: Limits = { decide: 500, medium: 800, identity: 1200, note: 600, reason: 800 };

export function limitOf(state: BoardState | null | undefined, kind: keyof Limits): number {
  const n = state?.limits?.[kind];
  return typeof n === "number" && n > 0 ? n : DEFAULT_LIMITS[kind];
}

/** مفتاح بطاقة البوابة: بصمة المعروض فيه لكل نوع، فيُبنى المكوّن من جديد حين يتغيّر المعروض ولا تبقى مسودة على قديم. */
export function gateKey(it: InboxItem): string {
  const gate = it.kind === "identity" || it.kind === "stalled" ? (it.gate ?? "") : "";
  const digest = "digest" in it ? it.digest : "";
  return [it.project, it.version, it.kind, gate, it.key, digest].join("|");
}

/** رابط صورة بوابة مختوم ببصمة المعروض: صورة تغيّرت في المسار نفسه لا تُعرض من ذاكرة المتصفح القديمة. */
export function stamped(path: string | undefined, digest: string | undefined): string {
  const u = out(path);
  return u && digest ? `${u}?d=${encodeURIComponent(digest)}` : u;
}
