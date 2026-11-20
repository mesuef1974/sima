<script setup lang="ts">
import { computed } from "vue";
import { useBoard } from "@/stores/board";
import { finished, waitLabel } from "@/utils/timelines";

// لافتة «اليوم» الثابتة: لكل مشروع أين يقف الآن ومن ينتظر ونسبة تقدمه، وزر يفتح صندوق ما جرى.
const board = useBoard();
const rows = computed(() => Object.values(board.timelines));
const pct = (d: number, t: number): number => Math.round((100 * d) / t);
</script>

<template>
  <section v-if="rows.length" class="card pstrip" aria-label="تقدم المشاريع">
    <div v-for="t in rows" :key="t.project" class="pstrip-row">
      <div class="pstrip-main">
        <b>{{ t.project }} <span class="sub">{{ t.version }}</span></b>
        <span class="fm-who" :class="{ o: t.now.who === 'owner' && !finished(t), m: t.now.who === 'model' }">{{ waitLabel(t) }}</span>
        <span v-if="t.stale" class="rl-st warn" title="تعذّر جلب سجل هذا المشروع في آخر تحديث">آخر ما وصل</span>
        <span class="pstrip-now">{{ t.now.text }}</span>
      </div>
      <div class="plog-prog">
        <div class="plog-bar" role="progressbar" :aria-valuenow="pct(t.progress.done, t.progress.total)" aria-valuemin="0" aria-valuemax="100">
          <i :style="{ inlineSize: `${pct(t.progress.done, t.progress.total)}%` }"></i>
        </div>
        <span class="rl-num">{{ t.progress.done }}/{{ t.progress.total }}</span>
        <button class="btn" type="button" @click="board.openLog(t.project)">ماذا جرى؟</button>
      </div>
    </div>
  </section>
</template>
