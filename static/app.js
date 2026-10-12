// Side Quest — a tiny client. The screen should be the shortest part of the experience.

const app = document.getElementById("app");

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function duration(seconds) {
  const m = Math.round((seconds || 0) / 60);
  if (seconds < 60) return `${Math.max(0, Math.round(seconds || 0))}s`;
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60 ? `${m % 60}m` : ""}`.trim();
}

function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail?.[0]?.msg ?? body?.detail ?? `Request failed (${res.status})`);
  return body;
}

// --- screen-time counter -------------------------------------------------------------------
// Counts the seconds this page is actually visible while a quest is active. That number is the
// "screen" half of the screen-vs-outside ratio, so glancing at the card outside counts too.

const screenKey = (id) => `sq:screen:${id}`;
let screenTimer = null;

function trackScreen(id) {
  stopScreen();
  screenTimer = setInterval(() => {
    if (document.visibilityState !== "visible") return;
    try {
      localStorage.setItem(screenKey(id), String(Number(localStorage.getItem(screenKey(id)) || 0) + 1));
    } catch { /* private mode: the ratio just reads 0 */ }
  }, 1000);
}
function stopScreen() {
  if (screenTimer) clearInterval(screenTimer);
  screenTimer = null;
}
function screenSeconds(id) {
  try { return Number(localStorage.getItem(screenKey(id)) || 0); } catch { return 0; }
}

// Keep the current quest so the card still shows with no signal.
function remember(q) { try { localStorage.setItem("sq:current", JSON.stringify(q)); } catch {} }
function remembered() { try { return JSON.parse(localStorage.getItem("sq:current")); } catch { return null; } }

// --- views ---------------------------------------------------------------------------------

const choice = { minutes: 30, setting: "park", energy: "curious" };
const OPTIONS = {
  minutes: [[15, "15 min"], [30, "30 min"], [45, "45 min"], [60, "1 hour"]],
  setting: [["park", "Park"], ["street", "Street"], ["garden", "Garden"], ["water", "Lake / river"], ["woods", "Woods"], ["campus", "Campus"]],
  energy: [["calm", "Calm"], ["curious", "Curious"], ["active", "Active"]],
};

async function home() {
  document.body.classList.remove("outside");
  stopScreen();
  const chips = (key) =>
    OPTIONS[key].map(([v, label]) =>
      `<button class="chip" data-k="${key}" data-v="${v}" aria-pressed="${choice[key] === v}">${label}</button>`).join("");

  app.innerHTML = `
    <h1>Go outside. Come back with three things.</h1>
    <p class="lede">Tell me how long you've got. I'll give you one small quest, then you put your phone away.</p>
    <div class="group"><span class="label">Time</span><div class="chips">${chips("minutes")}</div></div>
    <div class="group"><span class="label">Where</span><div class="chips">${chips("setting")}</div></div>
    <div class="group"><span class="label">Mood</span><div class="chips">${chips("energy")}</div></div>
    <div class="stack"><button class="btn" id="go">Give me a quest</button></div>
    <p class="muted" id="ai" style="margin-top:12px"></p>
    <div id="stats"></div>`;

  app.querySelectorAll(".chip").forEach((b) =>
    b.addEventListener("click", () => {
      const k = b.dataset.k;
      choice[k] = k === "minutes" ? Number(b.dataset.v) : b.dataset.v;
      app.querySelectorAll(`.chip[data-k="${k}"]`).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    }));

  document.getElementById("go").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.innerHTML = `<span class="loading">Gemma is dreaming up a quest…</span>`;
    try {
      const q = await api("/quests", { method: "POST", body: JSON.stringify(choice) });
      location.hash = `#/quest/${q.id}`;
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Give me a quest";
      alertBox(err.message);
    }
  });

  api("/health").then(({ ai }) => {
    document.getElementById("ai").textContent = ai.available
      ? `● ${ai.message} (${ai.model})`
      : `○ ${ai.message}`;
  }).catch(() => {});

  api("/stats").then((s) => {
    if (!s.quests_done) return;
    document.getElementById("stats").innerHTML = `
      <div class="card">
        <h2>So far</h2>
        ${ratio(s.screen_seconds, s.outside_seconds)}
        <p class="muted">${s.quests_done} quest${s.quests_done > 1 ? "s" : ""} · ${s.finds_confirmed} finds confirmed by Gemma</p>
      </div>`;
  }).catch(() => {});
}

