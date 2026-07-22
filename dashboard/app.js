/* Administrador de Conexiones LAN — lógica del dashboard */
"use strict";

const DOW = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

const state = {
  devices: [],
  alerts: [],
  rules: [],
  status: null,
  vendorChart: null,
  chartReady: false,
  editingId: null,
  view: "inventario",
};

/* ------------------------------- utilidades ------------------------------ */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts) {
  const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
  // Sesión expirada o ausente: el middleware responde 401 -> volver al login.
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("No autenticado");
  }
  if (!res.ok && res.status !== 501) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

function relTime(iso) {
  if (!iso) return "nunca";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "—";
  const s = Math.round((Date.now() - then) / 1000);
  if (s < 5) return "ahora";
  if (s < 60) return `hace ${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `hace ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.round(h / 24);
  return `hace ${d} d`;
}

function absTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleString();
}

function toast(msg, kind) {
  const el = document.createElement("div");
  el.className = "toast " + (kind || "");
  el.textContent = msg;
  $("#toast-container").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .4s"; }, 3600);
  setTimeout(() => el.remove(), 4100);
}

/* ------------------------------- carga de datos -------------------------- */
async function loadStatus() {
  try {
    state.status = await api("/api/status");
    renderStatus();
  } catch (e) { console.error("status", e); }
}

async function loadDevices() {
  try {
    state.devices = await api("/api/devices");
    renderDevices();
    renderStats();
    populateGroups();
    populateRuleTargets();
  } catch (e) { console.error("devices", e); }
}

async function loadAlerts() {
  try {
    state.alerts = await api("/api/alerts?limit=40");
    renderAlerts();
  } catch (e) { console.error("alerts", e); }
}

async function loadVendors() {
  try {
    const data = await api("/api/stats/vendors");
    renderVendorChart(data);
  } catch (e) { console.error("vendors", e); }
}

async function loadRules() {
  try {
    state.rules = await api("/api/rules");
    renderRules();
    renderCalendar();
  } catch (e) { console.error("rules", e); }
}

