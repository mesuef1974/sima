import type { BoardState, SimaRun, Timeline, TrackNode } from "@/types";
import { WHO_AR } from "@/utils/format";

/** سجلات المشاريع بعد تحديث: الناجح يحلّ محلّ القديم، والفاشل يُبقي آخر ما وصل بعلامة stale (لا يسقط المشروع من العرض
 *  فيُستنتج من غيابه ما ليس فيه)، وما خرج من اللقطة (مخفي أو محذوف) يسقط. */
export function mergeTimelines(prev: Record<string, Timeline>, projects: string[], fetched: Record<string, Timeline | null>): Record<string, Timeline> {
  const next: Record<string, Timeline> = {};
  for (const p of projects) {
    const t = fetched[p];
    if (t) next[p] = { ...t, stale: false };
    else if (prev[p]) next[p] = { ...prev[p], stale: true };
  }
  return next;
}

/** إصدار بلغ آخر خطواته: لا ينتظر أحدًا. */
export const finished = (t: Timeline): boolean => t.progress.total > 0 && t.progress.done >= t.progress.total;

/** ما يُكتب عن المنتظَر في لافتة التقدم: إصدار مكتمل لا «ينتظر الخط». */
export function waitLabel(t: Timeline): string {
  if (t.now.who === "script" && finished(t)) return "مكتمل";
  return `ينتظر: ${WHO_AR[t.now.who] ?? t.now.who}`;
}

export interface OwnerRow { at: string; project: string; name: string; version: string; text: string }

/** كل قرارات المالك في كل مشروع من سجلاته (أحداث who=owner)، الأحدث أولًا. مشروع لم يصل سجله بعد تُعرض قرارات مفاهيمه
 *  من اللقطة فلا يختفي ما سُجّل. */
export function ownerDecisions(state: BoardState | null, timelines: Record<string, Timeline | undefined>): OwnerRow[] {
  const rows: OwnerRow[] = [];
  for (const r of state?.sima ?? []) {
    const t = timelines[r.project];
    if (t) {
      for (const e of t.events) if (e.who === "owner") rows.push({ at: e.at, project: r.project, name: r.name_ar, version: t.version, text: e.text });
    } else {
      for (const d of r.decisions)
        rows.push({ at: d.at, project: r.project, name: r.name_ar, version: r.version,
          text: `${d.verdict_ar} ${d.concept}`.trim() + (d.reason ? `: ${d.reason}` : "") });
    }
  }
  return rows.sort((a, b) => b.at.localeCompare(a.at));
}

/** مسار مراحل إصدار في صفحة المشاريع من خطواته كما يرسلها الخادم (نموذج سجل المشروع وترتيبه وأسماؤه)؛
 *  لا عدد ثابتًا للمراحل ولا مرحلة أخيرة مسمّاة هنا: الأخيرة آخر ما أرسله الخادم. */
export function trackOf(steps: SimaRun["steps"]): { nodes: TrackNode[]; p: number; chip: string; finalKey: string } {
  const nodes: TrackNode[] = steps.map((s) => ({ key: s.key, label: s.label, status: s.status === "current" ? "active" : s.status, at: "" }));
  const done = nodes.length > 0 && nodes.every((x) => x.status === "done");
  const active = nodes.findIndex((x) => x.status === "active");
  const lastDone = nodes.map((x) => x.status).lastIndexOf("done");
  return { nodes, p: done ? nodes.length - 1 : active >= 0 ? active : Math.max(0, lastDone), chip: done ? "good" : "run", finalKey: nodes.at(-1)?.key ?? "" };
}
