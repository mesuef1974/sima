<script setup lang="ts">
import { computed } from "vue";
import CardNow from "@/components/CardNow.vue";
import FlowMap from "@/components/FlowMap.vue";
import LayerMap from "@/components/LayerMap.vue";
import RepairMap from "@/components/RepairMap.vue";
import { useBoard } from "@/stores/board";
import { WHO_AR, cardKind, full } from "@/utils/format";

const board = useBoard();
const s = computed(() => board.state!);
const deliveries = computed(() => board.deliveries);
</script>

<template>
  <div class="pagehead"><div><h1>الأتمتة</h1><p class="sub">من الموجز إلى هوية معتمدة: النموذج يرسم، والسكربت يدقّق ويبني، وأنت تقرّر ما تراه بعينك، والمشروع يستلم المخرجات فقط.</p></div></div>
  <LayerMap />
  <FlowMap />
  <RepairMap />
  <section class="card" aria-labelledby="dl-title">
    <div class="cardhead"><h2 id="dl-title">ما بعد التسليم</h2><span class="sub">أين يقف كل إصدار مسلَّم الآن؛ الدمج والنشر بيد مشغّل المشروع المستلم</span></div>
    <div v-if="deliveries.length" class="tblwrap"><table class="rl-tbl">
      <thead><tr><th>المشروع</th><th>الإصدار</th><th>التسليم</th><th>الحال الآن</th><th>ينتظر</th></tr></thead>
      <tbody>
        <tr v-for="d in deliveries" :key="d.run.project">
          <td>{{ d.run.name_ar }} <span class="sub mono">{{ d.run.project }}</span></td>
          <td class="rl-num">{{ d.run.version }}</td>
          <td v-if="d.run.deliver.in_place">في المكان، النقطة <bdi class="mono">{{ d.run.deliver.in_place }}</bdi></td>
          <td v-else-if="d.run.deliver.manual">يدويًّا في <bdi class="mono">{{ d.run.deliver.repo }}</bdi>، النقطة <bdi class="mono">{{ d.run.deliver.manual }}</bdi></td>
          <td v-else>بطاقة <bdi class="mono">{{ d.run.deliver.card }}</bdi> على الفرع <bdi class="mono">{{ d.run.deliver.branch }}</bdi></td>
          <td>{{ d.now?.text ?? "—" }} <a v-if="d.now?.pr_url" :href="d.now.pr_url" target="_blank" rel="noopener">طلب الدمج</a></td>
          <td><span v-if="d.now" class="fm-who" :class="{ o: d.now.who === 'owner', m: d.now.who === 'model', d: d.now.who === 'project' || d.now.who === 'designer' }">{{ WHO_AR[d.now.who] }}</span></td>
        </tr>
      </tbody>
    </table></div>
    <p v-else class="empty">لم يُسلَّم إصدار بعد.</p>
  </section>
  <template v-if="s.repo">
    <section class="card">
      <div class="cardhead"><h2>بطاقة المستودع المربوط الآن</h2><span class="sub mono">{{ s.repo }}</span></div>
      <CardNow v-if="s.cards[0]" :card="s.cards[0]" :now="s.now" />
      <p v-else class="empty">لا بطاقات في الدفتر.</p>
    </section>
    <section class="card">
      <div class="cardhead"><h2>تاريخ البطاقات</h2><span class="sub">الأحدث أوّلًا</span></div>
      <div class="tblwrap" v-if="s.cards.length"><table class="rl-tbl">
        <thead><tr><th>البطاقة</th><th>العنوان</th><th>الحالة</th><th>آخر حركة</th><th>طلب الدمج</th></tr></thead>
        <tbody>
          <tr v-for="c in s.cards" :key="c.id">
            <td class="id">{{ c.id }}</td><td>{{ c.title }}</td>
            <td><span class="rl-st" :class="cardKind(c.state)">{{ c.state_ar }}</span></td>
            <td class="rl-num">{{ full(c.updated) }}</td>
            <td><a v-if="c.url" :href="c.url" target="_blank" rel="noopener">#{{ c.url.split("/").pop() }}</a><template v-else>—</template></td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="empty">—</p>
    </section>
  </template>
</template>
