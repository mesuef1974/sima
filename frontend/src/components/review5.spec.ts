import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import ConceptsGate from "@/components/ConceptsGate.vue";
import IdentityGate from "@/components/IdentityGate.vue";
import NameCheckGate from "@/components/NameCheckGate.vue";
import ProgressStrip from "@/components/ProgressStrip.vue";
import SketchGate from "@/components/SketchGate.vue";
import StalledGate from "@/components/StalledGate.vue";
import StyleGate from "@/components/StyleGate.vue";
import DecisionsPage from "@/pages/DecisionsPage.vue";
import HomePage from "@/pages/HomePage.vue";
import ProjectsPage from "@/pages/ProjectsPage.vue";
import { REGISTRY_EVERY, useBoard } from "@/stores/board";
import type { BoardState, ConceptsItem, IdentityItem, NameItem, SimaRun, SketchesItem, StalledItem, StyleItem, Timeline } from "@/types";

vi.mock("@/api/client", () => ({ fetchState: vi.fn(), fetchTimeline: vi.fn(), fetchRegistry: vi.fn(), fetchBox: vi.fn(), post: vi.fn() }));
import * as api from "@/api/client";

// المرحلة 5 من مراجعة الأتمتة 2026-11-14: البطاقات والصفحات كما يراها المالك.
const stubs = { JobLine: true, ResumeButton: true, ProgressStrip: true, WorkshopPanel: true, CardNow: true, AppIcon: true, RouterLink: true, RunTrack: false };
const run = (over: Partial<SimaRun> = {}): SimaRun => ({
  project: "awraq", name_ar: "أوراق", version: "v6", key: "k", closed: false, mark: "", preview: "", concept: {},
  name_check: { status: "", status_ar: "", at: "", note: "" }, deliver: { card: "", branch: "" }, files: [], steps: [], decisions: [], ...over,
});
const snap = (over: Partial<BoardState> = {}): BoardState =>
  ({ now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: null }, sima: [], cards: [], inbox: [], jobs: [], ...over });
const tl = (now: Partial<Timeline["now"]>, over: Partial<Timeline> = {}): Timeline => ({
  project: "awraq", version: "v6", key: "k", closed: false, now: { who: "script", text: "", since: "", ...now }, events: [],
  progress: { done: 3, total: 14, current: "diverge", steps: [] }, ...over,
});

function board(over: Partial<BoardState> = {}, timelines: Record<string, Timeline> = {}) {
  setActivePinia(createPinia());
  const b = useBoard();
  b.state = snap(over);
  b.timelines = timelines;
  return b;
}

const concepts = { kind: "concepts", project: "awraq", version: 6, key: "k", title: "", after: "", preview: "", digest: "dg1",
  medium: "abstract_mark", mediums: [{ id: "abstract_mark", ar: "علامة مجردة" }],
  concepts: [{ id: "c1", name: "أ", medium_ar: "علامة", sentence: "ج", img: "awraq/v6/c1.png", last: "" }] } as ConceptsItem;

describe("م5 وم8: ConceptsGate", () => {
  it("صورة المفهوم مختومة بالبصمة، وحقلا السبب بحدّي الخادم، وطلب الرسم الجديد يحمل البصمة", async () => {
    const b = board({ limits: { decide: 321, medium: 654 } });
    const send = vi.spyOn(b, "send").mockResolvedValue({ ok: true, message: "" });
    const w = mount(ConceptsGate, { props: { item: concepts }, global: { stubs } });
    expect(w.get(".ib-img img").attributes("src")).toBe("/out/awraq/v6/c1.png?d=dg1");
    const areas = w.findAll("textarea");
    expect(areas[0].attributes("maxlength")).toBe("321");
    expect(areas.at(-1)!.attributes("maxlength")).toBe("654");
    await areas.at(-1)!.setValue("أريد خطًا أثقل");
    await w.get(".ib-redraw button").trigger("click");
    expect(send).toHaveBeenCalledWith("medium", expect.objectContaining({ digest: "dg1", medium: "abstract_mark", reason: "أريد خطًا أثقل" }));
  });
});

