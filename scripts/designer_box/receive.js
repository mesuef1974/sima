// صندوق المصمّم، جهة الاستلام. يُشغَّل في تبويب محادثة المصمّم بعد اكتمال ردّه: يجمع آخر ردّ نصًّا (القوائم مرقّمة وكتل
// الشيفرة مسوّرة كما هي) وآخر صورة كبيرة إن طُلبت، ثم ينتقل إلى صندوق المصمّم في منصة سِمة حاملًا إياهما في جزء الرابط
// (لا يُرسل إلى أي خادم). لا يدخل الخط شيء قبل زر «استلم في الخط» هناك.
const PLATFORM = "http://127.0.0.1:8766/";
const WITH_IMAGE = true; // صفحة السكتشات: true. ردود المتجه والتصحيح: false
const BLOCK = "[data-code-block],pre";
const md = [];
const walk = (n) => {
  for (const c of n.childNodes) {
    if (c.nodeType === 3) {
      if (c.textContent.trim()) md.push(c.textContent.trim());
    } else if (c.nodeType !== 1) {
      continue;
    } else if (c.matches(BLOCK)) {
      // textContent لا innerText: الكتلة خارج مجال الرؤية (أو في تبويب مخفي) لا تُصيَّر فيعود innerText فارغًا
      const code = (c.getAttribute("data-markdown-copy-text") || (c.querySelector("code") || c).textContent).replace(/\n+$/, "");
      md.push(code.startsWith("```") ? code : "```\n" + code + "\n```");
    } else if (c.tagName === "OL") {
      [...c.children].forEach((li, i) => {
        const no = (c.start || 1) + i;
        if (li.querySelector(BLOCK)) { md.push(no + "."); walk(li); } else md.push(no + ". " + li.innerText.trim());
      });
    } else if (c.querySelector(BLOCK + ",ol")) {
      walk(c);
    } else if (c.innerText.trim()) {
      md.push(c.innerText.trim());
    }
  }
};
const replies = [...document.querySelectorAll('[data-markdown-text-style="assistant-message"]')];
if (!replies.length) throw new Error("لا ردّ نصّي من المصمّم في الصفحة");
walk(replies[replies.length - 1]);
const text = md.join("\n\n");
const b64 = (blob) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res(String(r.result).split(",")[1]);
  r.onerror = rej;
  r.readAsDataURL(blob);
});
let kind = "txt";
let image = "";
if (WITH_IMAGE) {
  const el = [...document.querySelectorAll("main img")].filter((i) => i.naturalWidth >= 512).pop();
  if (!el) throw new Error("لا صورة كبيرة في المحادثة");
  const canvas = (type, q) => new Promise((res) => {
    const c = document.createElement("canvas");
    c.width = el.naturalWidth;
    c.height = el.naturalHeight;
    c.getContext("2d").drawImage(el, 0, 0);
    c.toBlob(res, type, q);
  });
  let blob;
  try { blob = await (await fetch(el.src)).blob(); } catch { blob = await canvas("image/png"); }
  if (!/^image\/(png|jpeg)$/.test(blob.type)) blob = await canvas("image/png");
  if (blob.size > 1400000) blob = await canvas("image/jpeg", 0.92); // حدّ طول الرابط في المتصفح نحو 2 م.ب
  kind = blob.type === "image/png" ? "png" : "jpg";
  image = await b64(blob);
}
let bin = "";
for (const b of new TextEncoder().encode(text)) bin += String.fromCharCode(b);
const url = PLATFORM + "#sima-in=" + kind + "." + btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") + "." + image;
if (url.length > 2000000) throw new Error("الردّ أكبر من أن يحمله الرابط: " + url.length);
location.assign(url);
({ ok: true, chars: text.length, image: kind, url: url.length });
