import type { BoardState, InboxItem, Job, SimaRun, Timeline } from "@/types";
import { awaitingDelivery, deliveriesOf } from "@/utils/deliveries";
import { DEFAULT_LIMITS, gateKey, limitOf, stamped } from "@/utils/gates";
import { layerLive } from "@/utils/layerLive";
import { mergeTimelines, ownerDecisions, trackOf, waitLabel } from "@/utils/timelines";
import { todos } from "@/utils/todos";

// المرحلة 5 من مراجعة الأتمتة 2026-11-14 (م5 م6 م7 م8): عروض تخالف الحال أو تُبنى من بيانات فارغة.
const run = (over: Partial<SimaRun> = {}): SimaRun => ({
  project: "awraq", name_ar: "أوراق", version: "v6", key: "k", closed: false, mark: "", preview: "", concept: {},
  name_check: { status: "", status_ar: "", at: "", note: "" }, deliver: { card: "", branch: "" }, files: [], steps: [], decisions: [], ...over,
});
const state = (sima: SimaRun[], over: Partial<BoardState> = {}): BoardState =>
  ({ now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: null }, sima, cards: [], inbox: [], jobs: [], ...over });
const tl = (now: Partial<Timeline["now"]>, over: Partial<Timeline> = {}): Timeline => ({
  project: "awraq", version: "v6", key: "k", closed: false, now: { who: "script", text: "", since: "", ...now }, events: [],
  progress: { done: 3, total: 14, current: "diverge", steps: [] }, ...over,
});
const landedTl = (landed: boolean) => tl({ who: "project" }, { progress: { done: 13, total: 14, current: "landed",
  steps: [{ key: "landed", label: "الدمج في المشروع", status: landed ? "done" : "current" }] } });

describe("م5: بصمة المعروض في مفتاح البطاقة وروابط صورها", () => {
  it("مفتاح كل بطاقة يحمل بصمتها، فتغيّر المعروض بالمفتاح نفسه يبني بطاقة جديدة", () => {
    const a = { kind: "concepts", project: "p", version: 1, key: "k", digest: "aaa" } as InboxItem;
    const b = { ...a, digest: "bbb" } as InboxItem;
    expect(gateKey(a)).not.toBe(gateKey(b));
    for (const kind of ["style", "sketches", "stalled"]) {
      const x = { kind, project: "p", version: 1, key: "k", digest: "x1" } as InboxItem;
      expect(gateKey(x), kind).toContain("x1");
    }
    expect(gateKey({ kind: "identity", gate: "book", project: "p", version: 1, key: "k", digest: "d" } as InboxItem)).toContain("book");
  });

  it("رابط الصورة مختوم بالبصمة ومرمَّز، وبلا بصمة يبقى كما هو", () => {
    expect(stamped("p/v1/c 1.png", "ab+c")).toBe("/out/p/v1/c%201.png?d=ab%2Bc");
    expect(stamped("p/v1/c.png", "")).toBe("/out/p/v1/c.png");
    expect(stamped("", "x")).toBe("");
  });
});

describe("م8: حدود الملاحظات من الخادم", () => {
  it("تُقرأ من state.limits، وأرقام العقد بديل لخادم أقدم أو قيمة فاسدة", () => {
    expect(limitOf(state([], { limits: { note: 50 } }), "note")).toBe(50);
    expect(limitOf(state([], { limits: { note: 50 } }), "reason")).toBe(DEFAULT_LIMITS.reason);
    expect(limitOf(state([], { limits: { decide: 0 } }), "decide")).toBe(500);
    expect(limitOf(null, "identity")).toBe(1200);
    expect(DEFAULT_LIMITS).toEqual({ decide: 500, medium: 800, identity: 1200, note: 600, reason: 800 });
  });
});

