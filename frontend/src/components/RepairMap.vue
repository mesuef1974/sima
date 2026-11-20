<script setup lang="ts">
import CodeText from "@/components/CodeText.vue";
import { REPAIR } from "@/data/repair";

// مراحل إصلاح مراجعة الأتمتة: لكل مرحلة إيداعها وبنودها وما لم يُتحقق منه. بيانات فقط (data/repair.ts).
</script>

<template>
  <section class="card" aria-labelledby="rp-title">
    <div class="cardhead"><h2 id="rp-title">مراحل إصلاح المراجعة</h2><span class="sub">{{ REPAIR.length }} مراحل أُودعت محليًا على main بلا push</span></div>
    <div class="fm-phases">
      <div v-for="r in REPAIR" :key="r.n" class="fm-phase">
        <h3>{{ r.t }}<small class="mono">{{ r.items }}</small></h3>
        <div class="fm-step built">
          <span class="fm-n">{{ r.n }}</span>
          <div>
            <p><CodeText :text="r.d" /></p>
            <p v-if="r.note" class="rp-note"><b>ملاحظة:</b> <CodeText :text="r.note" /></p>
            <span class="fm-tags"><span class="fm-st built">أُودعت</span><span class="fm-who s mono">{{ r.commit }}</span></span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
