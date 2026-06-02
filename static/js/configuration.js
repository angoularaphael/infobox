const $ = (id) => document.getElementById(id);

function showStatus(msg, type = "info") {
  const box = $("statusBox");
  box.className = `alert alert-${type}`;
  box.textContent = msg;
}

async function loadConfig() {
  const res = await fetch("/api/config");
  const data = await res.json();
  if (data.username_hint) {
    $("username").placeholder = data.username_hint;
  }
  if (data.configured) {
    showStatus(
      `Compte configuré${data.username_hint ? " (" + data.username_hint + ")" : ""} — source : ${data.source === "env" ? ".env" : "enregistrement local"}.`,
      "ok"
    );
  } else {
    showStatus("Aucun identifiant enregistré. La collecte automatique échouera sans connexion.", "warn");
  }
}

$("configForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = $("username").value.trim();
  const password = $("password").value;
  if (!username) {
    showStatus("Indiquez un nom d'utilisateur.", "err");
    return;
  }
  const body = { username };
  if (password) body.password = password;

  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    showStatus(data.error || "Erreur", "err");
    return;
  }
  $("password").value = "";
  showStatus(data.message || "Enregistré.", "ok");
  loadConfig();
});

$("btnTest").addEventListener("click", async () => {
  const password = $("password").value;
  if (password) {
    await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("username").value.trim(), password }),
    });
  }
  showStatus("Test de connexion en cours…", "info");
  const res = await fetch("/api/config/test", { method: "POST" });
  const data = await res.json();
  let msg = data.message || (data.ok ? "Connexion réussie." : "Échec");
  if (!data.ok && data.manual_mode) {
    msg += " → Utilisez le mode manuel (/manuel).";
  }
  showStatus(msg, data.ok ? "ok" : "err");
});

$("btnClear").addEventListener("click", async () => {
  if (!confirm("Supprimer les identifiants enregistrés via l'interface ?")) return;
  await fetch("/api/config", { method: "DELETE" });
  $("username").value = "";
  $("password").value = "";
  showStatus("Identifiants locaux supprimés (.env inchangé).", "info");
  loadConfig();
});

document.addEventListener("DOMContentLoaded", loadConfig);
