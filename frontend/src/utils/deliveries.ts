import type { BoardState, SimaRun, Timeline } from "@/types";

/** known: سجل المشروع معروف (ولو قديمًا)؛ بلا سجل لا يُحكم على الدمج بشيء، فلا يُعدّ مدموجًا ولا منتظرًا. */
export interface Delivery { run: SimaRun; now?: Timeline["now"]; landed: boolean; known: boolean }

/** تسليم بلا بطاقة سُجّل بنقطة مدموجة: في مستودع سِمة نفسه أو يدويًّا في مستودع المشروع؛ كلاهما مدموج بنقطته. */
export const applied = (r: SimaRun): boolean => Boolean(r.deliver.in_place || r.deliver.manual);

export const delivered = (r: SimaRun): boolean => Boolean(r.deliver.card) || applied(r);

/** ما سُلّم من إصدارات: من علامة التسليم في كل إصدار، وحاله الآن من سجل المشروع نفسه (يقرأ دفتر المستودع المستلم).
 *  المنصة تعمل بلا مستودع واحد مربوط (قرار المالك 2026-11-11)، فالتسليمات تُعدّ لكل مشروع لا من دفتر واحد. */
export function deliveriesOf(state: BoardState | null, timelines: Record<string, Timeline | undefined>): Delivery[] {
  return (state?.sima ?? []).filter(delivered).map((r) => {
    const t = timelines[r.project];
    const inPlace = applied(r);
    return { run: r, now: t?.now, known: inPlace || Boolean(t), landed: inPlace || t?.progress?.steps.find((x) => x.key === "landed")?.status === "done" };
  });
}

/** حزم معتمدة تنتظر التسليم فعلًا: أُغلق إصدارها وبُنيت حزمته ولم يُسلَّم بعد (ما سُلّم أو دُمج لا يُعدّ، ولا حزمة دليلها
 *  لم يُعتمد بعد). */
export function awaitingDelivery(state: BoardState | null): SimaRun[] {
  return (state?.sima ?? []).filter((r) => r.closed && !delivered(r) && r.steps.find((x) => x.key === "package")?.status === "done");
}