describe("م5 وم8: StyleGate وSketchGate وNameCheckGate وIdentityGate", () => {
  it("صور الطابع مختومة بالبصمة وملاحظته بحدّ note", () => {
    board({ limits: { note: 99 } });
    const item = { kind: "style", project: "awraq", version: 6, key: "k", title: "", after: "", digest: "st9", max: 2,
      styles: [{ id: "s1", name: "هندسي", principle: "", img: "awraq/v6/s1.png" }] } as StyleItem;
    const w = mount(StyleGate, { props: { item }, global: { stubs } });
    expect(w.get(".st-img img").attributes("src")).toBe("/out/awraq/v6/s1.png?d=st9");
    expect(w.get("textarea").attributes("maxlength")).toBe("99");
  });

  it("ملاحظة السكتش بحدّ note وسبب رفض الصفحة بحدّ reason", () => {
    board({ limits: { note: 77, reason: 88 } });
    const item = { kind: "sketches", project: "awraq", version: 6, key: "k", title: "", after: "", digest: "sk", img: "a.jpg", source: "",
      sketches: [] } as SketchesItem;
    const areas = mount(SketchGate, { props: { item }, global: { stubs } }).findAll("textarea");
    expect(areas.map((a) => a.attributes("maxlength"))).toEqual(["77", "88"]);
  });

  it("بلا حدود في اللقطة (خادم أقدم) تُستعمل أرقام العقد", () => {
    board();
    const name = { kind: "name_check", project: "awraq", version: 6, key: "k", title: "", after: "", preview: "", concept: "c1", name: "أوراق", note: "", sources: [] } as NameItem;
    expect(mount(NameCheckGate, { props: { item: name }, global: { stubs } }).get("textarea").attributes("maxlength")).toBe("600");
    board({ limits: { note: 40 } });
    expect(mount(NameCheckGate, { props: { item: name }, global: { stubs } }).get("textarea").attributes("maxlength")).toBe("40");
  });

  it("سبب بوابة الهوية بحدّ identity وسبب ردّ الشعار بحدّ reason", () => {
    board({ limits: { identity: 1111, reason: 222 } });
    const item = { kind: "identity", gate: "book", gate_ar: "دليل الهوية", project: "awraq", version: 6, key: "k", title: "", after: "", digest: "b1",
      history: [], book: "awraq/v6/book.html", designer_sketch: 11 } as IdentityItem;
    const areas = mount(IdentityGate, { props: { item }, global: { stubs } }).findAll("textarea");
    expect(areas.map((a) => a.attributes("maxlength"))).toEqual(["1111", "222"]);
  });
});

describe("بطاقة توقف تصحيح المصمّم", () => {
  const item = { kind: "stalled", project: "awraq", version: 6, key: "k", title: "الخط واقف عندك", after: "", preview: "", digest: "fx1",
    message: "نفدت جولات التصحيح الثلاث", gate: "designer_fix" } as StalledItem;

  it("تردّ المتجه إلى المصمّم بسبب إلزامي ببصمة البطاقة", async () => {
    const b = board({ limits: { reason: 300 } });
    const send = vi.spyOn(b, "send").mockResolvedValue({ ok: true, message: "أُعيد المتجه إلى المصمّم" });
    const w = mount(StalledGate, { props: { item }, global: { stubs } });
    const btn = w.findAll("button").find((x) => x.text() === "ردّ المتجه إلى المصمّم")!;
    expect(w.get("textarea").attributes("maxlength")).toBe("300");
    await btn.trigger("click");
    expect(send).not.toHaveBeenCalled();
    expect(w.text()).toContain("اكتب سبب ردّ المتجه أولًا");
    await w.get("textarea").setValue("الميل غير مطابق للسكتش");
    await btn.trigger("click");
    expect(send).toHaveBeenCalledWith("vector-return", { project: "awraq", version: 6, key: "k", digest: "fx1", reason: "الميل غير مطابق للسكتش" });
    await flushPromises();
    expect(w.text()).toContain("أُعيد المتجه إلى المصمّم");
  });

  it("لا تظهر في توقف آخر", () => {
    board();
    const w = mount(StalledGate, { props: { item: { ...item, gate: "" } }, global: { stubs } });
    expect(w.find("textarea").exists()).toBe(false);
  });
});

describe("م6: صفحة «اليوم»", () => {
  it("الحزم الجاهزة للتسليم لا تعدّ ما سُلّم، وطلب ينتظر اعتمادك يظهر في «ينتظر قرارك أيضًا» وفي الشارة", () => {
    const pkg = [{ key: "package", label: "الحزمة", status: "done" as const }];
    const b = board({ sima: [run({ closed: true, steps: pkg, deliver: { card: "c1", branch: "card/c1" } }), run({ project: "watad", name_ar: "وتد", closed: true, steps: pkg })] },
      { awraq: tl({ who: "owner", text: "الطلب ينتظر اعتمادك.", pr_url: "https://github.com/o/r/pull/7" }) });
    const w = mount(HomePage, { global: { stubs } });
    const tile = w.findAll(".tile").find((t) => t.get(".k").text() === "حزم معتمدة")!;
    expect(tile.get(".v").text()).toBe("1");
    expect(w.get(".todo").text()).toContain("استلام المشروع: أوراق");
    expect(b.badge).toBeGreaterThanOrEqual(1);
  });

  it("تسليم لم يصل سجل مشروعه لا يُعدّ «ينتظر الدمج»", () => {
    board({ sima: [run({ deliver: { card: "c1", branch: "card/c1" } })] });
    const w = mount(HomePage, { global: { stubs } });
    const tile = w.findAll(".tile").find((t) => t.get(".k").text() === "تنتظر الدمج")!;
    expect(tile.get(".v").text()).toBe("0");
    expect(tile.get(".s").text()).toContain("غير معروف");
  });
});

