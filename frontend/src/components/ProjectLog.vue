<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import ResumeButton from "@/components/ResumeButton.vue";
import { useBoard } from "@/stores/board";
import { full, hm, WHO_AR } from "@/utils/format";

// صندوق حالة المشروع: أين يقف الآن ومن ينتظر، وما سيحدث بعد قرارك، ونسبة التقدم، وكل ما جرى الأحدث أولًا.
const board = useBoard();
const dlg = ref<HTMLDialogElement | null>(null);
const t = computed(() => (board.logProject ? board.timelines[board.logProject] : undefined));
const pct = computed(() => (t.value ? Math.round((100 * t.value.progress.done) / t.value.progress.total) : 0));

watch(
  () => board.logProject,
  async (p) => {
    await nextTick();
    if (p && dlg.value && !dlg.value.open) dlg.value.showModal();
    if (!p && dlg.value?.open) dlg.value.close();
  },
);
const close = (): void => {
  board.logProject = null;
};
// أمر سطر الاعتماد يشغّله المالك بنفسه في PowerShell بعد مراجعة الطلب؛ المنصة تنسخه فقط ولا تشغّله
const copied = ref(false);
async function copyCommand(cmd: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(cmd);
    copied.value = true;
    setTimeout(() => (copied.value = false), 2500);
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <dialog ref="dlg" class="plog" aria-labelledby="plog-title" @close="close" @click.self="close">
    <div v-if="t" class="plog-in">
      <div class="plog-head">
        <h2 id="plog-title">ماذا جرى على {{ t.project }} <span class="sub">{{ t.version }} · <bdi class="mono">{{ t.key }}</bdi></span></h2>
        <button class="btn" type="button" @click="close">إغلاق</button>
      </div>

      <div class="plog-now" :class="[t.now.who, t.now.state]" role="status">
        <span class="fm-who" :class="{ o: t.now.who === 'owner', m: t.now.who === 'model' }">{{ WHO_AR[t.now.who] }}</span>
        <div>
          <b>{{ t.now.text }}</b>
          <span v-if="t.now.since" class="sub"> منذ {{ hm(t.now.since) }}</span>
          <p v-if="t.now.after" class="sub">{{ t.now.after }}</p>
          <ResumeButton :project="t.project" />
          <div v-if="t.now.command" class="plog-cmd">
            <p class="sub">
              راجع <a :href="t.now.pr_url" target="_blank" rel="noopener noreferrer">الطلب على GitHub</a>، ثم شغّل هذا الأمر في PowerShell
              ليكتب سطر اعتمادك مربوطًا بالرأس المعروض (يرفض إن تغيّر الرأس):
            </p>
            <pre dir="ltr"><code>{{ t.now.command }}</code></pre>
            <button class="btn" type="button" @click="copyCommand(t.now.command)">{{ copied ? "نُسخ" : "انسخ الأمر" }}</button>
          </div>
        </div>
      </div>

      <div class="plog-prog">
        <div class="plog-bar" role="progressbar" :aria-valuenow="pct" aria-valuemin="0" aria-valuemax="100" :aria-label="`التقدم ${pct}%`">
          <i :style="{ inlineSize: `${pct}%` }"></i>
        </div>
        <span class="rl-num">{{ t.progress.done }} من {{ t.progress.total }} مراحل · {{ pct }}%</span>
      </div>
      <ol class="plog-steps">
        <li v-for="s in t.progress.steps" :key="s.key" :class="s.status">{{ s.label }}</li>
      </ol>

      <h3 class="rl-h3">ما جرى <span class="sub">الأحدث أولًا</span></h3>
      <ul class="rl-log plog-log">
        <li v-for="(e, i) in t.events" :key="i" :class="`k-${e.who === 'owner' ? 'good' : 'x'}`">
          <span class="tm" :title="full(e.at)">{{ hm(e.at) }}</span><span class="d"></span>
          <span><b class="plog-who">{{ WHO_AR[e.who] }}:</b> {{ e.text }}</span>
        </li>
      </ul>
    </div>
    <p v-else class="empty">جارٍ التحميل…</p>
  </dialog>
</template>
