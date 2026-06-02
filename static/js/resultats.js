const $ = (id) => document.getElementById(id);
let people = [];

function refresh() {
  people = loadPeople();
  renderResultsTable($("resultsTable").querySelector("tbody"), people);
  $("resultCount").textContent = `(${people.length})`;
  const has = people.length > 0;
  $("btnCsv").disabled = !has;
  $("btnPdfClient").disabled = !has;
  $("btnPdfServer").disabled = !has;
  $("emptyHint").hidden = has;
}

$("btnCsv").addEventListener("click", () => exportCsvClient(people));
$("btnPdfClient").addEventListener("click", () =>
  exportPdfClient(people, "BoxRec — Contacts")
);
$("btnPdfServer").addEventListener("click", async () => {
  try {
    await exportPdfServer(people, "BoxRec — Contacts");
  } catch {
    alert("Échec export PDF serveur.");
  }
});
$("btnClear").addEventListener("click", () => {
  if (!people.length || confirm("Supprimer tous les contacts de la session ?")) {
    clearPeople();
    refresh();
  }
});

document.addEventListener("DOMContentLoaded", refresh);
