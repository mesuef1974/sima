<script setup lang="ts">
import { computed } from "vue";
import RunTrack from "@/components/RunTrack.vue";
import { useBoard } from "@/stores/board";
import { full, out } from "@/utils/format";
import { trackOf } from "@/utils/timelines";

const board = useBoard();
const runs = computed(() => board.state!.sima);

const ncKind = (s: string) => (s === "clear" ? "good" : s === "conflict" ? "bad" : "warn");
</script>

<template>
  <div class="pagehead"><div><h1>المشاريع</h1><p class="sub">كل موجز وإصداره الأخير ومراحله.</p></div></div>
  <p v-if="!runs.length" class="empty">لا مشاريع بعد. ابدأ بـ <code>uv run sima run briefs/&lt;project&gt;.yaml</code></p>
  <section v-for="r in runs" :key="r.project" class="card">
    <div class="cardhead">
      <h2>{{ r.name_ar }}</h2>
      <span class="rl-tag m">{{ r.project }} · {{ r.version }}</span>
      <span v-if="r.closed" class="rl-tag good">مكتمل</span>
      <button class="btn" type="button" @click="board.openLog(r.project)">ماذا جرى؟</button>
    </div>
    <p v-if="board.timelines[r.project]" class="ib-after"><b>الآن:</b> {{ board.timelines[r.project].now.text }}</p>
    <div class="proj">
      <div class="markbox" :class="{ empty: !r.mark }">
        <img v-if="r.mark" :src="out(r.mark)" :alt="`العلامة المعتمدة لـ ${r.name_ar}`" /><template v-else>لا علامة معتمدة بعد</template>
      </div>
      <div>
        <template v-if="r.concept.id">
          <p class="rl-prob">{{ r.concept.name }} <span class="sub">({{ r.concept.id }} · {{ r.concept.medium_ar }})</span></p>
          <p class="sub">{{ r.concept.sentence }}</p>
        </template>
        <dl class="kv spaced">
          <dt>مفتاح التشغيل</dt><dd class="mono">{{ r.key }}</dd>
          <dt>توافر الاسم</dt>
          <dd>
            <span class="rl-st" :class="ncKind(r.name_check.status)">{{ r.name_check.status_ar }}</span>
            <span v-if="r.name_check.at" class="sub"> {{ full(r.name_check.at) }}</span>
            <div v-if="r.name_check.note" class="sub">{{ r.name_check.note }}</div>
          </dd>
          <dt>درجة الحَكَم</dt>
          <dd>
            <template v-if="r.judge?.total != null">
              {{ r.judge.total }}/40 <span class="rl-st" :class="r.judge.below ? 'warn' : 'good'">{{ r.judge.below ? `دون العتبة (${r.judge.bar})` : "اجتاز العتبة" }}</span>
            </template>
            <template v-else>غير متوفرة</template>
          </dd>
          <dt>كلفة النموذج</dt>
          <dd v-if="r.cost">
            <span class="rl-num">{{ r.cost.usd.toFixed(2) }}$</span> في {{ r.cost.calls }} استدعاء
            <div v-if="r.cost.unknown" class="sub">{{ r.cost.unknown }} منها قُطعت فلم تُبلَّغ كلفتها، فحُسبت بحدّها الأعلى المحجوز.</div>
            <span v-if="r.cost.level !== 'ok'" class="rl-st" :class="r.cost.level === 'over' ? 'bad' : 'warn'">
              {{ r.cost.level === "over" ? "تجاوز مرجع الإصدار" : "قارب مرجع الإصدار" }} ({{ r.cost.ref }}$)
            </span>
          </dd>
          <dt>التسليم</dt>
          <dd><template v-if="r.deliver.card">بطاقة <span class="mono">{{ r.deliver.card }}</span> على <span class="mono">{{ r.deliver.branch }}</span></template><template v-else-if="r.deliver.in_place">مطبّق في مستودع سِمة نفسه (النقطة <span class="mono">{{ r.deliver.in_place }}</span>)</template><template v-else-if="r.deliver.manual">طبّقته جلسة المشروع يدويًّا في <span class="mono">{{ r.deliver.repo }}</span> (النقطة <span class="mono">{{ r.deliver.manual }}</span>)</template><template v-else>لم يُسلَّم</template></dd>
        </dl>
        <div class="files">
          <a v-if="r.preview" class="btn pri" :href="out(r.preview)" target="_blank" rel="noopener">ورقة المعاينة</a>
          <a v-for="f in r.files" :key="f.href" :href="out(f.href)" target="_blank" rel="noopener">{{ f.name }}</a>
        </div>
      </div>
    </div>
    <RunTrack v-if="r.steps.length" v-bind="trackOf(r.steps)" :chip-text="r.version" />
  </section>
</template>