/* ------------------------------- render ---------------------------------- */
function renderStatus() {
  const st = state.status;
  if (!st) return;
  const caps = st.capabilities;

  // Botón de salir: solo si la autenticación está activa.
  $("#logout-btn").classList.toggle("hidden", !(st.config && st.config.auth_enabled));

  const banner = $("#cap-banner");
  if (!caps.can_scan) {
    banner.className = "banner banner-error";
    banner.innerHTML = "<b>⚠ Requisitos incompletos para escanear.</b><ul>" +
      caps.messages.map((m) => `<li>${esc(m)}</li>`).join("") + "</ul>";
    banner.classList.remove("hidden");
  } else if (caps.is_admin === false) {
    banner.className = "banner banner-warn";
    banner.innerHTML = "<b>Escaneo activo.</b> Estás sin privilegios de administrador: " +
      "el inventario y las alertas funcionan; fijar la ARP de defensa requiere administrador.";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  // Banner de exposición/autenticación
  const ab = $("#auth-banner");
  if (st.config.exposed_on_lan && !st.config.auth_enabled) {
    ab.innerHTML = "<b>El dashboard está expuesto en la LAN sin autenticación.</b> " +
      "Activá la autenticación (server.auth_required) o serví en 127.0.0.1.";
    ab.classList.remove("hidden");
  } else { ab.classList.add("hidden"); }

  const ul = $("#limitations");
  ul.innerHTML = (st.limitations || []).map((l) => `<li>${esc(l)}</li>`).join("");

  $("#stat-lastscan").textContent = relTime(st.scanner.last_scan_at);
  $("#stat-alerts").textContent = st.counts.alerts_unack;
}

function renderStats() {
  const online = state.devices.filter((d) => d.online).length;
  $("#stat-online").textContent = online;
  $("#stat-total").textContent = state.devices.length;
  const dayAgo = Date.now() - 86400e3;
  const recent = state.devices.filter((d) => d.first_seen && new Date(d.first_seen).getTime() >= dayAgo).length;
  $("#stat-new").textContent = recent;
  $("#stat-watched").textContent = state.devices.filter((d) => d.is_watched).length;
}

function deviceMatchesFilters(d) {
  const q = $("#search").value.trim().toLowerCase();
  if ($("#filter-online").checked && !d.online) return false;
  if ($("#filter-watched").checked && !d.is_watched) return false;
  const gf = $("#group-filter").value;
  if (gf && (d.device_group || "") !== gf) return false;
  if (!q) return true;
  return [d.ip, d.mac, d.custom_name, d.hostname, d.vendor, d.device_group, d.device_type, d.display_name]
    .filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
}

function ipSortKey(ip) {
  const p = String(ip || "").split(".").map(Number);
  return p.length === 4 && p.every((n) => !isNaN(n)) ? p[0] * 2 ** 24 + p[1] * 2 ** 16 + p[2] * 256 + p[3] : 2 ** 32;
}

function renderDevices() {
  const list = $("#device-list");
  const shown = state.devices.filter(deviceMatchesFilters).sort((a, b) => {
    if (a.online !== b.online) return a.online ? -1 : 1;
    return ipSortKey(a.ip) - ipSortKey(b.ip);
  });

  const es = $("#empty-state");
  if (state.devices.length === 0) {
    es.innerHTML = '<p>No hay dispositivos en el inventario todavía.</p>' +
      '<p class="muted">Ejecutá un escaneo. Si no encuentra nada, revisá Npcap y tu conexión a la LAN.</p>';
    es.classList.remove("hidden");
  } else if (shown.length === 0) {
    es.innerHTML = '<p>Sin resultados para el filtro actual.</p>' +
      '<p class="muted">Probá con otro texto de búsqueda, grupo, o quitá los filtros.</p>';
    es.classList.remove("hidden");
  } else {
    es.classList.add("hidden");
  }
  list.innerHTML = shown.map(renderDeviceCard).join("");
  $$(".edit-btn").forEach((b) => b.addEventListener("click", () => openEdit(Number(b.dataset.id))));
  $$(".watch-btn").forEach((b) => b.addEventListener("click", () => toggleWatch(Number(b.dataset.id))));
  $$(".wake-btn").forEach((b) => b.addEventListener("click", () => wakeDevice(Number(b.dataset.id))));
}

function renderDeviceCard(d) {
  const badges = [];
  if (d.device_type) badges.push(`<span class="badge type">${esc(d.device_type)}</span>`);
  if (d.device_group) badges.push(`<span class="badge group">${esc(d.device_group)}</span>`);
  if (d.is_watched) badges.push(`<span class="badge watched" title="Equipo vigilado">👁️ vigilado</span>`);
  if (d.is_random_mac) badges.push(`<span class="badge random" title="MAC localmente administrada/aleatoria">MAC aleatoria</span>`);
  const cls = ["device"]; if (d.online) cls.push("online"); if (d.is_blocked) cls.push("blocked");
  return `
  <div class="${cls.join(" ")}">
    <div class="device-head">
      <div class="device-name">
        <span class="status-dot ${d.online ? "online" : ""}" title="${d.online ? "en línea" : "fuera de línea"}"></span>
        <span class="txt" title="${esc(d.display_name)}">${esc(d.display_name)}</span>
      </div>
      <div class="device-actions">
        <button class="icon-btn watch-btn ${d.is_watched ? "on" : ""}" data-id="${d.id}" title="${d.is_watched ? "Dejar de vigilar" : "Vigilar (avisar si se cae)"}">👁️</button>
        <button class="icon-btn wake-btn" data-id="${d.id}" title="Encender (Wake-on-LAN)">⏻</button>
        <button class="icon-btn edit-btn" data-id="${d.id}" title="Editar nombre y grupo">✎</button>
      </div>
    </div>
    <div class="device-meta">
      <span class="k">IP</span><span class="v">${esc(d.ip || "—")}</span>
      <span class="k">MAC</span><span class="v">${esc(d.mac)}</span>
      <span class="k">Fabricante</span><span class="v">${esc(d.vendor || "Desconocido")}</span>
      <span class="k">Hostname</span><span class="v">${esc(d.hostname || "—")}</span>
      <span class="k">Visto</span><span class="v">${relTime(d.last_seen)} · alta ${relTime(d.first_seen)}</span>
    </div>
    <div class="badges">${badges.join("")}</div>
  </div>`;
}

function populateGroups() {
  const groups = [...new Set(state.devices.map((d) => d.device_group).filter(Boolean))].sort();
  const sel = $("#group-filter");
  const cur = sel.value;
  sel.innerHTML = '<option value="">Todos los grupos</option>' +
    groups.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join("");
  if (groups.includes(cur)) sel.value = cur;
  $("#group-suggestions").innerHTML = groups.map((g) => `<option value="${esc(g)}">`).join("");
}

function renderAlerts() {
  const box = $("#alert-list");
  const unack = state.alerts.filter((a) => !a.acknowledged).length;
  $("#alert-count").textContent = unack;
  if (!state.alerts.length) { box.innerHTML = '<p class="muted small">Sin alertas.</p>'; return; }
  const ico = { new_device: "🆕", device_down: "📴", arp_spoof_detected: "🛡️" };
  box.innerHTML = state.alerts.slice(0, 30).map((a) => `
    <div class="alert ${esc(a.severity)}">
      <span class="a-ico">${ico[a.alert_type] || "🔔"}</span>
      <div class="a-body">
        <div class="a-msg">${esc(a.message)}</div>
        <div class="a-time">${absTime(a.timestamp)}</div>
      </div>
      ${a.acknowledged ? "" : `<button class="a-ack" data-id="${a.id}">Visto</button>`}
    </div>`).join("");
  $$(".a-ack").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/alerts/${b.dataset.id}/ack`, { method: "POST" }); loadAlerts(); loadStatus(); }
    catch (e) { toast("No se pudo marcar la alerta: " + e.message, "bad"); }
  }));
}

const CHART_COLORS = ["#3d8bff","#37d67a","#ffb020","#ff5964","#a07aff","#22c3d6","#f078c8","#8bd450","#ff8a5b","#6f7f99"];

function renderVendorChart(data) {
  const canvas = $("#vendor-chart");
  if (!state.chartReady || !window.Chart) { $("#chart-fallback").classList.remove("hidden"); return; }
  if (!data || !data.length) { return; }
  const top = data.slice(0, 8);
  const rest = data.slice(8).reduce((s, x) => s + x.n, 0);
  const labels = top.map((x) => x.vendor.length > 22 ? x.vendor.slice(0, 21) + "…" : x.vendor);
  const values = top.map((x) => x.n);
  if (rest) { labels.push("Otros"); values.push(rest); }

  if (state.vendorChart) {
    state.vendorChart.data.labels = labels;
    state.vendorChart.data.datasets[0].data = values;
    state.vendorChart.update();
    return;
  }
  state.vendorChart = new window.Chart(canvas, {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: CHART_COLORS, borderColor: "#182234", borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "58%",
      plugins: { legend: { position: "bottom", labels: { color: "#93a3bd", boxWidth: 12, font: { size: 11 } } } },
    },
  });
}

/* ------------------------------- edición --------------------------------- */
function openEdit(id) {
  const d = state.devices.find((x) => x.id === id);
  if (!d) return;
  state.editingId = id;
  $("#edit-meta").innerHTML = `${esc(d.ip || "—")} · ${esc(d.mac)} · ${esc(d.vendor || "fabricante desconocido")}`;
  $("#edit-name").value = d.custom_name || "";
  $("#edit-group").value = d.device_group || "";
  $("#edit-watched").checked = !!d.is_watched;
  $("#edit-modal").classList.remove("hidden");
  $("#edit-name").focus();
}
function closeEdit() { $("#edit-modal").classList.add("hidden"); state.editingId = null; }

async function saveEdit() {
  if (state.editingId == null) return;
  const id = state.editingId;
  const d = state.devices.find((x) => x.id === id);
  const body = { custom_name: $("#edit-name").value.trim(), device_group: $("#edit-group").value.trim() };
  const wantWatch = $("#edit-watched").checked;
  try {
    await api(`/api/devices/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    if (d && !!d.is_watched !== wantWatch) {
      await api(`/api/devices/${id}/watch`, { method: "POST", body: JSON.stringify({ watched: wantWatch }) });
    }
    closeEdit();
    toast("Dispositivo actualizado", "good");
    loadDevices();
  } catch (e) { toast("No se pudo guardar: " + e.message, "bad"); }
}

