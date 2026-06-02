const $ = (id) => document.getElementById(id);

function getBookmarkletHref() {
  const urlField = $("bookmarkletUrl");
  const fromField = urlField?.value?.trim() || "";
  if (fromField.startsWith("javascript:")) return fromField;
  const link = $("bookmarkletBtn");
  const fromLink = link?.getAttribute("href") || "";
  if (fromLink.startsWith("javascript:")) return fromLink;
  return "";
}

async function copyBookmarkletLink() {
  let href = getBookmarkletHref();
  if (!href) {
    try {
      const res = await fetch("/api/bookmarklet");
      const data = await res.json();
      href = data.href || "";
      const link = $("bookmarkletBtn");
      if (link && href.startsWith("javascript:")) link.href = href;
    } catch {
      /* ignore */
    }
  }
  const urlField = $("bookmarkletUrl");
  const status = $("copyStatus");
  if (!href.startsWith("javascript:")) {
    if (status) status.textContent = "Rechargez la page (python app.py doit tourner).";
    return;
  }
  if (urlField) urlField.value = href;
  try {
    await navigator.clipboard.writeText(href);
    if (status) {
      status.textContent = "Copié. Ctrl+Shift+O → nouveau favori → coller l’URL.";
    }
  } catch {
    urlField?.select();
    if (status) status.textContent = "Sélectionnez le texte ci-dessus et Ctrl+C.";
  }
}

async function setupBookmarklet() {
  let href = "";
  try {
    const res = await fetch("/api/bookmarklet");
    const data = await res.json();
    href = data.href || "";
  } catch {
    href = "";
  }
  const urlField = $("bookmarkletUrl");
  const errBox = $("favoriErreur");
  const dlBtn = $("btnDownloadFavori");
  const link = $("bookmarkletBtn");

  if (!href.startsWith("javascript:")) {
    if (errBox) {
      errBox.style.display = "block";
      errBox.innerHTML =
        "<strong>InfoBox non prêt.</strong> Lancez <code>python app.py</code> dans le dossier du projet, puis rechargez cette page (F5).";
    }
    if (dlBtn) dlBtn.style.pointerEvents = "none";
    return;
  }

  if (urlField) urlField.value = href;
  if (link) {
    link.href = href;
    link.draggable = true;
    link.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", href);
      e.dataTransfer.setData("text/uri-list", href);
      e.dataTransfer.effectAllowed = "copy";
    });
    link.addEventListener("click", (e) => {
      e.preventDefault();
      copyBookmarkletLink();
    });
  }
  $("btnCopyBookmarklet")?.addEventListener("click", copyBookmarkletLink);
}

function showFavoriInstallHint() {
  const params = new URLSearchParams(window.location.search);
  const el = $("favoriErreur");
  if (!el) return;
  const fromBoxrec = /boxrec\.com/i.test(document.referrer || "");
  const badParam =
    params.get("erreur") === "favori-invalide" || params.get("from") === "badbookmark";
  if (fromBoxrec || badParam) {
    el.style.display = "block";
    el.innerHTML =
      "<strong>Mauvais favori.</strong> Vous venez de BoxRec : le favori enregistre cette page, pas le script. " +
      "Supprimez-le, cliquez <strong>Copier le lien du favori</strong> ci-dessous, puis créez un nouveau favori (URL = javascript:…).";
  }
}

function setImportStatus(msg, err = false) {
  const el = $("importStatus");
  el.textContent = msg;
  el.classList.toggle("error", err);
}

