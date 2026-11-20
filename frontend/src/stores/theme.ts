import { defineStore } from "pinia";

export type ThemeMode = "auto" | "light" | "dark";
export const THEME_KEY = "sima_theme";
export const THEME_MODES: ThemeMode[] = ["light", "auto", "dark"];
export const THEME_AR: Record<ThemeMode, string> = { auto: "تلقائية", light: "فاتحة", dark: "داكنة" };

function stored(): ThemeMode {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto"; // التخزين محجوب: تبقى السمة تلقائية بلا خطأ
  }
}

// تفضيل السمة وحده يُحفظ في المتصفح (راحة عرض لا بيانات)؛ «تلقائية» تتبع نظام التشغيل بلا data-theme.
export function applyTheme(mode: ThemeMode, root: HTMLElement = document.documentElement): void {
  if (mode === "auto") delete root.dataset.theme;
  else root.dataset.theme = mode;
}

export const useThemeStore = defineStore("theme", {
  state: () => ({ mode: stored() as ThemeMode }),
  actions: {
    init() {
      applyTheme(this.mode);
    },
    set(mode: ThemeMode) {
      this.mode = mode;
      applyTheme(mode);
      try {
        if (mode === "auto") localStorage.removeItem(THEME_KEY);
        else localStorage.setItem(THEME_KEY, mode);
      } catch {
        // التفضيل يسري في هذه الجلسة فقط
      }
    },
  },
});
