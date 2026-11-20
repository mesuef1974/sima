<script setup lang="ts">
import { computed } from "vue";
import ResumeButton from "@/components/ResumeButton.vue";
import { useBoard } from "@/stores/board";
import { hm } from "@/utils/format";

// حال التشغيل الخلفي لمشروع بعد قرار من المنصة. التوقف (سقف، تكرار، فشل استدعاء) تحذير بسببه وزر استئناف، لا اكتمال.
const props = defineProps<{ project: string }>();
const board = useBoard();
const job = computed(() => board.jobFor(props.project));
const cls = computed(() => ({ failed: "bad", stopped: "warn", done: "good", running: "" })[job.value?.state ?? "running"]);
const text = computed(() => {
  const j = job.value;
  if (!j) return "";
  if (j.state === "running") return `الخط يعمل في الخلفية منذ ${hm(j.started)}…`;
  if (j.state === "failed") return `فشل التشغيل الخلفي (${j.code}): ${j.message}`;
  if (j.state === "stopped") return `${j.code_ar}: ${j.message}`;
  return `انتهى التشغيل الخلفي: ${j.code_ar}`;
});
</script>

<template>
  <div v-if="job" class="rl-status" :class="cls" role="status">
    {{ text }} <button class="linkbtn" type="button" @click="board.openLog(project)">ماذا جرى؟</button>
    <ResumeButton v-if="job.state !== 'running'" :project="project" />
  </div>
</template>
