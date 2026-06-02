/** État partagé entre les pages (sessionStorage). */
const STORAGE_KEY = "infobox_people";

function loadPeople() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function savePeople(list) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

function clearPeople() {
  sessionStorage.removeItem(STORAGE_KEY);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}

function downloadBlob(content, filename, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvToUtf16LeBlob(text) {
  const bytes = new Uint8Array(2 + text.length * 2);
  bytes[0] = 0xff;
  bytes[1] = 0xfe;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    bytes[2 + i * 2] = c & 0xff;
    bytes[2 + i * 2 + 1] = c >> 8;
  }
  return new Blob([bytes], { type: "text/csv;charset=utf-16le" });
}

function exportCsvClient(people) {
  const sep = ";";
  const headers = ["nom", "email", "telephone", "adresse", "role", "pays_recherche", "localisation"];
  const esc = (c) => `"${String(c || "").replace(/"/g, '""')}"`;
  const rows = people.map((p) =>
    [p.name, p.email, p.phone, p.address, p.role, p.search_country, p.location].map(esc).join(sep)
  );
  const csv = "sep=" + sep + "\n" + headers.join(sep) + "\n" + rows.join("\n");
  downloadBlob(csvToUtf16LeBlob(csv), "boxrec_contacts.csv", "text/csv;charset=utf-16le");
}

function exportPdfClient(people, title) {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  if (typeof renderContactsPdf === "function") {
    renderContactsPdf(doc, people, title || "BoxRec — Contacts", people[0]?.search_country || "");
  } else {
    doc.setFontSize(14);
    doc.text(title || "BoxRec — Contacts", 14, 15);
    doc.autoTable({
      startY: 22,
      theme: "grid",
      head: [["Nom", "Email", "Telephone", "Adresse", "Role", "Pays", "Localisation"]],
      body: people.map((p) => [
        p.name || "",
        p.email || "",
        p.phone || "",
        p.address || "",
        p.role || "",
        p.search_country || "",
        p.location || "",
      ]),
      styles: { fontSize: 8, lineWidth: 0.25 },
    });
  }
  doc.save("boxrec_contacts.pdf");
}

async function exportPdfServer(people, title) {
  const res = await fetch("/api/export/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ people, title: title || "BoxRec — Contacts" }),
  });
  if (!res.ok) throw new Error("Échec export PDF");
  const blob = await res.blob();
  downloadBlob(blob, "boxrec_contacts.pdf", "application/pdf");
}

function renderResultsTable(tbody, people) {
  tbody.innerHTML = "";
  for (const p of people) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.name || "")}</td>
      <td>${escapeHtml(p.email || "")}</td>
      <td>${escapeHtml(p.phone || "")}</td>
      <td>${escapeHtml(p.role || "")}</td>
      <td>${escapeHtml(p.search_country || "")}</td>
      <td>${escapeHtml(p.address || "")}</td>
      <td>${escapeHtml(p.location || "")}</td>`;
    tbody.appendChild(tr);
  }
}

function setActiveNav() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  document.querySelectorAll(".nav a").forEach((a) => {
    const href = a.getAttribute("href").replace(/\/$/, "") || "/";
    a.classList.toggle("active", href === path);
  });
}

document.addEventListener("DOMContentLoaded", setActiveNav);
