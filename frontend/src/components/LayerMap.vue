<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import CodeText from "@/components/CodeText.vue";
import { ACTOR, GUARDS, LINKS, READING, TIERS } from "@/data/layers";
import type { Actor } from "@/data/layers";
import { useBoard } from "@/stores/board";
import { full } from "@/utils/format";
import { TONE_AR, layerLive } from "@/utils/layerLive";
import type { LayerId, Tone } from "@/utils/layerLive";

// رسم طبقات الأتمتة: ست طبقات من قرار المالك إلى المشروع المستلم داخل سياجها، بوصلاتها وحلقة الرسم والفحص.
// البناء من data/layers.ts، وفوقه الحال الحيّ من لقطة المنصة (utils/layerLive.ts): أين يقف كل مشروع الآن،
// ونبض كل طبقة، والوصلة التي يمرّ بها العمل، وآخر حركة وأرقام كل طبقة. يتحدّث مع التحديث الدوري للمنصة.
const board = useBoard();
let no = 0;
const tiers = TIERS.map((t) => ({ ...t, layers: t.layers.map((l) => ({ ...l, no: ++no })) }));
const actors = Object.entries(ACTOR) as [Actor, string][];
const tones = (["run", "wait", "ok", "off", "idle"] as Tone[]).map((t) => [t, TONE_AR[t]] as const);

const live = computed(() => layerLive(board.state, board.timelines, board.registry, { online: board.online, polling: board.polling }));
const net = computed(() => (!board.online ? { cls: "off", text: "منقطع" } : board.polling ? { cls: "", text: "حيّ" } : { cls: "paused", text: "متوقف" }));
const here = (layer: LayerId, part: string) => live.value.tokens.filter((t) => t.layer === layer && t.part === part);
const flows = (i: number, dir: "down" | "up") => live.value.links[i] === dir || live.value.links[i] === "both";

// النقر على مشروع في شريط «الآن» يُظهر طبقته ويومضها لحظة
const flashed = ref<LayerId | null>(null);
let timer: number | undefined;
function show(id: LayerId): void {
  const el = document.getElementById(`lm-layer-${id}`);
  el?.scrollIntoView({ block: "center", behavior: "smooth" });
  el?.focus({ preventScroll: true });
  flashed.value = id;
  window.clearTimeout(timer);
  timer = window.setTimeout(() => (flashed.value = null), 1800);
}
onMounted(() => {
  if (!board.registry) void board.loadRegistry();
});
onBeforeUnmount(() => window.clearTimeout(timer));
</script>

