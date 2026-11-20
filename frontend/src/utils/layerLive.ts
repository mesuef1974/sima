import type { Actor, Layer } from "@/data/layers";
import type { BoardState, InboxItem, Job, Registry, SimaRun, Timeline, Who } from "@/types";
import { deliveriesOf } from "@/utils/deliveries";
import { clock } from "@/utils/format";

// الحال الحيّ فوق رسم الطبقات: أين يقف كل مشروع الآن (طبقة ومكوّن)، ونبض كل طبقة ووصلة، وأرقامها.
// دالة صافية على لقطة /api/state وسجلات المشاريع؛ لا تخمين: ما لا تقوله اللقطة لا يُرسم.
export type LayerId = Layer["id"];
/** run يعمل الآن، wait ينتظر طرفًا، ok سليم مستقر، off متعطّل أو متوقف يُستأنف بزر، idle لا شيء هنا الآن. */
export type Tone = "run" | "wait" | "ok" | "off" | "idle";
export type Flow = "down" | "up" | "both" | null;
/** stopped: توقّف التشغيل الآلي أو الخط على هذا المشروع ويُستأنف بزر. */
export interface Token { project: string; name: string; version: string; layer: LayerId; no: number; part: string; who: Actor; tone: Tone; text: string; stopped?: boolean }
export interface Fact { k: string; v: string }
export interface LayerLive { tone: Tone; note: string; facts: Fact[]; last?: { text: string; at: string } }
export interface Live { headline: string; tokens: Token[]; layers: Record<LayerId, LayerLive>; links: Flow[]; loop: boolean }

export const LAYER_NO: Record<LayerId, number> = { owner: 1, platform: 2, line: 3, models: 4, checks: 5, store: 6 };
export const TONE_AR: Record<Tone, string> = { run: "يعمل الآن", wait: "ينتظر", ok: "سليم", off: "متعطّل", idle: "هادئ" };
/** بطاقة الوارد ← مكوّن طبقة المالك (الأسماء كما في data/layers.ts). */
export const GATE_PART: Record<string, string> = { style: "الطابع البصري", concepts: "العلامة", sketches: "العلامة", name_check: "تحقق الاسم",
  strategy: "المنصة الاستراتيجية", directions: "اتجاه الهوية", book: "دليل الهوية" };
export const PART = { auto: "التشغيل الآلي", run: "`sima run`", drawer: "الرسّام", designer: "المصمّم الخارجي", disk: "القرص", deliver: "التسليم", project: "المشروع المستلم" } as const;
const EVENT_LAYER: Record<Who, LayerId> = { owner: "owner", model: "models", designer: "models", script: "line", project: "store" };

function decisions(n: number): string {
  return n === 1 ? "قرار واحد ينتظرك" : n === 2 ? "قراران ينتظرانك" : n <= 10 ? `${n} قرارات تنتظرك` : `${n} قرارًا ينتظرك`;
}
const names = (xs: { name: string }[]): string => [...new Set(xs.map((x) => x.name))].join("، ");
const latest = (js: Job[]): Job | undefined => [...js].sort((a, b) => (a.ended || a.started).localeCompare(b.ended || b.started)).at(-1);

function place(r: SimaRun, t: Timeline | undefined, item: InboxItem | undefined, job: Job | undefined): Omit<Token, "project" | "name" | "version" | "no"> | null {
  if (job?.state === "running") return { layer: "line", part: PART.auto, who: "s", tone: "run", text: "الخط يعمل الآن في الخلفية" };
  if (item) return { layer: "owner", part: GATE_PART[item.kind === "identity" ? item.gate : item.kind] ?? "", who: "o", tone: "wait", text: item.title };
  // توقّف التشغيل الآلي أو الخط: حال يُستأنف بزر، لا هدوء (رمز التوقف في الطبقة نفسها)
  if (t?.now.state === "stopped" || (job?.state === "stopped" && !t?.closed))
    return { layer: "line", part: PART.auto, who: "s", tone: "off", stopped: true, text: t?.now.text || job?.code_ar || job?.message || "توقّف التشغيل الآلي" };
  if (!t) return null;
  const { who, text } = t.now;
  const cur = t.progress?.current ?? null;
  if (who === "owner") {
    if (cur === "landed") return { layer: "store", part: PART.project, who: "o", tone: "wait", text };
    if (cur === "deliver") return { layer: "store", part: PART.deliver, who: "o", tone: "wait", text };
    return { layer: "owner", part: "", who: "o", tone: "wait", text };
  }
  if (who === "model") return { layer: "models", part: PART.drawer, who: "m", tone: "wait", text };
  if (who === "designer") return { layer: "models", part: PART.designer, who: "d", tone: "wait", text };
  if (who === "project") return { layer: "store", part: PART.project, who: "d", tone: "wait", text };
  if (t.progress && t.progress.total > 0 && t.progress.done === t.progress.total)
    return { layer: "store", part: r.deliver.card || r.deliver.in_place || r.deliver.manual ? PART.deliver : PART.disk, who: "s", tone: "ok", text };
  return { layer: "line", part: PART.run, who: "s", tone: "idle", text };
}