describe("م6 هـ: لافتة التقدم", () => {
  it("إصدار مكتمل لا يُكتب عليه «ينتظر: الخط»، والسجل القديم معلَّم", () => {
    board({}, { awraq: tl({ who: "script", text: "اكتمل كل شيء" }, { closed: true, stale: true, progress: { done: 14, total: 14, current: null, steps: [] } }) });
    const w = mount(ProgressStrip);
    expect(w.text()).not.toContain("ينتظر: الخط");
    expect(w.get(".fm-who").text()).toBe("مكتمل");
    expect(w.text()).toContain("آخر ما وصل");
  });
});

describe("م6 و ز: صفحة القرارات", () => {
  it("لا تذكر القاعدة الملغاة، وتعرض كل قرارات المالك من السجلات", () => {
    const b = board({ sima: [run()] }, { awraq: tl({}, { events: [{ at: "2026-11-14T08:00:00", who: "owner", text: "اعتُمد دليل الهوية" },
      { at: "2026-11-14T07:00:00", who: "owner", text: "بُدّل الوسيط إلى الطباعي" }, { at: "2026-11-14T06:00:00", who: "model", text: "رسم" }] }) });
    b.registry = { online: false, runs: 0, gate_decisions: 0, identities: [] };
    vi.spyOn(b, "loadRegistry").mockResolvedValue();
    const w = mount(DecisionsPage);
    expect(w.text()).not.toContain("الرفض الثالث");
    expect(w.text()).toContain("والوسيط لا يتغيّر إلا باختيارك");
    const rows = w.findAll("tbody tr").map((r) => r.text());
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("اعتُمد دليل الهوية");
    expect(rows[1]).toContain("بُدّل الوسيط إلى الطباعي");
  });
});

describe("م6 د و13: صفحة المشاريع", () => {
  it("ترسم خطوات الخادم كلها بأسمائها ونهايتها آخرها، وتذكر الاستدعاءات المحسوبة بحدّها الأعلى", () => {
    const steps = ["الموجز", "البحث", "المفاهيم", "الفحص", "النقد", "المعاينة", "تحقق الاسم", "الحزمة", "المنصة", "الاتجاه", "بناء الهوية", "الدليل", "التسليم", "الدمج في المشروع"]
      .map((label, i) => ({ key: `s${i}`, label, status: (i < 5 ? "done" : i === 5 ? "current" : "pending") as "done" | "current" | "pending" }));
    board({ sima: [run({ steps, cost: { usd: 6, calls: 9, ref: 10, level: "ok", unknown: 2 } })] });
    const w = mount(ProjectsPage, { global: { stubs: { RunTrack: false, AppIcon: true } } });
    expect(w.findAll(".rl-node")).toHaveLength(14);
    expect(w.findAll(".rl-node .lb b").map((x) => x.text())).toEqual(steps.map((s) => s.label));
    expect(w.findAll(".rl-node.final")).toHaveLength(1);
    expect(w.get(".rl-node.final").text()).toContain("الدمج في المشروع");
    expect(w.text()).toContain("2 منها قُطعت فلم تُبلَّغ كلفتها");
  });
});

describe("م7 وم6 ط: التحديث الدوري", () => {
  beforeEach(() => vi.mocked(api.fetchRegistry).mockReset());

  it("فشل جلب سجل يُبقي السابق بعلامة stale، وسجل القاعدة يتجدّد مع التحديث بعد أن يُطلب", async () => {
    const b = board();
    vi.mocked(api.fetchState).mockResolvedValue(snap({ sima: [run()] }));
    vi.mocked(api.fetchTimeline).mockResolvedValueOnce(tl({ who: "project", text: "مدموج" }));
    vi.mocked(api.fetchRegistry).mockResolvedValue({ online: true, runs: 2, gate_decisions: 1, identities: [] });
    await b.tick();
    expect(b.timelines.awraq.stale).toBe(false);
    vi.mocked(api.fetchTimeline).mockRejectedValueOnce(new Error("HTTP 500"));
    await b.tick();
    expect(b.timelines.awraq).toMatchObject({ stale: true, now: { text: "مدموج" } });
    expect(api.fetchRegistry).not.toHaveBeenCalled(); // لم تطلبه صفحة بعد
    await b.loadRegistry();
    vi.mocked(api.fetchTimeline).mockResolvedValue(tl({}));
    for (let i = 0; i < REGISTRY_EVERY; i++) await b.tick();
    await flushPromises();
    expect(vi.mocked(api.fetchRegistry).mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
