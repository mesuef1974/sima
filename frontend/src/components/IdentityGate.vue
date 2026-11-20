<script setup lang="ts">
import { computed, ref } from "vue";
import DecisionActions from "@/components/DecisionActions.vue";
import JobLine from "@/components/JobLine.vue";
import { useBoard } from "@/stores/board";
import type { IdentityItem } from "@/types";
import { hm, intentProblem, out } from "@/utils/format";

// بوابات الهوية الثلاث: المنصة الاستراتيجية، ثم اختيار اتجاه، ثم دليل الهوية؛ القرار مربوط ببصمة المعروض.
const props = defineProps<{ item: IdentityItem }>();
const board = useBoard();
const option = ref("");
const v = computed(() => props.item.visuals ?? {});
// اتجاه واحد (اعتماد خارجي أو مسار المصمّم الخارجي): اللوحة لا تُسمّى «الثلاثة» وهي تعرض واحدًا.
const single = computed(() => (v.value.options?.length ?? 0) === 1);
const VERD: Record<string, string> = { approved: "اعتُمد", revise: "طُلب تعديل", rejected: "رُفض" };

const check = (reason: string): string => {
  const ids = (props.item.gate === "directions" ? props.item.options : v.value.options)?.map((o) => o.id) ?? [];
  return intentProblem(reason, ids, option.value) || (props.item.gate === "directions" && !option.value ? "اختر اتجاهًا أولًا." : "");
};
// في بطاقة المنصة: اختيار الاتجاه اختياري؛ إن اختير سُجّل مع الاعتماد فيمضي الخط حتى الدليل.
const combined = computed(() => props.item.gate === "strategy" && Boolean(props.item.directions_digest) && Boolean(v.value.options?.length));
const confirmHint = computed(() =>
  props.item.gate === "strategy" && option.value
    ? `يُعتمد مع المنصة الاتجاه ${option.value}، ويمضي الخط حتى دليل الهوية. اضغط مرة ثانية للتأكيد.`
    : combined.value
      ? "لم تختر اتجاهًا: يتوقف الخط بعد الاعتماد عند بوابة الاتجاهات. اضغط مرة ثانية للتأكيد."
      : "اضغط مرة ثانية للتأكيد.");

function decide(verdict: string, reason: string, done: (ok: boolean, msg: string) => void): void {
  const it = props.item;
  void board.send("identity", { project: it.project, version: it.version, key: it.key, gate: it.gate, digest: it.digest, verdict, option: option.value,
    option_digest: it.gate === "strategy" && option.value ? it.directions_digest : "", reason })
    .then((r) => done(r.ok, (r.ok ? r.message : r.error) ?? ""));
}

// ردّ المتجه (قرار المالك 2026-11-13): الشعار في الدليل لا يطابق السكتش المختار، فيعود السكتش نفسه إلى المصمّم الخارجي
// بسبب المالك بنصّه. ليس «طلب تعديل»: ذاك يذهب إلى نموذج الخط الذي لا يملك الشعار.
const why = ref("");
const busy = ref(false);
const returned = ref<{ ok: boolean; text: string } | null>(null);