<template>
  <section class="card lm" aria-labelledby="lm-title">
    <div class="cardhead"><h2 id="lm-title">طبقات الأتمتة</h2><span class="sub">البناء القائم من قرارك إلى المشروع المستلم، وعليه ما يجري الآن</span></div>

    <div class="lm-now" aria-labelledby="lm-now-title">
      <div class="lm-now-head">
        <span class="rl-live" :class="net.cls"><i></i><span>{{ net.text }}</span></span>
        <h3 id="lm-now-title">الآن</h3>
        <p role="status">{{ live.headline }}</p>
      </div>
      <ul v-if="live.tokens.length" class="lm-tokens">
        <li v-for="t in live.tokens" :key="t.project">
          <button type="button" class="lm-token" :class="t.tone" :title="t.text" @click="show(t.layer)">
            <i class="lm-dot" :class="t.tone" aria-hidden="true"></i>
            <b>{{ t.name }}</b><span class="rl-num">{{ t.version }}</span>
            <span class="lm-token-at">الطبقة {{ t.no }}<template v-if="t.part"> · <CodeText :text="t.part" /></template></span>
            <span class="fm-who" :class="t.who">{{ ACTOR[t.who] }}</span>
          </button>
        </li>
      </ul>
    </div>

    <div class="fm-legend">
      <span v-for="[k, name] in actors" :key="k"><span class="fm-who" :class="k">{{ name }}</span></span>
      <span>لون حافة كل مكوّن يدل على من ينفّذه</span>
      <span v-for="[k, name] in tones" :key="k" class="lm-key"><i class="lm-dot" :class="k" aria-hidden="true"></i>{{ name }}</span>
    </div>

    <div class="lm-fence" aria-labelledby="lm-fence-title">
      <div class="lm-fence-head">
        <h3 id="lm-fence-title">السياج</h3>
        <ul class="lm-fence-chips"><li v-for="g in GUARDS" :key="g.n">{{ g.n }}</li></ul>
      </div>
      <div class="lm-stack">
        <template v-for="(tier, i) in tiers" :key="i">
          <div class="lm-tier" :class="{ pair: tier.layers.length > 1 }">
            <template v-for="(l, k) in tier.layers" :key="l.id">
              <article :id="`lm-layer-${l.id}`" class="lm-layer" :class="[l.id, live.layers[l.id].tone, { flash: flashed === l.id }]" :aria-labelledby="`lm-${l.id}`" tabindex="-1">
                <header>
                  <span class="lm-no" aria-hidden="true">{{ l.no }}</span>
                  <div class="lm-title">
                    <h3 :id="`lm-${l.id}`">{{ l.t }}</h3>
                    <p class="lm-role"><CodeText :text="l.role" /></p>
                  </div>
                  <p class="lm-state" :class="live.layers[l.id].tone">
                    <i class="lm-dot" :class="live.layers[l.id].tone" aria-hidden="true"></i>
                    <span class="visually-hidden">الحال الآن: {{ TONE_AR[live.layers[l.id].tone] }}.</span>
                    <span>{{ live.layers[l.id].note }}</span>
                  </p>
                </header>
                <ul class="lm-parts">
                  <li v-for="p in l.parts" :key="p.n" class="lm-part" :class="[p.who, { on: here(l.id, p.n).length }]">
                    <b><CodeText :text="p.n" /></b>
                    <p><CodeText :text="p.d" /></p>
                    <div class="lm-part-foot">
                      <span class="fm-who" :class="p.who">{{ ACTOR[p.who] }}</span>
                      <span v-for="t in here(l.id, p.n)" :key="t.project" class="lm-here" :title="t.text">
                        <i class="lm-dot" :class="t.tone" aria-hidden="true"></i>{{ t.name }} <span class="rl-num">{{ t.version }}</span>
                      </span>
                    </div>
                  </li>
                </ul>
                <div class="lm-foot">
                  <dl v-if="live.layers[l.id].facts.length" class="lm-facts">
                    <div v-for="f in live.layers[l.id].facts" :key="f.k"><dt>{{ f.k }}</dt><dd class="rl-num">{{ f.v }}</dd></div>
                  </dl>
                  <p v-if="live.layers[l.id].last" class="lm-last" :title="live.layers[l.id].last!.text">
                    <b>آخر حركة</b> <span class="rl-num">{{ full(live.layers[l.id].last!.at) }}</span> {{ live.layers[l.id].last!.text }}
                  </p>
                </div>
                <p class="lm-edge"><CodeText :text="l.edge" /></p>
              </article>
              <div v-if="tier.loop && k === 0" class="lm-loop" :class="{ on: live.loop }" role="note" aria-label="حلقة الرسم والفحص">
                <span class="there">
                  <svg class="lm-arrow" viewBox="0 0 48 24" aria-hidden="true"><path class="lm-track" d="M46 12H6" /><path d="M12 6l-6 6 6 6" /></svg>{{ tier.loop.there }}
                </span>
                <span class="back">
                  <svg class="lm-arrow" viewBox="0 0 48 24" aria-hidden="true"><path class="lm-track" d="M2 12h40" /><path d="M36 6l6 6-6 6" /></svg>{{ tier.loop.back }}
                </span>
              </div>
            </template>
          </div>
          <div v-if="LINKS[i]" class="lm-link" role="note">
            <span class="down" :class="{ on: flows(i, 'down') }">
              <svg class="lm-arrow" viewBox="0 0 24 48" aria-hidden="true"><path class="lm-track" d="M12 2v40" /><path d="M6 36l6 6 6-6" /></svg>
              <span>ينزل: <CodeText :text="LINKS[i].down" /></span>
            </span>
            <span class="up" :class="{ on: flows(i, 'up') }">
              <svg class="lm-arrow" viewBox="0 0 24 48" aria-hidden="true"><path class="lm-track" d="M12 46V6" /><path d="M6 12l6-6 6 6" /></svg>
              <span>يعود: <CodeText :text="LINKS[i].up" /></span>
            </span>
          </div>
        </template>
      </div>
    </div>

    <div class="lm-guards" aria-labelledby="lm-guards">
      <h3 id="lm-guards">ما يفرضه السياج</h3>
      <p class="sub">يحيط بكل الطبقات ولا تتجاوزه واحدة منها</p>
      <ul>
        <li v-for="g in GUARDS" :key="g.n"><b>{{ g.n }}</b><p><CodeText :text="g.d" /></p></li>
      </ul>
    </div>
    <div class="lm-reading">
      <h3>كيف تقرأ الرسم</h3>
      <ol>
        <li v-for="r in READING" :key="r"><CodeText :text="r" /></li>
      </ol>
    </div>
  </section>
</template>
