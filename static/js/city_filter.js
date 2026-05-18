/**
 * city_filter.js — Dynamic city filter on movie_detail page
 * Works with BOTH static Jinja-rendered theater blocks AND dynamic fetch
 */
(function () {
  "use strict";

  const citySelect     = document.getElementById("city-select");
  const theaterSection = document.getElementById("theater-shows-section");
  const loadingEl      = document.getElementById("theaters-loading");
  const noResultEl     = document.getElementById("no-theaters-msg");

  if (!citySelect || !theaterSection) return;

  const movieId = citySelect.dataset.movieId || "";

  citySelect.addEventListener("change", () => {
    const city = citySelect.value.trim();

    if (!city) {
      // Show ALL static blocks
      theaterSection.querySelectorAll(".theater-block").forEach(el => {
        el.style.display = "";
      });
      if (noResultEl) noResultEl.style.display = "none";
      return;
    }

    // Check if there are static blocks first
    const staticBlocks = theaterSection.querySelectorAll(".theater-block");
    if (staticBlocks.length > 0) {
      // Filter existing static blocks by fetching city's theater IDs
      filterStaticBlocks(city);
    } else {
      // No static blocks — fetch dynamically
      fetchAndBuildBlocks(city);
    }
  });

  function filterStaticBlocks(city) {
    if (loadingEl) loadingEl.style.display = "";

    fetch(`/api/theaters-in-city?city=${encodeURIComponent(city)}&movie_id=${encodeURIComponent(movieId)}`)
      .then(r => r.json())
      .then(theaters => {
        if (loadingEl) loadingEl.style.display = "none";

        const validIds = new Set(theaters.map(t => t.theater_id));
        let shown = 0;

        document.querySelectorAll(".theater-block").forEach(el => {
          if (validIds.has(el.dataset.theaterId)) {
            el.style.display = "";
            shown++;
          } else {
            el.style.display = "none";
          }
        });

        if (noResultEl) noResultEl.style.display = shown === 0 ? "" : "none";
      })
      .catch(() => {
        if (loadingEl) loadingEl.style.display = "none";
      });
  }

  function fetchAndBuildBlocks(city) {
    if (loadingEl) loadingEl.style.display = "";
    if (noResultEl) noResultEl.style.display = "none";

    fetch(`/api/theaters-in-city?city=${encodeURIComponent(city)}&movie_id=${encodeURIComponent(movieId)}`)
      .then(r => r.json())
      .then(theaters => {
        if (loadingEl) loadingEl.style.display = "none";

        if (!theaters.length) {
          if (noResultEl) noResultEl.style.display = "";
          return;
        }

        theaterSection.innerHTML = "";
        theaters.forEach(theater => {
          const block = document.createElement("div");
          block.className = "bms-card mb-3 p-3 theater-block";
          block.dataset.theaterId = theater.theater_id;
          block.innerHTML = `
            <div class="mb-2">
              <h6 class="fw-bold text-white mb-0">${esc(theater.name)}</h6>
              <div class="small" style="color:var(--bms-muted)">
                <i class="bi bi-geo-alt me-1"></i>${esc(theater.location || theater.city)}
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2" id="shows-${theater.theater_id}">
              <span class="small" style="color:var(--bms-muted)">
                <span class="spinner-border spinner-border-sm me-1"></span>Loading shows…
              </span>
            </div>`;
          theaterSection.appendChild(block);
          fetchShowsFor(theater.theater_id);
        });
      })
      .catch(() => {
        if (loadingEl) loadingEl.style.display = "none";
      });
  }

  function fetchShowsFor(theaterId) {
    fetch(`/api/shows-for-theater?theater_id=${encodeURIComponent(theaterId)}&movie_id=${encodeURIComponent(movieId)}`)
      .then(r => r.json())
      .then(shows => {
        const c = document.getElementById(`shows-${theaterId}`);
        if (!c) return;
        if (!shows.length) {
          c.innerHTML = `<span class="small" style="color:var(--bms-muted)">No shows available</span>`;
          return;
        }
        c.innerHTML = shows.map(s => `
          <a href="/shows/${s.show_id}/seats" class="show-time-btn">
            <div class="fw-bold" style="font-size:.88rem">${s.start_time ? s.start_time.slice(0,5) : '—'}</div>
            <div style="font-size:.72rem;color:var(--bms-muted)">${s.show_date}</div>
            <div style="font-size:.72rem;color:var(--bms-red)">₹${s.price_per_ticket}</div>
          </a>`).join("");
      })
      .catch(() => {
        const c = document.getElementById(`shows-${theaterId}`);
        if (c) c.innerHTML = `<span style="color:#ef4444;font-size:.8rem">Failed to load shows</span>`;
      });
  }

  function esc(str) {
    const d = document.createElement("div");
    d.textContent = str || "";
    return d.innerHTML;
  }
})();
