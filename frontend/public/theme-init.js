// يطبّق تفضيل السمة قبل أول رسم فلا تومض الصفحة. ملف خارجي لأن CSP تمنع النصوص المضمّنة.
(function () {
  try {
    var mode = localStorage.getItem("sima_theme");
    if (mode === "light" || mode === "dark") document.documentElement.dataset.theme = mode;
  } catch (e) {
    /* التخزين محجوب: تبقى السمة تلقائية */
  }
})();
