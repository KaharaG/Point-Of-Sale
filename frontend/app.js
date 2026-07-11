/* app.js — all frontend logic. Talks to Python only via window.pywebview.api */

const fmt = (n) => `Ksh ${Number(n).toFixed(2)}`;

let cart = []; // { product_id, sku, name, track_by, imei (optional), qty, unit_price }

// ---------------- Clock ----------------
function tickClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleString("en-KE", { hour12: false });
}
setInterval(tickClock, 1000);
tickClock();

// ---------------- Tabs ----------------
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");

    if (btn.dataset.tab === "inventory") { loadInventory(); loadProductSelect(); }
    if (btn.dataset.tab === "history") loadHistory();
    if (btn.dataset.tab === "lowstock") loadLowStock();
  });
});

// ---------------- Scan input ----------------
const scanInput = document.getElementById("scanInput");
const scanMessage = document.getElementById("scanMessage");

function focusScan() { scanInput.focus(); }
focusScan();
document.addEventListener("click", (e) => {
  // Keep scan field focused unless user is typing elsewhere intentionally
  if (!["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) focusScan();
});

scanInput.addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  const code = scanInput.value.trim();
  scanInput.value = "";
  if (!code) return;

  const result = await window.pywebview.api.scan(code);
  handleScanResult(result, code);
});

function handleScanResult(result, code) {
  if (!result.found) {
    scanMessage.textContent = `No match found for "${code}"`;
    scanMessage.className = "scan-message error";
    return;
  }
  if (result.already_sold) {
    scanMessage.textContent = `IMEI ${code} is already marked SOLD — duplicate scan rejected`;
    scanMessage.className = "scan-message error";
    return;
  }

  const p = result.product;
  if (result.type === "imei") {
    addToCart({
      product_id: p.product_id,
      sku: p.sku,
      name: p.name,
      track_by: "imei",
      imei: p.imei,
      qty: 1,
      unit_price: p.price,
    });
    scanMessage.textContent = `Added: ${p.name} (IMEI ${p.imei})`;
    scanMessage.className = "scan-message ok";
  } else {
    addToCart({
      product_id: p.id,
      sku: p.sku,
      name: p.name,
      track_by: "qty",
      qty: 1,
      unit_price: p.price,
    });
    scanMessage.textContent = `Added: ${p.name}`;
    scanMessage.className = "scan-message ok";
  }
}

// ---------------- Manual search ----------------
const searchInput = document.getElementById("searchInput");
const searchResults = document.getElementById("searchResults");
let searchDebounce = null;

searchInput.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  const q = searchInput.value.trim();
  if (!q) { searchResults.innerHTML = ""; return; }
  searchDebounce = setTimeout(async () => {
    const results = await window.pywebview.api.search_products(q);
    renderSearchResults(results);
  }, 200);
});

function renderSearchResults(results) {
  searchResults.innerHTML = "";
  results.forEach(p => {
    const div = document.createElement("div");
    div.className = "search-result-item";
    div.innerHTML = `<div>${p.name}</div><div class="muted">${p.sku} · ${fmt(p.price)}</div>`;
    div.addEventListener("click", () => onSearchResultClick(p));
    searchResults.appendChild(div);
  });
}

async function onSearchResultClick(p) {
  if (p.track_by === "imei") {
    const imeis = await window.pywebview.api.get_available_imeis(p.id);
    if (imeis.length === 0) {
      scanMessage.textContent = `No available units in stock for ${p.name}`;
      scanMessage.className = "scan-message error";
      return;
    }
    addToCart({
      product_id: p.id, sku: p.sku, name: p.name,
      track_by: "imei", imei: imeis[0], qty: 1, unit_price: p.price,
    });
  } else {
    addToCart({
      product_id: p.id, sku: p.sku, name: p.name,
      track_by: "qty", qty: 1, unit_price: p.price,
    });
  }
  searchInput.value = "";
  searchResults.innerHTML = "";
  focusScan();
}

// ---------------- Cart ----------------
function addToCart(item) {
  if (item.track_by === "qty") {
    const existing = cart.find(c => c.track_by === "qty" && c.product_id === item.product_id);
    if (existing) { existing.qty += 1; renderCart(); return; }
  }
  cart.push(item);
  renderCart();
}

function removeFromCart(index) {
  cart.splice(index, 1);
  renderCart();
}

function renderCart() {
  const body = document.getElementById("cartBody");
  body.innerHTML = "";
  let total = 0;

  cart.forEach((item, idx) => {
    const subtotal = item.qty * item.unit_price;
    total += subtotal;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.name}</td>
      <td>${item.track_by === "imei" ? "IMEI " + item.imei : item.sku}</td>
      <td>${item.qty}</td>
      <td>${fmt(item.unit_price)}</td>
      <td>${fmt(subtotal)}</td>
      <td><button class="remove-btn" data-idx="${idx}">✕</button></td>
    `;
    body.appendChild(tr);
  });

  body.querySelectorAll(".remove-btn").forEach(btn => {
    btn.addEventListener("click", () => removeFromCart(Number(btn.dataset.idx)));
  });

  document.getElementById("cartTotal").textContent = fmt(total);
  document.getElementById("checkoutBtn").disabled = cart.length === 0;
}

// ---------------- Checkout ----------------
document.getElementById("checkoutBtn").addEventListener("click", async () => {
  if (cart.length === 0) return;
  const paymentMethod = document.getElementById("paymentMethod").value;
  const btn = document.getElementById("checkoutBtn");
  btn.disabled = true;
  btn.textContent = "Processing...";

  const result = await window.pywebview.api.checkout(cart, paymentMethod);

  btn.textContent = "Checkout";
  if (result.ok) {
    scanMessage.textContent = `Sale #${result.sale_id} complete — ${fmt(result.total)}`;
    scanMessage.className = "scan-message ok";
    cart = [];
    renderCart();
  } else {
    scanMessage.textContent = `Checkout failed: ${result.error}`;
    scanMessage.className = "scan-message error";
    btn.disabled = false;
  }
  focusScan();
});

