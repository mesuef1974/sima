import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import AppIcon from "@/components/AppIcon.vue";
import ConceptsGate from "@/components/ConceptsGate.vue";
import DecisionActions from "@/components/DecisionActions.vue";
import IdentityGate from "@/components/IdentityGate.vue";
import RunTrack from "@/components/RunTrack.vue";
import SketchGate from "@/components/SketchGate.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";
import WorkshopPanel from "@/components/WorkshopPanel.vue";
import { ICONS } from "@/data/icons";
import { useBoard } from "@/stores/board";
import type { ConceptsItem, IdentityItem, SketchesItem, Workshop } from "@/types";

const stubs = { JobLine: true };

describe("AppIcon", () => {
  it("يرسم مسارات الأيقونة بسماكتها ويخفيها عن قارئ الشاشة", () => {
    const w = mount(AppIcon, { props: { name: "done" } });
    const svg = w.get("svg");
    expect(svg.attributes("aria-hidden")).toBe("true");
    expect(svg.attributes("stroke-width")).toBe(String(ICONS.done.width));
    expect(svg.find("path").exists()).toBe(true);
  });

  it("كل أيقونة مسجّلة تُرسم", () => {
    for (const name of Object.keys(ICONS) as (keyof typeof ICONS)[]) {
      expect(mount(AppIcon, { props: { name } }).find("svg").element.innerHTML.length, name).toBeGreaterThan(10);
    }
  });
});

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    setActivePinia(createPinia());
  });

  it("ثلاثة أزرار وبالضغط تُطبَّق السمة ويُعلَّم الزر المضغوط", async () => {
    const w = mount(ThemeToggle);
    const btns = w.findAll("button");
    expect(btns).toHaveLength(3);
    expect(btns[1].attributes("aria-pressed")).toBe("true"); // تلقائية
    await btns[2].trigger("click");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(btns[2].attributes("aria-pressed")).toBe("true");
    expect(btns[1].attributes("aria-pressed")).toBe("false");
  });

  it("لكل زر نص مخفي بصريًا لقارئ الشاشة", () => {
    const w = mount(ThemeToggle);
    expect(w.findAll(".visually-hidden").map((x) => x.text())).toEqual(["فاتحة", "تلقائية", "داكنة"]);
  });
});

describe("DecisionActions", () => {
  const decide = (w: ReturnType<typeof mount>) => w.emitted("decide") ?? [];

  it("التعديل والرفض يشترطان سببًا ولا يُرسلان بدونه", async () => {
    const w = mount(DecisionActions, { props: { id: "r1" } });
    await w.findAll("button")[1].trigger("click");
    await w.findAll("button")[2].trigger("click");
    expect(decide(w)).toHaveLength(0);
    expect(w.get(".ib-m").text()).toContain("اكتب السبب");
  });

  it("الاعتماد يحتاج ضغطتين، والأولى تعرض نص التأكيد", async () => {
    const w = mount(DecisionActions, { props: { id: "r1", confirmHint: "تنبيه خاص", confirmLabel: "تأكيد!" } });
    const approve = w.findAll("button")[0];
    await approve.trigger("click");
    expect(decide(w)).toHaveLength(0);
    expect(w.get(".ib-m").text()).toBe("تنبيه خاص");
    expect(approve.text()).toBe("تأكيد!");
    await approve.trigger("click");
    expect(decide(w)).toHaveLength(1);
    expect(decide(w)[0].slice(0, 2)).toEqual(["approved", ""]);
  });

  it("فحص النيّة يمنع الاعتماد برسالته", async () => {
    const w = mount(DecisionActions, { props: { id: "r1", check: () => "السبب يطلب غير ما تعتمد" } });
    await w.findAll("button")[0].trigger("click");
    expect(w.get(".ib-m").text()).toBe("السبب يطلب غير ما تعتمد");
    expect(decide(w)).toHaveLength(0);
  });
});

describe("RunTrack", () => {
  it("عقدة منجزة بعلامة وفاشلة بصليب وغيرها برقمها", () => {
    const nodes = [
      { key: "a", label: "أ", status: "done" as const, at: "" },
      { key: "b", label: "ب", status: "fail" as const, at: "" },
      { key: "c", label: "ج", status: "pending" as const, at: "" },
    ];
    const w = mount(RunTrack, { props: { nodes, p: 1, chip: "", chipText: "v1", finalKey: "c" } });
    const cells = w.findAll(".rl-node .c");
    expect(cells[0].find("svg").exists()).toBe(true);
    expect(cells[1].find("svg").exists()).toBe(true);
    expect(cells[2].text()).toBe("3");
    expect(w.get(".rl-chip").text()).toContain("v1");
  });
});

