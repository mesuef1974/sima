<script setup lang="ts">
import { computed, ref } from "vue";
import { useBoard } from "@/stores/board";

// زر الاستئناف: يعيد تشغيل الخط حيث وقف على الإصدار المعروض (توقف التشغيل الآلي، أو قرار سُجّل ولم يُستأنف، أو خطأ أُصلح).
// يظهر حين يقول سجل المشروع إن الإصدار يُستأنف؛ لا يسجّل قرارًا، والخادم يرفضه إن تغيّر الإصدار أو جرى تشغيل.
// وزر «إصدار جديد» (قرار المالك 2026-11-20): بعد إصدار مغلق تغيّر بعده موجزه أو بيان اعتماده، يفتح الخادم الإصدار التالي.
const props = defineProps<{ project: string }>();
const board = useBoard();
const t = computed(() => board.timelines[props.project]);
const msg = ref("");
const kind = ref("");
const busy = ref(false);

async function run(action: "resume" | "new-version"): Promise<void> {
  const tl = t.value;
  if (!tl) return;
  busy.value = true;
  kind.value = "";
  msg.value = action === "resume" ? "جارٍ الاستئناف…" : "جارٍ فتح الإصدار الجديد…";
  const r = await board.send(action, { project: tl.project, version: Number(tl.version.replace(/^v/, "")), key: tl.key });
  busy.value = false;
  kind.value = r.ok ? "good" : "bad";
  msg.value = (r.ok ? r.message : r.error) ?? "";
}
</script>

<template>
  <div v-if="t?.now.resume || t?.now.renew || msg" class="rl-resume">
    <button v-if="t?.now.resume" class="btn pri" type="button" :disabled="busy" @click="run('resume')">استأنف الخط</button>
    <template v-else-if="t?.now.renew">
      <span class="sub">{{ t.now.renew }}</span>
      <button class="btn pri" type="button" :disabled="busy" @click="run('new-version')">افتح إصدارًا جديدًا</button>
    </template>
    <span v-if="t?.now.resume && t.now.who === 'model'" class="sub">يستدعي النموذج آليًا ضمن سقف الأمر (15 دولارًا و16 استدعاءً).</span>
    <span class="ib-m" :class="kind" role="status">{{ msg }}</span>
  </div>
</template>
