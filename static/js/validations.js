/**
 * static/js/validations.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Task 6 — Client-Side Validations for ALL forms.
 *
 * HOW TO USE:
 *   Add this ONE line to the <head> or just before </body> in your base.html:
 *
 *     <script src="{{ url_for('static', filename='js/validations.js') }}" defer></script>
 *
 *   The `defer` attribute ensures the DOM is ready before the script runs.
 *   All functions below fire automatically — no extra code needed in templates.
 *
 * COVERAGE:
 *   1. Bootstrap 5 generic validator   — all forms with id that ends in "-form"
 *   2. Registration form               — password match + strength
 *   3. Booking / seat-selection form   — at least one seat must be selected
 *   4. Contact Us form                 — name / email / message
 *   5. Add Screen form                 — seat count ≥ 10
 *   6. Add Show / Show form            — price & date sanity
 * ─────────────────────────────────────────────────────────────────────────────
 */

(function () {
  "use strict";

  /* ══════════════════════════════════════════════════════════════════════════
   * 1. GENERIC BOOTSTRAP 5 VALIDATION
   *    Applies to every <form novalidate> on the page.
   *    Shows .invalid-feedback messages on submit if any field is invalid.
   * ══════════════════════════════════════════════════════════════════════════ */
  document.querySelectorAll("form[novalidate]").forEach(function (form) {
    form.addEventListener(
      "submit",
      function (e) {
        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
        }
        form.classList.add("was-validated");
      },
      false
    );
  });


  /* ══════════════════════════════════════════════════════════════════════════
   * 2. REGISTRATION FORM  (#register-form)
   *    • Password must be ≥ 6 characters.
   *    • Confirm password must match.
   *    • Live strength indicator (weak / medium / strong).
   * ══════════════════════════════════════════════════════════════════════════ */
  var regForm = document.getElementById("register-form");
  if (regForm) {
    var pwdInput     = regForm.querySelector('[name="password"]');
    var confirmInput = regForm.querySelector('[name="confirm"]');
    var strengthBar  = document.getElementById("pwd-strength-bar");
    var strengthText = document.getElementById("pwd-strength-text");

    /* Live strength meter */
    if (pwdInput && strengthBar) {
      pwdInput.addEventListener("input", function () {
        var pwd    = pwdInput.value;
        var score  = 0;
        if (pwd.length >= 8)                          score++;
        if (/[A-Z]/.test(pwd))                        score++;
        if (/[0-9]/.test(pwd))                        score++;
        if (/[^A-Za-z0-9]/.test(pwd))                score++;

        var levels = [
          { label: "",        cls: "",        width: "0%"   },
          { label: "Weak",    cls: "bg-danger",   width: "25%"  },
          { label: "Fair",    cls: "bg-warning",  width: "50%"  },
          { label: "Good",    cls: "bg-info",     width: "75%"  },
          { label: "Strong",  cls: "bg-success",  width: "100%" },
        ];
        var lvl = levels[Math.min(score, 4)];

        strengthBar.style.width = lvl.width;
        strengthBar.className   = "progress-bar " + lvl.cls;
        if (strengthText) strengthText.textContent = lvl.label;
      });
    }

    /* On submit: check min length + match */
    regForm.addEventListener("submit", function (e) {
      var pwd     = pwdInput     ? pwdInput.value     : "";
      var confirm = confirmInput ? confirmInput.value : "";
      var ok = true;

      if (pwd.length < 6) {
        _setInvalid(pwdInput, "Password must be at least 6 characters.");
        ok = false;
      } else {
        _clearInvalid(pwdInput);
      }

      if (confirm !== pwd) {
        _setInvalid(confirmInput, "Passwords do not match.");
        ok = false;
      } else {
        _clearInvalid(confirmInput);
      }

      if (!ok) {
        e.preventDefault();
        e.stopPropagation();
      }
      regForm.classList.add("was-validated");
    });
  }


  /* ══════════════════════════════════════════════════════════════════════════
   * 3. BOOKING / SEAT-SELECTION FORM  (#seat-form)
   *    At least one seat checkbox must be checked before submitting.
   * ══════════════════════════════════════════════════════════════════════════ */
  var seatForm = document.getElementById("seat-form");
  if (seatForm) {
    var seatError = document.getElementById("seat-select-error");

    seatForm.addEventListener("submit", function (e) {
      var checked = seatForm.querySelectorAll('input[name="seat_ids"]:checked');
      if (checked.length === 0) {
        e.preventDefault();
        e.stopPropagation();
        if (seatError) {
          seatError.style.display = "";
          seatError.textContent   = "Please select at least one seat before continuing.";
        } else {
          alert("Please select at least one seat.");
        }
      } else {
        if (seatError) seatError.style.display = "none";
      }
    });

    /* Hide the error as soon as the user picks a seat */
    seatForm.querySelectorAll('input[name="seat_ids"]').forEach(function (cb) {
      cb.addEventListener("change", function () {
        if (seatError) seatError.style.display = "none";
      });
    });
  }


  /* ══════════════════════════════════════════════════════════════════════════
   * 4. CONTACT US FORM  (#contact-form)
   *    • Name ≥ 2 characters.
   *    • Valid email format.
   *    • Message ≥ 10 characters.
   *    (The Bootstrap novalidate handler above already covers `required`,
   *     but these rules add richer feedback messages.)
   * ══════════════════════════════════════════════════════════════════════════ */
  var contactForm = document.getElementById("contact-form");
  if (contactForm) {
    contactForm.addEventListener("submit", function (e) {
      var nameEl    = contactForm.querySelector('[name="name"]');
      var emailEl   = contactForm.querySelector('[name="email"]');
      var messageEl = contactForm.querySelector('[name="message"]');
      var ok = true;

      if (nameEl && nameEl.value.trim().length < 2) {
        _setInvalid(nameEl, "Name must be at least 2 characters.");
        ok = false;
      } else if (nameEl) {
        _clearInvalid(nameEl);
      }

      if (emailEl && !_isValidEmail(emailEl.value.trim())) {
        _setInvalid(emailEl, "Please enter a valid email address.");
        ok = false;
      } else if (emailEl) {
        _clearInvalid(emailEl);
      }

      if (messageEl && messageEl.value.trim().length < 10) {
        _setInvalid(messageEl, "Message must be at least 10 characters.");
        ok = false;
      } else if (messageEl) {
        _clearInvalid(messageEl);
      }

      if (!ok) {
        e.preventDefault();
        e.stopPropagation();
      }
      contactForm.classList.add("was-validated");
    });
  }


  /* ══════════════════════════════════════════════════════════════════════════
   * 5. ADD SCREEN FORM  (#screen-form)
   *    The inline script inside screen_form.html handles the live preview.
   *    This section adds a second guard: total seats < 10 → block submit.
   * ══════════════════════════════════════════════════════════════════════════ */
  var screenForm = document.getElementById("screen-form");
  if (screenForm) {
    screenForm.addEventListener("submit", function (e) {
      var gold    = parseInt((screenForm.querySelector('[name="gold_seats"]')    || {}).value, 10) || 0;
      var silver  = parseInt((screenForm.querySelector('[name="silver_seats"]')  || {}).value, 10) || 0;
      var general = parseInt((screenForm.querySelector('[name="general_seats"]') || {}).value, 10) || 0;

      if (gold + silver + general < 10) {
        e.preventDefault();
        e.stopPropagation();
        var errEl = document.getElementById("seat-error");
        if (errEl) errEl.style.display = "";
      }
      screenForm.classList.add("was-validated");
    });
  }


  /* ══════════════════════════════════════════════════════════════════════════
   * 6. ADD SHOW FORM  (#show-form)
   *    • Price per ticket must be > 0.
   *    • Available seats must be > 0.
   *    • Show date must not be in the past (warn only — not a hard block).
   * ══════════════════════════════════════════════════════════════════════════ */
  var showForm = document.getElementById("show-form");
  if (showForm) {
    showForm.addEventListener("submit", function (e) {
      var priceEl  = showForm.querySelector('[name="price_per_ticket"]');
      var seatsEl  = showForm.querySelector('[name="available_seats"]');
      var dateEl   = showForm.querySelector('[name="show_date"]');
      var ok       = true;

      if (priceEl && (parseFloat(priceEl.value) || 0) <= 0) {
        _setInvalid(priceEl, "Price per ticket must be greater than ₹0.");
        ok = false;
      } else if (priceEl) {
        _clearInvalid(priceEl);
      }

      if (seatsEl && (parseInt(seatsEl.value, 10) || 0) <= 0) {
        _setInvalid(seatsEl, "Available seats must be at least 1.");
        ok = false;
      } else if (seatsEl) {
        _clearInvalid(seatsEl);
      }

      if (dateEl && dateEl.value) {
        var chosen = new Date(dateEl.value);
        var today  = new Date();
        today.setHours(0, 0, 0, 0);
        if (chosen < today) {
          /* Warn but allow — your app intentionally allows historical shows */
          var warn = document.getElementById("show-date-warn");
          if (!warn) {
            warn = document.createElement("div");
            warn.id        = "show-date-warn";
            warn.className = "text-warning small mt-1";
            dateEl.parentNode.appendChild(warn);
          }
          warn.textContent = "⚠️ The selected date is in the past.";
        }
      }

      if (!ok) {
        e.preventDefault();
        e.stopPropagation();
      }
      showForm.classList.add("was-validated");
    });
  }


  /* ══════════════════════════════════════════════════════════════════════════
   * HELPERS
   * ══════════════════════════════════════════════════════════════════════════ */

  /** Mark an input as invalid with a custom message. */
  function _setInvalid(el, message) {
    if (!el) return;
    el.classList.add("is-invalid");
    el.classList.remove("is-valid");
    var fb = el.nextElementSibling;
    if (fb && fb.classList.contains("invalid-feedback")) {
      fb.textContent = message;
    }
  }

  /** Clear the invalid state from an input. */
  function _clearInvalid(el) {
    if (!el) return;
    el.classList.remove("is-invalid");
  }

  /** Lightweight RFC-5322-ish email check. */
  function _isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

})();