function parseCsvToPeople(text) {
  let lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter((l) => l.trim());
  lines = lines.filter((l) => !l.toLowerCase().startsWith("sep="));
  if (lines.length < 2) return [];
  const sep = lines[0].includes(";") ? ";" : ",";
  const people = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = [];
    let cur = "";
    let inQ = false;
    for (const ch of lines[i]) {
      if (ch === '"') inQ = !inQ;
      else if (ch === sep && !inQ) {
        cols.push(cur);
        cur = "";
      } else cur += ch;
    }
    cols.push(cur);
    people.push({
      name: cols[0] || "",
      email: cols[1] || "",
      phone: cols[2] || "",
      address: cols.length >= 7 ? cols[3] || "" : "",
      role: cols.length >= 7 ? cols[4] || "" : cols[3] || "",
      search_country: cols.length >= 7 ? cols[5] || "" : cols.length >= 6 ? cols[4] || "" : "",
      location:
        cols.length >= 7 ? cols[6] || "" : cols.length >= 6 ? cols[5] || "" : cols[4] || "",
    });
  }
  return people;
}

function parseInputToBody() {
  const raw = $("importJson").value.trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    if (raw.includes("nom,") || raw.includes("nom;")) {
      const people = parseCsvToPeople(raw);
      if (!people.length) return { error: "CSV vide ou illisible." };
      return { people, role: people[0]?.role || "manager" };
    }
    return { error: "Collez après le favori (Ctrl+V) ou chargez le CSV." };
  }
}

function getPeopleForExport() {
  const stored = loadPeople();
  if (stored.length) return stored;
  const body = parseInputToBody();
  if (body?.people?.length) return body.people;
  return [];
}

async function sendImport(body, { downloadPdfAfter = true } = {}) {
  setImportStatus("Import en cours…");
  const res = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    setImportStatus(data.error || "Erreur", true);
    return;
  }
  const people = data.people || [];
  savePeople(people);
  if (downloadPdfAfter && people.length) {
    try {
      exportPdfClient(people, `BoxRec — ${body.role || "contacts"}`);
    } catch (_) {
      /* ignore */
    }
  }
  setImportStatus(`${data.count} contact(s) importés. Utilisez CSV ou PDF ci-dessous.`);
}

const btnImport = $("btnImport");
if (btnImport) {
  btnImport.addEventListener("click", async () => {
  const body = parseInputToBody();
  if (!body) {
    setImportStatus("Collez après le favori (Ctrl+V), ou choisissez le fichier CSV.", true);
    return;
  }
  if (body.error) {
    setImportStatus(body.error, true);
    return;
  }
  await sendImport(body, { downloadPdfAfter: false });
  });
}

const btnPdf = $("btnPdf");
if (btnPdf) {
  btnPdf.addEventListener("click", () => {
  const people = getPeopleForExport();
  if (!people.length) {
    setImportStatus("Importez d'abord des données ou collez après le favori.", true);
    return;
  }
  const role = people[0]?.role || "contacts";
  exportPdfClient(people, `BoxRec — ${role}`);
  setImportStatus("PDF téléchargé.");
  });
}

const btnCsv = $("btnCsv");
if (btnCsv) {
  btnCsv.addEventListener("click", () => {
  const people = getPeopleForExport();
  if (!people.length) {
    setImportStatus("Importez d'abord des données ou collez après le favori.", true);
    return;
  }
  exportCsvClient(people);
  setImportStatus("CSV téléchargé.");
  });
}

const importCsvFile = $("importCsvFile");
if (importCsvFile) {
  importCsvFile.addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const people = parseCsvToPeople(String(reader.result));
    if (!people.length) {
      setImportStatus("Fichier CSV vide.", true);
      return;
    }
    sendImport({ people, role: people[0]?.role || "manager" });
  };
  reader.readAsText(file, "UTF-8");
  });
}

function updateServerStatus(ok, label) {
  const el = $("serverStatus");
  if (!el) return;
  el.textContent = label;
  el.classList.toggle("ok", ok);
  el.classList.toggle("err", !ok);
}

document.addEventListener("DOMContentLoaded", () => {
  showFavoriInstallHint();
  setupBookmarklet();
  fetch("/api/health")
    .then((r) => r.json())
    .then(() => updateServerStatus(true, "Serveur prêt"))
    .catch(() => updateServerStatus(false, "Lancez python app.py"));
});
