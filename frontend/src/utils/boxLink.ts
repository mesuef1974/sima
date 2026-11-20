// صندوق المصمّم: الطلب يذهب إلى محادثة المصمّم الخارجي، وردّه يعود، في جزء الرابط بعد # (لا يُرسل إلى أي خادم)،
// فلا يمرّ النص ولا الصورة عبر جلسة النموذج. الوارد من خارج المنصة بيانات تُعرض ولا تُرسل إلى الخط إلا بضغطة.
export const OUT_PREFIX = "#sima-out=";
export const IN_PREFIX = "#sima-in=";
export const CHAT_HOST = "chatgpt.com";
const MIME: Record<string, string> = { png: "image/png", jpg: "image/jpeg" };

export interface Inbound { text: string; image: string | null }

export function b64url(text: string): string {
  let bin = "";
  for (const b of new TextEncoder().encode(text)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function unb64url(s: string): string {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder("utf-8", { fatal: true }).decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

/** رابط محادثة المصمّم: https على chatgpt.com وحده، بلا بيانات دخول في الرابط. غيره لا يُفتح بالطلب. */
export function chatUrl(raw: string): URL | null {
  try {
    const u = new URL(raw.trim());
    return u.protocol === "https:" && u.hostname === CHAT_HOST && !u.username && !u.password ? u : null;
  } catch {
    return null;
  }
}

/** رابط المحادثة حاملًا النص وبصمته؛ ما يلصقه في خانة الكتابة يتحقق من البصمة أولًا. */
export function outLink(chat: URL, sha256: string, text: string): string {
  return `${chat.origin}${chat.pathname}${OUT_PREFIX}${sha256}.${b64url(text)}`;
}

/** الوارد: `#sima-in=<png|jpg|txt>.<النص base64url>.<الصورة base64>`. ما لا يطابق الصيغة يُهمل. */
export function readInbound(hash: string): Inbound | null {
  if (!hash.startsWith(IN_PREFIX)) return null;
  const [kind = "", text = "", image = ""] = hash.slice(IN_PREFIX.length).split(".");
  try {
    const t = unb64url(text);
    if (!t.trim()) return null;
    const mime = MIME[kind];
    return { text: t, image: mime && /^[A-Za-z0-9+/]+=*$/.test(image) ? `data:${mime};base64,${image}` : null };
  } catch {
    return null;
  }
}
