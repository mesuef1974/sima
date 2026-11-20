import { createPinia, setActivePinia } from "pinia";
import { THEME_KEY, applyTheme, useThemeStore } from "@/stores/theme";

describe("مخزن السمة", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    setActivePinia(createPinia());
  });

  it("تلقائية افتراضيًا بلا data-theme", () => {
    const t = useThemeStore();
    t.init();
    expect(t.mode).toBe("auto");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("يحفظ الداكنة ويطبّقها ثم يمحو المفتاح عند العودة إلى التلقائية", () => {
    const t = useThemeStore();
    t.set("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    t.set("auto");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("يقرأ المحفوظ ويتجاهل القيم الغريبة", () => {
    localStorage.setItem(THEME_KEY, "light");
    setActivePinia(createPinia());
    expect(useThemeStore().mode).toBe("light");
    localStorage.setItem(THEME_KEY, "neon");
    setActivePinia(createPinia());
    expect(useThemeStore().mode).toBe("auto");
  });

  it("applyTheme يعمل على أي عنصر جذر", () => {
    const el = document.createElement("div");
    applyTheme("light", el);
    expect(el.dataset.theme).toBe("light");
  });
});
