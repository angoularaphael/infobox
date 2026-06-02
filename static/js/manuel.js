const $ = (id) => document.getElementById(id);

function setStatus(msg, isError = false) {
  const el = $("statusText");
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

async function parseManual() {
  const html = $("manualHtml").value;
  if (!html.trim()) {
    setStatus("Collez d'abord le HTML.", true);
    return;
  }
  setStatus("Analyse en cours…");
  const role = $("role").value;
  const res = await fetch("/api/parse/manual", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      html,
      role,
      fetch_profiles: $("fetchContacts").checked,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    setStatus(data.error || "Erreur", true);
    return;
  }
  const people = data.people || [];
  savePeople(people);
  let msg = `${people.length} entrée(s) extraites.`;
  if (data.warning) msg += ` ${data.warning}`;
  if (data.is_login_page) {
    msg = "Page de connexion détectée — connectez-vous sur BoxRec et recopiez le HTML de la liste.";
    setStatus(msg, true);
    return;
  }
  setStatus(`${msg} Consultez les résultats.`);
  if (people.length) {
    setTimeout(() => {
      window.location.href = "/resultats";
    }, 800);
  }
}

$("btnManual").addEventListener("click", parseManual);