describe("م6 أ: طلب دمج ينتظر اعتماد المالك بلا --repo", () => {
  it("يُبنى بند «استلام المشروع» من سجل المشروع لا من بطاقات الدفتر الفارغة", () => {
    const s = state([run({ deliver: { card: "c1", branch: "card/c1" }, closed: true })]);
    const t = todos(s, { awraq: tl({ who: "owner", text: "الطلب ينتظر اعتمادك.", pr_url: "https://github.com/o/r/pull/7", command: "& x" }) });
    expect(t).toHaveLength(1);
    expect(t[0]).toMatchObject({ ic: "pr", href: "https://github.com/o/r/pull/7", external: true });
    expect(t[0].title).toContain("أوراق");
  });

  it("لا يُكرَّر إن جاء الطلب نفسه من دفتر مربوط، ولا يُذكر ما ليس عند المالك", () => {
    const card = { id: "c1", title: "هوية أوراق", state: "pr_opened", url: "https://github.com/o/r/pull/7", log: [] } as unknown as BoardState["cards"][number];
    const s = state([run()], { cards: [card] });
    expect(todos(s, { awraq: tl({ who: "owner", text: "", pr_url: card.url }) }).filter((x) => x.ic === "pr")).toHaveLength(1);
    expect(todos(state([run()]), { awraq: tl({ who: "project", text: "", pr_url: card.url }) })).toEqual([]);
  });
});

describe("م6 ج: حزم تنتظر التسليم", () => {
  it("لا تُعدّ حزمة سُلّم إصدارها أو دُمج، ولا حزمة لم يُغلق إصدارها", () => {
    const pkg = [{ key: "package", label: "الحزمة", status: "done" as const }];
    const s = state([
      run({ project: "a", closed: true, steps: pkg }),
      run({ project: "b", closed: true, steps: pkg, deliver: { card: "c1", branch: "card/c1" } }),
      run({ project: "c", closed: true, steps: pkg, deliver: { card: "", branch: "", in_place: "6f90530" } }),
      run({ project: "d", closed: false, steps: pkg }),
    ]);
    expect(awaitingDelivery(s).map((r) => r.project)).toEqual(["a"]);
  });
});

describe("م6 د: مسار صفحة المشاريع من خطوات الخادم", () => {
  it("يرسم كل الخطوات بأسمائها وترتيبها، والأخيرة نهاية المسار أيًّا كانت", () => {
    const steps = [{ key: "brief", label: "الموجز", status: "done" as const }, { key: "identity", label: "الدليل", status: "current" as const },
      { key: "deliver", label: "التسليم", status: "pending" as const }, { key: "landed", label: "الدمج في المشروع", status: "pending" as const }];
    const t = trackOf(steps);
    expect(t.nodes.map((n) => n.label)).toEqual(["الموجز", "الدليل", "التسليم", "الدمج في المشروع"]);
    expect(t).toMatchObject({ p: 1, chip: "run", finalKey: "landed" });
    expect(trackOf(steps.map((s) => ({ ...s, status: "done" as const })))).toMatchObject({ p: 3, chip: "good" });
  });
});

describe("م6 هـ: لافتة التقدم", () => {
  it("إصدار مكتمل يُكتب «مكتمل» لا «ينتظر: الخط»", () => {
    expect(waitLabel(tl({ who: "script", text: "اكتمل كل شيء" }, { closed: true, progress: { done: 14, total: 14, current: null, steps: [] } }))).toBe("مكتمل");
    expect(waitLabel(tl({ who: "model" }))).toBe("ينتظر: النموذج");
    expect(waitLabel(tl({ who: "script" }))).toBe("ينتظر: الخط");
  });
});

