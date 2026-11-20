import type { BoardState, SimaRun } from "@/types";
import { codeParts, out, verdictKind } from "@/utils/format";
import { todos } from "@/utils/todos";

const run = (over: Partial<SimaRun>): SimaRun => ({
  project: "p", name_ar: "أوراق", version: "v1", key: "k", closed: false, mark: "", preview: "", concept: {},
  name_check: { status: "", status_ar: "", at: "", note: "" }, deliver: { card: "", branch: "" }, files: [], steps: [], decisions: [], ...over,
});
const state = (sima: SimaRun[]): BoardState => ({ now: "", repo: null, runner: { running: false, pid: null }, sima, cards: [], inbox: [], jobs: [] });

describe("todos", () => {
  it("يطلب التسليم لحزمة مغلقة لم تُسلَّم", () => {
    const t = todos(state([run({ closed: true, steps: [{ key: "deliver", label: "التسليم", status: "current" }] })]));
    expect(t).toHaveLength(1);
    expect(t[0].code).toContain("sima deliver briefs/p.yaml");
  });
  it("يذكّر بالفحص الرسمي حين يكون التحقق أوليًا", () => {
    const t = todos(state([run({ name_check: { status: "clear", status_ar: "", at: "", note: "تحقق أولي" } })]));
    expect(t.map((x) => x.ic)).toEqual(["name"]);
  });
});

describe("format", () => {
  it("يرمّز كل مقطع من مسار المخرجات", () => {
    expect(out("a b/v1/x#.svg")).toBe("/out/a%20b/v1/x%23.svg");
    expect(out("")).toBe("");
  });
  it("يقسم الرموز المقتبسة بلا HTML", () => {
    expect(codeParts("شغّل `sima db` الآن")).toEqual([{ code: false, text: "شغّل " }, { code: true, text: "sima db" }, { code: false, text: " الآن" }]);
  });
  it("يصنّف القرار", () => {
    expect([verdictKind("approved"), verdictKind("رُفض"), verdictKind("revise")]).toEqual(["good", "bad", "warn"]);
  });
});

describe("intentProblem", () => {
  it("يمنع اعتمادًا ذُكر في ملاحظته خيار غير المختار", async () => {
    const { intentProblem } = await import("@/utils/format");
    expect(intentProblem("d2", ["d1", "d2", "d3"], "")).toContain("d2");
    expect(intentProblem("أفضّل d2 لوضوحه", ["d1", "d2", "d3"], "d2")).toBe("");
    expect(intentProblem("ملاحظة عامة", ["d1", "d2"], "")).toBe("");
    expect(intentProblem("sd2x", ["d2"], "")).toBe("");
  });
});