describe("ConceptsGate", () => {
  beforeEach(() => setActivePinia(createPinia()));
  const item = (over: Partial<ConceptsItem> = {}): ConceptsItem => ({
    kind: "concepts", project: "sima", name_ar: "سِمة", version: 1, key: "k", preview: "", digest: "d", after: "ثم تُبنى الحزمة",
    below_bar: true, bar: 30, medium: "abstract_mark", mediums: [{ id: "abstract_mark", ar: "علامة مجردة" }],
    concepts: [
      { id: "c1", name: "أ", medium_ar: "علامة", sentence: "ج", img: "", last: "", score: 23, passed: false },
      { id: "c2", name: "ب", medium_ar: "علامة", sentence: "ج", img: "", last: "", score: 33, passed: true },
    ],
    ...over,
  } as unknown as ConceptsItem);

  it("المفهوم دون العتبة يحمل تنبيه اعتماد صريحًا بدرجته، والمجتاز لا", async () => {
    const w = mount(ConceptsGate, { props: { item: item() }, global: { stubs } });
    const gates = w.findAllComponents(DecisionActions);
    expect(gates[0].props("confirmHint")).toContain("23/40");
    expect(gates[0].props("confirmHint")).toContain("30");
    expect(gates[0].props("confirmLabel")).toContain("دون العتبة");
    expect(gates[1].props("confirmHint")).toContain("يبني الحزمة");
    expect(gates[1].props("confirmLabel")).not.toContain("دون العتبة");
  });

  it("لافتة «لم يبلغ العتبة» تظهر فقط حين يكون below_bar", () => {
    expect(mount(ConceptsGate, { props: { item: item() }, global: { stubs } }).text()).toContain("لم يبلغ ثلاثة مفاهيم");
    expect(mount(ConceptsGate, { props: { item: item({ below_bar: false }) }, global: { stubs } }).text()).not.toContain("لم يبلغ ثلاثة مفاهيم");
  });
});

