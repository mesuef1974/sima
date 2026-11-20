import { createRouter, createWebHashHistory } from "vue-router";

// تاريخ hash: الخادم يخدم صفحة واحدة على «/» فلا حاجة إلى مسارات خادم لكل صفحة. الصفحات تُحمَّل كسولًا.
export const TITLES: Record<string, string> = { home: "اليوم", projects: "المشاريع", decisions: "القرارات", auto: "الأتمتة", box: "صندوق المصمّم" };

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "home", component: () => import("@/pages/HomePage.vue") },
    { path: "/projects", name: "projects", component: () => import("@/pages/ProjectsPage.vue") },
    { path: "/decisions", name: "decisions", component: () => import("@/pages/DecisionsPage.vue") },
    { path: "/auto", name: "auto", component: () => import("@/pages/AutomationPage.vue") },
    { path: "/box", name: "box", component: () => import("@/pages/DesignerBoxPage.vue") },
    { path: "/:rest(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

// صفحة كسولة لم تُحمَّل: الواجهة أُعيد بناؤها والتبويب مفتوح، فملف الصفحة القديم لم يعد موجودًا والنقر لا يفتح شيئًا.
// تُحمَّل الصفحة المطلوبة من جديد مرة واحدة لكل وجهة (علامة جلسة تمنع الدوران إن كان الخادم نفسه متوقفًا).
const RELOADED = "sima-chunk-reload";
export function staleChunk(err: unknown): boolean {
  return /dynamically imported module|module script failed|error loading dynamically/i.test(String((err as Error | null)?.message ?? err));
}
router.onError((err, to) => {
  if (!staleChunk(err)) return;
  try {
    if (window.sessionStorage.getItem(RELOADED) === to.fullPath) return;
    window.sessionStorage.setItem(RELOADED, to.fullPath);
  } catch {
    return; // بلا تخزين جلسة لا ضمان ضد الدوران: يبقى التحديث اليدوي
  }
  window.location.hash = to.fullPath;
  window.location.reload();
});

router.afterEach((to) => {
  try {
    window.sessionStorage.removeItem(RELOADED);
  } catch {
    /* لا تخزين جلسة */
  }
  document.title = `${TITLES[String(to.name)] ?? "اليوم"} · سِمة`;
  requestAnimationFrame(() => document.getElementById("main")?.focus({ preventScroll: true }));
});
