import { b64url, chatUrl, IN_PREFIX, outLink, OUT_PREFIX, readInbound, unb64url } from "@/utils/boxLink";

const TEXT = "ارسم صفحة سكتشات لشعار «أوراق»: زرًّا واحدًا، مولَّدة.\nسطر ثانٍ + / = ?";

describe("صندوق المصمّم: الرابط", () => {
  it("الترميز يعيد النص العربي بتشكيله كما هو وبلا محارف تكسر الرابط", () => {
    const enc = b64url(TEXT);
    expect(enc).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(unb64url(enc)).toBe(TEXT);
  });

  it("لا يُفتح بالطلب إلا محادثة https على chatgpt.com", () => {
    expect(chatUrl(" https://chatgpt.com/c/abc ")?.pathname).toBe("/c/abc");
    for (const bad of ["http://chatgpt.com/c/abc", "https://chatgpt.com.evil.example/c/abc", "https://evil.example/chatgpt.com", "https://user:pw@chatgpt.com/", "javascript:alert(1)", "ليس رابطًا"]) {
      expect(chatUrl(bad)).toBeNull();
    }
  });

  it("رابط الإرسال يحمل البصمة والنص في جزء الرابط وحده ويسقط ما كان فيه", () => {
    const link = outLink(chatUrl("https://chatgpt.com/c/abc?x=1#old")!, "a".repeat(64), TEXT);
    const [base, frag] = link.split("#");
    expect(base).toBe("https://chatgpt.com/c/abc");
    expect(`#${frag}`.startsWith(`${OUT_PREFIX}${"a".repeat(64)}.`)).toBe(true);
    expect(unb64url(frag.split(".")[1])).toBe(TEXT);
  });

  it("الوارد يُقرأ نصًّا وصورة، وما لا يطابق الصيغة يُهمل", () => {
    expect(readInbound(`${IN_PREFIX}png.${b64url(TEXT)}.iVBORw0KGgo=`)).toEqual({ text: TEXT, image: "data:image/png;base64,iVBORw0KGgo=" });
    expect(readInbound(`${IN_PREFIX}jpg.${b64url(TEXT)}./9j/4AAQ`)?.image).toBe("data:image/jpeg;base64,/9j/4AAQ");
    expect(readInbound(`${IN_PREFIX}txt.${b64url(TEXT)}.`)).toEqual({ text: TEXT, image: null });
    expect(readInbound(`${IN_PREFIX}svg.${b64url(TEXT)}.PHN2Zz4=`)?.image).toBeNull(); // نوع غير مقبول: النص وحده
    expect(readInbound(`${IN_PREFIX}png.${b64url(TEXT)}.<script>`)?.image).toBeNull();
    expect(readInbound("#/box")).toBeNull();
    expect(readInbound(`${IN_PREFIX}png.%%%.AAAA`)).toBeNull();
    expect(readInbound(`${IN_PREFIX}txt.${b64url("   ")}.`)).toBeNull();
  });
});
