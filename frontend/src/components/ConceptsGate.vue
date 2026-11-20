<script setup lang="ts">
import { ref } from "vue";
import DecisionActions from "@/components/DecisionActions.vue";
import JobLine from "@/components/JobLine.vue";
import { useBoard } from "@/stores/board";
import type { ConceptsItem } from "@/types";
import { intentProblem, out, verdictKind } from "@/utils/format";
import { stamped } from "@/utils/gates";

const props = defineProps<{ item: ConceptsItem }>();

// مفهوم له درجة حَكَم ولم يجتز العتبة: الاعتماد ممكن لكن بتنبيه صريح عند التأكيد
const belowBar = (c: { score?: number | null; passed?: boolean }): boolean => c.score != null && !c.passed;
const board = useBoard();

function decide(concept: string, verdict: string, reason: string, done: (ok: boolean, msg: string) => void): void {
  const it = props.item;
  void board.send("decide", { project: it.project, version: it.version, key: it.key, digest: it.digest, concept, verdict, reason })
    .then((r) => done(r.ok, (r.ok ? r.message : r.error) ?? ""));
}

// رسم جديد كامل بالمعيار في الوسيط الحالي أو في وسيط يختاره المالك؛ الوسيط لا يتغيّر إلا من هنا
const medium = ref(props.item.medium ?? "");
const why = ref("");
const busy = ref(false);
const note = ref<{ ok: boolean; text: string } | null>(null);
function redraw(): void {
  const it = props.item;
  busy.value = true;
  void board.send("medium", { project: it.project, version: it.version, key: it.key, digest: it.digest, medium: medium.value, reason: why.value })
    .then((r) => { note.value = { ok: r.ok, text: (r.ok ? r.message : r.error) ?? "" }; busy.value = false; });
}
</script>

<template>
  <section class="card">
    <div class="cardhead">
      <h2>قرّر في المفاهيم: {{ item.project }}</h2>
      <span class="rl-tag m">v{{ item.version }} · {{ item.key }}</span>
      <a v-if="item.preview" class="rl-tag" :href="out(item.preview)" target="_blank" rel="noopener">ورقة المعاينة كاملة</a>
      <button class="linkbtn sub" type="button" @click="board.openLog(item.project)">ماذا جرى؟</button>
    </div>
    <JobLine :project="item.project" />
    <p class="ib-after"><b>ماذا بعد؟</b> {{ item.after }}</p>
    <p v-if="item.below_bar" class="rl-status bad">
      لم يبلغ ثلاثة مفاهيم عتبة الاحتراف بعد جولات الصقل الآلي؛ المعروض أفضل ما وصل. ارفض بسبب محدد أو اطلب رسمًا جديدًا.
    </p>
    <div class="ib-grid">
      <article v-for="c in item.concepts" :key="c.id" class="ib-c">
        <div class="ib-img"><img v-if="c.img" :src="stamped(c.img, item.digest)" :alt="`المفهوم ${c.id}`" /><template v-else>بلا رسم</template></div>
        <div class="ib-b">
          <div class="ib-t"><b>{{ c.id }} · {{ c.name }}</b><span v-if="c.last" class="rl-st" :class="verdictKind(c.last)">{{ c.last }}</span></div>
          <span class="sub">{{ c.medium_ar }}<template v-if="c.score != null"> · الحَكَم {{ c.score }}/40
            <span class="rl-st" :class="c.passed ? 'good' : 'warn'">{{ c.passed ? "اجتاز العتبة" : "دون العتبة" }}</span></template></span>
          <p class="ib-s">{{ c.sentence }}</p>
          <DecisionActions :id="`r-${item.project}-${c.id}`" :maxlength="board.limit('decide')" :confirm-label="belowBar(c) ? `تأكيد اعتماد ${c.id} دون العتبة` : `تأكيد اعتماد ${c.id}`"
            :confirm-hint="belowBar(c) ? `تنبيه: درجة هذا المفهوم ${c.score}/40 دون عتبة الاحتراف (${item.bar ?? 30}). اضغط مرة ثانية لاعتماده رغم ذلك.` : 'الاعتماد يبني الحزمة بعد تحقق الاسم. اضغط مرة ثانية للتأكيد.'"
            :check="(r: string) => intentProblem(r, item.concepts.map((x) => x.id), c.id)"
            @decide="(v, r, done) => decide(c.id, v, r, done)" />
        </div>
      </article>
    </div>
    <details v-if="item.mediums?.length" class="ib-redraw">
      <summary>ارسم من جديد أو غيّر الوسيط</summary>
      <p class="sub">يؤرشف المفاهيم المعروضة ويرسم خمسة جديدة بالمعيار، ثم يحكم عليها الحَكَم ويعود إليك بأفضل ثلاثة.</p>
      <label class="sub" :for="`m-${item.project}`">الوسيط</label>
      <select :id="`m-${item.project}`" v-model="medium">
        <option v-for="m in item.mediums" :key="m.id" :value="m.id">{{ m.ar }}{{ m.id === item.medium ? " (الحالي)" : "" }}</option>
      </select>
      <textarea v-model="why" rows="2" :maxlength="board.limit('medium')" :aria-label="`ما تريده من الرسم الجديد في ${item.project}`"
        placeholder="ما الذي تريده تحديدًا؟ يقرؤه الرسّام والحَكَم"></textarea>
      <button type="button" class="btn" :disabled="busy || why.trim().length < 3" @click="redraw">ارسم من جديد</button>
      <p v-if="note" class="rl-status" :class="note.ok ? 'good' : 'bad'" role="status">{{ note.text }}</p>
    </details>
  </section>
</template>
