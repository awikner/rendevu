const BACKEND_URL = "RENDER_BACKEND_URL_PLACEHOLDER";
const CLIENT_TOKEN = "RENDEVU_CLIENT_TOKEN_PLACEHOLDER";

// ── Dynamic row management ──────────────────────────────────────────────────

function makeOriginRow() {
  const row = document.createElement("div");
  row.className = "origin-row input-row";
  row.innerHTML = `
    <div class="input-group">
      <label>City</label>
      <input type="text" class="origin-name" placeholder="New York" required>
    </div>
    <div class="input-group input-group--short">
      <label>Airport code</label>
      <input type="text" class="origin-iata" placeholder="JFK" maxlength="3" required>
    </div>
    <div class="input-group input-group--short">
      <label>Travelers</label>
      <input type="number" class="origin-travelers" min="1" value="1" required>
    </div>
    <button type="button" class="btn-remove" aria-label="Remove">&#times;</button>
  `;
  row.querySelector(".btn-remove").addEventListener("click", () => {
    if (document.querySelectorAll(".origin-row").length > 1) row.remove();
  });
  return row;
}

function makeDestinationRow() {
  const row = document.createElement("div");
  row.className = "destination-row input-row";
  row.innerHTML = `
    <div class="input-group">
      <label>City</label>
      <input type="text" class="dest-name" placeholder="Paris" required>
    </div>
    <div class="input-group input-group--short">
      <label>Airport code</label>
      <input type="text" class="dest-iata" placeholder="CDG" maxlength="3" required>
    </div>
    <button type="button" class="btn-remove" aria-label="Remove">&#times;</button>
  `;
  row.querySelector(".btn-remove").addEventListener("click", () => {
    if (document.querySelectorAll(".destination-row").length > 1) row.remove();
  });
  return row;
}

document.getElementById("add-origin").addEventListener("click", () => {
  document.getElementById("origins-list").appendChild(makeOriginRow());
});

document.getElementById("add-destination").addEventListener("click", () => {
  document.getElementById("destinations-list").appendChild(makeDestinationRow());
});

// Wire up remove buttons on the initial static rows
document.querySelectorAll(".origin-row .btn-remove").forEach(btn => {
  btn.addEventListener("click", () => {
    if (document.querySelectorAll(".origin-row").length > 1)
      btn.closest(".origin-row").remove();
  });
});
document.querySelectorAll(".destination-row .btn-remove").forEach(btn => {
  btn.addEventListener("click", () => {
    if (document.querySelectorAll(".destination-row").length > 1)
      btn.closest(".destination-row").remove();
  });
});

// ── Date mode toggle ────────────────────────────────────────────────────────

document.querySelectorAll("input[name='date-mode']").forEach(radio => {
  radio.addEventListener("change", () => {
    const isSpecific = radio.value === "specific";
    document.getElementById("specific-dates-panel").hidden = !isSpecific;
    document.getElementById("triptype-panel").hidden = isSpecific;
  });
});

// ── Form submission ─────────────────────────────────────────────────────────

document.getElementById("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("form-error");
  errEl.hidden = true;

  const origins = [...document.querySelectorAll(".origin-row")].map(row => ({
    name: row.querySelector(".origin-name").value.trim(),
    iata: row.querySelector(".origin-iata").value.trim().toUpperCase(),
    travelers: parseInt(row.querySelector(".origin-travelers").value, 10),
  }));

  const destinations = [...document.querySelectorAll(".destination-row")].map(row => ({
    name: row.querySelector(".dest-name").value.trim(),
    iata: row.querySelector(".dest-iata").value.trim().toUpperCase(),
  }));

  if (origins.some(o => !o.name || !o.iata)) {
    showError(errEl, "Please fill in all origin city fields.");
    return;
  }
  if (destinations.some(d => !d.name || !d.iata)) {
    showError(errEl, "Please fill in all destination city fields.");
    return;
  }

  const dateMode = document.querySelector("input[name='date-mode']:checked").value;
  const body = {
    origins,
    destinations,
    flight_constraints: {
      nonstop_only: document.getElementById("nonstop-only").checked,
      max_duration_hours: parseFloatOrNull(document.getElementById("max-duration").value),
    },
    lodging: {
      rooms: parseInt(document.getElementById("rooms").value, 10),
      type: document.getElementById("lodging-type").value,
      min_rating: parseFloatOrNull(document.getElementById("min-rating").value),
    },
  };

  if (dateMode === "specific") {
    body.depart_date = document.getElementById("depart-date").value || null;
    body.return_date = document.getElementById("return-date").value || null;
  } else {
    body.trip_type = document.getElementById("trip-type").value;
    body.earliest_depart = document.getElementById("earliest-depart").value || null;
    body.latest_return = document.getElementById("latest-return").value || null;
  }

  const submitBtn = document.querySelector(".btn-search");
  submitBtn.disabled = true;
  submitBtn.textContent = "Searching…";

  try {
    const res = await fetch(`${BACKEND_URL}/api/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Token": CLIENT_TOKEN,
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const results = await res.json();
    sessionStorage.setItem("rendevu_results", JSON.stringify(results));
    window.location.href = "results.html";
  } catch (err) {
    showError(errEl, err.message || "Something went wrong. Please try again.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Search destinations";
  }
});

function showError(el, msg) {
  el.textContent = msg;
  el.hidden = false;
}

function parseFloatOrNull(val) {
  const n = parseFloat(val);
  return isNaN(n) ? null : n;
}
