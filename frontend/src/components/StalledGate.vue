<script setup lang="ts">
import { ref } from "vue";
import JobLine from "@/components/JobLine.vue";
import ResumeButton from "@/components/ResumeButton.vue";
import { useBoard } from "@/stores/board";
import type { StalledItem } from "@/types";

// الخط وقف عند المالك ولا قرار له في بطاقة (اتجاه معتمد يلزمه إصلاح في بيانه مثلًا)، أو تغيّر المعروض بعد وقوفه.
// كان الإصدار يعلق هكذا بلا أثر في «اليوم»؛ الآن يُعرض ما وقف عنده الخط بنصّه ويُستأنف بزر.
const props = defineProps<{ item: StalledItem }>();
const board = useBoard();

// نفدت جولات تصحيح المصمّم الخارجي (designer_fix): للمالك أن يردّ المتجه إلى المصمّم بسبب بنصّه، كردّ الشعار من بطاقة الدليل
const why = ref("");
const busy = ref(false);
const returned = ref<{ ok: boolean; text: string } | null>(null);

function returnVector(): void {
  const it = props.item;
  const reason = why.value.trim();
  if (reason.length < 3) {
    returned.value = { ok: false, text: "اكتب سبب ردّ المتجه أولًا؛ يُنقل إلى المصمّم بنصّه." };
    return;
  }
  busy.value = true;
  void board.send("vector-return", { project: it.project, version: it.version, key: it.key, digest: it.digest, reason })
    .then((r) => { returned.value = { ok: r.ok, text: (r.ok ? r.message : r.error) ?? "" }; busy.value = false; });
}
</script>

<template>
  <section class="card">
    <div class="cardhead">
      <h2>{{ item.title }}: {{ item.project }}</h2>
      <span class="rl-tag m">v{{ item.version }} · {{ item.key }}</span>
      <button class="linkbtn sub" type="button" @click="board.openLog(item.project)">ماذا جرى؟</button>
    </div>
    <JobLine v-if="board.jobFor(item.project)?.state === 'running'" :project="item.project" />
    <p class="rl-stalled" role="status">{{ item.message }}</p>
    <p class="ib-after"><b>ماذا بعد؟</b> {{ item.after }}</p>
    <ResumeButton :project="item.project" />
    <div v-if="item.gate === 'designer_fix'" class="st-form sk-reject ib-vector">
      <label class="ib-l" :for="`fix-reason-${item.project}`">نفدت جولات تصحيح المصمّم ولم يمرّ المتجه بالفحص. ردّه إليه بسبب، فيبنيه من جديد</label>
      <textarea :id="`fix-reason-${item.project}`" v-model="why" rows="2" :maxlength="board.limit('reason')"
        placeholder="مطلوب: ما الذي يجب أن يتغيّر في المتجه؟ يُنقل إلى المصمّم بنصّه"></textarea>
      <button type="button" class="btn ib-x" :disabled="busy" @click="returnVector">ردّ المتجه إلى المصمّم</button>
      <p v-if="returned" class="rl-status" :class="returned.ok ? 'good' : 'bad'" role="status">{{ returned.text }}</p>
    </div>
  </section>
</template>
