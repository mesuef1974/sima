<script setup lang="ts">
import { computed } from "vue";
import type { Workshop } from "@/types";
import { out } from "@/utils/format";

// ورشة الرسم: ما يُرسم الآن قبل الحَكَم، للاطلاع فقط. القرار يبقى على بطاقة المفاهيم بعد التحكيم، فلا أزرار هنا.
const props = defineProps<{ item: Workshop }>();
const boards = computed(() => props.item.explore ?? []);
const passed = computed(() => props.item.thumbs.filter((t) => t.state === "allowed").length);
// الرسم يتبدّل في أثناء الصقل والمسار ثابت: طابع زمن الملف يفرض إعادة الجلب
const src = (p: string, stamp: number): string => `${out(p)}?v=${stamp}`;
const chip = (state: string): string => (state === "allowed" ? "good" : state === "blocked" ? "bad" : "warn");
</script>

<template>
  <section class="card">
    <div class="cardhead">
      <h2 v-if="item.eval">تقييم الرسّام: {{ item.eval.name }}</h2>
      <h2 v-else-if="item.designer">تسليم المصمّم الخارجي: {{ item.project }}</h2>
      <h2 v-else>ما يُرسم الآن: {{ item.project }}</h2>
      <span class="rl-tag m">{{ item.eval ? item.eval.run : `v${item.version}` }}</span>
      <span v-if="item.stage" class="rl-tag">{{ item.stage }}</span>
    </div>
    <p v-if="item.eval" class="ib-after"><b>للاطلاع فقط.</b> حالة خيالية تقيس الرسّام وليست مشروعًا: لا قرار عليها، ولا تدخل حزمة ولا تسليمًا.</p>
    <p v-else-if="item.designer" class="ib-after"><b>للاطلاع فقط.</b> المتجه الذي سلّمه المصمّم الخارجي للسكتش الذي اخترته، كما هو. ما يردّه الفحص يعود إليه بسببه دون سؤالك؛ قرارك يُطلب على الدليل.</p>
    <p v-else class="ib-after"><b>للاطلاع فقط.</b> هذه مسودات الورشة قبل الحَكَم وقد تتغيّر؛ قرارك يُطلب على أفضل ثلاثة بعد التحكيم.</p>
    <template v-if="boards.length">
      <h3 class="rl-h3">لوحات استكشاف الاتجاهات <span class="sub">تجربة للمقارنة، ليست مخرجًا معتمدًا</span></h3>
      <p v-if="boards[0]?.source" class="ib-s">{{ boards[0].source }}</p>
      <div class="ws-boards">
        <figure v-for="b in boards" :key="b.id" class="ws-b">
          <a :href="src(b.img, b.stamp)" target="_blank" rel="noopener"><img :src="src(b.img, b.stamp)" :alt="`لوحة الاتجاه ${b.id}: ${b.name}`" loading="lazy" /></a>
          <figcaption>
            <span class="ib-t"><b>{{ b.id }} · {{ b.name }}</b></span>
            <span>{{ b.detail }}</span>
            <span v-if="b.misread" class="sub">أقرب قراءة خاطئة: {{ b.misread }}</span>
          </figcaption>
        </figure>
      </div>
    </template>
    <template v-if="item.concepts.length">
      <h3 class="rl-h3">المفاهيم <span class="sub">{{ item.eval ? "التقييم يقف عند أول حكم، بلا صقل بعده" : item.designer ? "المستلم من المصمّم، بلا تعديل" : "تُنقد وتُصقل قبل الحَكَم" }}</span></h3>
      <div class="ib-grid">
        <article v-for="c in item.concepts" :key="c.id" class="ib-c">
          <div class="ib-img"><img v-if="c.img" :src="src(c.img, c.stamp)" :alt="`مسودة المفهوم ${c.id}`" /><template v-else>يُرسم الآن</template></div>
          <div class="ib-b">
            <div class="ib-t"><b>{{ c.id }} · {{ c.name }}</b><span v-if="c.idea" class="sub">من الفكرة {{ c.idea }}</span></div>
            <p class="ib-s">{{ c.sentence }}</p>
            <p v-if="c.seen" class="ib-s"><span class="rl-st" :class="c.misread ? 'bad' : 'good'">القارئ الأعمى</span> {{ c.seen }}</p>
            <p v-if="c.score !== undefined" class="ib-s"><span class="rl-st" :class="c.passed ? 'good' : 'bad'">الحَكَم</span> {{ c.score }} من 40 · {{ c.passed ? "مجتاز" : "دون العتبة" }}</p>
          </div>
        </article>
      </div>
    </template>
    <details v-if="item.thumbs.length" class="ws-thumbs" :open="!item.concepts.length">
      <summary>مصغّرات الأفكار <span class="sub">{{ passed }} مجتازة من {{ item.thumbs.length }}</span></summary>
      <div class="ws-grid">
        <figure v-for="t in item.thumbs" :key="t.id" class="ws-t" :class="{ off: t.state === 'blocked' }">
          <div class="ib-img"><img :src="src(t.img, t.stamp)" :alt="`مصغّرة الفكرة ${t.id}`" /></div>
          <figcaption>
            <span class="ib-t"><b>{{ t.id }}</b><span class="rl-st" :class="chip(t.state)">{{ t.state_ar }}</span></span>
            <span>{{ t.sentence }}</span>
            <span v-if="t.seen" class="sub">{{ t.seen }}</span>
          </figcaption>
        </figure>
      </div>
    </details>
  </section>
</template>
