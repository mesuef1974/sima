import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import vue from "eslint-plugin-vue";

// فحص ساكن للواجهة: نواة JS وTS وVue. لا قواعد تنسيق (الأسلوب ليس موضوع الفحص هنا).
export default tseslint.config(
  { ignores: ["node_modules/**", "../src/sima/web/frontend_dist/**", "public/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs["flat/essential"],
  {
    files: ["**/*.{ts,vue}"],
    languageOptions: { globals: { ...globals.browser }, parserOptions: { parser: tseslint.parser } },
    rules: { "vue/multi-word-component-names": "off" },
  },
  { files: ["**/*.spec.ts", "vite.config.ts"], languageOptions: { globals: { ...globals.node, ...globals.vitest } } },
);
