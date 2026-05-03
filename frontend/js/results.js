const results = JSON.parse(sessionStorage.getItem("rendevu_results") || "null");

const loadingEl = document.getElementById("loading");
const noResultsEl = document.getElementById("no-results");
const containerEl = document.getElementById("results-container");
const gridEl = document.getElementById("results-grid");

if (!results || results.length === 0) {
  loadingEl.hidden = true;
  noResultsEl.hidden = false;
} else {
  loadingEl.hidden = true;
  containerEl.hidden = false;
  document.getElementById("results-count").textContent =
    `${results.length} destination${results.length !== 1 ? "s" : ""} found`;
  renderResults(results);
}

document.getElementById("sort-by").addEventListener("change", (e) => {
  const key = e.target.value;
  const sorted = [...results].sort((a, b) => {
    if (key === "flights") return a.flight_cost - b.flight_cost;
    if (key === "lodging") return a.lodging_cost - b.lodging_cost;
    return a.total_cost - b.total_cost;
  });
  gridEl.innerHTML = "";
  sorted.forEach(r => gridEl.appendChild(buildCard(r)));
});

function renderResults(data) {
  data.forEach(r => gridEl.appendChild(buildCard(r)));
}

function buildCard(result) {
  const card = document.createElement("div");
  card.className = "destination-card";

  const flightsHtml = result.flights.map(f => `
    <div class="flight-item">
      <span class="item-details">
        ${f.origin_name} (${f.origin_iata}) &rarr; ${f.destination_iata}
        &nbsp;&middot;&nbsp; ${f.depart_date} &ndash; ${f.return_date}
        ${f.airline ? `&nbsp;&middot;&nbsp; ${f.airline}` : ""}
      </span>
      <span class="item-price">$${f.total_price.toLocaleString()}</span>
      <span class="item-book-links">
        ${f.outbound_url ? `<a href="${f.outbound_url}" target="_blank" rel="noopener" class="item-book">Outbound &nearr;</a>` : ""}
        ${f.return_url   ? `<a href="${f.return_url}"   target="_blank" rel="noopener" class="item-book">Return &nearr;</a>`   : ""}
      </span>
    </div>
  `).join("");

  const lodgingHtml = result.lodging_options.length
    ? result.lodging_options.map(l => `
        <div class="lodging-item">
          <span class="item-details">
            ${l.name} &middot; ${l.type}
            ${l.rating ? `&nbsp;&middot;&nbsp; &#9733; ${l.rating}` : ""}
            &nbsp;&middot;&nbsp; ${l.nights} nights
          </span>
          <span class="item-price">$${l.total_price.toLocaleString()}</span>
          ${l.booking_url
            ? `<a href="${l.booking_url}" target="_blank" rel="noopener" class="item-book">Book</a>`
            : ""}
        </div>
      `).join("")
    : `<p style="font-size:0.85rem;color:var(--color-text-muted)">No lodging results available.</p>`;

  card.innerHTML = `
    <div class="card-header">
      <h3>${result.destination_name} (${result.destination_iata})</h3>
      <div class="total-cost">$${result.total_cost.toLocaleString()} total</div>
    </div>
    <div class="cost-breakdown">
      <span>Flights: $${result.flight_cost.toLocaleString()}</span>
      <span>Lodging: $${result.lodging_cost.toLocaleString()}</span>
    </div>
    <div class="card-section">
      <h4>Flights</h4>
      ${flightsHtml}
    </div>
    <div class="card-section">
      <h4>Lodging</h4>
      ${lodgingHtml}
    </div>
  `;

  return card;
}
