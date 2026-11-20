// أيقونات المنصة (المشاريع والقرارات والتسليم من أيقونات الهوية المعتمدة، حزمة v1): خط بلا تعبئة يأخذ لون النص. نصوص SVG ثابتة من المصدر لا مدخلات مستخدم، فيُعرض داخلها بـ v-html آمنًا مع CSP.
export interface IconDef {
  body: string;
  width: number;
}

export const ICONS = {
  home: { width: 1.8, body: '<path d="M4 11l8-7 8 7v9H4z"/><path d="M10 20v-6h4v6"/>' },
  projects: { width: 1.75, body: '<path d="M3 9V5a2 2 0 0 1 2-2h4M21 15v4a2 2 0 0 1-2 2h-4"/><path d="M12 8l4 2-4 2-4-2zM8 13l4 2 4-2"/>' },
  decisions: { width: 1.75, body: '<path d="M3 9V5a2 2 0 0 1 2-2h4M21 15v4a2 2 0 0 1-2 2h-4"/><path d="M8 12h4M12 12l4-3M12 12l4 3"/>' },
  auto: { width: 1.75, body: '<path d="M3 9V5a2 2 0 0 1 2-2h4M21 15v4a2 2 0 0 1-2 2h-4"/><path d="M8 12h8M13 9l3 3-3 3"/>' },
  pr: { width: 2, body: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M6 8v8M18 16V9a3 3 0 0 0-3-3h-4"/>' },
  warn: { width: 2, body: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>' },
  search: { width: 2, body: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>' },
  done: { width: 3, body: '<path d="M5 12.5l4.5 4.5L19 7.5"/>' },
  fail: { width: 3, body: '<path d="M7 7l10 10M17 7L7 17"/>' },
  light: { width: 1.75, body: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"/>' },
  dark: { width: 1.75, body: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>' },
  auto_theme: { width: 1.75, body: '<circle cx="12" cy="12" r="8"/><path d="M12 4v16"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none"/>' },
} as const satisfies Record<string, IconDef>;

export type IconName = keyof typeof ICONS;