async function toggleWatch(id) {
  const d = state.devices.find((x) => x.id === id);
  if (!d) return;
  try {
    const r = await api(`/api/devices/${id}/watch`, {
      method: "POST", body: JSON.stringify({ watched: !d.is_watched }),
    });
    d.is_watched = r.is_watched;
    toast(r.is_watched ? "Equipo marcado como vigilado" : "Se dejó de vigilar el equipo", "good");
    renderDevices(); renderStats();
  } catch (e) { toast("No se pudo cambiar la vigilancia: " + e.message, "bad"); }
}

async function wakeDevice(id) {
  const d = state.devices.find((x) => x.id === id);
  if (!d) return;
  try {
    await api(`/api/devices/${id}/wake`, { method: "POST" });
    toast(`Magic packet enviado a ${d.display_name}`, "good");
  } catch (e) { toast("No se pudo enviar Wake-on-LAN: " + e.message, "bad"); }
}

/* ------------------------------- reglas y horarios ----------------------- */
function populateRuleTargets() {
  const sel = $("#rule-target");
  if (!sel) return;
  const cur = sel.value;
  const groups = [...new Set(state.devices.map((d) => d.device_group).filter(Boolean))].sort();
  const devs = [...state.devices].sort((a, b) => ipSortKey(a.ip) - ipSortKey(b.ip));
  let html = '<optgroup label="Grupos">';
  html += groups.map((g) => `<option value="group:${esc(g)}">Grupo · ${esc(g)}</option>`).join("") ||
    '<option disabled>(sin grupos)</option>';
  html += '</optgroup><optgroup label="Dispositivos">';
  html += devs.map((d) => `<option value="dev:${d.id}">${esc(d.display_name)} · ${esc(d.ip || d.mac)}</option>`).join("");
  html += '</optgroup>';
  sel.innerHTML = html;
  if (cur) sel.value = cur;
}

