// ---------- 1. State and talking to Python ----------
const ui = { tab: null };                 // which tab is open in this browser
const TAB_AFTER = { open: "mine", cancel: "mine", accept: "open", trade: "open", approve: "approvals", decline: "approvals" };
let data = null;                          // what the server last told us
let lastText = "";
const $ = (id) => document.getElementById(id);
const num = (n) => Number(n.toFixed(1));

// anything a person could type (names, notes) must be escaped before it goes into HTML
const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: res.status, ...(await res.json().catch(() => ({}))) };
}

function showLogin() {
  data = null; lastText = "";
  $("app").hidden = true;
  $("login").hidden = false;
  $("engine").textContent = "";
}
function showApp() {
  $("login").hidden = true;
  $("app").hidden = false;
}

async function refresh() {
  try {
    const res = await fetch("/api/state");
    if (res.status === 401) return showLogin();      // not logged in (or the login expired)
    const text = await res.text();
    if (text === lastText) return;                   // nothing changed, don't redraw
    lastText = text;
    data = JSON.parse(text);
    showApp();
    render();
  } catch (e) { /* server not reachable, try again at the next refresh */ }
}

async function send(name, id, give) {
  const result = await post(`/api/action/${name}`, give === undefined ? { id } : { id, give });
  if (result.status === 401) return showLogin();
  if (result.ok) ui.tab = TAB_AFTER[name];
  showToast(result.message);
  await refresh();
}

let toastTimer;
function showToast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 2800);
}

// ---------- 2. The screens ----------
const views = {
  mine() {
    if (!data.weeks.length) return `<p class="empty">No upcoming shifts.</p>`;
    return data.weeks.map((week) =>
      `<h2>${week.label} · ${num(week.hours)} / ${data.maxHours} h</h2>` +
      week.shifts.map((s) => {
        let actions = `<button data-action="open" data-id="${s.id}">Swap</button>`;
        if (s.swap && s.swap.status === "open") {
          actions = `<span class="badge">OPEN</span>
                     <button class="ghost" data-action="cancel" data-id="${s.swap.id}">Cancel</button>`;
        } else if (s.swap) {
          actions = `<span class="badge">${esc(s.swap.taker)} accepted${s.swap.give ? " (trade for " + esc(s.swap.give) + ")" : ""}. Waiting for manager</span>`;
        } else if (s.inTrade) {
          actions = `<span class="badge">Offered in a trade. Waiting for manager</span>`;
        }
        return `<div class="card"><div><b>${s.label}</b><small>${num(s.hours)} hours</small></div>
                <div class="actions">${actions}</div></div>`;
      }).join("")).join("");
  },

  open() {
    let html = "";
    html += data.available.length
      ? data.available.map((r) =>
          `<div class="card"><div><b>${r.shift.label}</b>
             <small>${esc(r.giver)}${r.canTake ? ` · your week: ${num(r.weekHoursAfter)} / ${data.maxHours} h` : " · trade only (hours limit)"}</small></div>
           <div class="actions">
             ${r.canTake ? `<button data-action="accept" data-id="${r.id}">Accept</button>` : ""}
             ${r.tradeOptions.length ? `<select id="give-${r.id}" aria-label="Shift you give back">
               ${r.tradeOptions.map((t) => `<option value="${t.id}">${t.label}</option>`).join("")}</select>
               <button class="ghost" data-action="trade" data-id="${r.id}">Trade</button>` : ""}
           </div></div>`).join("")
      : `<p class="empty">No open shifts you can take right now.</p>`;
    if (data.waiting.length) {
      html += `<h2>Waiting for manager</h2>` + data.waiting.map((r) =>
        `<div class="card"><div><b>${r.shift.label}</b><small>from ${esc(r.giver)}${r.give ? " · you give back " + esc(r.give) : ""}</small></div>
         <span class="badge">PENDING</span></div>`).join("");
    }
    return html;
  },

  approvals() {
    if (!data.approvals.length) return `<p class="empty">Nothing to approve.</p>`;
    return data.approvals.map((a) =>
      `<div class="card stack">
         <div><b>${esc(a.giver)} → ${esc(a.taker)}</b><small>${a.shift.label}${a.give ? " ⇄ " + esc(a.give) : ""}</small><br>
           <small>Week hours: ${esc(a.giver)} ${num(a.giverBefore)} → ${num(a.giverAfter)} h,
           ${esc(a.taker)} ${num(a.takerBefore)} → ${num(a.takerAfter)} h</small></div>
         <div class="row">
           <button class="ghost" data-action="decline" data-id="${a.id}">Decline</button>
           <button data-action="approve" data-id="${a.id}">Approve</button>
         </div></div>`).join("");
  },

  alerts() {
    if (!data.notifications.length) return `<p class="empty">No alerts yet.</p>`;
    return data.notifications.map((n) =>
      `<div class="note ${n.unread ? "new" : ""}"><span>${esc(n.text)}</span><small>${esc(n.time)}</small></div>`).join("");
  },
};

// ---------- 3. Draw the page ----------
function render() {
  const alerts = ["alerts", data.unread ? `Alerts (${data.unread})` : "Alerts"];
  const tabs = data.user.role === "manager"
    ? [["approvals", data.approvals.length ? `Approvals (${data.approvals.length})` : "Approvals"], alerts]
    : [["mine", "My shifts"],
       ["open", data.available.length ? `Open shifts (${data.available.length})` : "Open shifts"], alerts];
  if (!tabs.some((t) => t[0] === ui.tab)) ui.tab = tabs[0][0];

  $("engine").textContent = `Rules: ${data.engine}`;
  $("who").textContent = `${data.user.name} · ${data.user.role}`;
  $("tabs").innerHTML = tabs
    .map(([id, text]) => `<button class="${id === ui.tab ? "on" : ""}" data-tab="${id}">${text}</button>`).join("");
  $("screen").innerHTML = views[ui.tab]();
}

// ---------- 4. Clicks, login and logout ----------
document.addEventListener("click", (e) => {
  const tab = e.target.closest("[data-tab]");
  if (tab) {
    ui.tab = tab.dataset.tab;
    render();
    if (ui.tab === "alerts" && data.unread) post("/api/notifications/read", {}).then(refresh);
    return;
  }
  const btn = e.target.closest("[data-action]");
  if (btn) {
    const id = Number(btn.dataset.id);
    // a trade also sends the shift picked in the dropdown next to the button
    send(btn.dataset.action, id, btn.dataset.action === "trade" ? Number($(`give-${id}`).value) : undefined);
  }
});

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const result = await post("/api/login", { email: $("email").value, password: $("password").value });
  if (!result.ok) { $("login-error").textContent = result.message; return; }
  $("login-error").textContent = "";
  $("password").value = "";
  ui.tab = null;
  refresh();
});

$("logout").addEventListener("click", async () => {
  await post("/api/logout", {});
  showLogin();
});

refresh();
setInterval(refresh, 3000);     // pick up changes made on other phones or windows