function returnVector(): void {
  const it = props.item;
  const reason = why.value.trim();
  if (reason.length < 3) {
    returned.value = { ok: false, text: "اكتب سبب ردّ الشعار أولًا؛ يُنقل إلى المصمّم بنصّه." };
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
      <h2>{{ item.gate_ar }}: {{ item.project }}</h2>
      <span class="rl-tag m">v{{ item.version }} · {{ item.key }}</span>
      <button class="linkbtn sub" type="button" @click="board.openLog(item.project)">ماذا جرى؟</button>
    </div>
    <JobLine :project="item.project" />
    <div class="ib-look">
      <figure v-if="v.mark" class="ib-mark"><img :src="out(v.mark)" alt="العلامة المعتمدة" /><figcaption class="sub">العلامة المعتمدة</figcaption></figure>
      <div class="ib-links">
        <a v-if="v.reveal" class="btn pri ib-reveal" :href="out(v.reveal)" target="_blank" rel="noopener">شاهد عرض الهوية</a>
        <a v-if="v.preview" class="btn" :href="out(v.preview)" target="_blank" rel="noopener">ورقة معاينة العلامة</a>
        <a v-if="v.board" class="btn" :href="out(v.board)" target="_blank" rel="noopener">{{ single ? "لوحة الاتجاه المعتمد" : "لوحة الاتجاهات الثلاثة" }}</a>
        <a v-if="item.book" class="btn pri" :href="out(item.book)" target="_blank" rel="noopener">دليل الهوية</a>
      </div>
    </div>

    <p v-if="item.reply && item.gate !== 'book'" class="ib-after" role="status">
      <b>جواب الخط على ملاحظتك:</b> «{{ item.reply.note }}»<br />
      {{ item.reply.text || "لم يكتب النموذج جوابًا." }}<br />
      <span class="sub">لم يتغيّر شيء في المعروض، فالقرار لك من جديد: اعتمده، أو اطلب تعديلًا آخر بسبب.</span>
    </p>

    <template v-if="item.gate === 'strategy' && item.strategy">
      <dl class="ib-dl">
        <dt>التموضع</dt><dd>{{ item.strategy.positioning }}</dd>
        <dt>الوعد</dt><dd>{{ item.strategy.promise }}</dd>
        <dt>الشعار اللفظي</dt><dd><b>{{ item.strategy.tagline }}</b></dd>
      </dl>
      <div class="ib-cols">
        <div>
          <h3 class="rl-h3">الشخصية</h3>
          <ul class="ib-ul"><li v-for="t in item.strategy.personality" :key="t.trait"><b>{{ t.trait }}:</b> {{ t.means }} <span class="sub">(ليس: {{ t.not }})</span></li></ul>
        </div>
        <div>
          <h3 class="rl-h3">نقول</h3>
          <ul class="ib-ul"><li v-for="x in item.strategy.voice_do" :key="x">{{ x }}</li></ul>
          <h3 class="rl-h3">لا نقول</h3>
          <ul class="ib-ul"><li v-for="x in item.strategy.voice_dont" :key="x">{{ x }}</li></ul>
        </div>
      </div>
      <template v-if="combined">
        <h3 class="rl-h3">اختر اتجاه الهوية <span class="sub">اختياري هنا: إن اخترته يُعتمد مع المنصة ويمضي الخط حتى الدليل</span></h3>
        <fieldset class="ib-grid ib-dir">
          <legend class="ib-l">{{ single ? "الاتجاه مفحوص آليًا" : "الاتجاهات الثلاثة مفحوصة آليًا" }}؛<a :href="out(v.board)" target="_blank" rel="noopener">اللوحة كاملة</a></legend>
          <label v-for="x in v.options" :key="x.id" class="ib-c">
            <div class="ib-img"><img :src="out(x.img)" :alt="`منشور بالاتجاه ${x.id}`" /></div>
            <div class="ib-b">
              <div class="ib-t"><input v-model="option" type="radio" :name="`opt-${item.project}`" :value="x.id" /> <b>{{ x.id }} · {{ x.name }}</b></div>
              <span class="ib-sw"><i v-for="c in x.swatches" :key="c" :style="{ background: c }" :title="c"></i></span>
              <p class="ib-s">{{ x.idea }}</p>
            </div>
          </label>
        </fieldset>
      </template>
    </template>

    <template v-else-if="item.gate === 'directions'">
      <p class="sub">{{ (item.options?.length ?? 0) === 1 ? 'الاتجاه الذي اخترته مكتملًا (ألوانه كلها ووضعه الداكن ونمطه) اجتاز' : 'ثلاثة اتجاهات اجتازت' }} فحوص التباين وعمى الألوان وتغطية الخطوط. <a :href="out(item.board)" target="_blank" rel="noopener">لوحة الاتجاهات كاملة</a></p>
      <fieldset class="ib-grid ib-dir">
        <legend class="ib-l">اختر اتجاهًا للاعتماد</legend>
        <label v-for="o in item.options" :key="o.id" class="ib-c">
          <div class="ib-img"><img :src="out(o.img)" :alt="`منشور بالاتجاه ${o.id}`" /></div>
          <div class="ib-b">
            <div class="ib-t"><input v-model="option" type="radio" :name="`opt-${item.project}`" :value="o.id" /> <b>{{ o.id }} · {{ o.name }}</b></div>
            <span class="ib-sw"><i v-for="c in o.swatches" :key="c" :style="{ background: c }" :title="c"></i></span>
            <p class="ib-s">{{ o.idea }}</p>
          </div>
        </label>
      </fieldset>
    </template>

    <template v-else>
      <p v-if="item.reply" class="ib-after" role="status">
        <b>جواب الخط على ملاحظتك:</b> «{{ item.reply.note }}»<br />
        {{ item.reply.text || "لم يكتب النموذج جوابًا." }}<br />
        <span class="sub">لم يتغيّر شيء في الدليل، فالقرار لك من جديد: اعتمده، أو اطلب تعديلًا آخر بسبب.</span>
      </p>
      <p class="sub">الهوية مبنية كاملة بالاتجاه المعتمد. راجع الدليل ثم قرّر؛ الاعتماد يغلق الإصدار ويحفظ الهوية في قاعدة سِمة ويجعلها قابلة للتسليم.</p>
      <p>
        <a class="btn pri" :href="out(item.book)" target="_blank" rel="noopener">افتح دليل الهوية</a>
        <a v-if="item.pdf" class="btn" :href="out(item.pdf)" target="_blank" rel="noopener">PDF</a>
      </p>
      <div class="ib-apps"><a v-for="a in item.apps ?? []" :key="a" :href="out(a)" target="_blank" rel="noopener"><img :src="out(a)" alt="تطبيق من الهوية" /></a></div>
      <iframe class="ib-book" :src="out(item.book)" title="دليل الهوية"></iframe>
    </template>

    <ul v-if="item.history.length" class="ib-ul sub">
      <li v-for="h in item.history" :key="h.at">{{ hm(h.at) }} {{ VERD[h.verdict] ?? h.verdict }} {{ h.option }} — {{ h.reason }}</li>
    </ul>
    <p class="ib-after"><b>ماذا بعد؟</b> {{ item.after }}</p>
    <DecisionActions :id="`g-${item.project}-${item.gate}`" :maxlength="board.limit('identity')" :check="check" :confirm-hint="confirmHint" @decide="decide" />
    <div v-if="item.gate === 'book' && item.designer_sketch" class="st-form sk-reject ib-vector">
      <label class="ib-l" :for="`vec-reason-${item.project}`">الشعار نفسه لا يطابق السكتش {{ item.designer_sketch }} الذي اخترته؟ ردّه بسبب، فيعود السكتش إلى المصمّم ليبنيه من جديد («طلب تعديل» أعلاه لا يغيّر الشعار)</label>
      <textarea :id="`vec-reason-${item.project}`" v-model="why" rows="2" :maxlength="board.limit('reason')"
        placeholder="مطلوب: ما الذي لا يطابق السكتش؟ يُنقل إلى المصمّم بنصّه"></textarea>
      <button type="button" class="btn ib-x" :disabled="busy" @click="returnVector">ردّ الشعار وأعد السكتش إلى المصمّم</button>
      <p v-if="returned" class="rl-status" :class="returned.ok ? 'good' : 'bad'" role="status">{{ returned.text }}</p>
    </div>
  </section>
</template>