function parseDays(s) {
  if (!s) return [];
  return String(s).split(",").map((x) => parseInt(x, 10)).filter((n) => n >= 0 && n <= 6);
}

function ruleTargetLabel(r) {
  if (r.device_group) return `Grupo · ${r.device_group}`;
  if (r.device_id != null) {
    const d = state.devices.find((x) => x.id === r.device_id);
    return d ? d.display_name : `Dispositivo #${r.device_id}`;
  }
  return "—";
}

function ruleTypeLabel(t) {
  return { schedule: "Horario", block: "Bloqueo", bandwidth_limit: "Límite BW" }[t] || t;
}

function renderRules() {
  const box = $("#rule-list");
  $("#rule-count").textContent = state.rules.length;
  if (!state.rules.length) { box.innerHTML = '<p class="muted small">Sin reglas configuradas.</p>'; return; }
  box.innerHTML = state.rules.map((r) => {
    const bits = [];
    if (r.rule_type === "schedule") {
      const days = parseDays(r.days_of_week).map((i) => DOW[i]).join(", ") || "todos los días";
      bits.push(`${esc(r.schedule_start || "?")}–${esc(r.schedule_end || "?")} · ${esc(days)}`);
    }
    if (r.rule_type === "bandwidth_limit") bits.push(`${esc(r.limit_kbps)} kbps`);
    return `
    <div class="rule-item">
      <span class="badge type">${esc(ruleTypeLabel(r.rule_type))}</span>
      <div class="rule-body">
        <div class="rule-target">${esc(ruleTargetLabel(r))}</div>
        <div class="rule-detail muted small">${bits.join(" · ") || "—"}</div>
      </div>
      <button class="btn btn-sm rule-del" data-id="${r.id}">Eliminar</button>
    </div>`;
  }).join("");
  $$(".rule-del").forEach((b) => b.addEventListener("click", () => deleteRule(Number(b.dataset.id))));
}