// ---------------- Inventory: add product ----------------
const trackBySelect = document.querySelector('#addProductForm select[name="track_by"]');
const qtyFieldWrap = document.getElementById("qtyFieldWrap");
trackBySelect.addEventListener("change", () => {
  qtyFieldWrap.style.display = trackBySelect.value === "qty" ? "flex" : "none";
});

document.getElementById("addProductForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const result = await window.pywebview.api.add_product(
    f.get("sku"), f.get("name"), f.get("category"),
    f.get("price"), f.get("cost") || 0, f.get("track_by"),
    f.get("qty") || 0, f.get("reorder_level") || 5
  );
  const msg = document.getElementById("addProductMsg");
  if (result.ok) {
    msg.textContent = "Product added.";
    msg.className = "msg ok";
    e.target.reset();
    loadInventory();
    loadProductSelect();
  } else {
    msg.textContent = `Error: ${result.error}`;
    msg.className = "msg error";
  }
});

// ---------------- Inventory: add stock ----------------
const stockProductSelect = document.getElementById("stockProductSelect");
const qtyRestockWrap = document.getElementById("qtyRestockWrap");
const imeiRestockWrap = document.getElementById("imeiRestockWrap");

async function loadProductSelect() {
  const products = await window.pywebview.api.get_all_products();
  stockProductSelect.innerHTML = "";
  products.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.sku})`;
    opt.dataset.trackBy = p.track_by;
    stockProductSelect.appendChild(opt);
  });
  toggleRestockFields();
}

function toggleRestockFields() {
  const opt = stockProductSelect.selectedOptions[0];
  const trackBy = opt ? opt.dataset.trackBy : "qty";
  qtyRestockWrap.style.display = trackBy === "qty" ? "block" : "none";
  imeiRestockWrap.style.display = trackBy === "imei" ? "block" : "none";
}
stockProductSelect.addEventListener("change", toggleRestockFields);

document.getElementById("addStockForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const productId = f.get("product_id");
  const opt = stockProductSelect.selectedOptions[0];
  const trackBy = opt ? opt.dataset.trackBy : "qty";
  const msg = document.getElementById("addStockMsg");

  if (trackBy === "qty") {
    const result = await window.pywebview.api.restock_qty(productId, f.get("amount"));
    msg.textContent = result.ok ? "Stock updated." : `Error: ${result.error}`;
    msg.className = result.ok ? "msg ok" : "msg error";
  } else {
    const result = await window.pywebview.api.add_imei_units(productId, f.get("imei_text"));
    msg.textContent = `Added ${result.added.length} unit(s).` +
      (result.skipped.length ? ` Skipped ${result.skipped.length} duplicate(s).` : "");
    msg.className = "msg ok";
  }
  e.target.reset();
  loadInventory();
});

// ---------------- Inventory table ----------------
async function loadInventory() {
  const products = await window.pywebview.api.get_all_products();
  const tbody = document.querySelector("#inventoryTable tbody");
  tbody.innerHTML = "";
  products.forEach(p => {
    const stockDisplay = p.track_by === "imei" ? "— (see low stock tab)" : p.qty;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.sku}</td><td>${p.name}</td><td>${p.category || ""}</td>
      <td>${fmt(p.price)}</td><td>${p.track_by.toUpperCase()}</td><td>${stockDisplay}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---------------- Sales history ----------------
async function loadHistory() {
  const sales = await window.pywebview.api.get_sales_history(50);
  const tbody = document.querySelector("#historyTable tbody");
  tbody.innerHTML = "";
  sales.forEach(s => {
    const itemSummary = s.items.map(i => `${i.name} x${i.qty}`).join(", ");
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.id}</td><td>${new Date(s.timestamp).toLocaleString("en-KE")}</td>
      <td>${itemSummary}</td><td>${s.payment_method}</td><td>${fmt(s.total)}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ---------------- Low stock ----------------
async function loadLowStock() {
  const data = await window.pywebview.api.get_low_stock();
  const tbody = document.querySelector("#lowStockTable tbody");
  tbody.innerHTML = "";

  data.qty_items.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.sku}</td><td>${p.name}</td><td>QTY</td>
      <td><span class="badge low">${p.qty}</span></td><td>${p.reorder_level}</td>
    `;
    tbody.appendChild(tr);
  });

  data.imei_items.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.sku}</td><td>${p.name}</td><td>IMEI</td>
      <td><span class="badge low">${p.available}</span></td><td>${p.reorder_level}</td>
    `;
    tbody.appendChild(tr);
  });
}
