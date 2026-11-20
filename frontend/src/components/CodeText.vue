<script setup lang="ts">
import { computed } from "vue";
import { codeParts } from "@/utils/format";

// نص عربي فيه مقاطع بين علامتَي ` ` (أسماء ملفات وأوامر): تُعزل اتجاهًا بـbdi وتُكتب بخط الشيفرة.
const props = defineProps<{ text: string }>();
const parts = computed(() => codeParts(props.text));
</script>

<template>
  <template v-for="(x, i) in parts" :key="i"><bdi v-if="x.code" class="mono">{{ x.text }}</bdi><template v-else>{{ x.text }}</template></template>
</template>
