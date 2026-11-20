import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import IdentityGate from "@/components/IdentityGate.vue";
import JobLine from "@/components/JobLine.vue";
import StalledGate from "@/components/StalledGate.vue";
import { useBoard } from "@/stores/board";
import type { BoardState, IdentityItem, Job, StalledItem, Timeline } from "@/types";
import { layerLive } from "@/utils/layerLive";

// التوقف حالة بسببها تُستأنف بزر، لا «اكتمل» أخضر؛ وما وقف عنده الخط بلا قرار في بطاقة يُعرض بنصّه (مراجعة الأتمتة 2026-11-14).
const now = (over: Partial<Timeline["now"]>): Timeline["now"] => ({ who: "model", text: "توقّف التشغيل الآلي", since: "", ...over });
const tl = (over: Partial<Timeline["now"]>) => ({ project: "sima", version: "v2", key: "k-s1", closed: false, now: now(over), events: [],
  progress: { done: 3, total: 12, current: "diverge", steps: [] } }) as Timeline;
const job = (over: Partial<Job>): Job => ({ project: "sima", state: "stopped", code: 6, code_ar: "توقّف التشغيل الآلي", started: "2026-11-14T00:00:00+00:00",
  ended: "2026-11-14T00:10:00+00:00", message: "بلغ التشغيل الآلي سقف 16 استدعاءات", ...over });

function board(jobs: Job[], timeline?: Timeline) {
  setActivePinia(createPinia());
  const b = useBoard();
  b.state = { now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: "" }, sima: [], cards: [], inbox: [], jobs } as unknown as BoardState;
  b.timelines = timeline ? { sima: timeline } : {};
  return b;
}

describe("JobLine", () => {
  it("التوقف تحذير بسببه ومعه زر الاستئناف مربوطًا بالإصدار والمفتاح المعروضين", async () => {
    const b = board([job({})], tl({ state: "stopped", resume: true }));
    const send = vi.spyOn(b, "send").mockResolvedValue({ ok: true, message: "يُستأنف الخط على sima v2." });
    const w = mount(JobLine, { props: { project: "sima" } });
    expect(w.get(".rl-status").classes()).toContain("warn");
    expect(w.get(".rl-status").classes()).not.toContain("good");
    expect(w.text()).toContain("توقّف التشغيل الآلي: بلغ التشغيل الآلي سقف 16 استدعاءات");
    expect(w.text()).toContain("يستدعي النموذج آليًا ضمن سقف الأمر");
    await w.get(".rl-resume button").trigger("click");
    expect(send).toHaveBeenCalledWith("resume", { project: "sima", version: 2, key: "k-s1" });
    await vi.waitFor(() => expect(w.get(".rl-resume .ib-m").text()).toContain("يُستأنف الخط على sima v2."));
  });

  it("بلوغ بوابة يبقى أخضر بلا زر استئناف، والجاري بلا زر", () => {
    board([job({ state: "done", code: 4, code_ar: "بانتظار قرارك" })], tl({ who: "owner", resume: false }));
    const w = mount(JobLine, { props: { project: "sima" } });
    expect(w.get(".rl-status").classes()).toContain("good");
    expect(w.find(".rl-resume").exists()).toBe(false);
    board([job({ state: "running", code: null, code_ar: "" })], tl({ who: "script", resume: false }));
    expect(mount(JobLine, { props: { project: "sima" } }).find(".rl-resume").exists()).toBe(false);
  });
});