/* Vista semanal: 7 columnas (días) con franjas por regla de horario. */
function renderCalendar() {
  const cal = $("#calendar");
  if (!cal) return;
  const HOURS = 24, PXH = 26; // alto por hora
  let html = '<div class="cal-axis">';
  for (let h = 0; h <= 24; h += 3) html += `<div class="cal-hr" style="top:${h * PXH}px">${String(h).padStart(2, "0")}:00</div>`;
  html += '</div>';
  const schedules = state.rules.filter((r) => r.rule_type === "schedule");
  for (let day = 0; day < 7; day++) {
    html += `<div class="cal-col"><div class="cal-col-h">${DOW[day]}</div><div class="cal-track" style="height:${HOURS * PXH}px">`;
    schedules.forEach((r, idx) => {
      const days = parseDays(r.days_of_week);
      if (days.length && !days.includes(day)) return;
      const bands = timeBands(r.schedule_start, r.schedule_end);
      const color = CHART_COLORS[idx % CHART_COLORS.length];
      bands.forEach(([a, b]) => {
        const top = (a / 60) * PXH, hgt = ((b - a) / 60) * PXH;
        html += `<div class="cal-band" style="top:${top}px;height:${Math.max(hgt, 3)}px;background:${color}33;border-color:${color}"
          title="${esc(ruleTargetLabel(r))}: ${esc(r.schedule_start)}–${esc(r.schedule_end)}">
          <span>${esc(r.schedule_start)}</span></div>`;
      });
    });
    html += '</div></div>';
  }
  cal.innerHTML = html;
}

function toMin(hhmm) {
  const m = /^(\d{2}):(\d{2})$/.exec(hhmm || "");
  return m ? (+m[1]) * 60 + (+m[2]) : null;
}
// Devuelve tramos [inicioMin, finMin] dentro de un día; parte los que cruzan medianoche.
function timeBands(start, end) {
  const a = toMin(start), b = toMin(end);
  if (a == null || b == null) return [];
  if (a === b) return [[0, 1440]];
  if (a < b) return [[a, b]];
  return [[a, 1440], [0, b]]; // overnight
}

async function createRule(ev) {
  ev.preventDefault();
  const type = $("#rule-type").value;
  const target = $("#rule-target").value;
  if (!target) { toast("Elegí un dispositivo o grupo", "warn"); return; }
  const body = { rule_type: type };
  if (target.startsWith("group:")) body.device_group = target.slice(6);
  else if (target.startsWith("dev:")) body.device_id = Number(target.slice(4));
  if (type === "bandwidth_limit") {
    const kbps = parseInt($("#rule-kbps").value, 10);
    if (!kbps || kbps <= 0) { toast("Indicá un límite en kbps > 0", "warn"); return; }
    body.limit_kbps = kbps;
  }
  if (type === "schedule") {
    body.schedule_start = $("#rule-start").value;
    body.schedule_end = $("#rule-end").value;
    const days = [...$$(".dow:checked")].map((c) => c.value);
    if (!days.length) { toast("Seleccioná al menos un día", "warn"); return; }
    body.days_of_week = days.join(",");
  }
  try {
    await api("/api/rules", { method: "POST", body: JSON.stringify(body) });
    toast("Regla agregada", "good");
    loadRules();
  } catch (e) { toast("No se pudo crear la regla: " + e.message, "bad"); }
}

async function deleteRule(id) {
  try {
    await api(`/api/rules/${id}`, { method: "DELETE" });
    toast("Regla eliminada", "good");
    loadRules();
  } catch (e) { toast("No se pudo eliminar: " + e.message, "bad"); }
}

function onRuleTypeChange() {
  const t = $("#rule-type").value;
  $("#rule-bw-wrap").classList.toggle("hidden", t !== "bandwidth_limit");
  $("#rule-sched-wrap").classList.toggle("hidden", t !== "schedule");
}

/* ------------------------------- herramientas ---------------------------- */
async function runSpeedtest() {
  const btn = $("#speed-btn");
  btn.disabled = true; btn.textContent = "Midiendo…";
  try {
    const r = await api("/api/network/speedtest", { method: "POST" });
    $("#speed-result").classList.remove("hidden");
    $("#speed-lat").textContent = `${r.latency_ms} ms`;
    $("#speed-down").textContent = `${r.download_mbps} Mbps`;
    $("#speed-up").textContent = `${r.upload_mbps} Mbps`;
    toast("Test de velocidad completo", "good");
  } catch (e) {
    toast("No se pudo medir la velocidad: " + e.message, "bad");
  } finally {
    btn.disabled = false; btn.textContent = "Medir ahora";
  }
}

