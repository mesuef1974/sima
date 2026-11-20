<script setup lang="ts">
import { computed } from "vue";
import { ICONS, type IconName } from "@/data/icons";

const props = defineProps<{ name: IconName }>();
const icon = computed(() => ICONS[props.name]);
</script>

<template>
  <svg class="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="icon.width" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" v-html="icon.body"></svg>
</template>
