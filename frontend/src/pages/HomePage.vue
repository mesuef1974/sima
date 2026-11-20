<script setup lang="ts">
import { computed } from "vue";
import AppIcon from "@/components/AppIcon.vue";
import CardNow from "@/components/CardNow.vue";
import ConceptsGate from "@/components/ConceptsGate.vue";
import IdentityGate from "@/components/IdentityGate.vue";
import JobLine from "@/components/JobLine.vue";
import NameCheckGate from "@/components/NameCheckGate.vue";
import ProgressStrip from "@/components/ProgressStrip.vue";
import SketchGate from "@/components/SketchGate.vue";
import StalledGate from "@/components/StalledGate.vue";
import StyleGate from "@/components/StyleGate.vue";
import WorkshopPanel from "@/components/WorkshopPanel.vue";
import { useBoard } from "@/stores/board";
import { awaitingDelivery } from "@/utils/deliveries";
import { gateKey } from "@/utils/gates";

const board = useBoard();
const s = computed(() => board.state!);
// حزم تنتظر التسليم فعلًا: ما سُلّم أو دُمج لا يُعدّ هنا
const packages = computed(() => awaitingDelivery(s.value).length);
// التسليم يُعدّ من إصدارات سِمة وسجل كل مشروع لا من دفتر مستودع واحد: المنصة تعمل بلا مستودع مربوط، فعدّ البطاقات كان صفرًا دائمًا.
const landed = computed(() => board.deliveries.filter((d) => d.landed).length);
// تسليم لم يصل سجل مشروعه لا يُحكم عليه: لا يُعدّ منتظرًا ولا مدموجًا، ويُذكر أن حاله غير معروف
const pending = computed(() => board.deliveries.filter((d) => d.known && !d.landed));
const unknown = computed(() => board.deliveries.filter((d) => !d.known).length);
const mine = computed(() => pending.value.filter((d) => d.now?.who === "owner").length);
const pendingNote = computed(() => {
  const base = mine.value ? `${mine.value} منها تنتظر اعتمادك على الطلب` : pending.value.length ? "عند مشغّل المشروع" : unknown.value ? "" : "لا شيء معلّق";
  const miss = unknown.value ? `حال ${unknown.value} غير معروف الآن` : "";
  return [base, miss].filter(Boolean).join("؛ ");
});
const loneJobs = computed(() => s.value.jobs.filter((j) => !s.value.inbox.some((i) => i.project === j.project)));
</script>

<template>
  <div class="pagehead"><div><h1>اليوم</h1><p class="sub">ما ينتظر قرارك، وحال المشاريع والأتمتة.</p></div></div>
  <div class="tiles">
    <div class="tile"><div class="k">المشاريع</div><div class="v brand">{{ s.sima.length }}</div><div class="s">في out/</div></div>
    <div class="tile"><div class="k">حزم معتمدة</div><div class="v good">{{ packages }}</div><div class="s">جاهزة للتسليم</div></div>
    <div class="tile"><div class="k">إصدارات مسلَّمة</div><div class="v">{{ board.deliveries.length }}</div><div class="s">{{ landed }} منها مدموجة</div></div>
    <div class="tile"><div class="k">تنتظر الدمج</div><div class="v">{{ pending.length }}</div><div class="s">{{ pendingNote }}</div></div>
  </div>
  <ProgressStrip />

  <template v-for="it in s.inbox" :key="gateKey(it)">
    <IdentityGate v-if="it.kind === 'identity'" :item="it" />
    <ConceptsGate v-else-if="it.kind === 'concepts'" :item="it" />
    <StyleGate v-else-if="it.kind === 'style'" :item="it" />
    <SketchGate v-else-if="it.kind === 'sketches'" :item="it" />
    <StalledGate v-else-if="it.kind === 'stalled'" :item="it" />
    <NameCheckGate v-else :item="it" />
  </template>

  <WorkshopPanel v-for="w in s.workshop ?? []" :key="`ws-${w.eval?.run ?? ''}-${w.project}-${w.version}`" :item="w" />

  <section v-for="j in loneJobs" :key="j.project" class="card">
    <div class="cardhead"><h2>تشغيل {{ j.project }}</h2></div>
    <JobLine :project="j.project" />
  </section>

  <section class="card">
    <div class="cardhead"><h2>ينتظر قرارك أيضًا</h2><span class="sub">{{ board.todoList.length ? `${board.todoList.length} بنود` : "لا شيء الآن" }}</span></div>
    <ul v-if="board.todoList.length" class="todo">
      <li v-for="x in board.todoList" :key="x.title">
        <span class="ic">
          <AppIcon :name="x.ic === 'pr' ? 'pr' : x.ic === 'warn' ? 'warn' : 'search'" />
        </span>
        <div><b>{{ x.title }}</b><span class="sub">{{ x.body }} <code v-if="x.code">{{ x.code }}</code></span></div>
        <a v-if="x.href" class="btn" :class="{ pri: x.external }" :href="x.href" v-bind="x.external ? { target: '_blank', rel: 'noopener' } : {}">{{ x.cta }}</a>
      </li>
    </ul>
    <p v-else class="empty">كل شيء يسير وحده.</p>
  </section>

  <section v-if="s.cards[0]" class="card">
    <div class="cardhead"><h2>البطاقة الآن</h2><RouterLink class="sub" to="/auto">التفاصيل في الأتمتة</RouterLink></div>
    <CardNow :card="s.cards[0]" :now="s.now" compact />
  </section>
</template>