function ratio(screen, outside) {
  const total = Math.max(1, (screen || 0) + (outside || 0));
  return `
    <div class="ratio">
      <div><span class="muted">Outside</span><b>${duration(outside)}</b></div>
      <div><span class="muted">On screen</span><b>${duration(screen)}</b></div>
    </div>
    <div class="bar" aria-label="Screen time compared with time outside">
      <span class="scr" style="width:${((screen || 0) / total) * 100}%"></span><span class="out"></span>
    </div>`;
}

function findsList(q) {
  return `<ol class="finds">${q.finds.map((f) => `<li><span class="what">${esc(f.what)}</span><span class="hint">${esc(f.hint)}</span></li>`).join("")}</ol>`;
}

async function questView(id) {
  let q;
  try {
    q = await api(`/quests/${id}`);
    remember(q);
  } catch {
    q = remembered();
    if (!q || String(q.id) !== String(id)) return alertBox("Can't load this quest right now.");
  }
  trackScreen(q.id);
  ({ ready: cardView, out: outsideView, back: backView, done: entryView })[q.status](q);
}

function cardView(q) {
  document.body.classList.remove("outside");
  app.innerHTML = `
    <p class="muted">${q.minutes} min · ${esc(q.setting)} ${q.source === "ai" ? '· <span class="badge">by Gemma, on this computer</span>' : '· <span class="badge">from the offline deck</span>'}</p>
    <h1>${esc(q.title)}</h1>
    <p class="lede">${esc(q.intro)}</p>
    <div class="card">
      <h2>Find</h2>
      ${findsList(q)}
      <h2>Then sit</h2>
      <p>${esc(q.sit_spot)}</p>
      <h2 style="margin-top:14px">Turn back</h2>
      <p>${esc(q.turn_back)}</p>
    </div>
    ${q.safety_note ? `<p class="note sun">${esc(q.safety_note)}</p>` : ""}
    <p class="muted">Look, listen, photograph. Don't pick, touch or eat anything alive.</p>
    <div class="stack">
      <button class="btn" id="start">I'm heading out</button>
      <button class="btn ghost" id="again">Different quest</button>
    </div>`;
  document.getElementById("start").addEventListener("click", async () => {
    const started = await api(`/quests/${q.id}/start`, { method: "POST" });
    remember(started);
    outsideView(started);
  });
  document.getElementById("again").addEventListener("click", () => { location.hash = "#/"; });
}

function outsideView(q) {
  document.body.classList.add("outside");
  const startedAt = new Date(q.started_at).getTime();
  app.innerHTML = `
    <section class="outside-view">
      <p class="clock" id="clock">0:00 outside</p>
      <h1>Phone away.</h1>
      <p>Come back when you've found them, or after ${q.minutes} minutes.</p>
      <div style="text-align:left;margin:18px 0">${findsList(q)}</div>
      <button class="btn" id="back">I'm back</button>
      <p class="clock" style="margin-top:10px">This screen counts as screen time, so glance and go.</p>
    </section>`;
  const tick = () => {
    const el = document.getElementById("clock");
    if (el) el.textContent = `${clock((Date.now() - startedAt) / 1000)} outside`;
  };
  tick();
  const t = setInterval(() => (document.getElementById("clock") ? tick() : clearInterval(t)), 1000);
  document.getElementById("back").addEventListener("click", async () => {
    const back = await api(`/quests/${q.id}/back`, { method: "POST", body: JSON.stringify({ screen_seconds: screenSeconds(q.id) }) });
    remember(back);
    backView(back);
  });
}

const VERDICT = { yes: "Found it", maybe: "Close enough", no: "Not quite, but you looked", unchecked: "Saved (AI offline)" };

