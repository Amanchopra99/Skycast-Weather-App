const form = document.querySelector("#search-form");
const cityInput = document.querySelector("#city-input");
const searchButton = document.querySelector("#search-button");
const message = document.querySelector("#message");
const weatherContent = document.querySelector("#weather-content");
const citySuggestions = document.querySelector("#city-suggestions");
let suggestionRequest;
let suggestionTimer;

function setText(id, value) {
  document.getElementById(id).textContent = value ?? "—";
}
function formatHour(value) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], {hour: "numeric"});
}
function formatDay(value, index) {
  if (index === 0) return "Today";
  if (index === 1) return "Tomorrow";
  return new Date(`${value}T12:00:00`).toLocaleDateString([], {weekday: "short"});
}
function formatDate(value) {
  const date = value ? new Date(value) : new Date();
  return date.toLocaleDateString([], {weekday:"long", month:"short", day:"numeric"});
}
function number(value, digits = 0) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(digits);
}

cityInput.addEventListener("input", () => {
  clearTimeout(suggestionTimer);
  const query = cityInput.value.trim();
  if (query.length < 2) {
    citySuggestions.replaceChildren();
    return;
  }

  suggestionTimer = setTimeout(async () => {
    suggestionRequest?.abort();
    suggestionRequest = new AbortController();
    try {
      const response = await fetch(`/api/cities?query=${encodeURIComponent(query)}`, {
        signal: suggestionRequest.signal,
      });
      const data = await response.json();
      citySuggestions.replaceChildren(
        ...(data.cities || []).map((city) => {
          const option = document.createElement("option");
          option.value = city.name;
          option.label = [city.admin1, city.country].filter(Boolean).join(", ");
          return option;
        }),
      );
    } catch (error) {
      if (error.name !== "AbortError") citySuggestions.replaceChildren();
    }
  }, 250);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const city = cityInput.value.trim();
  if (!city) return;
  searchButton.disabled = true;
  searchButton.textContent = "Loading…";
  message.textContent = "";
  try {
    const response = await fetch(`/api/weather?city=${encodeURIComponent(city)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load weather.");
    renderWeather(data);
    weatherContent.classList.remove("hidden");
    await loadHistory();
  } catch (error) {
    message.textContent = error.message || "Something went wrong. Please try again.";
  } finally {
    searchButton.disabled = false;
    searchButton.innerHTML = 'Search <span>↗</span>';
  }
});

function renderWeather(data) {
  const loc = data.location;
  const current = data.current;
  setText("place-name", loc.name);
  setText("place-region", [loc.admin1, loc.country].filter(Boolean).join(", "));
  setText("current-date", formatDate(current.time));
  setText("current-icon", current.icon);
  setText("temperature", number(current.temperature));
  setText("description", current.description);
  setText("feels-like", `${number(current.feels_like)}°`);
  setText("humidity", number(current.humidity));
  setText("wind", number(current.wind_speed, 1));
  setText("pressure", number(current.pressure));
  setText("precipitation", number(current.precipitation, 1));

  const hourlyList = document.querySelector("#hourly-list");
  hourlyList.innerHTML = data.hourly.map((hour) => `
    <article class="hour-card">
      <div class="hour-time">${formatHour(hour.time)}</div>
      <div class="hour-icon">${hour.icon}</div>
      <div class="hour-temp">${number(hour.temperature)}°</div>
      <div class="hour-rain">${hour.precipitation_probability ?? 0}% rain</div>
    </article>`).join("");

  const dailyList = document.querySelector("#daily-list");
  dailyList.innerHTML = data.daily.map((day, index) => `
    <div class="day-row">
      <div class="day-name">${formatDay(day.date, index)}</div>
      <div><span class="day-icon">${day.icon}</span></div>
      <div class="day-condition">${day.description}</div>
      <div class="day-temps">${number(day.max)}° <span>${number(day.min)}°</span></div>
      <div class="uv">UV ${number(day.uv_index, 1)}</div>
    </div>`).join("");

  const sunrise = data.daily?.[0]?.date;
  // The API response includes sunrise/sunset in the daily array only when requested.
  setText("sunrise", data.daily?.[0]?.sunrise ? formatHour(data.daily[0].sunrise) : "Daily forecast");
  setText("sunset", data.daily?.[0]?.sunset ? formatHour(data.daily[0].sunset) : "available");
}

async function loadHistory() {
  const container = document.querySelector("#history-list");
  try {
    const response = await fetch("/api/history");
    const data = await response.json();
    if (!data.history?.length) {
      container.innerHTML = `<p class="muted">${data.message || "Your searches will appear here after your first search."}</p>`;
      return;
    }
    container.innerHTML = data.history.map(item => `
      <button class="history-chip" data-city="${escapeHtml(item.city)}">
        <strong>${escapeHtml(item.city)}, ${escapeHtml(item.country || "")}</strong>
        <span>${number(item.temperature)}° · ${escapeHtml(item.description || "")}</span>
      </button>`).join("");
    container.querySelectorAll("[data-city]").forEach(button => {
      button.addEventListener("click", () => {
        cityInput.value = button.dataset.city;
        form.requestSubmit();
      });
    });
  } catch {
    container.innerHTML = '<p class="muted">Could not load search history.</p>';
  }
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[char]);
}
document.querySelector("#refresh-history").addEventListener("click", loadHistory);
loadHistory();
