<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useBoard } from "@/stores/board";
import { full } from "@/utils/format";
import { ownerDecisions } from "@/utils/timelines";

const board = useBoard();
// كل قرار للمالك في كل مشروع من سجله: المفاهيم وتبديل الوسيط والطابع والسكتش وردّ المتجه وبوابات الهوية وتحقق الاسم
const rows = computed(() => ownerDecisions(board.state, board.timelines));
const reg = computed(() => board.registry);
onMounted(() => void board.loadRegistry());
</script>

<template>
  <div class="pagehead"><div><h1>القرارات</h1><p class="sub">سجلّ قرارات المالك في كل مشروع، الأحدث أوّلًا. رفض مفهوم بسبب يعيد رسمه في الوسيط نفسه ثم يعود إلى الحَكَم المستقل، والوسيط لا يتغيّر إلا باختيارك.</p></div></div>

  <section class="card">
    <div class="cardhead">
      <h2>الهويات المعتمدة في قاعدة سِمة</h2>
      <span v-if="reg?.online" class="rl-tag good">القاعدة متصلة</span>
      <span v-else-if="reg" class="rl-tag bad">القاعدة متوقفة</span>
      <button class="linkbtn sub" type="button" @click="board.loadRegistry()">تحديث</button>
    </div>
    <p v-if="!reg" class="empty">جارٍ التحميل…</p>
    <p v-else-if="!reg.online" class="db-off">لا اتصال بقاعدة سِمة. شغّلها بـ <code>uv run sima db start</code> ثم <code>uv run sima db sync</code>.</p>
    <template v-else>
      <p class="sub">{{ reg.runs }} إصدار و{{ reg.gate_decisions }} قرار بوابة مسجّلة. تُحفظ الهوية هنا بعد اعتمادك للدليل فقط.</p>
      <div class="tblwrap" v-if="reg.identities.length"><table class="rl-tbl">
        <thead><tr><th>المشروع</th><th>الإصدار</th><th>الاتجاه</th><th>الألوان</th><th>الفحوص</th><th>الأصول</th><th>اعتُمد</th></tr></thead>
        <tbody>
          <tr v-for="i in reg.identities" :key="`${i.project}-${i.version}`">
            <td>{{ i.name_ar }}</td><td class="id">v{{ i.version }}</td><td>{{ i.direction }} · {{ i.direction_name }}</td>
            <td><span class="ib-sw"><i v-for="(c, k) in i.colors" :key="k" :style="{ background: c }" :title="`${k} ${c}`"></i></span></td>
            <td class="rl-num">{{ i.checks }}</td><td class="rl-num">{{ i.assets }}</td><td class="rl-num">{{ full(i.approved_at) }}</td>
          </tr>
        </tbody>
      </table></div>
      <p v-else class="empty">لا هوية معتمدة بعد.</p>
    </template>
  </section>

  <section class="card">
    <div class="cardhead"><h2>قرارات المالك</h2><span class="sub">من سجل كل مشروع لإصداره الأخير</span></div>
    <div class="tblwrap" v-if="rows.length"><table class="rl-tbl">
      <thead><tr><th>الوقت</th><th>المشروع</th><th>الإصدار</th><th>القرار</th></tr></thead>
      <tbody>
        <tr v-for="(d, i) in rows" :key="i">
          <td class="rl-num">{{ full(d.at) }}</td><td>{{ d.name }}</td><td class="rl-num">{{ d.version }}</td><td>{{ d.text }}</td>
        </tr>
      </tbody>
    </table></div>
    <p v-else class="empty">لا قرارات بعد.</p>
  </section>
</template>