async function loadDefense() {
  try {
    const r = await api("/api/defense");
    $("#def-gw").textContent = r.gateway || "—";
    $("#def-base").textContent = r.baseline || "—";
    $("#def-cur").textContent = r.current || "—";
    const st = $("#def-state");
    if (r.gateway == null) { st.textContent = "sin gateway detectado"; st.className = "v"; }
    else if (r.spoofed) { st.textContent = "⚠ posible spoofing"; st.className = "v bad"; }
    else if (r.first_run) { st.textContent = "referencia fijada"; st.className = "v good"; }
    else { st.textContent = "✓ sin anomalías"; st.className = "v good"; }
  } catch (e) { toast("No se pudo leer la defensa: " + e.message, "bad"); }
}

async function defenseBaseline() {
  try { await api("/api/defense/baseline", { method: "POST" }); toast("Referencia ARP actualizada", "good"); loadDefense(); }
  catch (e) { toast("No se pudo fijar la referencia: " + e.message, "bad"); }
}

async function defensePin() {
  try {
    const r = await api("/api/defense/pin", { method: "POST" });
    toast("ARP fijada: " + (r.detail || "ok"), "good");
  } catch (e) { toast("No se pudo fijar la ARP (¿admin?): " + e.message, "bad"); }
}

async function loadNotif() {
  try {
    const r = await api("/api/notifications");
    const c = r.config || {};
    $("#n-tg-en").checked = !!(c.telegram && c.telegram.enabled);
    $("#n-tg-chat").value = (c.telegram && c.telegram.chat_id) || "";
    $("#n-ntfy-en").checked = !!(c.ntfy && c.ntfy.enabled);
    $("#n-ntfy-server").value = (c.ntfy && c.ntfy.server) || "https://ntfy.sh";
    $("#n-ntfy-topic").value = (c.ntfy && c.ntfy.topic) || "";
    $("#n-smtp-en").checked = !!(c.email && c.email.enabled);
    $("#n-smtp-host").value = (c.email && c.email.host) || "";
    $("#n-smtp-to").value = (c.email && c.email.to) || "";
    // Nota: los secretos (tokens/contraseñas) nunca vuelven del backend.
  } catch (e) { console.error("notif", e); }
}

function notifPayload() {
  const body = {
    telegram_enabled: $("#n-tg-en").checked,
    ntfy_enabled: $("#n-ntfy-en").checked,
    ntfy_server: $("#n-ntfy-server").value.trim(),
    ntfy_topic: $("#n-ntfy-topic").value.trim(),
    smtp_enabled: $("#n-smtp-en").checked,
    smtp_host: $("#n-smtp-host").value.trim(),
    smtp_to: $("#n-smtp-to").value.trim(),
    smtp_tls: $("#n-smtp-tls").checked,
  };
  // Solo mandamos secretos/campos sensibles si el usuario los completó (no pisar con vacío).
  const tok = $("#n-tg-token").value.trim(); if (tok) body.telegram_token = tok;
  const chat = $("#n-tg-chat").value.trim(); if (chat) body.telegram_chat_id = chat;
  const port = $("#n-smtp-port").value.trim(); if (port) body.smtp_port = port;
  const user = $("#n-smtp-user").value.trim(); if (user) body.smtp_user = user;
  const pass = $("#n-smtp-pass").value.trim(); if (pass) body.smtp_password = pass;
  const from = $("#n-smtp-from").value.trim(); if (from) body.smtp_from = from;
  return body;
}

async function saveNotif(ev) {
  ev.preventDefault();
  try {
    await api("/api/notifications", { method: "PUT", body: JSON.stringify(notifPayload()) });
    toast("Notificaciones guardadas", "good");
    $("#n-tg-token").value = ""; $("#n-smtp-pass").value = "";
    loadNotif();
  } catch (e) { toast("No se pudo guardar: " + e.message, "bad"); }
}

async function testNotif() {
  try {
    // Guardar primero para que la prueba use la configuración actual.
    await api("/api/notifications", { method: "PUT", body: JSON.stringify(notifPayload()) });
    const r = await api("/api/notifications/test", { method: "POST" });
    const ok = (r.results || []).filter((x) => x.ok).length;
    toast(`Prueba enviada: ${ok}/${(r.results || []).length} backend(s) OK`, ok ? "good" : "warn");
  } catch (e) { toast("No se pudo enviar la prueba: " + e.message, "bad"); }
}

