import "@/inbound"; // أولًا، قبل الموجّه: ردّ المصمّم الوارد في جزء الرابط يُلتقط ويُزال منه
import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "@/App.vue";
import { router } from "@/router";
import "@/styles/index.css";

createApp(App).use(createPinia()).use(router).mount("#app");