function backView(q) {
  document.body.classList.remove("outside");
  const photos = Object.fromEntries((q.photos || []).map((p) => [p.idx, p]));
  app.innerHTML = `
    <p class="muted">Welcome back · ${duration(q.outside_seconds)} outside</p>
    <h1>What did you find?</h1>
    <p class="lede">Add a photo for each find. Gemma checks them right here on this computer, and location data is removed first.</p>
    <div class="card">
      ${q.finds.map((f, i) => {
        const p = photos[i];
        return `
        <div class="photo-slot" data-idx="${i}">
          ${p ? `<img class="thumb" src="/api/photos/${esc(p.file)}" alt="">` : `<div class="thumb" aria-hidden="true">${i + 1}</div>`}
          <div>
            <div class="what"><b>${esc(f.what)}</b></div>
            <div class="status">${p ? `<span class="verdict-${esc(p.match)}">${VERDICT[p.match]}</span>${p.saw ? ` · ${esc(p.saw)}` : ""}` : ""}</div>
            <label class="file-btn">${p ? "Replace photo" : "Add photo"}
              <input type="file" accept="image/*" capture="environment" data-idx="${i}">
            </label>
          </div>
        </div>`;
      }).join("")}
    </div>
    <div class="card">
      <label for="heard"><b>Sit spot:</b> ${esc(q.sit_spot)}</label>
      <textarea id="heard" rows="2" maxlength="200" placeholder="What did you notice? (optional)" style="margin-top:8px">${esc(q.heard || "")}</textarea>
    </div>
    <div class="stack"><button class="btn" id="finish">Write my journal entry</button></div>`;

  app.querySelectorAll('input[type="file"]').forEach((input) =>
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      const slot = input.closest(".photo-slot");
      slot.querySelector(".status").innerHTML = `<span class="loading">Gemma is looking…</span>`;
      const form = new FormData();
      form.append("photo", file);
      try {
        const updated = await api(`/quests/${q.id}/finds/${input.dataset.idx}/photo`, { method: "POST", body: form });
        remember(updated);
        backView(updated);
      } catch (err) {
        slot.querySelector(".status").textContent = err.message;
      }
    }));

  document.getElementById("finish").addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    e.currentTarget.innerHTML = `<span class="loading">Writing your field notes…</span>`;
    const heard = document.getElementById("heard").value.trim() || null;
    const done = await api(`/quests/${q.id}/finish`, {
      method: "POST",
      body: JSON.stringify({ heard, screen_seconds: screenSeconds(q.id) }),
    });
    stopScreen();
    remember(done);
    entryView(done);
  });
}

function entryView(q) {
  document.body.classList.remove("outside");
  stopScreen();
  const photos = q.photos || [];
  app.innerHTML = `
    <p class="muted">${new Date(q.started_at || q.created_at).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p>
    <h1>${esc(q.title)}</h1>
    <div class="card">
      <p style="font-size:1.08rem;line-height:1.6">${esc(q.journal)}</p>
      <p class="muted" style="margin-top:8px">${q.journal_source === "ai" ? "Written by Gemma, on this computer, from what you found." : "From your quest notes."}</p>
      ${photos.length ? `<div class="gallery">${photos.map((p) => `<img src="/api/photos/${esc(p.file)}" alt="${esc(p.saw || "")}">`).join("")}</div>` : ""}
    </div>
    ${ratio(q.screen_seconds, q.outside_seconds)}
    <div class="stack">
      <a class="btn" href="#/">Another quest</a>
      <a class="btn ghost" href="#/journal">All entries</a>
    </div>`;
}

async function journalView() {
  document.body.classList.remove("outside");
  stopScreen();
  const [done, s] = await Promise.all([api("/quests?status=done"), api("/stats")]);
  app.innerHTML = `
    <h1>Field journal</h1>
    ${s.quests_done ? ratio(s.screen_seconds, s.outside_seconds) : ""}
    ${done.length ? `<ul class="journal-list card">${done.map((q) => `
      <li><a href="#/quest/${q.id}">
        <b>${esc(q.title)}</b><br>
        <span class="muted">${new Date(q.started_at).toLocaleDateString()} · ${duration(q.outside_seconds)} outside · ${(q.photos || []).filter((p) => p.match === "yes").length}/3 found</span>
      </a></li>`).join("")}</ul>` : `<p class="lede">No entries yet. <a href="#/">Go on a quest</a>.</p>`}`;
}

function alertBox(msg) {
  const p = document.createElement("p");
  p.className = "note sun";
  p.textContent = msg;
  app.prepend(p);
}

// --- router --------------------------------------------------------------------------------

function route() {
  const m = location.hash.match(/^#\/quest\/(\d+)/);
  if (m) return questView(m[1]);
  if (location.hash.startsWith("#/journal")) return journalView();
  return home();
}

window.addEventListener("hashchange", route);
route();

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