describe("م6 ز: كل قرارات المالك", () => {
  it("من أحداث المالك في سجل كل مشروع، الأحدث أولًا، ومن قرارات المفاهيم لمشروع لم يصل سجله", () => {
    const s = state([run(), run({ project: "watad", name_ar: "وتد", version: "v1",
      decisions: [{ at: "2026-11-13T09:00:00", verdict: "rejected", verdict_ar: "رُفض", concept: "c2", medium_ar: "", reason: "مزدحم" }] })]);
    const rows = ownerDecisions(s, { awraq: tl({}, { events: [
      { at: "2026-11-14T08:00:00", who: "owner", text: "اعتُمد دليل الهوية" },
      { at: "2026-11-14T09:00:00", who: "model", text: "رسم" },
      { at: "2026-11-14T07:00:00", who: "owner", text: "اختير السكتش 11" }] }) });
    expect(rows.map((r) => r.text)).toEqual(["اعتُمد دليل الهوية", "اختير السكتش 11", "رُفض c2: مزدحم"]);
    expect(rows[2]).toMatchObject({ name: "وتد", version: "v1" });
  });
});

describe("م6 ط: رسم الطبقات الحيّ", () => {
  const net = { online: true, polling: true };
  it("الفحص المردود من audit.failed لا من حالة خطوة", () => {
    const live = layerLive(state([run({ audit: { passed: 9, failed: 1 } })]), {}, null, net);
    expect(live.layers.checks).toMatchObject({ tone: "off", note: "فحص مردود في أوراق: 1 من 10" });
    expect(layerLive(state([run({ audit: { passed: 10, failed: 0 } })]), {}, null, net).layers.checks.tone).toBe("idle");
  });

  it("تشغيل توقّف يظهر متوقفًا على التشغيل الآلي لا «هادئًا»، من حالة التشغيل أو من سجل المشروع", () => {
    const job: Job = { project: "awraq", state: "stopped", code: 6, code_ar: "توقّف التشغيل الآلي", started: "2026-11-14T00:00:00", ended: "2026-11-14T00:05:00", message: "" };
    const fromJob = layerLive(state([run()], { jobs: [job] }), { awraq: tl({ who: "script", text: "جاهز للاستئناف" }) }, null, net);
    expect(fromJob.tokens[0]).toMatchObject({ layer: "line", part: "التشغيل الآلي", tone: "off", stopped: true });
    expect(fromJob.layers.line.note).toBe("متوقف ويُستأنف بزر: أوراق");
    expect(fromJob.headline).not.toContain("هادئ");
    const fromTl = layerLive(state([run()]), { awraq: tl({ who: "script", state: "stopped", text: "توقّف الخط بخطأ" }) }, null, net);
    expect(fromTl.tokens[0]).toMatchObject({ tone: "off", text: "توقّف الخط بخطأ" });
  });

  it("كلفة استدعاءات مقطوعة تُذكر بحدّها الأعلى", () => {
    const live = layerLive(state([run({ cost: { usd: 4, calls: 5, ref: 10, level: "ok", unknown: 2 } })]), {}, null, net);
    expect(live.layers.models.facts).toContainEqual({ k: "محسوبة بحدّها الأعلى", v: "2" });
  });
});

describe("م7: فشل جلب سجل مشروع", () => {
  it("يبقى آخر سجل بعلامة stale، والناجح يحلّ محلّه، وما خرج من اللقطة يسقط", () => {
    const old = landedTl(true);
    const next = mergeTimelines({ awraq: old, gone: old }, ["awraq", "watad"], { awraq: null, watad: tl({}) });
    expect(Object.keys(next).sort()).toEqual(["awraq", "watad"]);
    expect(next.awraq).toMatchObject({ stale: true, progress: old.progress });
    expect(next.watad.stale).toBe(false);
  });

  it("المدموج لا يُعدّ «ينتظر الدمج» إن غاب سجله: حاله غير معروف", () => {
    const s = state([run({ deliver: { card: "c1", branch: "card/c1" } })]);
    expect(deliveriesOf(s, {})[0]).toMatchObject({ landed: false, known: false });
    expect(deliveriesOf(s, { awraq: landedTl(true) })[0]).toMatchObject({ landed: true, known: true });
    const live = layerLive(s, {}, null, { online: true, polling: true });
    expect(live.layers.store.note).not.toBe("كل ما سُلّم مدموج");
    expect(live.layers.store.facts).toContainEqual({ k: "حالها غير معروف", v: "1" });
  });
});
