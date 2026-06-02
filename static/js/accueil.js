async function refreshHome() {
  const banner = document.getElementById("configBanner");
  const stats = document.getElementById("statsText");
  const people = loadPeople();

  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    if (!cfg.configured) {
      banner.hidden = false;
      banner.innerHTML =
        'Collecte auto non configurée — sans impact : utilisez l’<a href="/assistant">Assistant</a> (recommandé pour vos clients).';
    } else {
      banner.hidden = true;
    }
    const hint = cfg.username_hint ? ` (${cfg.username_hint})` : "";
    const source = cfg.source === "env" ? "fichier .env" : "interface";
    stats.textContent = `${people.length} contact(s) en mémoire. Connexion BoxRec : configurée${hint} via ${source}.`;
  } catch {
    stats.textContent = `${people.length} contact(s). Serveur injoignable.`;
  }
}

document.addEventListener("DOMContentLoaded", refreshHome);
