import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import FlowMap from "@/components/FlowMap.vue";
import LayerMap from "@/components/LayerMap.vue";
import { FLOW, LOOPS, WHO } from "@/data/flow";
import { REPAIR } from "@/data/repair";
import RepairMap from "@/components/RepairMap.vue";
import { ACTOR, GUARDS, LINKS, READING, TIERS } from "@/data/layers";
import AutomationPage from "@/pages/AutomationPage.vue";
import { staleChunk } from "@/router";
import { useBoard } from "@/stores/board";
import type { BoardState, Registry, Timeline } from "@/types";
import { GATE_PART, LAYER_NO, PART, layerLive } from "@/utils/layerLive";

// صفحة الأتمتة تصف البناء القائم: هذه الاختبارات تحرس اتساق الرسم وما لا يجوز أن يعود من نصوصها المتقادمة.
const layers = TIERS.flatMap((t) => t.layers);

describe("بيانات رسم الطبقات", () => {
  it("ست طبقات بمعرّفات فريدة، ولكل صفّين متتاليين وصلة واحدة", () => {
    expect(layers.map((l) => l.id)).toEqual(["owner", "platform", "line", "models", "checks", "store"]);
    expect(LINKS).toHaveLength(TIERS.length - 1);
  });

  it("الحلقة بين طبقتين متجاورتين فقط، وهما النماذج والفحص", () => {
    const looped = TIERS.filter((t) => t.loop);
    expect(looped).toHaveLength(1);
    expect(looped[0].layers.map((l) => l.id)).toEqual(["models", "checks"]);
  });

  it("كل مكوّن منسوب إلى منفّذ معروف، وكل طبقة تذكر دورها وحدّها", () => {
    for (const l of layers) {
      expect(l.role.length, l.id).toBeGreaterThan(10);
      expect(l.edge.startsWith("حدّها:"), l.id).toBe(true);
      expect(l.parts.length, l.id).toBeGreaterThanOrEqual(4);
      for (const p of l.parts) expect(Object.keys(ACTOR)).toContain(p.who);
    }
  });

  it("المصمّم الخارجي والمشروع المستلم خارج سِمة، وطبقة المالك كلها للمالك", () => {
    const by = (n: string) => layers.flatMap((l) => l.parts).find((p) => p.n === n);
    expect(by("المصمّم الخارجي")?.who).toBe("d");
    expect(by("المشروع المستلم")?.who).toBe("d");
    expect(layers[0].parts.every((p) => p.who === "o")).toBe(true);
  });
});

describe("LayerMap", () => {
  setActivePinia(createPinia());
  const w = mount(LayerMap);

  it("يرسم الطبقات الست مرقّمة بترتيبها، وطبقتَي الحلقة في صفّ واحد", () => {
    expect(w.findAll(".lm-layer")).toHaveLength(6);
    expect(w.findAll(".lm-no").map((x) => x.text())).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(w.findAll(".lm-tier.pair")).toHaveLength(1);
    expect(w.get(".lm-tier.pair").findAll(".lm-layer")).toHaveLength(2);
    expect(w.findAll(".lm-loop")).toHaveLength(1);
  });

  it("بين كل صفّين وصلة تذكر ما ينزل وما يعود", () => {
    const links = w.findAll(".lm-link");
    expect(links).toHaveLength(LINKS.length);
    for (const l of links) {
      expect(l.get(".down").text()).toContain("ينزل:");
      expect(l.get(".up").text()).toContain("يعود:");
    }
  });

  it("السياج وشرح القراءة مكتوبان كاملين، والأسهم مخفية عن قارئ الشاشة", () => {
    expect(w.findAll(".lm-guards li")).toHaveLength(GUARDS.length);
    expect(w.findAll(".lm-reading li")).toHaveLength(READING.length);
    expect(w.findAll("svg.lm-arrow").every((x) => x.attributes("aria-hidden") === "true")).toBe(true);
  });

  it("أسماء الملفات والأوامر معزولة الاتجاه بخط الشيفرة", () => {
    expect(w.findAll("bdi.mono").some((x) => x.text() === "sima run")).toBe(true);
    expect(w.text()).not.toContain("`");
  });
});

