<script setup lang="ts">
import { computed } from "vue";
import AppIcon from "@/components/AppIcon.vue";
import type { TrackNode } from "@/types";
import { hm } from "@/utils/format";

// مسار المراحل: عقد على سكة تملؤها نسبة التقدم، وشارة فوق المرحلة الحالية.
const props = defineProps<{ nodes: TrackNode[]; p: number; chip: string; chipText: string; finalKey: string }>();
const n = computed(() => Math.max(1, props.nodes.length - 1));
const fill = computed(() => (props.chip === "bad" || props.chip === "good" ? props.chip : ""));
</script>

<template>
  <div class="rl-trackbox">
    <div class="rl-track" :style="{ '--p': p, '--n': n }">
      <div class="rl-chip" :class="chip"><span class="in"><i></i><span>{{ chipText }}</span></span></div>
      <div class="rl-rail"></div>
      <div class="rl-fill" :class="fill"></div>
      <div class="rl-nodes">
        <div v-for="(x, i) in nodes" :key="x.key" class="rl-node" :class="[x.status, { final: x.key === finalKey }]">
          <div class="c">
            <AppIcon v-if="x.status === 'done'" name="done" />
            <AppIcon v-else-if="x.status === 'fail'" name="fail" />
            <template v-else>{{ i + 1 }}</template>
          </div>
          <div class="lb"><b>{{ x.label }}</b><span>{{ x.at ? hm(x.at) : "—" }}</span></div>
        </div>
      </div>
      <div class="rl-spacer"></div>
    </div>
  </div>
</template>
