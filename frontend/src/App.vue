<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import AppIcon from "@/components/AppIcon.vue";
import BrandWordmark from "@/components/BrandWordmark.vue";
import ProjectLog from "@/components/ProjectLog.vue";
import ThemeToggle from "@/components/ThemeToggle.vue";
import { useBoard } from "@/stores/board";
import { clock } from "@/utils/format";
import { useThemeStore } from "@/stores/theme";

const board = useBoard();
useThemeStore().init();

const live = computed(() => (!board.online ? "off" : board.polling ? "" : "paused"));
const liveText = computed(() => (!board.online ? "منقطع" : board.polling ? "حيّ" : "متوقف"));
const runner = computed(() => board.state?.runner);

onMounted(() => {
  void board.tick();
  board.schedule();
});
onBeforeUnmount(() => {
  if (board.polling) board.togglePolling();
});
</script>

<template>
  <a class="skip" href="#main">تخطَّ إلى المحتوى</a>
  <div class="shell">
    <aside class="side" aria-label="التنقّل">
      <RouterLink class="brand" to="/" aria-label="سِمة، الصفحة الرئيسة">
        <BrandWordmark :height="44" />
        <small>من الموجز إلى الهوية</small>
      </RouterLink>
      <nav class="nav">
        <RouterLink to="/" exact-active-class="" active-class="" :aria-current="$route.name === 'home' ? 'page' : undefined">
          <AppIcon name="home" />اليوم<span class="navbadge">{{ board.badge || "" }}</span>
        </RouterLink>
        <div class="navsec">الهوية</div>
        <RouterLink to="/projects" :aria-current="$route.name === 'projects' ? 'page' : undefined">
          <AppIcon name="projects" />المشاريع
        </RouterLink>
        <RouterLink to="/decisions" :aria-current="$route.name === 'decisions' ? 'page' : undefined">
          <AppIcon name="decisions" />القرارات
        </RouterLink>
        <div class="navsec">التسليم</div>
        <RouterLink to="/auto" :aria-current="$route.name === 'auto' ? 'page' : undefined">
          <AppIcon name="auto" />الأتمتة
        </RouterLink>
        <RouterLink to="/box" :aria-current="$route.name === 'box' ? 'page' : undefined">
          <AppIcon name="pr" />صندوق المصمّم
        </RouterLink>
      </nav>
      <div class="sidefoot">
        <ThemeToggle />
        <button class="sbtn" type="button" @click="board.togglePolling()">التحديث الدوري: {{ board.polling ? "يعمل" : "إيقاف" }}</button>
      </div>
    </aside>

    <main id="main" class="main rl" tabindex="-1">
      <div class="topbar">
        <div class="rl-bar">
          <span class="rl-live" :class="live"><i></i><span>{{ liveText }}</span></span>
          <span v-if="board.state?.repo" class="rl-runner" :class="{ run: runner?.running }"><span class="dot"></span><span>{{ runner?.running ? `المشغّل يعمل (PID ${runner.pid})` : "المشغّل خامل" }}</span></span>
          <span class="sub">آخر تحديث <span class="rl-num">{{ clock(board.state?.now) }}</span></span>
        </div>
        <button class="btn" type="button" @click="board.tick()">تحديث فوري</button>
      </div>
      <RouterView v-if="board.state" />
      <p v-else class="empty">{{ board.online ? "جارٍ التحميل…" : "تعذّر الاتصال بخادم المنصة." }}</p>
    </main>
  </div>
  <ProjectLog />
</template>