describe("الحال الحيّ على رسم الطبقات", () => {
  const parts = new Set(layers.flatMap((l) => l.parts.map((p) => p.n)));
  const run = (over: Record<string, unknown>) => ({ project: "awraq", name_ar: "أوراق", version: "v6", key: "k", closed: false, mark: "", preview: "", steps: [], decisions: [], files: [],
    concept: {}, name_check: { status: "", status_ar: "", at: "", note: "" }, deliver: { card: "", branch: "" }, ...over }) as unknown as BoardState["sima"][number];
  const tl = (who: string, done: number, current: string | null, events: Timeline["events"] = []) => ({ now: { who, text: "نص الحال", since: "" }, events,
    progress: { done, total: 12, current, steps: [{ key: "landed", label: "", status: done === 12 ? "done" : "pending" }] } }) as unknown as Timeline;
  const snap = (over: Partial<BoardState>) => ({ now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: "" }, sima: [run({})], cards: [], inbox: [], jobs: [], ...over }) as BoardState;
  const net = { online: true, polling: true };

  it("كل مكوّن يوضع عليه مشروع موجود باسمه في بيانات الطبقات", () => {
    for (const n of [...Object.values(GATE_PART), ...Object.values(PART)]) expect(parts, n).toContain(n);
    expect(Object.keys(LAYER_NO)).toEqual(layers.map((l) => l.id));
  });

  it("بوابة في الوارد تضع المشروع على مكوّنها في طبقة المالك وتحرّك الوصلة الصاعدة", () => {
    const item = { kind: "identity", gate: "book", project: "awraq", title: "دليل الهوية ينتظر اعتمادك" } as unknown as BoardState["inbox"][number];
    const live = layerLive(snap({ inbox: [item] }), { awraq: tl("owner", 10, "identity") }, null, net);
    expect(live.tokens[0]).toMatchObject({ layer: "owner", no: 1, part: "دليل الهوية", who: "o", tone: "wait" });
    expect(live.layers.owner).toMatchObject({ tone: "wait", note: "قرار واحد ينتظرك" });
    expect(live.links).toEqual(["up", null, null, null]);
    expect(live.headline).toContain("قرار واحد ينتظرك");
  });

  it("خط يعمل يغلب البوابة: المشروع على التشغيل الآلي، والوصلات إلى النماذج والحلقة متحركة", () => {
    const job = { project: "awraq", state: "running", code: null, code_ar: "", started: "2026-11-14T00:00:00+00:00", ended: "", message: "" } as BoardState["jobs"][number];
    const live = layerLive(snap({ jobs: [job] }), { awraq: tl("script", 4, "critique") }, null, net);
    expect(live.tokens[0]).toMatchObject({ layer: "line", part: "التشغيل الآلي", tone: "run" });
    expect(live.layers.line.tone).toBe("run");
    expect(live.links).toEqual([null, "down", "both", null]);
    expect(live.loop).toBe(true);
  });

  it("من يُنتظر يحدّد الطبقة: النموذج والمصمّم الخارجي في الرابعة، والمشروع المستلم واعتماد طلبه في السادسة", () => {
    const where = (who: string, current: string | null, over = {}) => layerLive(snap({ sima: [run(over)] }), { awraq: tl(who, 10, current) }, null, net).tokens[0];
    expect(where("model", "critique")).toMatchObject({ layer: "models", part: "الرسّام", who: "m" });
    expect(where("designer", "diverge")).toMatchObject({ layer: "models", part: "المصمّم الخارجي", who: "d" });
    expect(where("project", "landed", { deliver: { card: "c1", branch: "card/c1" } })).toMatchObject({ layer: "store", part: "المشروع المستلم", who: "d" });
    expect(where("owner", "landed", { deliver: { card: "c1", branch: "card/c1" } })).toMatchObject({ layer: "store", part: "المشروع المستلم", who: "o" });
  });

  it("إصدار مكتمل يستقر في الحفظ والتسليم بلا نبض، والعنوان يقول إن الحال هادئ", () => {
    const live = layerLive(snap({ sima: [run({ closed: true, deliver: { card: "c1", branch: "card/c1" }, cost: { usd: 3.5, calls: 7, ref: 10, level: "ok" } })] }),
      { awraq: tl("script", 12, null, [{ at: "2026-11-14T04:04:20+00:00", who: "project", text: "نُشرت الهوية" }, { at: "2026-11-13T10:00:00+00:00", who: "project", text: "أقدم" }]) },
      { online: true, runs: 1, gate_decisions: 3, identities: [{}] } as unknown as Registry, net);
    expect(live.tokens[0]).toMatchObject({ layer: "store", part: "التسليم", tone: "ok" });
    expect(live.layers.store).toMatchObject({ tone: "ok", note: "كل ما سُلّم مدموج" });
    expect(live.layers.store.last?.text).toBe("أوراق: نُشرت الهوية");
    expect(live.layers.store.facts).toContainEqual({ k: "هويات في القاعدة", v: "1" });
    expect(live.layers.models.facts).toEqual([{ k: "استدعاءات النموذج", v: "7" }, { k: "الكلفة بالدولار", v: "3.50" }]);
    expect(live.links.every((x) => x === null)).toBe(true);
    expect(live.headline).toContain("هادئ");
  });

  it("انقطاع المنصة وفشل فحص وآخر تشغيل متوقف تظهر على طبقاتها", () => {
    const job = { project: "awraq", state: "failed", code: 1, code_ar: "خطأ في الخط", started: "2026-11-14T00:00:00+00:00", ended: "2026-11-14T00:01:00+00:00", message: "" } as BoardState["jobs"][number];
    const live = layerLive(snap({ jobs: [job], sima: [run({ audit: { passed: 8, failed: 2 } })] }), {}, null, { online: false, polling: true });
    expect(live.layers.platform.tone).toBe("off");
    expect(live.layers.line).toMatchObject({ tone: "off", note: "آخر تشغيل فشل: خطأ في الخط" });
    expect(live.layers.checks).toMatchObject({ tone: "off", note: "فحص مردود في أوراق: 2 من 10" });
    expect(live.headline).toContain("منقطعة");
    expect(live.tokens).toEqual([]);
  });

  it("الرسم يعرض الحال: شريط «الآن» بزر لكل مشروع، واسمه على مكوّنه، والوصلة النشطة معلَّمة", async () => {
    setActivePinia(createPinia());
    const board = useBoard();
    board.registry = { online: false, runs: 0, gate_decisions: 0, identities: [] };
    board.state = snap({ inbox: [{ kind: "name_check", project: "awraq", title: "تحقق الاسم" } as unknown as BoardState["inbox"][number]] });
    board.timelines = { awraq: tl("owner", 6, "name_check") };
    const w = mount(LayerMap);
    expect(w.get(".lm-now [role=status]").text()).toContain("قرار واحد ينتظرك");
    expect(w.findAll(".lm-token")).toHaveLength(1);
    expect(w.get(".lm-layer.owner").classes()).toContain("wait");
    const on = w.findAll(".lm-part.on");
    expect(on).toHaveLength(1);
    expect(on[0].text()).toContain("تحقق الاسم");
    expect(on[0].get(".lm-here").text()).toContain("أوراق");
    expect(w.findAll(".lm-link")[0].get(".up").classes()).toContain("on");
    expect(w.findAll(".lm-link .on")).toHaveLength(1);
    await w.get(".lm-token").trigger("click");
    expect(w.get(".lm-layer.owner").classes()).toContain("flash");
    w.unmount();
  });
});

