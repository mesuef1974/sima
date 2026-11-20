<script setup lang="ts">
import { computed } from "vue";
import RunTrack from "@/components/RunTrack.vue";
import type { Card } from "@/types";
import { dur, full, hm } from "@/utils/format";

// بطاقة المشروع المستلم من دفتره: الحالة والمحاولة ومسارها، وسجلّها في العرض الكامل.
const props = defineProps<{ card: Card; now: string; compact?: boolean }>();
const t = computed(() => props.card.track);
const fin = computed(() => t.value.chip === "good" || t.value.chip === "bad");
const prNum = computed(() => props.card.url.split("/").pop());
</script>

<template>
  <div class="rl-head">
    <div class="rl-ttl">
      <div class="rl-cid">{{ card.id }}</div>
      <div class="rl-prob">{{ card.title }}</div>
      <div class="rl-tags">
        <span class="rl-tag m">{{ card.state_ar }}</span>
        <span class="rl-tag">المحاولة {{ t.attempts }}</span>
        <a v-if="card.url" class="rl-tag" :href="card.url" target="_blank" rel="noopener">طلب الدمج #{{ prNum }}</a>
      </div>
    </div>
    <div class="rl-elapsed rl-num" :title="fin ? 'مدّة المحاولة' : 'مدّة المحاولة (جارية)'">{{ dur(t.attempt_start, fin ? card.updated : now) }}</div>
  </div>
  <div class="rl-status" :class="t.status_kind" role="status">{{ t.status }}</div>
  <RunTrack :nodes="t.nodes" :p="t.p" :chip="t.chip" :chip-text="card.id" final-key="published" />
  <div v-if="!compact" class="rl-cols">
    <div>
      <h3 class="rl-h3">حقائق المحاولة</h3>
      <ul class="rl-facts">
        <li><span>أُنشئت البطاقة</span><span>{{ full(card.created) }}</span></li>
        <li><span>بدأت المحاولة</span><span>{{ hm(t.attempt_start) }}</span></li>
        <li><span>في المرحلة الحالية</span><span>منذ {{ dur(t.stage_since, now) }}</span></li>
        <li><span>آخر حدث</span><span>{{ hm(card.updated) }}</span></li>
      </ul>
    </div>
    <div>
      <h3 class="rl-h3">سجلّ البطاقة <span class="sub">الأحدث أوّلًا</span></h3>
      <ul class="rl-log">
        <li v-for="(l, i) in card.log" :key="i" :class="`k-${l.kind || 'x'}`"><span class="tm">{{ hm(l.at) }}</span><span class="d"></span><span>{{ l.text }}</span></li>
      </ul>
    </div>
  </div>
</template>
