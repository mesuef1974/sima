<script setup lang="ts">
// كلمة «سِمة» المعتمدة (v4، المفهوم a1): خط واحد متصل بسماكة ثابتة، والكسرة ضربته المستقيمة الوحيدة.
// المسارات من out/sima/v4/package/sima-wordmark.svg كما هي؛ لا يتغيّر فيها إلا اللون (حبر في الفاتح، أبيض في الداكن).
withDefaults(defineProps<{ height?: number }>(), { height: 44 });
</script>

<template>
  <svg class="brand-wordmark" :height="height" :width="(height * 923) / 457" aria-hidden="true" focusable="false" viewBox="62 284 923 457">
    <g fill="none" stroke="var(--color-mark-ink)" stroke-width="38.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M206 411 A90 90 0 0 1 306 511 V550 A101 101 0 0 1 205 616 A96 96 0 0 1 104 516 A108 108 0 0 1 206 411 Z" />
      <path d="M479 443 A80 80 0 0 1 560 521 V554 A80 80 0 0 1 480 611 A80 80 0 0 1 397 549 V526 A80 80 0 0 1 479 443 Z" />
      <path d="M305 559 V566 A45.5 45.5 0 0 0 396 566 M560 548 V572 A33 33 0 0 0 626 572 V484 A26.5 26.5 0 0 1 679 484 V556 A28.5 28.5 0 0 0 736 556 V431 A40 40 0 0 1 816 431 V553 A33.5 33.5 0 0 0 883 553 V489 A31 31 0 0 1 945 489 V540 A108 108 0 0 1 873 650" />
    </g>
    <circle cx="167.5" cy="335" r="35.5" fill="var(--color-mark-ink)" />
    <circle cx="264" cy="335" r="35.5" fill="var(--color-mark-ink)" />
    <path d="M648 711 L798 658" fill="none" stroke="var(--color-mark-ink)" stroke-width="34" stroke-linecap="round" />
  </svg>
</template>

<style scoped>
.brand-wordmark {
  flex: none;
  display: block;
}
</style>
