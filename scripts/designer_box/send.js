// صندوق المصمّم، جهة الإرسال. يُشغَّل في تبويب محادثة المصمّم بعد زر «افتح المحادثة بالطلب» في منصة سِمة:
// يقرأ نص الطلب من جزء الرابط، يتحقق من بصمته، يزيله من الرابط، ويلصقه في خانة الكتابة. لا يرسل: الإرسال بضغطة بعده.
// للمتجه وتصحيحه تُستدعى إضافة الشعارات في الخانة قبل تشغيله (@Logo Des ثم Tab).
const m = location.hash.match(/^#sima-out=([0-9a-f]{64})\.([\w-]+)$/);
if (!m) throw new Error("لا طلب في الرابط");
history.replaceState(null, "", location.pathname + location.search);
const bytes = Uint8Array.from(atob(m[2].replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const hex = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
if (hex !== m[1]) throw new Error("بصمة النص لا تطابق ما عرضته المنصة");
const text = new TextDecoder().decode(bytes);
const box = document.querySelector('.ProseMirror[contenteditable="true"]');
box.focus();
const dt = new DataTransfer();
dt.setData("text/plain", text);
box.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
await new Promise((r) => setTimeout(r, 500));
({ ok: true, chars: text.length, sha: hex.slice(0, 12), draft: box.innerText.length, title: document.title });
