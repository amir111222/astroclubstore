(() => {
  "use strict";

  document.querySelectorAll("[data-category-dropdown]").forEach((item) => {
    const toggle = item.querySelector("[data-category-toggle]");
    const menu = item.querySelector(".nav-category-menu");
    if (!toggle || !menu) return;
    let pinnedOpen = false;
    let hovered = false;
    let suppressFocusOpen = false;
    const setOpen = (open) => {
      item.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      menu.hidden = !open;
    };
    toggle.addEventListener("click", () => {
      pinnedOpen = !pinnedOpen;
      setOpen(pinnedOpen || hovered);
    });
    item.addEventListener("pointerenter", (event) => {
      if (event.pointerType === "mouse") { hovered = true; setOpen(true); }
    });
    item.addEventListener("pointerleave", (event) => {
      if (event.pointerType === "mouse") { hovered = false; if (!pinnedOpen) setOpen(false); }
    });
    item.addEventListener("focusin", (event) => {
      if (suppressFocusOpen && event.target === toggle) { suppressFocusOpen = false; return; }
      setOpen(true);
    });
    item.addEventListener("focusout", (event) => {
      if (!item.contains(event.relatedTarget) && !pinnedOpen) setOpen(false);
    });
    document.addEventListener("click", (event) => {
      if (!item.contains(event.target)) { pinnedOpen = false; hovered = false; setOpen(false); }
    });
    item.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        pinnedOpen = false;
        hovered = false;
        setOpen(false);
        suppressFocusOpen = true;
        toggle.focus();
      }
    });
  });

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

      let pointerStart = null;
      let suppressClickUntil = 0;
      hero.addEventListener("pointerdown", (event) => {
        if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) return;
        pointerStart = { x: event.clientX, y: event.clientY, id: event.pointerId };
        try { hero.setPointerCapture(event.pointerId); } catch (_) {}
      });
      hero.addEventListener("pointerup", (event) => {
        if (!pointerStart || pointerStart.id !== event.pointerId) return;
        const deltaX = event.clientX - pointerStart.x;
        const deltaY = event.clientY - pointerStart.y;
        pointerStart = null;
        if (Math.abs(deltaX) < 45 || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) return;
        show(active + (deltaX < 0 ? 1 : -1));
        start();
        suppressClickUntil = Date.now() + 500;
      });
      hero.addEventListener("pointercancel", () => { pointerStart = null; });
      hero.addEventListener("click", (event) => {
        if (event.detail && Date.now() < suppressClickUntil) {
          event.preventDefault();
          event.stopPropagation();
          suppressClickUntil = 0;
        }
      }, true);
      hero.addEventListener("dragstart", (event) => event.preventDefault());
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

  document.querySelectorAll("[data-phone-input]").forEach((input) => {
    const map = "۰۱۲۳۴۵۶۷۸۹";
    const button = input.form && input.form.querySelector("[data-phone-submit]");
    const update = () => {
      let v = input.value.replace(/[۰-۹]/g, (d) => map.indexOf(d)).replace(/\D/g, "").slice(0, 11);
      if (v !== input.value) input.value = v;
      const ok = /^09\d{9}$/.test(v);
      if (button && button.getAttribute("aria-busy") !== "true") button.disabled = !ok;
      input.setAttribute("aria-invalid", v && !ok ? "true" : "false");
    };
    input.addEventListener("input", update);
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

  // ── Cart dropdown toggle ──────────────────────────────────────────────────
  document.querySelectorAll("[data-cart-dropdown]").forEach((wrap) => {
    const toggle = wrap.querySelector("[data-cart-toggle]");
    const dropdown = wrap.querySelector(".cart-dropdown");
    if (!toggle || !dropdown) return;
    const fit = () => {
      dropdown.style.transform = "";
      const rect = dropdown.getBoundingClientRect();
      const margin = 12;
      const width = document.documentElement.clientWidth;
      let shift = 0;
      if (rect.right > width - margin) shift = width - margin - rect.right;
      if (rect.left + shift < margin) shift = margin - rect.left;
      if (shift) dropdown.style.transform = "translateX(" + shift + "px)";
    };
    const open = () => { dropdown.hidden = false; toggle.setAttribute("aria-expanded", "true"); fit(); };
    window.addEventListener("resize", () => { if (!dropdown.hidden) fit(); });
    const close = () => { dropdown.hidden = true; toggle.setAttribute("aria-expanded", "false"); };
    toggle.addEventListener("click", () => dropdown.hidden ? open() : close());
    document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  });

  // ── Cart dropdown: "−" removes one unit ───────────────────────────────────
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("[data-cart-dec]");
    if (!form) return;
    e.preventDefault();
    const btn = form.querySelector("button");
    if (btn) btn.disabled = true;
    try {
      const res = await fetch(form.action, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        body: new FormData(form),
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "خطا");
      const body = form.closest("[data-cart-dropdown-body]");
      if (body) body.innerHTML = data.html;
      document.querySelectorAll("[data-cart-count]").forEach((el) => { el.textContent = data.cart_count; });
    } catch (err) {
      if (btn) btn.disabled = false;
      alert("حذف انجام نشد. دوباره تلاش کنید.");
    }
  });

  // ── Card +/- quantity ─────────────────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-qty-dec],[data-qty-inc]");
    if (!btn) return;
    const input = btn.closest(".card-qty-control")?.querySelector(".card-qty-input");
    if (!input) return;
    const step = btn.hasAttribute("data-qty-inc") ? 1 : -1;
    const next = Math.max(1, Math.min(99, (parseInt(input.value) || 1) + step));
    input.value = next;
  });

  // ── Add-to-cart fetch + modal ─────────────────────────────────────────────
  const cartModal = document.getElementById("cart-added-modal");
  const cartModalName = document.getElementById("cart-modal-name");
  const cartCountEls = () => document.querySelectorAll("[data-cart-count]");

  function showCartModal(productName) {
    if (!cartModal) return;
    if (cartModalName) cartModalName.textContent = productName;
    cartModal.hidden = false;
    cartModal.querySelector("[data-modal-continue]")?.focus();
  }
  if (cartModal) {
    cartModal.querySelector("[data-modal-continue]")?.addEventListener("click", () => {
      cartModal.hidden = true;
    });
    cartModal.addEventListener("click", (e) => {
      if (e.target === cartModal) cartModal.hidden = true;
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !cartModal.hidden) cartModal.hidden = true;
    });
  }

  // forms on product card (data-card-cart) and product detail (data-add-to-cart)
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("[data-card-cart],[data-add-to-cart]");
    if (!form) return;
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    const productName = form.closest("[data-product-name]")?.dataset.productName
      || form.closest(".product-card")?.querySelector("h3 a")?.textContent?.trim()
      || form.closest(".product-info")?.querySelector("h1")?.textContent?.trim()
      || "محصول";
    const origText = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "در حال افزودن…"; }
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          cartCountEls().forEach((el) => { el.textContent = data.cart_count; });
          showCartModal(productName);
        } else {
          alert(data.error || "خطا در افزودن به سبد");
        }
      })
      .catch(() => { alert("خطا در ارتباط با سرور"); })
      .finally(() => {
        if (btn) { btn.disabled = false; btn.textContent = origText; }
      });
  });

})();