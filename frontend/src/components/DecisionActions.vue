<script setup lang="ts">
import { ref } from "vue";

// أزرار القرار الثلاثة مع سبب إلزامي للتعديل والرفض، وتأكيد ثانٍ للاعتماد.
const props = withDefaults(defineProps<{ id: string; maxlength?: number; confirmLabel?: string; confirmHint?: string; check?: (reason: string) => string }>(), {
  maxlength: 500, confirmLabel: "تأكيد الاعتماد", confirmHint: "اضغط مرة ثانية للتأكيد.", check: () => "",
});
const emit = defineEmits<{ decide: [verdict: string, reason: string, done: (ok: boolean, msg: string) => void] }>();

const reason = ref("");
const confirming = ref(false);
const busy = ref(false);
const msg = ref("");
const kind = ref("");

function act(verdict: "approved" | "revise" | "rejected"): void {
  const r = reason.value.trim();
  if (verdict !== "approved" && r.length < 3) return say("bad", "اكتب السبب أولًا؛ يقرؤه النموذج في الجولة التالية.");
  if (verdict === "approved") {
    const problem = props.check(r);
    if (problem) return say("bad", problem);
    if (!confirming.value) {
      confirming.value = true;
      return say("", props.confirmHint);
    }
  }
  busy.value = true;
  say("", "جارٍ التسجيل…");
  emit("decide", verdict, r, (ok, m) => {
    busy.value = false;
    confirming.value = false;
    if (ok) reason.value = "";
    say(ok ? "good" : "bad", m);
  });
}

function say(k: string, m: string): void {
  kind.value = k;
  msg.value = m;
}
</script>

<template>
  <label class="ib-l" :for="id">السبب أو الملاحظة</label>
  <textarea :id="id" v-model="reason" rows="2" :maxlength="maxlength" placeholder="مطلوب للتعديل والرفض"></textarea>
  <div class="ib-a">
    <button class="btn pri" type="button" :disabled="busy" @click="act('approved')">{{ confirming ? confirmLabel : "اعتمد" }}</button>
    <button class="btn" type="button" :disabled="busy" @click="act('revise')">اطلب تعديلًا</button>
    <button class="btn ib-x" type="button" :disabled="busy" @click="act('rejected')">ارفض</button>
  </div>
  <div class="ib-m" :class="kind" role="status">{{ msg }}</div>
</template>
