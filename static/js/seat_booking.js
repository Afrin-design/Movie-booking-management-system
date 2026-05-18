/**
 * seat_booking.js  — BookMyShow Clone
 * Handles seat toggling, price calculation, and reliable form submission.
 *
 * KEY FIX: The confirm button is now INSIDE the <form> tag.
 * No more form="seat-form" cross-reference issues.
 */

(function () {
  "use strict";

  const form = document.getElementById("seat-form");
  if (!form) return;

  const basePrice    = parseFloat(form.dataset.basePrice || "0");
  const maxSeats     = parseInt(form.dataset.maxSeats    || "10", 10);
  const seatInput    = document.getElementById("seat-ids-container");
  const countEl      = document.getElementById("selected-count");
  const totalEl      = document.getElementById("total-price");
  const confirmBtn   = document.getElementById("confirm-btn");
  const selectedList = document.getElementById("selected-seats-list");
  const emptySeatMsg = document.getElementById("empty-seat-msg");
  const errorBanner  = document.getElementById("seat-select-error");

  let selectedSeats = {}; // { seat_id: { number, type, charges } }

  // ── Attach click listeners ────────────────────────────────────────────────
  document.querySelectorAll(".seat-btn.available").forEach(btn => {
    btn.addEventListener("click", () => toggleSeat(btn));
  });

  function toggleSeat(btn) {
    const seatId  = btn.dataset.seatId;
    const seatNum = btn.dataset.seatNumber;
    const seatTyp = btn.dataset.seatType || "General";
    const charges = parseFloat(btn.dataset.charges || "0");

    if (btn.classList.contains("selected")) {
      btn.classList.replace("selected", "available");
      delete selectedSeats[seatId];
    } else {
      if (Object.keys(selectedSeats).length >= maxSeats) {
        showToast(`You can select at most ${maxSeats} seats.`, "warning");
        return;
      }
      btn.classList.replace("available", "selected");
      selectedSeats[seatId] = { number: seatNum, type: seatTyp, charges };
    }
    updateUI();
  }

  function updateUI() {
    const ids   = Object.keys(selectedSeats);
    const count = ids.length;
    const total = Object.values(selectedSeats).reduce(
      (sum, s) => sum + basePrice + s.charges, 0
    );

    // Counts
    if (countEl) countEl.textContent = count;
    if (totalEl) totalEl.textContent = "₹" + total.toFixed(2);

    // Confirm button state
    if (confirmBtn) {
      confirmBtn.disabled = count === 0;
      if (count > 0) {
        confirmBtn.innerHTML =
          `<i class="bi bi-lock-fill me-2"></i>` +
          `Confirm ${count} Seat${count > 1 ? "s" : ""} — ₹${total.toFixed(2)}`;
      } else {
        confirmBtn.innerHTML =
          `<i class="bi bi-cursor-fill me-2"></i>Select Seats to Continue`;
      }
    }

    // Error banner
    if (errorBanner) errorBanner.style.display = "none";

    // Hidden inputs — rebuilt on every change so form always has current selection
    if (seatInput) {
      seatInput.innerHTML = "";
      ids.forEach(id => {
        const inp   = document.createElement("input");
        inp.type    = "hidden";
        inp.name    = "seat_ids";
        inp.value   = id;
        seatInput.appendChild(inp);
      });
    }

    // Seat pill list
    if (selectedList) {
      selectedList.innerHTML = "";
      if (count === 0) {
        if (emptySeatMsg) emptySeatMsg.style.display = "";
      } else {
        if (emptySeatMsg) emptySeatMsg.style.display = "none";
        Object.values(selectedSeats).forEach(s => {
          const pill = document.createElement("span");
          pill.className = "badge bg-primary me-1 mb-1 py-2 px-3";
          pill.style.fontSize = ".8rem";
          pill.innerHTML = `<i class="bi bi-chair me-1"></i>${s.number}`;
          selectedList.appendChild(pill);
        });
      }
    }
  }

  // ── Form submit ───────────────────────────────────────────────────────────
  form.addEventListener("submit", function (e) {
    const ids = Object.keys(selectedSeats);

    if (ids.length === 0) {
      e.preventDefault();
      if (errorBanner) {
        errorBanner.textContent = "Please select at least one seat before continuing.";
        errorBanner.style.display = "block";
        errorBanner.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        showToast("Please select at least one seat.", "warning");
      }
      return;
    }

    // Double-check hidden inputs are present right before submit
    if (seatInput) {
      seatInput.innerHTML = "";
      ids.forEach(id => {
        const inp = document.createElement("input");
        inp.type  = "hidden";
        inp.name  = "seat_ids";
        inp.value = id;
        seatInput.appendChild(inp);
      });
    }

    // Show processing state
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.innerHTML =
        `<span class="spinner-border spinner-border-sm me-2" role="status"></span>Processing…`;
    }
    // Allow form to submit normally (no e.preventDefault)
  });

  // ── Toast ─────────────────────────────────────────────────────────────────
  function showToast(msg, type) {
    let tc = document.getElementById("toast-container");
    if (!tc) {
      tc = document.createElement("div");
      tc.id = "toast-container";
      tc.style.cssText = "position:fixed;top:80px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;";
      document.body.appendChild(tc);
    }
    const t = document.createElement("div");
    t.className = `alert alert-${type || "info"} py-2 px-3 shadow`;
    t.style.cssText = "min-width:220px;border-radius:10px;";
    t.innerHTML = `<i class="bi bi-exclamation-circle me-2"></i>${msg}`;
    tc.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  }

  // Initial render
  updateUI();
})();
