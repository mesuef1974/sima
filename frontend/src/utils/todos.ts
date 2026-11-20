import type { BoardState, Timeline } from "@/types";

export type TodoIcon = "pr" | "warn" | "name";
export interface Todo { ic: TodoIcon; title: string; body: string; code?: string; href?: string; cta?: string; external?: boolean }

/** ما ينتظر المالك خارج صندوق القرارات: استلام الطلبات، والبطاقات المتوقفة، والتسليم، والفحص الرسمي للاسم.
 *  طلب الدمج الذي ينتظر اعتماد المالك يُقرأ من سجل كل مشروع (now يحمل pr_url والأمر)، لأن بطاقات الدفتر s.cards فارغة
 *  ما لم تعمل المنصة بـ --repo. */
export function todos(s: BoardState, timelines: Record<string, Timeline | undefined> = {}): Todo[] {
  const t: Todo[] = [];
  for (const r of s.sima) {
    const now = timelines[r.project]?.now;
    if (now?.who !== "owner" || !(now.pr_url || timelines[r.project]?.progress?.current === "landed")) continue;
    t.push({ ic: "pr", title: `استلام المشروع: ${r.name_ar}`, body: `${now.text} راجع الطلب ثم شغّل أمر سطر الاعتماد من «ماذا جرى؟» في صفحة المشاريع.`,
      ...(now.pr_url ? { href: now.pr_url, cta: "افتح الطلب", external: true } : { href: "#/projects", cta: "المشروع" }) });
  }
  for (const c of s.cards) {
    if ((c.state === "pr_opened" || c.state === "ci_green") && !t.some((x) => x.href && x.href === c.url)) {
      const head = (c.log.find((l) => l.text.includes("الرأس"))?.text ?? "").split("الرأس ").pop() ?? "";
      t.push({ ic: "pr", title: `استلام المشروع: ${c.title}`, body: `المخرجات سُلّمت؛ اعتماد طلب الدمج في المشروع المستلم بسطر «اعتُمد من المالك» على الرأس ${head}.`,
        href: c.url, cta: "افتح الطلب", external: true });
    }
    if (c.state === "prepush_failed" || c.state === "blocked")
      t.push({ ic: "warn", title: `بطاقة متوقفة: ${c.title}`, body: "راجع worktree البطاقة ثم أعدها جاهزة.", href: "#/auto", cta: "الأتمتة" });
  }
  for (const r of s.sima) {
    const cur = r.steps.find((x) => x.status === "current");
    if (cur?.key === "deliver" && r.closed)
      t.push({ ic: "pr", title: `سلّم ${r.name_ar} إلى مشروعه`, body: "الحزمة معتمدة ولم تُسلَّم:",
        code: `uv run sima deliver briefs/${r.project}.yaml --repo <المستودع>`, href: "#/projects", cta: "المشروع" });
  }
  if (s.sima.some((r) => r.name_check.status === "clear" && /لم تُفحصا|أولي/.test(r.name_check.note)))
    t.push({ ic: "name", title: "الفحص الرسمي للاسم لم يكتمل", body: "تحقق الاسم المسجّل أولي (بحث ويب). افحص قاعدة WIPO وبوابة وزارة التجارة ثم حدّث السجل.",
      href: "#/projects", cta: "المشروع" });
  return t;
}
