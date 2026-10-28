(() => {
  "use strict";

  const menuToggle = document.querySelector("[data-menu-toggle]");
  const menu = document.getElementById("main-navigation");
  if (menuToggle && menu) {
    menuToggle.addEventListener("click", () => {
      const open = menuToggle.getAttribute("aria-expanded") !== "true";
      menuToggle.setAttribute("aria-expanded", String(open));
      menu.classList.toggle("is-open", open);
    });
  }

  const slides = Array.from(document.querySelectorAll("[data-banner-slide]"));
  const dots = Array.from(document.querySelectorAll("[data-banner-dot]"));
  if (slides.length > 1) {
    let active = 0;
    let timer = null;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const show = (index) => {
      active = (index + slides.length) % slides.length;
      const heroImage = document.querySelector("[data-hero-image]");
      if (heroImage && slides[active].dataset.bannerImage) {
        heroImage.src = slides[active].dataset.bannerImage;
      }
      slides.forEach((slide, i) => {
        slide.hidden = i !== active;
        slide.setAttribute("aria-hidden", String(i !== active));
      });
      dots.forEach((dot, i) => dot.setAttribute("aria-current", String(i === active)));
    };
    const stop = () => { if (timer) window.clearInterval(timer); timer = null; };
    const start = () => {
      stop();
      if (!reducedMotion) timer = window.setInterval(() => show(active + 1), 5500);
    };
    dots.forEach((dot) => dot.addEventListener("click", () => {
      show(Number(dot.dataset.bannerDot) || 0);
      start();
    }));
    const hero = slides[0].closest(".hero");
    if (hero) {
      hero.addEventListener("mouseenter", stop);
      hero.addEventListener("mouseleave", start);
      hero.addEventListener("focusin", stop);
      hero.addEventListener("focusout", (event) => {
        if (!hero.contains(event.relatedTarget)) start();
      });
    }
    show(0);
    start();
  }

  const numberFormat = new Intl.NumberFormat("fa-IR");
  document.querySelectorAll("[data-variant-select]").forEach((select) => {
    const form = select.closest("form");
    const price = document.querySelector("[data-product-price]");
    const stock = document.querySelector("[data-product-stock]");
    const submit = form && form.querySelector('button[type="submit"]');
    const defaultPrice = price ? Number(price.dataset.defaultPrice || 0) : 0;
    const update = () => {
      const option = select.selectedOptions[0];
      if (!option || !option.value) {
        if (price) price.textContent = numberFormat.format(defaultPrice);
        if (stock) {
          stock.textContent = "یک گزینه را انتخاب کنید";
          stock.classList.remove("out");
        }
        if (submit) submit.disabled = true;
        return;
      }
      const available = Number(option.dataset.stock || 0) > 0;
      const amount = Number(option.dataset.price || defaultPrice);
      if (price) price.textContent = numberFormat.format(amount);
      if (stock) {
        stock.textContent = available ? "موجود" : "ناموجود";
        stock.classList.toggle("out", !available);
      }
      if (submit) submit.disabled = !available;
    };
    select.addEventListener("change", update);
    update();
  });

  document.querySelectorAll("[data-loading-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"], button:not([type])');
      if (!button || button.disabled) return;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = "در حال ثبت…";
    });
  });

  document.querySelectorAll("[data-resend-form]").forEach((form) => {
    const button = form.querySelector("[data-resend-button]");
    if (!button) return;
    let seconds = Math.max(0, Number(form.dataset.cooldown || 0));
    const label = "ارسال دوبارهٔ کد";
    const update = () => {
      button.disabled = seconds > 0;
      button.textContent = seconds > 0 ? label + " (" + numberFormat.format(seconds) + " ثانیه)" : label;
    };
    update();
    if (seconds > 0) {
      const timer = window.setInterval(() => {
        seconds -= 1;
        update();
        if (seconds <= 0) window.clearInterval(timer);
      }, 1000);
    }
  });

  document.querySelectorAll("[data-formset-add]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.formsetAdd;
      const template = document.querySelector('[data-formset-template="' + name + '"]');
      const rows = document.querySelector('[data-formset="' + name + '"]');
      const total = document.getElementById("id_" + name + "-TOTAL_FORMS");
      if (!template || !rows || !total) return;
      const index = Number(total.value);
      rows.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", String(index)));
      total.value = String(index + 1);
    });
  });
})();