describe("WorkshopPanel", () => {
  const item = (over: Partial<Workshop> = {}): Workshop => ({
    project: "sima", version: 2, stage: "جولة النقد 1",
    thumbs: [
      { id: "i1", sentence: "قوس وحلقة", img: "sima/v2/work/thumbs/i1.svg", stamp: 7, state: "allowed", state_ar: "مجتازة", seen: "رأى قوسًا" },
      { id: "i2", sentence: "حلقة ونقطة", img: "sima/v2/work/thumbs/i2.svg", stamp: 8, state: "blocked", state_ar: "مردودة", seen: "مؤشر إشعار" },
    ],
    concepts: [{ id: "c1", name: "كأس وعين", sentence: "نصف حلقة", idea: "i1", img: "sima/v2/work/concepts/c1.svg", stamp: 9, seen: "", misread: false }],
    ...over,
  });

  it("يعرض المفاهيم والمصغّرات للاطلاع فقط بلا أي زر قرار", () => {
    const w = mount(WorkshopPanel, { props: { item: item() } });
    expect(w.text()).toContain("ما يُرسم الآن: sima");
    expect(w.text()).toContain("للاطلاع فقط");
    expect(w.text()).toContain("1 مجتازة من 2");
    expect(w.findAll("button")).toHaveLength(0);
    expect(w.findAll("textarea")).toHaveLength(0);
    expect(w.get(".ib-c img").attributes("src")).toBe("/out/sima/v2/work/concepts/c1.svg?v=9");
    expect(w.get(".ws-t.off .rl-st").classes()).toContain("bad");
    expect(w.get("details").attributes("open")).toBeUndefined(); // المفاهيم رُسمت: المصغّرات مطويّة
  });

  it("يعرض لوحات الاستكشاف بمصدرها وقراءتها الخاطئة بلا زر قرار", () => {
    const explore = [{ id: "d1", name: "التوقيع في الكسرة", detail: "الاسم وحده", misread: "ختم إداري", img: "sima/v2/work/explore/d1.jpg", stamp: 5, source: "صور نقطية خارجية" }];
    const w = mount(WorkshopPanel, { props: { item: item({ explore }) } });
    expect(w.get(".ws-b img").attributes("src")).toBe("/out/sima/v2/work/explore/d1.jpg?v=5");
    expect(w.text()).toContain("ليست مخرجًا معتمدًا");
    expect(w.text()).toContain("صور نقطية خارجية");
    expect(w.text()).toContain("أقرب قراءة خاطئة: ختم إداري");
    expect(w.findAll("button")).toHaveLength(0);
    expect(mount(WorkshopPanel, { props: { item: item() } }).find(".ws-boards").exists()).toBe(false);
  });

  it("حالة تقييم الرسّام تُعنون بغير عنوان المشاريع وتعرض درجة الحَكَم بلا زر", () => {
    const concepts = [
      { id: "c1", name: "وتد", sentence: "خط يثبت", idea: "i1", img: "_eval/r1/eval_watad/v1/work/concepts/c1.svg", stamp: 9, seen: "", misread: false, score: 31, passed: true },
      { id: "c2", name: "حبل", sentence: "عقدة", idea: "i2", img: "_eval/r1/eval_watad/v1/work/concepts/c2.svg", stamp: 9, seen: "", misread: false, score: 24, passed: false },
    ];
    const w = mount(WorkshopPanel, { props: { item: item({ project: "eval_watad", version: 1, concepts, eval: { run: "r1", name: "وَتَد" } }) } });
    expect(w.text()).toContain("تقييم الرسّام: وَتَد");
    expect(w.text()).not.toContain("ما يُرسم الآن");
    expect(w.text()).toContain("ليست مشروعًا");
    expect(w.text()).not.toContain("قرارك يُطلب");
    expect(w.get(".rl-tag.m").text()).toBe("r1");
    expect(w.get(".ib-c img").attributes("src")).toBe("/out/_eval/r1/eval_watad/v1/work/concepts/c1.svg?v=9");
    expect(w.text()).toContain("31 من 40 · مجتاز");
    expect(w.text()).toContain("24 من 40 · دون العتبة");
    expect(w.findAll("button")).toHaveLength(0);
    expect(mount(WorkshopPanel, { props: { item: item() } }).text()).not.toContain("من 40"); // مشروع حقيقي: لا درجة في الورشة
  });

  it("قبل رسم المفاهيم تُفتح المصغّرات", () => {
    const w = mount(WorkshopPanel, { props: { item: item({ concepts: [] }) } });
    expect(w.get("details").attributes("open")).toBeDefined();
    expect(w.find(".ib-grid").exists()).toBe(false);
  });
});