describe("مراحل إصلاح المراجعة", () => {
  it("تعرض المراحل السبع متصلة بإيداع لكل منها والمرحلة 7 صراحةً", () => {
    expect(REPAIR.map((r) => r.n)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    for (const r of REPAIR) expect(r.commit.length, String(r.n)).toBeGreaterThan(6);
    const w = mount(RepairMap);
    expect(w.findAll(".fm-phase")).toHaveLength(7);
    expect(w.findAll(".fm-n").map((x) => x.text())).toEqual(["1", "2", "3", "4", "5", "6", "7"]);
    expect(w.text()).toContain("التقييم والضمانات");
  });
});

describe("خريطة الخطوات", () => {
  const steps = FLOW.flatMap((p) => p.steps);

  it("تذكر ما يعمل اليوم في المسارين: الرسم في الخط ومن خارجه", () => {
    const names = steps.map((x) => x.n);
    for (const n of ["الطابع البصري", "مصغّرات الأفكار", "الحَكَم المستقل", "صفحة السكتشات", "الاعتماد الخارجي", "التسليم الآلي"]) expect(names).toContain(n);
    expect(steps.filter((x) => x.who === "d").length).toBeGreaterThan(0);
  });

  it("تذكر قياس الرسّام وسقوفه والضمانات المختبرة", () => {
    expect(steps.map((x) => x.n)).toEqual(expect.arrayContaining(["تشغيل التقييم", "السقوف وسبب التوقف"]));
    expect(steps.find((x) => x.n === "السقوف وسبب التوقف")?.d).toContain("8 دولارات");
    expect(layers.flatMap((l) => l.parts.map((p) => p.n))).toContain("تقييم الرسّام");
    expect(GUARDS.map((g) => g.n)).toContain("ضمانات مختبرة");
  });

  it("لا تقول إن الرفض الثالث يبدّل الوسيط: الوسيط لا يتغيّر إلا باختيار المالك", () => {
    const all = [...steps.map((x) => x.d), ...LOOPS.map((l) => l.d)].join(" ");
    expect(all).not.toContain("الرفض الثالث");
    expect(all).toContain("الوسيط لا يتغيّر إلا باختيارك");
  });

  it("ترقّم الخطوات متصلة وتعدّ القائم منها، ولكل منفّذ حبّته في المفتاح", () => {
    const w = mount(FlowMap);
    expect(w.findAll(".fm-n").map((x) => Number(x.text()))).toEqual(steps.map((_, i) => i + 1));
    const built = steps.filter((x) => x.st === "built").length;
    expect(w.get(".cardhead .sub").text()).toContain(`${built} من ${steps.length}`);
    expect(w.findAll(".fm-legend .fm-who").map((x) => x.text())).toEqual(Object.values(WHO));
    expect(w.findAll(".fm-loop")).toHaveLength(LOOPS.length);
  });
});

describe("AutomationPage", () => {
  const run = (over: Record<string, unknown>) => ({ project: "awraq", name_ar: "أوراق", version: "v6", key: "k-s1", closed: true, mark: "", preview: "",
    concept: {}, name_check: { status: "clear", status_ar: "متاح", at: "", note: "" }, deliver: { card: "", branch: "" }, ...over });
  const state = (over: Partial<BoardState>): BoardState =>
    ({ now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: "" }, sima: [], cards: [], inbox: [], jobs: [], ...over }) as BoardState;

  function page(s: BoardState, timelines: Record<string, Timeline> = {}) {
    setActivePinia(createPinia());
    const board = useBoard();
    board.state = s;
    board.timelines = timelines;
    return mount(AutomationPage, { global: { stubs: { LayerMap: true, FlowMap: true, CardNow: true } } });
  }

  it("بلا مستودع مربوط لا تعرض أقسام دفتر فارغة، وتقول إن لا تسليم بعد", () => {
    const w = page(state({}));
    expect(w.text()).toContain("لم يُسلَّم إصدار بعد.");
    expect(w.text()).not.toContain("تاريخ البطاقات");
    expect(w.text()).not.toContain("لا مستودع");
  });

  it("تعرض لكل إصدار مسلَّم بطاقته وفرعه وحاله الآن ومن يُنتظر", () => {
    const now = { who: "project", text: "اعتُمد الطلب؛ ينتظر طابور الدمج", since: "" } as Timeline["now"];
    const w = page(state({ sima: [run({ deliver: { card: "20261113-7d1410", branch: "card/20261113-7d1410" } }),
      run({ project: "sima", name_ar: "سِمة", version: "v4", deliver: { card: "", branch: "", in_place: "6f90530" } }),
      run({ project: "draft", name_ar: "مسودة" })] as BoardState["sima"] }), { awraq: { now } as Timeline });
    const rows = w.findAll("tbody tr");
    expect(rows).toHaveLength(2); // ما لم يُسلَّم لا يظهر
    expect(rows[0].text()).toContain("20261113-7d1410");
    expect(rows[0].text()).toContain("ينتظر طابور الدمج");
    expect(rows[0].get(".fm-who").text()).toBe("المشروع");
    expect(rows[1].text()).toContain("في المكان");
    expect(rows[1].text()).toContain("6f90530");
  });

  it("مع مستودع مربوط تعرض دفتره أيضًا", () => {
    const w = page(state({ repo: "D:/x" }));
    expect(w.text()).toContain("تاريخ البطاقات");
  });
});

describe("تحميل صفحة كسولة بعد إعادة البناء", () => {
  it("يميّز فشل تحميل ملف الصفحة من غيره", () => {
    expect(staleChunk(new TypeError("Failed to fetch dynamically imported module: http://127.0.0.1:8766/static/assets/AutomationPage-x.js"))).toBe(true);
    expect(staleChunk(new TypeError("Importing a module script failed."))).toBe(true);
    expect(staleChunk(new Error("HTTP 500"))).toBe(false);
    expect(staleChunk(null)).toBe(false);
  });
});
