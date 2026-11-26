/* =========================================================================
   AppointED Progressive Enhancement Scripts
   All forms, links, modals, and theme switching still work without JS.
   ========================================================================= */
(function () {
  "use strict";

  let lastTriggerEl = null;
  let activeModal = null;

  // ---- Password visibility toggles ----
  document.querySelectorAll('input[type="password"]').forEach((input) => {
    if (input.dataset.pwEnhanced) return;
    input.dataset.pwEnhanced = "1";
    const wrap = document.createElement("div");
    wrap.className = "password-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "password-toggle-btn";
    btn.textContent = "Show";
    btn.setAttribute("aria-label", "Show password");
    btn.addEventListener("click", () => {
      const hidden = input.type === "password";
      input.type = hidden ? "text" : "password";
      btn.textContent = hidden ? "Hide" : "Show";
      btn.setAttribute("aria-label", hidden ? "Hide password" : "Show password");
    });
    wrap.appendChild(btn);
  });

  // ---- Live booking purpose character counter (0 / 255) ----
  const purposeEl = document.getElementById("id_purpose");
  const counterEl = document.getElementById("purpose-counter");
  if (purposeEl && counterEl) {
    const updateCount = () => {
      counterEl.textContent = `${purposeEl.value.length} / ${purposeEl.maxLength || 255}`;
    };
    purposeEl.addEventListener("input", updateCount);
    updateCount();
  }

  // ---- Accessible Confirm Modals (:target progressive enhancement) ----
  function getFocusable(container) {
    return Array.from(
      container.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])')
    );
  }

  function closeActiveModal() {
    if (!activeModal) return;
    activeModal.classList.remove("is-open");
    activeModal = null;
    if (window.location.hash && window.location.hash !== "#_") {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    }
    if (lastTriggerEl && typeof lastTriggerEl.focus === "function") {
      lastTriggerEl.focus();
      lastTriggerEl = null;
    }
  }

  function openModal(modal, trigger) {
    lastTriggerEl = trigger || document.activeElement;
    activeModal = modal;
    modal.classList.add("is-open");
    const safeBtn = modal.querySelector("[data-modal-safe]") || getFocusable(modal)[0];
    if (safeBtn) safeBtn.focus();
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-modal-target]");
    if (trigger) {
      const targetId = trigger.getAttribute("data-modal-target");
      const modal = document.getElementById(targetId);
      if (modal) {
        e.preventDefault();
        openModal(modal, trigger);
      }
      return;
    }

    const cancelLink = e.target.closest("[data-modal-close]");
    if (cancelLink && activeModal) {
      e.preventDefault();
      closeActiveModal();
      return;
    }

    if (activeModal && e.target === activeModal) {
      closeActiveModal();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (!activeModal) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeActiveModal();
      return;
    }
    if (e.key === "Tab") {
      const focusables = getFocusable(activeModal);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  // ---- Arrow-key navigation on History status tablist ----
  const tablist = document.querySelector('[role="tablist"]');
  if (tablist) {
    const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
    tablist.addEventListener("keydown", (e) => {
      const idx = tabs.indexOf(document.activeElement);
      if (idx === -1) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        tabs[(idx + 1) % tabs.length].focus();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        tabs[(idx - 1 + tabs.length) % tabs.length].focus();
      }
    });
  }
})();