describe("SketchGate", () => {
  const item: SketchesItem = {
    kind: "sketches", project: "watad", version: 1, key: "k-s1", title: "اختيار السكتش", after: "يُبنى متجهًا ثم تعود بالدليل", digest: "d1",
    img: "watad/v1/designer/sketches.jpg", source: "صفحة من المصمّم الخارجي",
    sketches: [{ id: 1, idea: "وتد مائل", pick: false }, { id: 2, idea: "ظل الوتد", pick: true }, { id: 3, idea: "حبل مشدود", pick: false }],
  };

  beforeEach(() => setActivePinia(createPinia()));

  it("يعرض الصفحة وأفكارها ولا يرسل قبل اختيار، ثم يرسل الرقم المختار وحده ببصمة المعروض", async () => {
    const send = vi.spyOn(useBoard(), "send").mockResolvedValue({ ok: true, message: "اختير السكتش 3" });
    const w = mount(SketchGate, { props: { item }, global: { stubs } });
    expect(w.get(".ws-b img").attributes("src")).toBe(`/out/watad/v1/designer/sketches.jpg?d=${item.digest}`);
    expect(w.findAll(".st-c")).toHaveLength(3);
    expect(w.findAll(".st-c")[1]!.text()).toContain("رشّحه المصمّم");
    const submit = w.get("button.btn");
    expect(submit.attributes("disabled")).toBeDefined();
    await w.findAll(".st-c")[0]!.trigger("click");
    await w.findAll(".st-c")[2]!.trigger("click"); // اختيار واحد: الثاني يستبدل الأول
    expect(w.findAll('.st-c[aria-pressed="true"]')).toHaveLength(1);
    expect(w.text()).toContain("اخترت السكتش 3");
    await w.get("textarea").setValue("احفظ الميل");
    await submit.trigger("click");
    expect(send).toHaveBeenCalledWith("sketch", { project: "watad", version: 1, key: "k-s1", digest: "d1", sketch: 3, note: "احفظ الميل" });
  });

  it("«طوّره أولًا» يرسل السكتش المختار وملاحظته لصفحة معالجات حوله، لا لبنائه", async () => {
    const send = vi.spyOn(useBoard(), "send").mockResolvedValue({ ok: true, message: "طُلب تطوير السكتش 3" });
    const w = mount(SketchGate, { props: { item }, global: { stubs } });
    expect(w.get(".sk-develop").attributes("disabled")).toBeDefined(); // بلا اختيار لا يُرسل شيء
    await w.findAll(".st-c")[2].trigger("click");
    await w.get(".st-form textarea").setValue("أريد تعديلات احترافية");
    await w.get(".sk-develop").trigger("click");
    expect(send).toHaveBeenCalledWith("sketch-develop", { project: "watad", version: 1, key: "k-s1", digest: "d1", sketch: 3, note: "أريد تعديلات احترافية" });
  });

  it("يرفض الصفحة كلها بسبب إلزامي ويرسله بنصّه ببصمة المعروض، بلا اختيار سكتش", async () => {
    const send = vi.spyOn(useBoard(), "send").mockResolvedValue({ ok: true, message: "رُفضت صفحة السكتشات" });
    const w = mount(SketchGate, { props: { item }, global: { stubs } });
    const reject = w.get(".sk-reject button");
    await reject.trigger("click");
    expect(send).not.toHaveBeenCalled(); // بلا سبب لا يُرسل شيء
    expect(w.get(".sk-reject .rl-status").text()).toContain("اكتب سبب الرفض");
    await w.get(".sk-reject textarea").setValue("  كلها حرفية، أريد رمزًا واحدًا  ");
    await reject.trigger("click");
    expect(send).toHaveBeenCalledWith("sketch-reject", { project: "watad", version: 1, key: "k-s1", digest: "d1", reason: "كلها حرفية، أريد رمزًا واحدًا" });
    await vi.waitFor(() => expect(w.get(".sk-reject .rl-status").text()).toContain("رُفضت صفحة السكتشات"));
  });
});

describe("IdentityGate", () => {
  const book = (over: Partial<IdentityItem> = {}): IdentityItem => ({
    kind: "identity", project: "awraq", version: 4, key: "k-s1", title: "اعتماد دليل الهوية", after: "الاعتماد يغلق الإصدار", gate: "book",
    gate_ar: "دليل الهوية", digest: "b1", history: [], book: "awraq/v4/package/identity/brand-book.html", ...over,
  });

  beforeEach(() => setActivePinia(createPinia()));

  it("ردّ الشعار يظهر في دليل مسار المصمّم الخارجي وحده", () => {
    expect(mount(IdentityGate, { props: { item: book() }, global: { stubs } }).find(".ib-vector").exists()).toBe(false);
    expect(mount(IdentityGate, { props: { item: book({ designer_sketch: 11, gate: "directions", options: [] }) }, global: { stubs } }).find(".ib-vector").exists()).toBe(false);
    expect(mount(IdentityGate, { props: { item: book({ designer_sketch: 11 }) }, global: { stubs } }).get(".ib-vector").text()).toContain("السكتش 11");
  });

  it("يردّ الشعار بسبب إلزامي ويرسله بنصّه ببصمة الدليل المعروض، لا طلبَ تعديل", async () => {
    const send = vi.spyOn(useBoard(), "send").mockResolvedValue({ ok: true, message: "رُدّ متجه السكتش 11" });
    const w = mount(IdentityGate, { props: { item: book({ designer_sketch: 11 }) }, global: { stubs } });
    const back = w.get(".ib-vector button");
    await back.trigger("click");
    expect(send).not.toHaveBeenCalled(); // بلا سبب لا يُرسل شيء
    expect(w.get(".ib-vector .rl-status").text()).toContain("اكتب سبب ردّ الشعار");
    await w.get(".ib-vector textarea").setValue("  ليس هذا الشعار الذي اتفقنا عليه  ");
    await back.trigger("click");
    expect(send).toHaveBeenCalledWith("vector-return", { project: "awraq", version: 4, key: "k-s1", digest: "b1", reason: "ليس هذا الشعار الذي اتفقنا عليه" });
    await vi.waitFor(() => expect(w.get(".ib-vector .rl-status").text()).toContain("رُدّ متجه السكتش 11"));
  });
});