/* ------------------------------- escaneo --------------------------------- */
async function doScan() {
  const btn = $("#scan-btn");
  btn.disabled = true; btn.classList.add("scanning");
  try {
    const r = await api("/api/network/scan", { method: "POST" });
    if (r && r.error) toast("Escaneo con error: " + r.error, "bad");
    else if (r && r.skipped) toast("Ya hay un escaneo en curso…", "warn");
    else {
      const n = (r.new || []).length, rc = (r.reconnected || []).length, dn = (r.disconnected || []).length;
      toast(`Escaneo: ${r.online_count} en línea · ${n} nuevo(s) · ${rc} reconexión(es) · ${dn} baja(s)`, "good");
    }
    await Promise.all([loadDevices(), loadStatus(), loadAlerts(), loadVendors()]);
  } catch (e) {
    toast("No se pudo escanear: " + e.message, "bad");
  } finally {
    btn.disabled = false; btn.classList.remove("scanning");
  }
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) {}
  location.href = "/login";
}

/* ------------------------------- WebSocket ------------------------------- */
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws;
  try { ws = new WebSocket(`${proto}://${location.host}/ws/live`); }
  catch (_) { setConn("down"); return setTimeout(connectWS, 4000); }

  ws.onopen = () => { setConn("live"); };
  ws.onclose = () => { setConn("down"); setTimeout(connectWS, 4000); };
  ws.onerror = () => { setConn("down"); };
  ws.onmessage = (ev) => {
    let msg; try { msg = JSON.parse(ev.data); } catch (_) { return; }
    if (msg.type === "hello" && msg.data && msg.data.devices) {
      state.devices = msg.data.devices; renderDevices(); renderStats(); populateGroups(); populateRuleTargets();
    } else if (msg.type === "scan") {
      const s = msg.data || {};
      (s.new || []).forEach((x) => toast(`Nuevo dispositivo: ${x.label} (${x.ip})`, "warn"));
      (s.disconnected || []).forEach((x) => toast(`Se desconectó: ${x.label}`, ""));
      Promise.all([loadDevices(), loadStatus(), loadAlerts(), loadVendors()]);
    }
  };
}
function setConn(kind) {
  const el = $("#conn-indicator");
  el.className = "conn-indicator " + (kind === "live" ? "live" : kind === "down" ? "down" : "");
  el.querySelector(".conn-label").textContent =
    kind === "live" ? "en vivo" : kind === "down" ? "reconectando…" : "conectando…";
}

/* ------------------------------- navegación ------------------------------ */
function switchView(name) {
  state.view = name;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  if (name === "reglas") loadRules();
  if (name === "herramientas") { loadDefense(); loadNotif(); }
}

/* ------------------------------- init ------------------------------------ */
function bindUI() {
  $("#scan-btn").addEventListener("click", doScan);
  $("#logout-btn").addEventListener("click", logout);
  $("#search").addEventListener("input", renderDevices);
  $("#filter-online").addEventListener("change", renderDevices);
  $("#filter-watched").addEventListener("change", renderDevices);
  $("#group-filter").addEventListener("change", renderDevices);
  $("#edit-cancel").addEventListener("click", closeEdit);
  $("#edit-save").addEventListener("click", saveEdit);
  $("#edit-modal").addEventListener("click", (e) => { if (e.target.id === "edit-modal") closeEdit(); });

  $$(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
  $("#rule-form").addEventListener("submit", createRule);
  $("#rule-type").addEventListener("change", onRuleTypeChange);
  $("#speed-btn").addEventListener("click", runSpeedtest);
  $("#def-refresh").addEventListener("click", loadDefense);
  $("#def-baseline").addEventListener("click", defenseBaseline);
  $("#def-pin").addEventListener("click", defensePin);
  $("#notif-form").addEventListener("submit", saveNotif);
  $("#notif-test").addEventListener("click", testNotif);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeEdit();
    if (e.key === "Enter" && state.editingId != null) saveEdit();
  });
  onRuleTypeChange();
}

function init() {
  bindUI();
  window.__loadChart((ok) => {
    state.chartReady = ok;
    if (!ok) $("#chart-fallback").classList.remove("hidden");
    loadVendors();
  });
  loadStatus();
  loadDevices();
  loadAlerts();
  loadRules();
  connectWS();
  setInterval(() => { loadStatus(); }, 15000);
}

document.addEventListener("DOMContentLoaded", init);
