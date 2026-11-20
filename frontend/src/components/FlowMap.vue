<script setup lang="ts">
import CodeText from "@/components/CodeText.vue";
import { FLOW, LOOPS, WHO } from "@/data/flow";
import type { Who } from "@/data/flow";

// خريطة الخطوات: المراحل بترتيبها، ولكل خطوة من ينفّذها وهل هي قائمة اليوم. بيانات فقط (data/flow.ts).
let i = 0;
const phases = FLOW.map((p) => ({ ...p, steps: p.steps.map((x) => ({ ...x, i: ++i })) }));
const all = FLOW.flatMap((p) => p.steps);
const built = all.filter((x) => x.st === "built").length;
const who = Object.entries(WHO) as [Who, string][];
</script>

<template>
  <section class="card" aria-labelledby="fm-title">
    <div class="cardhead"><h2 id="fm-title">خريطة الخطوات</h2><span class="sub">{{ built }} من {{ all.length }} خطوة قائمة اليوم، والباقي مخطط للمنصة المنتجة</span></div>
    <div class="fm-legend">
      <span><span class="fm-st built">قائم</span> يعمل في الخط الآن</span>
      <span><span class="fm-st planned">مخطط</span> لم يُبنَ بعد</span>
      <span><span v-for="[k, name] in who" :key="k" class="fm-who" :class="k">{{ name }}</span> من ينفّذ</span>
    </div>
    <div class="fm-phases">
      <div v-for="p in phases" :key="p.t" class="fm-phase">
        <h3>{{ p.t }}<small>{{ p.s }}</small></h3>
        <ol class="fm-steps">
          <li v-for="x in p.steps" :key="x.n" class="fm-step" :class="[x.st, { owner: x.who === 'o' }]">
            <span class="fm-n">{{ x.i }}</span>
            <div>
              <b>{{ x.n }}</b>
              <p><CodeText :text="x.d" /></p>
              <span class="fm-tags"><span class="fm-who" :class="x.who">{{ WHO[x.who] }}</span><span class="fm-st" :class="x.st">{{ x.st === "built" ? "قائم" : "مخطط" }}</span></span>
            </div>
          </li>
        </ol>
      </div>
    </div>
    <h3 class="fm-back">ما يعيد العمل إلى الوراء وما يحرسه</h3>
    <div class="fm-loops">
      <div v-for="l in LOOPS" :key="l.t" class="fm-loop" :class="{ g: l.good }"><b>{{ l.t }}:</b> {{ l.d }}</div>
    </div>
  </section>
</template>
