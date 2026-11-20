<script setup lang="ts">
import { computed, ref } from "vue";
import JobLine from "@/components/JobLine.vue";
import { useBoard } from "@/stores/board";
import type { StyleItem } from "@/types";
import { stamped } from "@/utils/gates";

// بوابة الطابع البصري: يختار المالك أسلوبًا أو اثنين قبل الرسم، فيتقيّد بهما الرسّام والحَكَم
const props = defineProps<{ item: StyleItem }>();
const board = useBoard();
const picked = ref<string[]>([]);
const note = ref("");
const busy = ref(false);
const result = ref<{ ok: boolean; text: string } | null>(null);
const full = computed(() => picked.value.length >= props.item.max);

function toggle(id: string): void {
  picked.value = picked.value.includes(id) ? picked.value.filter((x) => x !== id) : full.value ? picked.value : [...picked.value, id];
}

function submit(): void {
  const it = props.item;
  busy.value = true;
  void board.send("style", { project: it.project, version: it.version, key: it.key, digest: it.digest, styles: picked.value, note: note.value })
    .then((r) => { result.value = { ok: r.ok, text: (r.ok ? r.message : r.error) ?? "" }; busy.value = false; });
}
</script>

<template>
  <section class="card">
    <div class="cardhead">
      <h2>اختر الطابع البصري: {{ item.project }}</h2>
      <span class="rl-tag m">v{{ item.version }} · {{ item.key }}</span>
      <button class="linkbtn sub" type="button" @click="board.openLog(item.project)">ماذا جرى؟</button>
    </div>
    <JobLine :project="item.project" />
    <p class="ib-after"><b>ماذا بعد؟</b> {{ item.after }}</p>
    <div class="st-grid">
      <button v-for="s in item.styles" :key="s.id" type="button" class="st-c" :aria-pressed="picked.includes(s.id)"
        :disabled="full && !picked.includes(s.id)" @click="toggle(s.id)">
        <span class="st-img"><img :src="stamped(s.img, item.digest)" :alt="`عينة الأسلوب ${s.name}`" /></span>
        <b>{{ s.id }} · {{ s.name }}</b>
        <span class="sub">{{ s.principle }}</span>
      </button>
    </div>
    <div class="st-form">
      <p class="sub" role="status">اخترت {{ picked.length }} من {{ item.max }}.</p>
      <textarea v-model="note" rows="2" :maxlength="board.limit('note')" :aria-label="`ملاحظة على الطابع في ${item.project}`"
        placeholder="اختياري: ما الذي أعجبك تحديدًا أو ما تريد تجنّبه؟ يقرؤه الرسّام والحَكَم"></textarea>
      <button type="button" class="btn" :disabled="busy || picked.length === 0" @click="submit">اعتمد الطابع وارسم به</button>
      <p v-if="result" class="rl-status" :class="result.ok ? 'good' : 'bad'" role="status">{{ result.text }}</p>
    </div>
  </section>
</template>
