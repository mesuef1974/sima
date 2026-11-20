<script setup lang="ts">
import { ref } from "vue";
import JobLine from "@/components/JobLine.vue";
import { useBoard } from "@/stores/board";
import type { NameItem } from "@/types";
import { out } from "@/utils/format";

const props = defineProps<{ item: NameItem }>();
const board = useBoard();
const sources = ref<string[]>([]);
const status = ref("");
const note = ref(props.item.note ?? "");
const msg = ref("");
const kind = ref("");
const busy = ref(false);

async function submit(): Promise<void> {
  if (!status.value) {
    kind.value = "bad";
    msg.value = "اختر النتيجة.";
    return;
  }
  busy.value = true;
  kind.value = "";
  msg.value = "جارٍ التسجيل…";
  const it = props.item;
  const r = await board.send("name-check", { project: it.project, version: it.version, key: it.key, status: status.value, sources: sources.value, note: note.value });
  busy.value = false;
  kind.value = r.ok ? "good" : "bad";
  msg.value = (r.ok ? r.message : r.error) ?? "";
}
</script>

<template>
  <section class="card">
    <div class="cardhead">
      <h2>تحقق من توافر الاسم: {{ item.project }}</h2>
      <span class="rl-tag m">v{{ item.version }} · {{ item.key }}</span>
      <a v-if="item.preview" class="rl-tag" :href="out(item.preview)" target="_blank" rel="noopener">ورقة المعاينة كاملة</a>
      <button class="linkbtn sub" type="button" @click="board.openLog(item.project)">ماذا جرى؟</button>
    </div>
    <JobLine :project="item.project" />
    <p class="ib-after"><b>ماذا بعد؟</b> {{ item.after }}</p>
    <form class="ib-n" @submit.prevent="submit">
      <p class="sub">المفهوم المعتمد {{ item.concept }}. افحص الاسم «{{ item.name }}» في المصادر بنفسك، ثم علّم ما فحصته. الأداة لا تتصل بالشبكة.</p>
      <ul class="ib-src">
        <li v-for="x in item.sources" :key="x.key">
          <label><input v-model="sources" type="checkbox" :value="x.key" /> <span>{{ x.label }}</span></label>
          <a :href="x.url" target="_blank" rel="noopener noreferrer">افتح</a>
          <span v-if="x.hint" class="sub"> {{ x.hint }}</span>
        </li>
      </ul>
      <fieldset class="ib-st">
        <legend>النتيجة</legend>
        <label><input v-model="status" type="radio" value="clear" /> متاح</label>
        <label><input v-model="status" type="radio" value="conflict" /> متعارض</label>
      </fieldset>
      <label class="ib-l" :for="`n-${item.project}`">ملاحظة</label>
      <textarea :id="`n-${item.project}`" v-model="note" rows="2" :maxlength="board.limit('note')"></textarea>
      <div class="ib-a"><button class="btn pri" type="submit" :disabled="busy">سجّل النتيجة</button></div>
      <div class="ib-m" :class="kind" role="status">{{ msg }}</div>
    </form>
  </section>
</template>