describe("StalledGate", () => {
  const item: StalledItem = { kind: "stalled", project: "sima", version: 2, key: "k-s1", title: "الخط واقف عندك", after: "أصلِح ما يذكره ثم استأنف.",
    preview: "", digest: "", message: "قرار المالك على الاتجاه (revise): غيّر الذهبي — يُصلح في بيان الاعتماد ثم يُعاد التشغيل." };

  it("يعرض ما وقف عنده الخط بنصّه ويستأنفه بزر، بلا أي زر قرار", async () => {
    const b = board([], tl({ who: "owner", state: "stopped", resume: true }));
    const send = vi.spyOn(b, "send").mockResolvedValue({ ok: true, message: "يُستأنف الخط على sima v2." });
    const w = mount(StalledGate, { props: { item } });
    expect(w.get(".rl-stalled").text()).toContain("غيّر الذهبي");
    expect(w.get("h2").text()).toContain("الخط واقف عندك: sima");
    expect(w.findAll("button.btn")).toHaveLength(1);
    expect(w.text()).not.toContain("يستدعي النموذج"); // المنتظَر المالك لا النموذج
    await w.get(".rl-resume button").trigger("click");
    expect(send).toHaveBeenCalledWith("resume", { project: "sima", version: 2, key: "k-s1" });
  });
});

describe("جواب الخط في بوابات الهوية", () => {
  it("طلب تعديل للمنصة أجابه النموذج بلا تغيير يُعرض جوابه كاملًا في بطاقتها", () => {
    board([]);
    const item = { kind: "identity", gate: "strategy", gate_ar: "المنصة الاستراتيجية", project: "awraq", version: 7, key: "k-s1", title: "اعتماد المنصة",
      after: "", digest: "s1", history: [], reply: { note: "لماذا هذا الوعد؟", text: "الوعد مأخوذ من الموجز كاملًا." },
      strategy: { positioning: "تموضع", promise: "وعد", tagline: "شعار", personality: [], voice_do: [], voice_dont: [] } } as IdentityItem;
    const w = mount(IdentityGate, { props: { item }, global: { stubs: { JobLine: true } } });
    expect(w.text()).toContain("جواب الخط على ملاحظتك:");
    expect(w.text()).toContain("الوعد مأخوذ من الموجز كاملًا.");
  });
});

describe("طبقة الخط الحيّة", () => {
  it("خط متوقف يظهر متعطّلًا باسم مشروعه لا «هادئًا»، ولو أُعيد تشغيل المنصة فلا تشغيل في ذاكرتها", () => {
    const run = { project: "sima", name_ar: "سِمة", version: "v2", key: "k-s1", closed: false, mark: "", preview: "", steps: [], decisions: [], files: [],
      concept: {}, name_check: { status: "", status_ar: "", at: "", note: "" }, deliver: { card: "", branch: "" } } as unknown as BoardState["sima"][number];
    const state = { now: "2026-11-14T00:00:00+00:00", repo: "", runner: { running: false, pid: "" }, sima: [run], cards: [], inbox: [], jobs: [] } as unknown as BoardState;
    const live = layerLive(state, { sima: tl({ state: "stopped", resume: true }) }, null, { online: true, polling: true });
    expect(live.layers.line).toMatchObject({ tone: "off", note: "متوقف ويُستأنف بزر: سِمة" });
    expect(layerLive(state, { sima: tl({}) }, null, { online: true, polling: true }).layers.line.tone).toBe("idle");
  });
});

describe("ResumeButton: إصدار جديد", () => {
  it("بعد إصدار مغلق تغيّر مدخله يعرض السبب وزرًا يفتح الإصدار التالي، ولا زر استئناف", async () => {
    const closed = { ...tl({ who: "script", text: "اكتمل كل شيء في هذا الإصدار.", renew: "تغيّر محتوى بيان الاعتماد بعد إغلاق v2." }), closed: true };
    const b = board([], closed);
    const send = vi.spyOn(b, "send").mockResolvedValue({ ok: true, message: "يُفتح v3 في الخلفية." });
    const { default: ResumeButton } = await import("@/components/ResumeButton.vue");
    const w = mount(ResumeButton, { props: { project: "sima" } });
    expect(w.text()).toContain("تغيّر محتوى بيان الاعتماد");
    expect(w.findAll("button")).toHaveLength(1);
    await w.get("button").trigger("click");
    expect(send).toHaveBeenCalledWith("new-version", { project: "sima", version: 2, key: "k-s1" });
    await vi.waitFor(() => expect(w.get(".ib-m").text()).toContain("يُفتح v3"));
  });
});
