<script setup lang="ts">
import AppIcon from "@/components/AppIcon.vue";
import type { IconName } from "@/data/icons";
import { THEME_AR, THEME_MODES, type ThemeMode, useThemeStore } from "@/stores/theme";

const theme = useThemeStore();
const glyph: Record<ThemeMode, IconName> = { light: "light", auto: "auto_theme", dark: "dark" };
</script>

<template>
  <div class="theme-toggle" role="group" aria-label="سمة الواجهة">
    <button v-for="m in THEME_MODES" :key="m" type="button" class="theme-option" :aria-pressed="theme.mode === m" :title="THEME_AR[m]" @click="theme.set(m)">
      <AppIcon :name="glyph[m]" />
      <span class="visually-hidden">{{ THEME_AR[m] }}</span>
    </button>
  </div>
</template>