export function layerLive(state: BoardState | null, timelines: Record<string, Timeline | undefined>, registry: Registry | null,
  net: { online: boolean; polling: boolean }): Live {
  const runs = state?.sima ?? [];
  const inbox = state?.inbox ?? [];
  const jobs = state?.jobs ?? [];
  const running = jobs.filter((j) => j.state === "running");
  const tokens: Token[] = [];
  for (const r of runs) {
    // آخر تشغيل للمشروع (الجاري يغلب): منه يُعرف التوقف ولو غاب سجله
    const job = running.find((j) => j.project === r.project) ?? latest(jobs.filter((j) => j.project === r.project));
    const p = place(r, timelines[r.project], inbox.find((i) => i.project === r.project), job);
    if (p) tokens.push({ project: r.project, name: r.name_ar, version: r.version, no: LAYER_NO[p.layer], ...p });
  }
  const at = (id: LayerId, tone?: Tone) => tokens.filter((t) => t.layer === id && (!tone || t.tone === tone));

  // آخر حركة في كل طبقة من سجلات المشاريع
  const last: Partial<Record<LayerId, { text: string; at: string }>> = {};
  for (const r of runs) for (const e of timelines[r.project]?.events ?? []) {
    const id = EVENT_LAYER[e.who];
    if (e.at && (!last[id] || e.at > last[id].at)) last[id] = { text: `${r.name_ar}: ${e.text}`, at: e.at };
  }

  const cost = runs.reduce((a, r) => ({ usd: a.usd + (r.cost?.usd ?? 0), calls: a.calls + (r.cost?.calls ?? 0), unknown: a.unknown + (r.cost?.unknown ?? 0) }), { usd: 0, calls: 0, unknown: 0 });
  // الفحص المردود من نتيجة الفحوص الحتمية لآخر إصدار (audit)، لا من حالة خطوة لا يرسلها الخادم
  const failed = runs.filter((r) => (r.audit?.failed ?? 0) > 0).map((r) => ({ name: r.name_ar, n: r.audit!.failed, of: r.audit!.failed + r.audit!.passed }));
  const lastJob = latest(jobs);
  // توقف التشغيل الآلي أو الخط حالة في سجل المشروع (من نتيجته على القرص)، تبقى بعد إعادة تشغيل المنصة
  const halted = tokens.filter((t) => t.stopped).map((t) => t.name);
  const dl = deliveriesOf(state, timelines);
  const landed = dl.filter((d) => d.landed).length;
  const unknownDl = dl.filter((d) => !d.known).length;
  const prog = runs.reduce((a, r) => ({ done: a.done + (timelines[r.project]?.progress?.done ?? 0), total: a.total + (timelines[r.project]?.progress?.total ?? 0) }), { done: 0, total: 0 });
  const waitModel = at("models").filter((t) => t.who === "m"), waitDesigner = at("models").filter((t) => t.who === "d");
  const waitStore = at("store", "wait");

  const layers: Record<LayerId, LayerLive> = {
    owner: { tone: inbox.length || at("owner").length ? "wait" : "idle", note: inbox.length ? decisions(inbox.length) : at("owner").length ? `ينتظرك: ${names(at("owner"))}` : "لا شيء ينتظر قرارك",
      facts: [{ k: "ينتظر قرارك", v: String(inbox.length) }] },
    platform: { tone: net.online ? "ok" : "off", note: !net.online ? "منقطعة: ما تراه آخر ما وصل" : net.polling ? "حيّة، تتحدّث كل ثلاث ثوانٍ" : "حيّة، والتحديث الدوري متوقف",
      facts: [{ k: "مشاريع معروضة", v: String(runs.length) }, { k: "آخر تحديث", v: clock(state?.now) }] },
    line: { tone: running.length ? "run" : halted.length || lastJob?.state === "failed" ? "off" : "idle",
      note: running.length ? `يعمل الآن على: ${names(at("line", "run"))}` : halted.length ? `متوقف ويُستأنف بزر: ${halted.join("، ")}`
        : lastJob?.state === "failed" ? `آخر تشغيل فشل: ${lastJob.code_ar || lastJob.message}` : "لا تشغيل الآن",
      facts: [{ k: "تشغيل جارٍ", v: String(running.length) }, ...(prog.total ? [{ k: "خطوات منجزة", v: `${prog.done} من ${prog.total}` }] : [])] },
    models: { tone: waitModel.length || waitDesigner.length ? "wait" : "idle",
      note: waitModel.length ? `طلب ينتظر النموذج: ${names(waitModel)}` : waitDesigner.length ? `طلب ينتظر المصمّم الخارجي: ${names(waitDesigner)}` : "لا طلب معلّق",
      facts: cost.calls ? [{ k: "استدعاءات النموذج", v: String(cost.calls) }, { k: "الكلفة بالدولار", v: cost.usd.toFixed(2) },
        ...(cost.unknown ? [{ k: "محسوبة بحدّها الأعلى", v: String(cost.unknown) }] : [])] : [] },
    checks: { tone: failed.length ? "off" : "idle", note: failed.length ? `فحص مردود في ${failed[0].name}: ${failed[0].n} من ${failed[0].of}` : "لا فحص مردود",
      facts: [...runs.filter((r) => r.judge?.total != null).map((r) => ({ k: `حكم ${r.name_ar}`, v: `${r.judge!.total} من 40` })),
        ...(failed.length ? [{ k: "فحوص مردودة", v: String(failed.reduce((a, f) => a + f.n, 0)) }] : [])] },
    store: { tone: waitStore.length ? "wait" : unknownDl ? "idle" : dl.length ? "ok" : "idle",
      note: waitStore.length ? `ينتظر الدمج في مشروعه: ${names(waitStore)}` : unknownDl ? "حال بعض ما سُلّم غير معروف: لم يصل سجل مشروعه"
        : dl.length ? "كل ما سُلّم مدموج" : "لم يُسلَّم إصدار بعد",
      facts: [{ k: "إصدارات مسلَّمة", v: String(dl.length) }, { k: "مدموجة", v: String(landed) }, ...(unknownDl ? [{ k: "حالها غير معروف", v: String(unknownDl) }] : []),
        ...(registry ? [registry.online ? { k: "هويات في القاعدة", v: String(registry.identities.length) } : { k: "القاعدة", v: "متوقفة" }] : [])] },
  };
  for (const id of Object.keys(last) as LayerId[]) layers[id].last = last[id];

  const headline = !net.online ? "المنصة منقطعة: ما تراه آخر ما وصل قبل الانقطاع."
    : running.length ? `الخط يعمل الآن على ${names(at("line", "run"))}.`
      : inbox.length ? `${decisions(inbox.length)}.`
        : waitModel.length ? `طلب ينتظر النموذج في ${names(waitModel)}.`
          : waitDesigner.length ? `طلب ينتظر المصمّم الخارجي في ${names(waitDesigner)}.`
            : waitStore.length ? `${names(waitStore)}: ينتظر الدمج في مشروعه.`
              : halted.length ? `متوقف ويُستأنف بزر: ${halted.join("، ")}.`
              : "هادئ الآن: لا خط يعمل ولا قرار ينتظرك.";

  // الوصلات بين الصفوف: 0 المالك والمنصة، 1 المنصة والخط، 2 الخط والنماذج والفحص، 3 إلى الحفظ والتسليم
  const links: Flow[] = [inbox.length ? "up" : null, running.length ? "down" : null, running.length ? "both" : waitModel.length ? "down" : null, waitStore.length ? "down" : null];
  return { headline, tokens, layers, links, loop: running.length > 0 };
}
