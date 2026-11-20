import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { fetchRegistry, fetchState, fetchTimeline, post } from "@/api/client";
import type { BoardState, Limits, PostPath, Registry, Reply, Timeline } from "@/types";
import { deliveriesOf } from "@/utils/deliveries";
import { limitOf } from "@/utils/gates";
import { mergeTimelines } from "@/utils/timelines";
import { todos } from "@/utils/todos";

const POLL_MS = 3000;
/** سجل القاعدة يتجدّد مع التحديث الدوري كل خمس دورات (15 ثانية) بعد أن تطلبه صفحة؛ لا يُجلب قبل ذلك. */
export const REGISTRY_EVERY = 5;

/** حالة المنصة: لقطة /api/state بتحديث دوري، والقرارات تُرسل ثم يُعاد التحميل. المسودات تبقى في المكوّنات فلا يمسحها التحديث. */
export const useBoard = defineStore("board", () => {
  const state = ref<BoardState | null>(null);
  const registry = ref<Registry | null>(null);
  const online = ref(true);
  const polling = ref(true);
  const timelines = ref<Record<string, Timeline>>({});
  const logProject = ref<string | null>(null);
  let timer: number | undefined;
  let ticks = 0;

  const todoList = computed(() => (state.value ? todos(state.value, timelines.value) : []));
  const badge = computed(() => todoList.value.length + (state.value?.inbox.length ?? 0));
  const deliveries = computed(() => deliveriesOf(state.value, timelines.value));
  const limit = (kind: keyof Limits): number => limitOf(state.value, kind);

  async function tick(): Promise<void> {
    try {
      state.value = await fetchState();
      online.value = true;
      if (registry.value && ++ticks % REGISTRY_EVERY === 0) void loadRegistry();
      const projects = state.value.sima.map((r) => r.project);
      const entries = await Promise.all(projects.map(async (p) => [p, await fetchTimeline(p).catch(() => null)] as const));
      // جلب فاشل لا يُسقط المشروع: يبقى آخر سجل له بعلامة stale فلا يُستنتج من غيابه أن المدموج ينتظر الدمج
      timelines.value = mergeTimelines(timelines.value, projects, Object.fromEntries(entries));
    } catch {
      online.value = false;
    }
  }

  async function loadRegistry(): Promise<void> {
    try {
      registry.value = await fetchRegistry();
    } catch {
      registry.value = { online: false, runs: 0, gate_decisions: 0, identities: [] };
    }
  }

  function schedule(): void {
    window.clearInterval(timer);
    if (polling.value) timer = window.setInterval(tick, POLL_MS);
  }

  function togglePolling(): void {
    polling.value = !polling.value;
    schedule();
    void tick();
  }

  async function send(path: PostPath, payload: Record<string, unknown>): Promise<Reply> {
    const r = await post(path, payload);
    if (r.ok) window.setTimeout(() => void tick(), 1500);
    return r;
  }

  function jobFor(project: string) {
    return state.value?.jobs.find((j) => j.project === project);
  }

  function openLog(project: string): void {
    logProject.value = project;
  }

  return { state, registry, online, polling, timelines, logProject, todoList, badge, deliveries, limit, tick, loadRegistry, schedule, togglePolling, send, jobFor, openLog };
});
