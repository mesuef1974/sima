import type { BoardState, BoxItem, PostPath, Registry, Reply, Timeline } from "@/types";

// رمز التشغيل يحقنه Django في الصفحة لكل تشغيل للخادم؛ لا يُخزَّن في المتصفح. إن أُعيد تشغيل الخادم والصفحة مفتوحة
// تغيّر الرمز، فتجلب الصفحة رمزها الجديد من أصلها نفسه وتعيد الطلب مرة واحدة، فلا يضيع قرار المالك. (أصل آخر لا يستطيع
// قراءة الصفحة، وفحص الأصل في الخادم باقٍ، فلا يُضعف هذا الحماية.)
let current = "";
const token = (): string => current || (document.querySelector<HTMLMetaElement>('meta[name="sima-token"]')?.content ?? "");

async function refreshToken(): Promise<boolean> {
  try {
    const html = await (await fetch("/", { cache: "no-store", credentials: "same-origin" })).text();
    const m = /<meta name="sima-token" content="([^"]+)"/.exec(html);
    if (!m || m[1] === token()) return false;
    current = m[1];
    return true;
  } catch {
    return false;
  }
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store", credentials: "same-origin" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as T;
}

export const fetchState = (): Promise<BoardState> => getJson<BoardState>("/api/state");
export const fetchTimeline = (project: string): Promise<Timeline> => getJson<Timeline>(`/api/timeline/${encodeURIComponent(project)}`);
export const fetchRegistry = (): Promise<Registry> => getJson<Registry>("/api/registry");
export const fetchBox = (): Promise<{ items: BoxItem[] }> => getJson<{ items: BoxItem[] }>("/api/designer-box");

async function send(path: string, payload: Record<string, unknown>): Promise<Response> {
  return fetch(`/api/${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Sima-Token": token() },
    body: JSON.stringify(payload),
  });
}

export async function post(path: PostPath, payload: Record<string, unknown>): Promise<Reply> {
  try {
    let r = await send(path, payload);
    if (r.status === 403 && (await refreshToken())) r = await send(path, payload); // أُعيد تشغيل الخادم: رمز جديد ثم محاولة واحدة
    const j = (await r.json()) as Partial<Reply>;
    return { ok: Boolean(j.ok), message: j.message ?? "", error: j.error ?? (r.ok ? "" : `HTTP ${r.status}`) };
  } catch {
    return { ok: false, error: "تعذّر الاتصال بالخادم." };
  }
}
