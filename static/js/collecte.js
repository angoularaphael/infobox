let people = [];
let eventSource = null;
let stopped = false;

const $ = (id) => document.getElementById(id);

function setStatus(msg, isError = false) {
  $("statusText").textContent = msg;
  $("statusText").classList.toggle("error", isError);
}

function setProgress(pct) {
  $("progressFill").style.width = `${Math.min(100, pct)}%`;
}

function finishScrape(keepError = false) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  $("btnScrape").disabled = false;
  $("btnStop").disabled = true;
  if (!keepError && people.length === 0) {
    setStatus(
      "Aucun résultat. Vérifiez la configuration BoxRec ou utilisez le mode manuel.",
      true
    );
  }
}

async function checkAuth() {
  const res = await fetch("/api/config");
  const cfg = await res.json();
  $("authWarning").hidden = !!cfg.configured;
}

async function startScrape() {
  stopped = false;
  people = [];
  setProgress(0);
  $("btnScrape").disabled = true;
  $("btnStop").disabled = false;

  const role = $("role").value;
  const fetchContacts = $("fetchContacts").checked;
  const maxPagesVal = $("maxPages").value;
  const body = { role, fetch_contacts: fetchContacts };
  if (maxPagesVal) body.max_pages = parseInt(maxPagesVal, 10);

  setStatus("Démarrage…");

  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);

    const jobId = data.job_id;
    setStatus(`Collecte en cours…`);

    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/scrape/${jobId}/stream`);

    eventSource.onmessage = (ev) => {
      if (stopped) return;
      const evt = JSON.parse(ev.data);
      if (evt.type === "person") {
        people.push(evt.person);
        savePeople(people);
        setStatus(`${people.length} contact(s) — page ${evt.page}`);
        setProgress(Math.min(95, people.length));
      } else if (evt.type === "page_done") {
        setStatus(`Page ${evt.page} — ${evt.count} contact(s)`);
      } else if (evt.type === "done") {
        setStatus(`Terminé : ${evt.count} contact(s). Ouvrez la page Résultats.`);
        setProgress(100);
        finishScrape();
      } else if (evt.type === "error") {
        setStatus(evt.message, true);
        finishScrape(true);
      } else if (evt.type === "timeout") {
        setStatus("Flux interrompu — résultats partiels enregistrés.", true);
        finishScrape(true);
      }
    };

    eventSource.onerror = () => {
      fetch(`/api/scrape/${jobId}`)
        .then((r) => r.json())
        .then((j) => {
          if (j.people?.length) {
            people = j.people;
            savePeople(people);
          }
          if (j.error) setStatus(j.error, true);
          else if (j.status === "done") setStatus(`Terminé : ${j.count} contact(s).`);
        })
        .finally(finishScrape);
    };
  } catch (err) {
    setStatus(err.message, true);
    finishScrape(true);
  }
}

$("btnScrape").addEventListener("click", startScrape);
$("btnStop").addEventListener("click", () => {
  stopped = true;
  finishScrape();
  setStatus("Suivi arrêté (la collecte serveur peut continuer).");
});

document.addEventListener("DOMContentLoaded", () => {
  people = loadPeople();
  checkAuth();
  setStatus("Prêt.");
});
