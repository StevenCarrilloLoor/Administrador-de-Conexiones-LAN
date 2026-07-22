/* Administrador de Conexiones LAN — logica del dashboard (Fase 1) */
"use strict";

const state = {
  devices: [],
  alerts: [],
  status: null,
  vendorChart: null,
  chartReady: false,
  editingId: null,
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

/* ------------------------------- render ---------------------------------- */
function renderStatus() {
  const st = state.status;
  if (!st) return;
  const caps = st.capabilities;

  // Banner de capacidades (solo si no puede escanear o hay mensajes relevantes)
  const banner = $("#cap-banner");
  if (!caps.can_scan) {
    banner.className = "banner banner-error";
    banner.innerHTML = "<b>⚠ Requisitos incompletos para escanear.</b><ul>" +
      caps.messages.map((m) => `<li>${esc(m)}</li>`).join("") + "</ul>";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  // Banner de exposicion/autenticacion
  const ab = $("#auth-banner");
  if (st.config.exposed_on_lan && !st.config.auth_enabled) {
    ab.innerHTML = "<b>El dashboard está expuesto en la LAN sin autenticación.</b> " +
      "La autenticación llega en la Fase 3; hasta entonces usá host 127.0.0.1 o protegé el acceso.";
    ab.classList.remove("hidden");
  } else { ab.classList.add("hidden"); }

  // Limitaciones (§8, documentadas en la propia UI)
  const ul = $("#limitations");
  ul.innerHTML = (st.limitations || []).map((l) => `<li>${esc(l)}</li>`).join("");

  // Ultimo escaneo + alertas
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
}

function deviceMatchesFilters(d) {
  const q = $("#search").value.trim().toLowerCase();
  if ($("#filter-online").checked && !d.online) return false;
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

  $("#empty-state").classList.toggle("hidden", state.devices.length !== 0);
  list.innerHTML = shown.map(renderDeviceCard).join("");
  $$(".edit-btn").forEach((b) => b.addEventListener("click", () => openEdit(Number(b.dataset.id))));
}

function renderDeviceCard(d) {
  const badges = [];
  if (d.device_type) badges.push(`<span class="badge type">${esc(d.device_type)}</span>`);
  if (d.device_group) badges.push(`<span class="badge group">${esc(d.device_group)}</span>`);
  if (d.is_random_mac) badges.push(`<span class="badge random" title="MAC localmente administrada/aleatoria">MAC aleatoria</span>`);
  const cls = ["device"]; if (d.online) cls.push("online"); if (d.is_blocked) cls.push("blocked");
  return `
  <div class="${cls.join(" ")}">
    <div class="device-head">
      <div class="device-name">
        <span class="status-dot ${d.online ? "online" : ""}" title="${d.online ? "en línea" : "fuera de línea"}"></span>
        <span class="txt" title="${esc(d.display_name)}">${esc(d.display_name)}</span>
      </div>
      <button class="edit-btn" data-id="${d.id}" title="Editar nombre y grupo">✎</button>
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

/* ------------------------------- edicion --------------------------------- */
function openEdit(id) {
  const d = state.devices.find((x) => x.id === id);
  if (!d) return;
  state.editingId = id;
  $("#edit-meta").innerHTML = `${esc(d.ip || "—")} · ${esc(d.mac)} · ${esc(d.vendor || "fabricante desconocido")}`;
  $("#edit-name").value = d.custom_name || "";
  $("#edit-group").value = d.device_group || "";
  $("#edit-modal").classList.remove("hidden");
  $("#edit-name").focus();
}
function closeEdit() { $("#edit-modal").classList.add("hidden"); state.editingId = null; }

async function saveEdit() {
  if (state.editingId == null) return;
  const body = { custom_name: $("#edit-name").value.trim(), device_group: $("#edit-group").value.trim() };
  try {
    await api(`/api/devices/${state.editingId}`, { method: "PATCH", body: JSON.stringify(body) });
    closeEdit();
    toast("Dispositivo actualizado", "good");
    loadDevices();
  } catch (e) { toast("No se pudo guardar: " + e.message, "bad"); }
}

/* ------------------------------- escaneo --------------------------------- */
async function doScan() {
  const btn = $("#scan-btn");
  btn.disabled = true; btn.classList.add("scanning");
  try {
    const r = await api("/api/network/scan");
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
      state.devices = msg.data.devices; renderDevices(); renderStats(); populateGroups();
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

/* ------------------------------- init ------------------------------------ */
function bindUI() {
  $("#scan-btn").addEventListener("click", doScan);
  $("#search").addEventListener("input", renderDevices);
  $("#filter-online").addEventListener("change", renderDevices);
  $("#group-filter").addEventListener("change", renderDevices);
  $("#edit-cancel").addEventListener("click", closeEdit);
  $("#edit-save").addEventListener("click", saveEdit);
  $("#edit-modal").addEventListener("click", (e) => { if (e.target.id === "edit-modal") closeEdit(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeEdit();
    if (e.key === "Enter" && state.editingId != null) saveEdit();
  });
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
  connectWS();
  // Respaldo por si el WS se cae: refresco suave periodico
  setInterval(() => { loadStatus(); }, 15000);
}

document.addEventListener("DOMContentLoaded", init);
