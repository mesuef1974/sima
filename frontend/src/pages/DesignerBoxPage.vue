<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { fetchBox, post } from "@/api/client";
import { takeInbound } from "@/inbound";
import type { BoxItem } from "@/types";
import { chatUrl, outLink } from "@/utils/boxLink";

// صندوق المصمّم (قرار المالك 2026-11-13): نص الطلب يذهب إلى محادثة المصمّم الخارجي وردّه يعود دون أن يمرّا بجلسة النموذج.
const route = useRoute();
const items = ref<BoxItem[]>([]);
const error = ref("");
const chat = ref(typeof route.query.chat === "string" ? route.query.chat : `https://chatgpt.com/`);
const copied = ref("");
const arrived = takeInbound();
const text = ref(arrived?.text ?? "");
const image = ref<string | null>(arrived?.image ?? null);
const target = ref("");
const busy = ref(false);
const result = ref<{ ok: boolean; text: string } | null>(null);

const chatOk = computed(() => chatUrl(chat.value) !== null);
const chosen = computed(() => items.value.find((i) => i.project === target.value) ?? items.value[0]);
const needsImage = computed(() => chosen.value?.kind === "sketches");
const ready = computed(() => Boolean(chosen.value) && text.value.trim().length > 0 && (!needsImage.value || image.value !== null));

async function load(): Promise<void> {
  try {
    items.value = (await fetchBox()).items;
    error.value = "";
    if (!items.value.some((i) => i.project === target.value)) target.value = items.value[0]?.project ?? "";
  } catch {
    error.value = "تعذّر قراءة الصندوق من الخادم.";
  }
}

function open(it: BoxItem): void {
  const u = chatUrl(chat.value);
  if (u) window.location.assign(outLink(u, it.sha256, it.text));
}

async function copy(it: BoxItem): Promise<void> {
  try {
    await navigator.clipboard.writeText(it.text);
    copied.value = it.project;
  } catch {
    copied.value = "";
    error.value = "المتصفح منع النسخ إلى الحافظة؛ استعمل «افتح المحادثة بالطلب» أو انسخ من النص المعروض.";
  }
}

function pickImage(e: Event): void {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = () => { image.value = typeof r.result === "string" ? r.result : null; };
  r.readAsDataURL(f);
}

async function receive(): Promise<void> {
  const it = chosen.value;
  if (!it || !ready.value) return;
  busy.value = true;
  const r = await post("designer-box/intake", { project: it.project, version: it.version, key: it.key, text: text.value,
    image: needsImage.value ? image.value : null });
  result.value = { ok: r.ok, text: (r.ok ? r.message : r.error) ?? "" };
  busy.value = false;
  if (r.ok) {
    text.value = "";
    image.value = null;
    void load();
  }
}

onMounted(load);
</script>

<template>
  <div class="pagehead"><div><h1>صندوق المصمّم</h1><p class="sub">ما ينتظر المصمّم الخارجي يخرج من هنا نصًّا وحده، وردّه يدخل من هنا إلى الخط كما وصل. الفحص والقرار كما هما: الخط يفحص، وأنت تختار السكتش وتعتمد الدليل.</p></div></div>
  <p v-if="error" class="rl-status bad" role="status">{{ error }}</p>

  <section class="card">
    <div class="cardhead"><h2>ينتظر الإرسال</h2><span class="sub">النص ما بعد «النص المرسل» وحده</span></div>
    <p v-if="!items.length" class="empty">لا طلب ينتظر المصمّم الخارجي الآن.</p>
    <template v-else>
      <div class="st-form">
        <label class="ib-l" for="bx-chat">رابط محادثة المصمّم (chatgpt.com وحده؛ المتجه وتصحيحه في المحادثة التي رُسمت فيها السكتشات)</label>
        <input id="bx-chat" v-model="chat" class="bx-in" type="url" dir="ltr" inputmode="url" autocomplete="off" />
        <p v-if="!chatOk" class="rl-status bad" role="status">الرابط ليس محادثة على chatgpt.com؛ لا يُفتح بالطلب.</p>
      </div>
      <article v-for="it in items" :key="it.project" class="bx-item">
        <div class="cardhead">
          <h3>{{ it.project }}: {{ it.kind_ar }}</h3>
          <span class="rl-tag m">v{{ it.version }} · {{ it.key }}</span>
          <span class="sub mono">{{ it.chars }} حرفًا · {{ it.sha256.slice(0, 12) }}</span>
        </div>
        <p v-if="it.invoke" class="sub">يُطلب من إضافة الشعارات في المحادثة نفسها: استدعِها في خانة الكتابة قبل لصق النص.</p>
        <details><summary>النص المرسل</summary><pre class="bx-pre">{{ it.text }}</pre></details>
        <div class="bx-acts">
          <button type="button" class="btn" :disabled="!chatOk" @click="open(it)">افتح المحادثة بالطلب</button>
          <button type="button" class="btn ib-x" @click="copy(it)">انسخ النص</button>
          <span v-if="copied === it.project" class="sub" role="status">نُسخ.</span>
        </div>
      </article>
    </template>
  </section>

  <section class="card">
    <div class="cardhead"><h2>استلام الردّ</h2><span class="sub">يُكتب في الإصدار الذي ينتظره وحده، ثم يُستأنف الخط</span></div>
    <p v-if="arrived" class="rl-status" role="status">وصل ردّ من خارج المنصة في الرابط. راجعه ثم استلمه؛ لا يدخل الخط قبل ضغطك.</p>
    <div class="st-form">
      <label class="ib-l" for="bx-target">المشروع الذي ينتظر الردّ</label>
      <select id="bx-target" v-model="target" class="bx-in" :disabled="!items.length">
        <option v-for="it in items" :key="it.project" :value="it.project">{{ it.project }} v{{ it.version }}: {{ it.kind_ar }}</option>
      </select>
      <label class="ib-l" for="bx-text">نص الردّ: القائمة المرقّمة للسكتشات، أو كتل الشيفرة يسبق كلًّا منها اسم ملفه</label>
      <textarea id="bx-text" v-model="text" rows="8" dir="auto" placeholder="الصق ردّ المصمّم هنا كما هو"></textarea>
      <template v-if="needsImage">
        <label class="ib-l" for="bx-image">صورة صفحة السكتشات (PNG أو JPEG)</label>
        <input id="bx-image" type="file" accept="image/png,image/jpeg" @change="pickImage" />
      </template>
      <figure v-if="image" class="ws-b">
        <img :src="image" alt="الصورة الواردة قبل استلامها" />
        <figcaption v-if="!needsImage"><span class="sub">وصلت صورة، وما ينتظره المشروع الآن لا يأخذ صورة؛ لن تُرسل.</span></figcaption>
      </figure>
      <button type="button" class="btn" :disabled="busy || !ready" @click="receive">استلم في الخط</button>
      <p v-if="result" class="rl-status" :class="result.ok ? 'good' : 'bad'" role="status">{{ result.text }}</p>
    </div>
  </section>
</template>
