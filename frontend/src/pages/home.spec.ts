import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import HomePage from "@/pages/HomePage.vue";
import { useBoard } from "@/stores/board";
import type { BoardState, Timeline } from "@/types";

// بلاطتا التسليم في «اليوم» تُعدّان من إصدارات سِمة وسجل كل مشروع: المنصة تعمل بلا مستودع مربوط، فعدّ بطاقات الدفتر كان صفرًا دائمًا.
const run = (over: Record<string, unknown>) => ({ project: "awraq", name_ar: "أوراق", version: "v6", key: "k-s1", closed: true, mark: "", preview: "", steps: [],
  concept: {}, name_check: { status: "clear", status_ar: "متاح", at: "", note: "" }, deliver: { card: "", branch: "" }, ...over });
const tl = (who: string, landed: boolean) => ({ now: { who, text: "", since: "" }, events: [],
  progress: { done: 0, total: 0, current: null, steps: [{ key: "landed", label: "الدمج في المشروع", status: landed ? "done" : "pending" }] } }) as unknown as Timeline;

function tiles(sima: unknown[], timelines: Record<string, Timeline> = {}) {
  setActivePinia(createPinia());
  const board = useBoard();
  board.state = { now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: "" }, sima, cards: [], inbox: [], jobs: [] } as unknown as BoardState;
  board.timelines = timelines;
  const w = mount(HomePage, { global: { stubs: { ProgressStrip: true, WorkshopPanel: true, JobLine: true, CardNow: true, AppIcon: true, RouterLink: true } } });
  return Object.fromEntries(w.findAll(".tile").map((t) => [t.get(".k").text(), { v: t.get(".v").text(), s: t.get(".s").text() }]));
}

describe("بلاطات «اليوم»", () => {
  it("بلا مستودع مربوط لا تعدّ بطاقات دفتر: تعدّ ما سُلّم وما ينتظر الدمج", () => {
    const t = tiles([run({ deliver: { card: "20261113-7d1410", branch: "card/20261113-7d1410" } }),
      run({ project: "sima", version: "v4", deliver: { card: "", branch: "", in_place: "6f90530" } }),
      run({ project: "draft" })], { awraq: tl("project", false), sima: tl("script", true) });
    expect(Object.keys(t)).not.toContain("بطاقات مفتوحة");
    expect(t["إصدارات مسلَّمة"]).toEqual({ v: "2", s: "1 منها مدموجة" });
    expect(t["تنتظر الدمج"]).toEqual({ v: "1", s: "عند مشغّل المشروع" });
  });

  it("طلب ينتظر اعتماد المالك يُذكر له", () => {
    const t = tiles([run({ deliver: { card: "c1", branch: "card/c1" } })], { awraq: tl("owner", false) });
    expect(t["تنتظر الدمج"]).toEqual({ v: "1", s: "1 منها تنتظر اعتمادك على الطلب" });
  });

  it("بعد الدمج لا شيء معلّق، والمسلَّم في مكانه مدموج بنقطته ولو غاب سجله", () => {
    const t = tiles([run({ deliver: { card: "c1", branch: "card/c1" } }), run({ project: "sima", deliver: { card: "", branch: "", in_place: "6f90530" } })],
      { awraq: tl("project", true) });
    expect(t["إصدارات مسلَّمة"]).toEqual({ v: "2", s: "2 منها مدموجة" });
    expect(t["تنتظر الدمج"]).toEqual({ v: "0", s: "لا شيء معلّق" });
  });

  it("المسلَّم يدويًّا مدموج بنقطته ولو غاب سجله، ولا يُعدّ منتظرًا", () => {
    const t = tiles([run({ project: "marsad", deliver: { card: "", branch: "", manual: "03bafcda", repo: "MonitorWidget" } })], {});
    expect(t["إصدارات مسلَّمة"]).toEqual({ v: "1", s: "1 منها مدموجة" });
    expect(t["تنتظر الدمج"]).toEqual({ v: "0", s: "لا شيء معلّق" });
  });
});
