<script setup lang="ts">
import { ref } from "vue";
import JobLine from "@/components/JobLine.vue";
import { useBoard } from "@/stores/board";
import type { SketchesItem } from "@/types";
import { stamped } from "@/utils/gates";

// بوابة السكتشات (مسار المصمّم الخارجي): صفحة واحدة مرقّمة، يختار المالك منها سكتشًا واحدًا فيُبنى متجهًا كما هو
const props = defineProps<{ item: SketchesItem }>();
const board = useBoard();
const picked = ref<number | null>(null);
const note = ref("");
const busy = ref(false);
const result = ref<{ ok: boolean; text: string } | null>(null);

// «ابنِه متجهًا» أو «طوّره أولًا» (طلب المالك 2026-11-13): الثاني يعيد السكتش إلى المصمّم ليرسم صفحة معالجات حوله قبل البناء
function submit(path: "sketch" | "sketch-develop" = "sketch"): void {
  const it = props.item;
  if (picked.value === null) return;
  busy.value = true;
  void board.send(path, { project: it.project, version: it.version, key: it.key, digest: it.digest, sketch: picked.value, note: note.value })
    .then((r) => { result.value = { ok: r.ok, text: (r.ok ? r.message : r.error) ?? "" }; busy.value = false; });
}

// رفض الصفحة كلها بسبب (قرار المالك 2026-11-13): يعود السبب بنصّه إلى المصمّم الخارجي ليرسم صفحة جديدة
const reason = ref("");
const rejected = ref<{ ok: boolean; text: string } | null>(null);

function reject(): void {
  const it = props.item;
  const why = reason.value.trim();
  if (why.length < 3) {
    rejected.value = { ok: false, text: "اكتب سبب الرفض أولًا؛ يُنقل إلى المصمّم بنصّه." };
    return;
  }
  busy.value = true;
  void board.send("sketch-reject", { project: it.project, version: it.version, key: it.key, digest: it.digest, reason: why })
    .then((r) => { rejected.value = { ok: r.ok, text: (r.ok ? r.message : r.error) ?? "" }; busy.value = false; });
}
</script>

<template>
  <section class="card">
    <div class="cardhead">
      <h2>اختر السكتش: {{ item.project }}</h2>
      <span class="rl-tag m">v{{ item.version }} · {{ item.key }}</span>
      <button class="linkbtn sub" type="button" @click="board.openLog(item.project)">ماذا جرى؟</button>
    </div>
    <JobLine :project="item.project" />
    <p class="ib-after"><b>ماذا بعد؟</b> {{ item.after }}</p>
    <figure class="ws-b">
      <a :href="stamped(item.img, item.digest)" target="_blank" rel="noopener"><img :src="stamped(item.img, item.digest)" :alt="`صفحة سكتشات ${item.project} المرقّمة`" /></a>
      <figcaption v-if="item.source"><span class="sub">{{ item.source }}</span></figcaption>
    </figure>
    <div class="st-grid" role="group" aria-label="السكتشات بأرقامها">
      <button v-for="s in item.sketches" :key="s.id" type="button" class="st-c" :aria-pressed="picked === s.id" @click="picked = s.id">
        <b>{{ s.id }}<span v-if="s.pick" class="rl-st warn"> رشّحه المصمّم</span></b>
        <span class="sub">{{ s.idea }}</span>
      </button>
    </div>
    <div class="st-form">
      <p class="sub" role="status">{{ picked === null ? "لم تختر بعد. ترشيح المصمّم رأي للاطلاع، والاختيار لك." : `اخترت السكتش ${picked}.` }}</p>
      <textarea v-model="note" rows="2" :maxlength="board.limit('note')" :aria-label="`ملاحظة على السكتش المختار في ${item.project}`"
        placeholder="اختياري: ما الذي تريد حفظه أو علاجه في هذا السكتش؟ يُنقل إلى المصمّم بنصّه"></textarea>
      <div class="sk-acts">
        <button type="button" class="btn" :disabled="busy || picked === null" @click="submit()">اختر هذا السكتش وابنِه متجهًا</button>
        <button type="button" class="btn ib-x sk-develop" :disabled="busy || picked === null" @click="submit('sketch-develop')">طوّره أولًا: صفحة سكتشات حول فكرته</button>
      </div>
      <p v-if="result" class="rl-status" :class="result.ok ? 'good' : 'bad'" role="status">{{ result.text }}</p>
    </div>
    <div class="st-form sk-reject">
      <label class="ib-l" :for="`sk-reason-${item.project}`">لا يصلح شيء منها؟ ارفض الصفحة كلها بسبب، فتعود إلى المصمّم ليرسم صفحة جديدة</label>
      <textarea :id="`sk-reason-${item.project}`" v-model="reason" rows="2" :maxlength="board.limit('reason')"
        placeholder="مطلوب: لماذا لا تصلح هذه الصفحة وما الذي تريده بدلها؟ يُنقل إلى المصمّم بنصّه"></textarea>
      <button type="button" class="btn ib-x" :disabled="busy" @click="reject">ارفض الصفحة وأعدها إلى المصمّم</button>
      <p v-if="rejected" class="rl-status" :class="rejected.ok ? 'good' : 'bad'" role="status">{{ rejected.text }}</p>
    </div>
  </section>
</template>
