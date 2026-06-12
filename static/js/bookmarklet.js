/**
 * Favori InfoBox — boxrec.com (utilisateur connecté).
 * v3.9 — erreur BoxRec TSB1, pauses anti-limite, captcha masquable
 */
const EMAIL_LABELS = ["email", "e-mail", "courriel", "mail"];
const PHONE_LABELS = [
  "phone",
  "phones",
  "telephone",
  "telephones",
  "téléphones",
  "téléphone",
  "tel",
  "mobile",
  "cell",
  "fax",
];
const ADDRESS_LABELS = ["residence", "company", "address", "adresse", "résidence", "société"];
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
const PROFILE_FETCH_DELAY_MS = 1100;
const PROFILE_RETRY_DELAY_MS = 1800;
const LIST_PAGE_DELAY_MS = 900;
const BOXREC_ERROR_RE = /something went wrong|return to the homepage|\bTSB\d+\b/i;

function listPageDelayMs() {
  return window.__infoboxThrottle ? 2800 : LIST_PAGE_DELAY_MS;
}

function profileFetchDelayMs() {
  return window.__infoboxThrottle ? 2200 : PROFILE_FETCH_DELAY_MS;
}

function markBoxRecThrottle() {
  window.__infoboxThrottle = true;
}

/** Décode les e-mails protégés par Cloudflare (data-cfemail sur BoxRec). */
function decodeCfEmail(hex) {
  if (!hex || hex.length < 4) return "";
  const r = parseInt(hex.slice(0, 2), 16);
  let out = "";
  for (let i = 2; i < hex.length; i += 2) {
    out += String.fromCharCode(parseInt(hex.slice(i, i + 2), 16) ^ r);
  }
  return out;
}

function isValidContactEmail(email) {
  if (!email || !email.includes("@")) return false;
  const low = email.toLowerCase();
  return !low.includes("boxrec.com") && !low.includes("example.com");
}

function addPhonesFromText(text, phones) {
  if (!text) return;
  const parts = text.split(/[\n,;|/]+/);
  for (const part of parts) {
    const p = part.trim();
    if (!p) continue;
    const intl = p.match(/\+\d[\d\s().-]{6,}/g);
    if (intl) intl.forEach((n) => phones.add(n.trim()));
    const digits = p.replace(/\D/g, "");
    if (digits.length >= 7 && digits.length <= 15) phones.add(p);
  }
}

function rowLabelName(tr) {
  const cell = tr.querySelector("td.rowLabel, th.rowLabel, th");
  if (!cell) return "";
  const b = cell.querySelector("b");
  return (b ? b.textContent : cell.textContent).trim().toLowerCase().replace(/:$/, "");
}

/** Toutes les cellules valeur (ignore rowLabel ; gère drapeau + texte sur 2+ colonnes). */
function rowValueCells(tr) {
  const labelCell = tr.querySelector("td.rowLabel, th.rowLabel");
  let cells = [...tr.querySelectorAll("td")].filter(
    (td) => !td.classList.contains("rowLabel") && td !== labelCell
  );
  if (!cells.length) {
    const th = tr.querySelector("th");
    const td = tr.querySelector("td");
    if (th && td && th !== labelCell) cells = [td];
  }
  if (!cells.length) {
    const tds = [...tr.querySelectorAll("td")];
    if (tds.length >= 2) cells = [tds[tds.length - 1]];
  }
  return cells;
}

function rowValueText(cells) {
  return cells
    .map((c) => c.textContent.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join(" ");
}

function labelMatches(label, keys) {
  return keys.some((k) => label === k || label.startsWith(k));
}

function fieldLabelFromNode(node) {
  if (!node) return "";
  const bold = node.querySelector(".font-bold, b, strong");
  const raw = (bold ? bold.textContent : node.textContent).trim().toLowerCase();
  return raw.replace(/:$/, "").replace(/^#/, "").trim();
}

function extractProfileDetailsFromFlexRows(root, target) {
  const emails = new Set();
  const phones = new Set();
  const addressParts = [];

  root.querySelectorAll("div.flex-row, div.flex.flex-row").forEach((row) => {
    const children = [...row.children].filter((el) => el.tagName === "DIV");
    if (children.length < 2) return;
    const label = fieldLabelFromNode(children[0]);
    if (!label) return;
    const valueCell = children[1];
    const val = valueCell.textContent.replace(/\s+/g, " ").trim();

    if (labelMatches(label, EMAIL_LABELS)) {
      valueCell.querySelectorAll("[data-cfemail]").forEach((el) => {
        const e = decodeCfEmail(el.getAttribute("data-cfemail"));
        if (isValidContactEmail(e)) emails.add(e);
      });
      valueCell.querySelectorAll('a[href^="mailto:"]').forEach((a) => {
        const e = a.getAttribute("href").replace(/^mailto:/i, "").split("?")[0].trim();
        if (isValidContactEmail(e)) emails.add(e);
      });
      const m = val.match(EMAIL_RE);
      if (m && isValidContactEmail(m[0])) emails.add(m[0]);
    }
    if (labelMatches(label, PHONE_LABELS)) {
      addPhonesFromText(val, phones);
      valueCell.querySelectorAll('a[href^="tel:"]').forEach((a) => {
        addPhonesFromText(a.getAttribute("href").replace(/^tel:/i, ""), phones);
      });
    }
    if (labelMatches(label, ADDRESS_LABELS) && val) addressParts.push(val);
  });

  mergeContactFields(target, emails, phones, addressParts);
}

function findProfileFlexScope(doc) {
  const h1 = doc.querySelector("h1");
  if (!h1) return null;
  let node = h1.parentElement;
  for (let n = 0; n < 25 && node; n++) {
    if (node.querySelector("div.flex-row .font-bold, div.flex.flex-row .font-bold")) return node;
    node = node.parentElement;
  }
  return null;
}

/** Toutes les tables « fiche » (rowLabel), pas le menu du site. */
function findProfileSections(doc) {
  const sections = [];
  doc.querySelectorAll("table").forEach((table) => {
    if (table.querySelector("td.rowLabel, th.rowLabel")) sections.push(table);
  });
  if (!sections.length) {
    const h1 = doc.querySelector("h1");
    if (h1) {
      let node = h1.parentElement;
      for (let n = 0; n < 16 && node; n++) {
        if (
          node.querySelector(
            "tr td.rowLabel, tr.drawRowBorder, tr th, a[href^='mailto:'], [data-cfemail], div.flex-row .font-bold"
          )
        ) {
          sections.push(node);
          break;
        }
        node = node.parentElement;
      }
    }
  }
  if (!sections.length && doc.body) sections.push(doc.body);
  return sections;
}

function profileContentScope(doc) {
  const h1 = doc.querySelector("h1");
  if (!h1) return doc.body || doc;
  let node = h1.parentElement;
  for (let n = 0; n < 20 && node; n++) {
    if (
      node.querySelector(
        "[data-cfemail], a[href^='mailto:'], td.rowLabel, tr.drawRowBorder, div.flex-row .font-bold"
      )
    ) {
      return node;
    }
    node = node.parentElement;
  }
  return doc.body || doc;
}

function scanProfileContactsGlobally(doc, target) {
  const emails = new Set();
  const phones = new Set();
  const scope = profileContentScope(doc);
  if (!scope) return;
  scope.querySelectorAll("[data-cfemail]").forEach((el) => {
    const e = decodeCfEmail(el.getAttribute("data-cfemail"));
    if (isValidContactEmail(e)) emails.add(e);
  });
  scope.querySelectorAll('a[href^="mailto:"]').forEach((a) => {
    const e = a.getAttribute("href").replace(/^mailto:/i, "").split("?")[0].trim();
    if (isValidContactEmail(e)) emails.add(e);
  });
  scope.querySelectorAll('a[href^="tel:"]').forEach((a) => {
    addPhonesFromText(a.getAttribute("href").replace(/^tel:/i, ""), phones);
  });
  mergeContactFields(target, emails, phones, []);
}

function mergeContactFields(target, emails, phones, addressParts) {
  if (emails.size && !target.email) target.email = [...emails][0];
  if (phones.size) {
    const merged = target.phone
      ? target.phone.split(/\s*;\s*/).concat([...phones])
      : [...phones];
    target.phone = [...new Set(merged.filter(Boolean))].join(" ; ");
  }
  if (addressParts.length) {
    const parts = target.address
      ? target.address.split(/\s*—\s*/).concat(addressParts)
      : addressParts;
    target.address = [...new Set(parts.filter(Boolean))].join(" — ");
  }
}

function extractProfileDetails(root, target) {
  const emails = new Set();
  const phones = new Set();
  const addressParts = [];

  root.querySelectorAll("tr").forEach((tr) => {
    const valueCells = rowValueCells(tr);
    if (!valueCells.length) return;
    const label = rowLabelName(tr);
    const val = rowValueText(valueCells);

    if (labelMatches(label, EMAIL_LABELS)) {
      valueCells.forEach((cell) => {
        cell.querySelectorAll("[data-cfemail]").forEach((el) => {
          const e = decodeCfEmail(el.getAttribute("data-cfemail"));
          if (isValidContactEmail(e)) emails.add(e);
        });
        cell.querySelectorAll('a[href^="mailto:"]').forEach((a) => {
          const e = a.getAttribute("href").replace(/^mailto:/i, "").split("?")[0].trim();
          if (isValidContactEmail(e)) emails.add(e);
        });
      });
      const m = val.match(EMAIL_RE);
      if (m && isValidContactEmail(m[0])) emails.add(m[0]);
    }

    if (labelMatches(label, PHONE_LABELS)) {
      addPhonesFromText(val, phones);
      valueCells.forEach((cell) => {
        cell.querySelectorAll('a[href^="tel:"]').forEach((a) => {
          addPhonesFromText(a.getAttribute("href").replace(/^tel:/i, ""), phones);
        });
      });
    }

    if (labelMatches(label, ADDRESS_LABELS) && val) addressParts.push(val);
  });

  mergeContactFields(target, emails, phones, addressParts);
}

/** Secours si le DOM change : lignes email/phones dans le HTML brut. */
function extractProfileDetailsFallback(html, target) {
  const chunk = html.split(/<h2[\s>]/i)[0] || html;
  const rowRe =
    /<tr[^>]*>[\s\S]*?<(?:td|th)[^>]*\browLabel\b[^>]*>[\s\S]*?<b>\s*([^<]+?)\s*<\/b>[\s\S]*?<\/(?:td|th)>((?:\s*<td[^>]*>[\s\S]*?<\/td>)+)/gi;
  let m;
  const emails = new Set();
  const phones = new Set();
  const addressParts = [];
  while ((m = rowRe.exec(chunk))) {
    const label = m[1].trim().toLowerCase().replace(/:$/, "");
    const cellsHtml = m[2];
    const cellText = cellsHtml
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    const cellHtml = cellsHtml;
    if (labelMatches(label, EMAIL_LABELS)) {
      const cf = cellHtml.match(/data-cfemail=["']([a-f0-9]+)["']/i);
      if (cf) {
        const e = decodeCfEmail(cf[1]);
        if (isValidContactEmail(e)) emails.add(e);
      }
      const em = cellText.match(EMAIL_RE);
      if (em && isValidContactEmail(em[0])) emails.add(em[0]);
    }
    if (labelMatches(label, PHONE_LABELS)) addPhonesFromText(cellText, phones);
    if (labelMatches(label, ADDRESS_LABELS) && cellText) addressParts.push(cellText);
  }
  const flexRe =
    /<div[^>]*class="[^"]*flex[^"]*flex-row[^"]*"[^>]*>[\s\S]*?(?:class="[^"]*font-bold[^"]*"[^>]*>|<b[^>]*>)\s*([^<]+?)\s*<\/(?:div|b|span)>[\s\S]*?<\/div>\s*<div[^>]*>([\s\S]*?)<\/div>\s*<\/div>/gi;
  while ((m = flexRe.exec(chunk))) {
    const label = m[1].trim().toLowerCase().replace(/:$/, "").replace(/^#/, "");
    const cellText = m[2]
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    const cellHtml = m[2];
    if (labelMatches(label, EMAIL_LABELS)) {
      const cf = cellHtml.match(/data-cfemail=["']([a-f0-9]+)["']/i);
      if (cf) {
        const e = decodeCfEmail(cf[1]);
        if (isValidContactEmail(e)) emails.add(e);
      }
      const em = cellText.match(EMAIL_RE);
      if (em && isValidContactEmail(em[0])) emails.add(em[0]);
    }
    if (labelMatches(label, PHONE_LABELS)) addPhonesFromText(cellText, phones);
    if (labelMatches(label, ADDRESS_LABELS) && cellText) addressParts.push(cellText);
  }
  mergeContactFields(target, emails, phones, addressParts);
}

function infoboxCancelled() {
  return !!window.__infoboxCancel;
}

function infoboxRequestCancel() {
  window.__infoboxCancel = true;
}

async function waitCancellable(ms) {
  const step = 250;
  let left = ms;
  while (left > 0) {
    if (infoboxCancelled()) return false;
    const chunk = Math.min(step, left);
    await new Promise((r) => setTimeout(r, chunk));
    left -= chunk;
  }
  return !infoboxCancelled();
}

function infoboxProgressShow(msg, sub, options) {
  const showStop = !options || options.showStop !== false;
  let root = document.getElementById("infobox-progress");
  let m = document.getElementById("infobox-progress-msg");
  if (!root || !m) {
    if (root) root.remove();
    root = document.createElement("div");
    root.id = "infobox-progress";
    root.innerHTML =
      '<div id="infobox-progress-overlay" class="infobox-overlay" style="position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,0.78);display:flex;align-items:center;justify-content:center;padding:0.75rem;font-family:Segoe UI,system-ui,sans-serif">' +
      '<div id="infobox-progress-card" style="background:#fff;padding:1.25rem 1.5rem;border-radius:12px;max-width:24rem;width:100%;text-align:center;border:2px solid #2563eb;box-shadow:0 16px 48px rgba(37,99,235,0.25);display:flex;flex-direction:column;max-height:min(92vh,560px)">' +
      '<div style="font-size:1.2rem;font-weight:700;color:#1d4ed8;margin-bottom:0.5rem;flex-shrink:0">InfoBox</div>' +
      '<div id="infobox-progress-msg" style="font-size:0.98rem;color:#1c1917;font-weight:600;flex-shrink:0"></div>' +
      '<div id="infobox-progress-actions" style="margin-top:0.85rem;flex-shrink:0"></div>' +
      '<div id="infobox-progress-sub" style="font-size:0.85rem;color:#57534e;margin-top:0.65rem;line-height:1.4;text-align:left;overflow-y:auto;flex:1;min-height:0"></div>' +
      "</div></div>";
    document.body.appendChild(root);
    m = document.getElementById("infobox-progress-msg");
  }
  const s = document.getElementById("infobox-progress-sub");
  const actions = document.getElementById("infobox-progress-actions");
  if (m) m.textContent = msg;
  if (s) s.textContent = sub || "Ne fermez pas cet onglet BoxRec.";
  if (actions) {
    if (options && options.preserveActions) {
      /* boutons captcha gérés par promptCaptchaResolved */
    } else if (showStop && !infoboxCancelled()) {
      actions.innerHTML =
        '<button type="button" id="infobox-progress-stop" style="cursor:pointer;padding:0.55rem 1.25rem;font-size:0.95rem;font-weight:600;border:2px solid #2563eb;background:#fff;color:#1d4ed8;border-radius:8px">Arrêter la collecte</button>';
      const stopBtn = document.getElementById("infobox-progress-stop");
      if (stopBtn && !stopBtn.dataset.bound) {
        stopBtn.dataset.bound = "1";
        stopBtn.addEventListener("click", () => {
          infoboxRequestCancel();
          infoboxProgressShow(
            "Arrêt en cours…",
            "La tâche en cours se termine, puis export partiel si possible.",
            { showStop: false }
          );
        });
      }
    } else {
      actions.innerHTML = "";
    }
  }
}

function infoboxProgressHide(delayMs) {
  setTimeout(() => {
    const el = document.getElementById("infobox-progress");
    if (el) el.remove();
    const floater = document.getElementById("infobox-captcha-float");
    if (floater) floater.remove();
  }, delayMs || 0);
}

function infoboxCaptchaMinimize(handlers) {
  const overlay = document.getElementById("infobox-progress-overlay");
  if (overlay) overlay.style.display = "none";
  let floater = document.getElementById("infobox-captcha-float");
  if (!floater) {
    floater = document.createElement("div");
    floater.id = "infobox-captcha-float";
    floater.style.cssText =
      "position:fixed;bottom:14px;right:14px;z-index:2147483647;background:#fff;border:2px solid #2563eb;border-radius:10px;padding:0.75rem 0.85rem;max-width:16rem;box-shadow:0 8px 28px rgba(37,99,235,0.35);font-family:Segoe UI,system-ui,sans-serif;font-size:0.85rem";
    document.body.appendChild(floater);
  }
  floater.innerHTML =
    '<div style="font-weight:700;color:#1d4ed8;margin-bottom:0.35rem">InfoBox — captcha</div>' +
    '<div style="color:#57534e;margin-bottom:0.55rem;line-height:1.35">Résolvez le reCAPTCHA sur BoxRec, puis continuez.</div>';
  const row = document.createElement("div");
  row.style.cssText = "display:flex;flex-wrap:wrap;gap:0.4rem";
  const cont = document.createElement("button");
  cont.type = "button";
  cont.textContent = "Continuer";
  cont.style.cssText =
    "cursor:pointer;padding:0.4rem 0.65rem;font-size:0.82rem;font-weight:700;border:0;background:#2563eb;color:#fff;border-radius:6px";
  cont.addEventListener("click", () => handlers?.onContinue?.());
  row.appendChild(cont);
  const show = document.createElement("button");
  show.type = "button";
  show.textContent = "Afficher";
  show.style.cssText =
    "cursor:pointer;padding:0.4rem 0.65rem;font-size:0.82rem;font-weight:600;border:1px solid #94a3b8;background:#fff;color:#475569;border-radius:6px";
  show.addEventListener("click", () => {
    if (overlay) overlay.style.display = "flex";
    floater.remove();
  });
  row.appendChild(show);
  floater.appendChild(row);
}

function infoboxCaptchaRestorePanel() {
  const floater = document.getElementById("infobox-captcha-float");
  if (floater) floater.remove();
  const overlay = document.getElementById("infobox-progress-overlay");
  if (overlay) overlay.style.display = "flex";
}

function isLoginHtml(html) {
  return (
    /please\s+login/i.test(html) &&
    (/_username|name="password"|connectez-vous/i.test(html) || /\/en\/login/i.test(html))
  );
}

const CHALLENGE_HTML_RE =
  /g-recaptcha|google\.com\/recaptcha|grecaptcha|h-captcha|cf-challenge|challenge-platform|data-sitekey|verify you are human|unusual traffic|just a moment|attention required|robot check|are you a robot/i;

function isChallengeHtml(html) {
  if (!html || html.length < 80) return false;
  if (isLoginHtml(html)) return false;
  return CHALLENGE_HTML_RE.test(html);
}

function isBoxRecErrorHtml(html) {
  if (!html || html.length < 40) return false;
  if (isLoginHtml(html)) return false;
  return BOXREC_ERROR_RE.test(html);
}

function isBoxRecErrorDocument(doc) {
  if (!doc?.body) return false;
  if (hasListPageContent(doc)) return false;
  const text = doc.body.innerText || doc.body.textContent || "";
  return BOXREC_ERROR_RE.test(text);
}

/** Vraie page bloquée (pas une liste/profil BoxRec normale qui contient g-recaptcha). */
function isBlockedFetchHtml(html, url) {
  if (!html || html.length < 80) return true;
  if (isLoginHtml(html)) return true;
  if (isBoxRecErrorHtml(html)) return true;
  const doc = new DOMParser().parseFromString(html, "text/html");
  if (hasListPageContent(doc)) return false;
  if (findProfileSections(doc).length > 0) return false;
  if (countProfileLinks(doc) > 0) return false;
  return isChallengeHtml(html);
}

function captchaProbeUrls(pageUrl) {
  const urls = [];
  const add = (u) => {
    if (!u) return;
    const clean = String(u).replace(/#.*$/, "");
    if (clean && !urls.includes(clean)) urls.push(clean);
  };
  add(pageUrl);
  add(location.href);
  try {
    add(listBaseUrlFromPage());
  } catch (_) {
    /* ignore */
  }
  return urls;
}

function isChallengeDocument(doc) {
  return isActiveChallengeDocument(doc);
}

/** Blocage actif (pas le simple badge reCAPTCHA laissé après validation). */
function isActiveChallengeDocument(doc) {
  if (!doc || !doc.body) return false;
  if (hasListPageContent(doc) && countProfileLinks(doc) >= 2) return false;
  if (isBoxRecErrorDocument(doc)) return true;

  const view = doc.defaultView;
  for (const frame of doc.querySelectorAll('iframe[src*="recaptcha"]')) {
    const src = frame.getAttribute("src") || "";
    if (!/api2\/bframe|enterprise\/bframe|\/anchor/.test(src)) continue;
    const rect = frame.getBoundingClientRect();
    const style = view?.getComputedStyle(frame);
    if (
      rect.width > 80 &&
      rect.height > 80 &&
      style?.visibility !== "hidden" &&
      style?.display !== "none" &&
      style?.opacity !== "0"
    ) {
      return true;
    }
  }

  for (const frame of doc.querySelectorAll('iframe[src*="challenges.cloudflare"]')) {
    const rect = frame.getBoundingClientRect();
    if (rect.width > 60 && rect.height > 60) return true;
  }

  const html = doc.body.innerHTML || "";
  return isChallengeHtml(html) && !hasListPageContent(doc);
}

function markCaptchaMode() {
  window.__infoboxCaptchaMode = true;
}

function clearCaptchaMode() {
  window.__infoboxCaptchaMode = false;
}

async function probeUrlAccessible(url) {
  const target = (url || location.href).replace(/#.*$/, "");
  try {
    const res = await fetch(target, {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "text/html,application/xhtml+xml" },
    });
    if (res.status === 403 || res.status === 429 || !res.ok) return false;
    const html = await res.text();
    return !isBlockedFetchHtml(html, target);
  } catch (_) {
    return false;
  }
}

async function captchaLooksResolved(pageUrl) {
  if (!isActiveChallengeDocument(document) && hasListPageContent(document)) return true;
  for (const url of captchaProbeUrls(pageUrl)) {
    if (await probeUrlAccessible(url)) return true;
  }
  return false;
}

async function promptBoxRecBlocked(message, pageUrl) {
  if (/TSB\d+|something went wrong/i.test(message || "")) {
    markBoxRecThrottle();
  }
  return promptCaptchaResolved(message, pageUrl);
}

function promptCaptchaResolved(message, pageUrl) {
  return new Promise((resolve) => {
    let done = false;
    let pollTimer = null;
    let pollBusy = false;

    const finish = () => {
      if (done) return;
      done = true;
      if (pollTimer) clearInterval(pollTimer);
      clearCaptchaMode();
      resolve();
    };

    const tryContinue = async (fromButton) => {
      const sub = document.getElementById("infobox-progress-sub");
      if (sub && fromButton) sub.textContent = "Vérification BoxRec en cours…";
      const ok = await captchaLooksResolved(pageUrl);
      if (ok) {
        infoboxCaptchaRestorePanel();
        if (sub) sub.textContent = "reCAPTCHA validé — reprise de la collecte…";
        setTimeout(finish, 400);
        return true;
      }
      if (sub && fromButton) {
        sub.textContent =
          "Pas encore détecté. Résolvez le captcha puis réessayez, ou ouvrez la même URL dans un autre onglet.";
      }
      return false;
    };

    infoboxProgressShow(
      "reCAPTCHA BoxRec",
      message || "BoxRec demande une vérification anti-robot.",
      { showStop: false, preserveActions: true }
    );
    const actions = document.getElementById("infobox-progress-actions");
    const sub = document.getElementById("infobox-progress-sub");
    if (sub) {
      const isTsb = /TSB\d+|something went wrong/i.test(message || "");
      sub.textContent = isTsb
        ? "1. Masquez InfoBox, attendez 2 à 5 minutes.\n" +
          "2. Sur BoxRec : « Return to the homepage », reconnectez-vous si besoin.\n" +
          "3. Rouvrez votre liste managers (même pays), puis « Continuer »."
        : "1. Cliquez « Masquer InfoBox » pour accéder à la page.\n" +
          "2. Résolvez le reCAPTCHA (ici ou dans un autre onglet du même navigateur).\n" +
          "3. Cliquez « Continuer » — détection automatique toutes les 2 s.";
    }
    if (!actions) {
      setTimeout(finish, 8000);
      return;
    }
    actions.innerHTML = "";

    const hide = document.createElement("button");
    hide.type = "button";
    hide.textContent = "Masquer InfoBox — résoudre le captcha";
    hide.style.cssText =
      "cursor:pointer;display:block;width:100%;margin-bottom:0.5rem;padding:0.7rem 1rem;font-size:0.95rem;font-weight:700;border:0;background:#16a34a;color:#fff;border-radius:8px";
    hide.addEventListener("click", () => {
      infoboxCaptchaMinimize({
        onContinue: () => tryContinue(true),
      });
    });
    actions.appendChild(hide);

    const cont = document.createElement("button");
    cont.type = "button";
    cont.textContent = "J’ai résolu — Continuer";
    cont.style.cssText =
      "cursor:pointer;display:block;width:100%;margin-bottom:0.5rem;padding:0.65rem 1rem;font-size:1rem;font-weight:700;border:0;background:#2563eb;color:#fff;border-radius:8px";
    cont.addEventListener("click", async () => {
      cont.disabled = true;
      const ok = await tryContinue(true);
      if (!ok) {
        cont.disabled = false;
      }
    });
    actions.appendChild(cont);

    const reload = document.createElement("button");
    reload.type = "button";
    reload.textContent = "Recharger cette page BoxRec";
    reload.style.cssText =
      "cursor:pointer;display:block;width:100%;margin-bottom:0.5rem;padding:0.55rem 1rem;font-size:0.9rem;font-weight:600;border:2px solid #16a34a;background:#fff;color:#15803d;border-radius:8px";
    reload.addEventListener("click", () => {
      try {
        sessionStorage.setItem("infobox_resume_after_reload", "1");
      } catch (_) {
        /* ignore */
      }
      location.reload();
    });
    actions.appendChild(reload);

    if (pageUrl && pageUrl.replace(/#.*$/, "") !== location.href.replace(/#.*$/, "")) {
      const open = document.createElement("button");
      open.type = "button";
      open.textContent = "Ouvrir la page bloquée (nouvel onglet)";
      open.style.cssText =
        "cursor:pointer;display:block;width:100%;margin-bottom:0.65rem;padding:0.55rem 1rem;font-size:0.9rem;font-weight:600;border:2px solid #2563eb;background:#fff;color:#1d4ed8;border-radius:8px";
      open.addEventListener("click", () => {
        window.open(pageUrl, "_blank", "noopener");
      });
      actions.appendChild(open);
    }

    const stop = document.createElement("button");
    stop.type = "button";
    stop.textContent = "Arrêter la collecte";
    stop.style.cssText =
      "cursor:pointer;display:block;width:100%;padding:0.5rem 1rem;font-size:0.9rem;font-weight:600;border:2px solid #94a3b8;background:#fff;color:#475569;border-radius:8px";
    stop.addEventListener("click", () => {
      infoboxRequestCancel();
      finish();
    });
    actions.appendChild(stop);

    pollTimer = setInterval(() => {
      if (done || pollBusy) return;
      pollBusy = true;
      (async () => {
        try {
          if (infoboxCancelled()) {
            finish();
            return;
          }
          const ok = await captchaLooksResolved(pageUrl);
          if (ok) {
            infoboxCaptchaRestorePanel();
            const subEl = document.getElementById("infobox-progress-sub");
            if (subEl) subEl.textContent = "reCAPTCHA validé — reprise de la collecte…";
            setTimeout(finish, 400);
          }
        } finally {
          pollBusy = false;
        }
      })();
    }, 2000);

    setTimeout(() => {
      if (done) return;
      const overlay = document.getElementById("infobox-progress-overlay");
      if (overlay && overlay.style.display !== "none") {
        infoboxCaptchaMinimize({ onContinue: () => tryContinue(true) });
      }
    }, 1500);
  });
}

function applyContactFieldsToPerson(person, found) {
  if (found.email) person.email = found.email;
  if (found.phone) person.phone = found.phone;
  if (found.address) {
    person.address = found.address;
    if (!person.location || person.location.length < 2) person.location = found.address;
  }
}

function extractContactsFromDocument(doc) {
  const found = { email: "", phone: "", address: "" };
  findProfileSections(doc).forEach((root) => {
    extractProfileDetails(root, found);
    extractProfileDetailsFromFlexRows(root, found);
  });
  const flexScope = findProfileFlexScope(doc);
  if (flexScope) extractProfileDetailsFromFlexRows(flexScope, found);
  scanProfileContactsGlobally(doc, found);
  return found;
}

function extractContactsFromHtml(html, person) {
  if (isLoginHtml(html)) return false;
  const found = { email: "", phone: "", address: "" };
  const doc = new DOMParser().parseFromString(html, "text/html");
  const parsed = extractContactsFromDocument(doc);
  Object.assign(found, parsed);
  extractProfileDetailsFallback(html, found);
  applyContactFieldsToPerson(person, found);
  return !!(found.email || found.phone);
}

async function fetchProfileHtml(url) {
  const opts = {
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "en-GB,en;q=0.9,fr;q=0.8",
      Referer: location.href,
    },
  };
  for (let attempt = 0; attempt < 5; attempt++) {
    if (infoboxCancelled()) return null;
    try {
      const res = await fetch(url, opts);
      if (res.status === 403 || res.status === 429) {
        markCaptchaMode();
        await promptCaptchaResolved(
          "BoxRec limite les requêtes. Résolvez le reCAPTCHA si affiché.",
          url
        );
        continue;
      }
      if (!res.ok) {
        await new Promise((r) => setTimeout(r, PROFILE_RETRY_DELAY_MS));
        continue;
      }
      const html = await res.text();
      if (isBlockedFetchHtml(html, url)) {
        markCaptchaMode();
        await promptCaptchaResolved(
          "reCAPTCHA détecté sur une fiche profil. Résolvez-le sur BoxRec.",
          url
        );
        continue;
      }
      if (isLoginHtml(html) && attempt < 4) {
        await new Promise((r) => setTimeout(r, PROFILE_RETRY_DELAY_MS));
        continue;
      }
      return html;
    } catch (_) {
      await new Promise((r) => setTimeout(r, PROFILE_RETRY_DELAY_MS));
    }
  }
  return null;
}

function enrichPersonFromDocument(doc, person) {
  const found = extractContactsFromDocument(doc);
  applyContactFieldsToPerson(person, found);
  return !!(found.email || found.phone);
}

function enrichOneProfileIframe(person) {
  return new Promise((resolve) => {
    if (!person.profile_url) {
      resolve(false);
      return;
    }
    const iframe = document.createElement("iframe");
    iframe.style.cssText =
      "position:fixed;left:-9999px;top:0;width:900px;height:700px;visibility:hidden;border:0";
    iframe.setAttribute("aria-hidden", "true");
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      iframe.remove();
      resolve(ok);
    };
    const timer = setTimeout(() => finish(false), 14000);
    iframe.onload = () => {
      setTimeout(() => {
        try {
          const doc = iframe.contentDocument;
          if (doc && enrichPersonFromDocument(doc, person)) finish(true);
          else finish(false);
        } catch (_) {
          finish(false);
        }
      }, 700);
    };
    iframe.onerror = () => finish(false);
    iframe.src = person.profile_url;
    document.body.appendChild(iframe);
  });
}

async function enrichOneProfile(person, { useIframe = false } = {}) {
  if (!person.profile_url) return;
  const iframeFirst = useIframe || !!window.__infoboxCaptchaMode;
  if (!iframeFirst) {
    const html = await fetchProfileHtml(person.profile_url);
    if (html) extractContactsFromHtml(html, person);
  }
  if (iframeFirst || !person.email || !person.phone) {
    await enrichOneProfileIframe(person);
  }
}

const PERSON_ROLES =
  "manager|matchmaker|promoter|trainer|media|referee|judge|inspector|supervisor|doctor|timekeeper";
const PERSON_HREF_RE = new RegExp(`/en/(${PERSON_ROLES})/(\\d+)(?:/|$|\\?|#)`, "i");
const NON_PERSON_PATHS = new Set([
  "locations",
  "login",
  "event",
  "events",
  "bout",
  "bouts",
  "ratings",
  "schedule",
  "results",
  "date",
  "champions",
  "clubs",
  "titles",
  "quick_search",
  "proboxer",
  "amateurboxer",
  "boxer",
  "wiki",
  "forum",
  "shop",
]);
const LIST_LOCATION_HEADERS = ["location", "residence", "town", "city", "résidence"];

function personHrefMatch(href) {
  if (!href) return null;
  let m = href.match(PERSON_HREF_RE);
  if (m) return m;
  m = href.match(/\/en\/([a-z][a-z0-9_-]*)\/(\d+)(?:\/|$|\?|#)/i);
  if (m && !NON_PERSON_PATHS.has(m[1].toLowerCase())) return m;
  return null;
}

const ROLE_SPORT_LABELS = {
  "2_0": "manager",
  "3_0": "matchmaker",
  "4_0": "promoter",
  "12_0": "trainer",
  "13_0": "media",
};

function countryFromAddressId(value) {
  if (!value || !value.includes("|")) return "";
  const parts = value.split("|").map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return "";
  const country = parts[parts.length - 1];
  if (/^[A-Z]{2,3}_?\d*$/i.test(country)) {
    return COUNTRY_CODE_LABELS[country.toUpperCase().replace(/_$/, "")] || country;
  }
  return country;
}

function listSearchRoot(doc) {
  return (
    doc.querySelector('turbo-frame#cal-list, turbo-frame[name="cal-list"], #cal-list') ||
    doc.body ||
    doc
  );
}

function listColumnIndex(headers, names) {
  for (const name of names) {
    const i = headers.indexOf(name);
    if (i >= 0) return i;
  }
  return -1;
}

function findListTable(doc) {
  let best = null;
  let bestCount = 0;
  doc.querySelectorAll("table.dataTable, table").forEach((table) => {
    let count = 0;
    table.querySelectorAll("a[href]").forEach((a) => {
      if (personHrefMatch(a.getAttribute("href") || "")) count += 1;
    });
    if (count > bestCount) {
      best = table;
      bestCount = count;
    }
  });
  return best;
}

function findRowProfileLink(row) {
  const person = row.querySelector("a.personLink");
  if (person && personHrefMatch(person.getAttribute("href") || "")) return person;
  for (const a of row.querySelectorAll("a[href]")) {
    if (personHrefMatch(a.getAttribute("href") || "")) return a;
  }
  return null;
}

function humanRowLocation(row) {
  for (const item of row.querySelectorAll(".humanItem")) {
    if (item.querySelector(".flag-icon, img[src*='flag']")) {
      const text = item.textContent.replace(/\s+/g, " ").trim();
      if (text) return text;
    }
  }
  return "";
}

function humanRowCompany(row) {
  for (const item of row.querySelectorAll(".humanItem.item-egeshgrg")) {
    if (item.classList.contains("isHidden")) continue;
    const text = item.textContent.replace(/\s+/g, " ").trim();
    if (text) return text;
  }
  return "";
}

function extractFromHumanContainers(doc, role, searchCountry) {
  const people = [];
  const seen = new Set();
  const root = listSearchRoot(doc);
  root.querySelectorAll("div.humanContainer").forEach((row) => {
    if ([...row.classList].some((c) => c.startsWith("border-b-2"))) return;
    const link = findRowProfileLink(row);
    if (!link) return;
    const href = link.href || link.getAttribute("href");
    const full = href.startsWith("http") ? href : new URL(href, "https://boxrec.com").href;
    if (seen.has(full)) return;
    seen.add(full);
    people.push({
      name: link.textContent.trim(),
      profile_url: full,
      location: humanRowLocation(row),
      search_country: searchCountry || "",
      address: humanRowCompany(row),
      email: "",
      phone: "",
      role,
    });
  });
  return people;
}

function countProfileLinks(doc) {
  const root = listSearchRoot(doc);
  let n = 0;
  root.querySelectorAll("a.personLink, a[href]").forEach((a) => {
    if (personHrefMatch(a.getAttribute("href") || "")) n += 1;
  });
  return n;
}

function hasListPageContent(doc) {
  if (extractFromHumanContainers(doc, "manager", "").length > 0) return true;
  if (findListTable(doc)) return true;
  if (countProfileLinks(doc) > 0) return true;
  if (/\/locations\/people/i.test(location.pathname) && /\d+\s+people\b/i.test(doc.body?.innerText || "")) {
    return countProfileLinks(doc) > 0 || !!listSearchRoot(doc).querySelector("a.personLink");
  }
  return false;
}

async function waitForListContent(doc, maxMs = 10000) {
  if (isActiveChallengeDocument(document)) {
    markCaptchaMode();
    await promptCaptchaResolved(
      "BoxRec affiche une vérification (reCAPTCHA). Complétez-la sur cette page.",
      location.href
    );
    await new Promise((r) => setTimeout(r, 600));
  }
  const step = 350;
  for (let elapsed = 0; elapsed < maxMs; elapsed += step) {
    const live = document;
    if (isActiveChallengeDocument(live)) {
      markCaptchaMode();
      await promptCaptchaResolved(
        "La liste n’apparaît pas tant que le reCAPTCHA n’est pas résolu.",
        location.href
      );
      elapsed = 0;
      continue;
    }
    if (hasListPageContent(live)) return true;
    if (extractListFromDoc(live, "manager", "").length > 0) return true;
    await new Promise((r) => setTimeout(r, step));
  }
  return hasListPageContent(document) && !isActiveChallengeDocument(document);
}

function extractRowLocation(tds, headers, linkTd) {
  const locIdx = listColumnIndex(headers, LIST_LOCATION_HEADERS);
  if (locIdx >= 0 && tds[locIdx]) return tds[locIdx].textContent.replace(/\s+/g, " ").trim();
  for (const td of tds) {
    if (td === linkTd) continue;
    if (td.querySelector("img[src*='flag'], img[alt]")) {
      const text = td.textContent.replace(/\s+/g, " ").trim();
      if (text) return text;
    }
  }
  for (let i = 1; i < tds.length; i++) {
    const td = tds[i];
    if (td === linkTd) continue;
    const text = td.textContent.replace(/\s+/g, " ").trim();
    if (text && !/^\d+$/.test(text) && !/^[♂♀]$/.test(text) && text !== "male" && text !== "female") {
      return text;
    }
  }
  return "";
}

function extractRowCompany(tds, headers) {
  const idx = listColumnIndex(headers, ["company", "société", "societe"]);
  return idx >= 0 && tds[idx] ? tds[idx].textContent.replace(/\s+/g, " ").trim() : "";
}

function extractListFromTable(doc, role, searchCountry) {
  const people = [];
  const seen = new Set();
  const table = findListTable(doc);
  if (!table) return people;

  const headerRow = table.querySelector("tr:has(th)") || table.querySelector("tr");
  const headerCells = headerRow
    ? [...headerRow.querySelectorAll("th"), ...(!headerRow.querySelector("th") ? headerRow.querySelectorAll("td") : [])]
    : [];
  const headers = headerCells.map((th) => th.textContent.trim().toLowerCase());

  table.querySelectorAll("tr").forEach((tr) => {
    if (tr.querySelector("th") && tr !== headerRow) return;
    const link = findRowProfileLink(tr);
    if (!link) return;
    const href = link.href || link.getAttribute("href");
    const full = href.startsWith("http") ? href : new URL(href, "https://boxrec.com").href;
    if (seen.has(full)) return;
    seen.add(full);
    const tds = [...tr.querySelectorAll("td")];
    const linkTd = link.closest("td");
    const location = extractRowLocation(tds, headers, linkTd);
    const company = extractRowCompany(tds, headers);
    let email = "";
    let phone = "";
    const mail = tr.querySelector('a[href^="mailto:"]');
    if (mail) {
      email = mail.getAttribute("href").replace(/^mailto:/i, "").split("?")[0].trim();
    }
    const tel = tr.querySelector('a[href^="tel:"]');
    if (tel) phone = tel.getAttribute("href").replace(/^tel:/i, "").trim();
    people.push({
      name: link.textContent.trim(),
      profile_url: full,
      location,
      search_country: searchCountry || "",
      address: company,
      email,
      phone,
      role,
    });
  });
  return people;
}

function extractListFromDoc(doc, role, searchCountry) {
  const human = extractFromHumanContainers(doc, role, searchCountry);
  if (human.length) return human;
  return extractListFromTable(doc, role, searchCountry);
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

const COUNTRY_CODE_LABELS = {
  GBR: "Royaume-Uni",
  GB: "Royaume-Uni",
  UK: "Royaume-Uni",
  USA: "États-Unis",
  US: "États-Unis",
  FRA: "France",
  FR: "France",
  GD: "Grenada",
  GRD: "Grenada",
  VEN: "Venezuela",
  VE: "Venezuela",
  PRI: "Puerto Rico",
  PR: "Puerto Rico",
  ESP: "Spain",
  ES: "Spain",
};

function getSearchCountryFromPage(doc) {
  for (const sel of [
    'input[name="locations_filter[addressId]"]',
    'input[name="addressId"]',
  ]) {
    const inp = doc.querySelector(sel);
    if (inp && inp.value && inp.value.trim()) {
      const fromAddr = countryFromAddressId(inp.value.trim());
      if (fromAddr) return fromAddr;
    }
  }
  for (const sel of [
    'input[name="l[loc_txt]"]',
    'input[name="locations_filter[loc_txt]"]',
    'input[name*="loc_txt"]',
  ]) {
    const inp = doc.querySelector(sel);
    if (inp && inp.value && inp.value.trim()) {
      const value = inp.value.trim();
      if (!/^[a-z]{2,3}_?$/i.test(value)) return value;
    }
  }
  for (const a of doc.querySelectorAll('a[href*="locations/people"]')) {
    const fromLink = getSearchCountryFromUrl(a.href || a.getAttribute("href") || "");
    if (fromLink) return fromLink;
  }
  const title = doc.title || "";
  const m = title.match(/\b(?:in|near|around)\s+(.+?)(?:\s*[-|]|$)/i);
  if (m) return m[1].trim();
  return "";
}

function getRoleFromUrl(url) {
  const params = new URL(url, "https://boxrec.com").searchParams;
  const oldRole = params.get("l[role]");
  if (oldRole) return oldRole;
  const roleSport =
    params.get("locations_filter[roleSport]") || params.get("roleSport");
  if (roleSport && ROLE_SPORT_LABELS[roleSport]) return ROLE_SPORT_LABELS[roleSport];
  const m = url.match(/l%5Brole%5D=(\w+)/);
  if (m) return m[1];
  return "manager";
}

/** Pays de la recherche BoxRec (filtre l[loc_txt], l[country], etc.). */
function getSearchCountryFromUrl(url) {
  try {
    const params = new URL(url, "https://boxrec.com").searchParams;
    const locTxt =
      params.get("l[loc_txt]") || params.get("locations_filter[loc_txt]");
    if (locTxt && locTxt.trim()) return locTxt.trim();
    const addressId =
      params.get("locations_filter[addressId]") || params.get("addressId");
    if (addressId && addressId.trim()) {
      const fromAddr = countryFromAddressId(addressId.trim());
      if (fromAddr) return fromAddr;
    }
    const country = (params.get("l[country]") || "").trim().toUpperCase();
    if (country) return COUNTRY_CODE_LABELS[country] || country;
    const level = (params.get("l[level_id]") || "").trim().toUpperCase();
    if (level && COUNTRY_CODE_LABELS[level]) return COUNTRY_CODE_LABELS[level];
    const loc = (params.get("l[location]") || "").trim().toLowerCase();
    if (loc.startsWith("gb")) return COUNTRY_CODE_LABELS.GB;
    const code = loc.match(/^([a-z]{2,3})_?/);
    if (code) {
      const mapped = COUNTRY_CODE_LABELS[code[1].toUpperCase()];
      if (mapped) return mapped;
    }
  } catch (_) {
    /* ignore */
  }
  return "";
}

function exportFileSlug(text) {
  return (
    String(text || "pays")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^\w]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 40) || "pays"
  );
}

function getOffsetFromUrl(url) {
  const m = String(url).match(/[?&]offset=(\d+)/);
  return m ? parseInt(m[1], 10) : 0;
}

function urlWithOffset(baseUrl, offset) {
  const u = new URL(baseUrl, "https://boxrec.com");
  u.searchParams.set("offset", String(offset));
  return u.toString();
}

function parseTotalPeople(doc) {
  const t = (doc.body && doc.body.innerText) || "";
  const patterns = [
    /\b(\d{1,4})\s+people\b/i,
    /\b(\d{1,4})\s+personnes?\b/i,
    /\b(\d{1,4})\s+results?\b/i,
    /\b(\d{1,4})\s+r[eé]sultats?\b/i,
    /\bof\s+(\d{1,4})\s+results?\b/i,
  ];
  for (const pat of patterns) {
    const m = t.match(pat);
    if (m) {
      const n = parseInt(m[1], 10);
      if (n >= 1 && n <= 5000) return n;
    }
  }
  return null;
}

function listSearchKey(url) {
  return `${getRoleFromUrl(url)}::${getSearchCountryFromUrl(url)}`;
}

function isListPaginationLink(href, base) {
  try {
    const u = new URL(href, base);
    if (!/\/locations\/people/i.test(u.pathname)) return false;
    return u.searchParams.has("offset");
  } catch (_) {
    return false;
  }
}

function listBaseUrlFromPage() {
  const u = new URL(location.href.replace(/#.*$/, ""));
  u.searchParams.set("offset", "0");
  return u.toString();
}

function gatherAllListUrlsFrom(doc, base) {
  const baseKey = listSearchKey(base);
  const urls = new Set([base]);
  const role = getRoleFromUrl(base);
  const searchCountry = getSearchCountryFromUrl(base);
  const onPage = extractListFromDoc(doc, role, searchCountry).length;
  const pageSize = Math.max(onPage || 0, 12, 20);

  doc.querySelectorAll('a[href*="offset="]').forEach((a) => {
    try {
      const full = new URL(a.href || a.getAttribute("href"), base).href.replace(/#.*$/, "");
      if (isListPaginationLink(full, base) || listSearchKey(full) === baseKey) urls.add(full);
    } catch (_) {
      /* ignore */
    }
  });

  const total = parseTotalPeople(doc);
  if (total && pageSize > 0) {
    const maxPages = Math.min(Math.ceil(total / pageSize), 40);
    for (let p = 0; p < maxPages; p++) {
      urls.add(urlWithOffset(base, p * pageSize));
    }
  }

  const sorted = [...urls].sort((a, b) => getOffsetFromUrl(a) - getOffsetFromUrl(b));
  if (sorted.length > 50) {
    console.warn("InfoBox: trop de pages liste détectées, limite à 50.", sorted.length);
    return sorted.slice(0, 50);
  }
  return sorted;
}

function gatherAllListUrls() {
  return gatherAllListUrlsFrom(document, listBaseUrlFromPage());
}

async function fetchPageDoc(url) {
  const same =
    url.replace(/#.*$/, "") === location.href.replace(/#.*$/, "") &&
    getOffsetFromUrl(url) === getOffsetFromUrl(location.href);
  if (same) {
    if (isActiveChallengeDocument(document)) {
      markCaptchaMode();
      await promptCaptchaResolved("reCAPTCHA sur la page actuelle — résolvez-le puis continuez.", url);
    }
    return document;
  }
  const opts = { credentials: "include", cache: "no-store" };
  for (let attempt = 0; attempt < 5; attempt++) {
    if (infoboxCancelled()) return null;
    try {
      const res = await fetch(url, opts);
      if (res.status === 403 || res.status === 429) {
        markCaptchaMode();
        await promptCaptchaResolved(
          "BoxRec bloque la lecture des pages liste. Résolvez le reCAPTCHA sur cette page BoxRec.",
          url
        );
        await new Promise((r) => setTimeout(r, 800));
        const sameAfter =
          url.replace(/#.*$/, "") === location.href.replace(/#.*$/, "") &&
          getOffsetFromUrl(url) === getOffsetFromUrl(location.href);
        if (sameAfter && (await captchaLooksResolved(url))) return document;
        continue;
      }
      if (!res.ok) return null;
      const html = await res.text();
      if (isBoxRecErrorHtml(html)) {
        markCaptchaMode();
        markBoxRecThrottle();
        await promptBoxRecBlocked(
          "BoxRec : Something went wrong (TSB1) — limite anti-bot. Attendez 2 à 5 min puis rouvrez la liste.",
          url
        );
        continue;
      }
      if (isBlockedFetchHtml(html, url)) {
        markCaptchaMode();
        await promptBoxRecBlocked(
          "reCAPTCHA sur une page liste. Ouvrez-la dans cet onglet et validez.",
          url
        );
        continue;
      }
      if (isLoginHtml(html) && attempt < 4) {
        await new Promise((r) => setTimeout(r, PROFILE_RETRY_DELAY_MS));
        continue;
      }
      return new DOMParser().parseFromString(html, "text/html");
    } catch (_) {
      await new Promise((r) => setTimeout(r, PROFILE_RETRY_DELAY_MS));
    }
  }
  return null;
}

async function collectAllListPagesForBase(base, role, searchCountry, seedDoc) {
  const byProfile = new Map();
  const firstDoc = seedDoc || (await fetchPageDoc(base));
  if (!firstDoc) return [];
  const urls = gatherAllListUrlsFrom(firstDoc, base);
  const total = parseTotalPeople(firstDoc);
  const countryLabel = searchCountry ? ` — ${searchCountry}` : "";

  infoboxProgressShow(
    `Liste${countryLabel} — ${urls.length} page(s)`,
    total ? `Environ ${total} contacts` : "Collecte des noms…"
  );
  await new Promise((r) => setTimeout(r, 250));

  for (let i = 0; i < urls.length; i++) {
    if (infoboxCancelled()) break;
    infoboxProgressShow(
      `Page liste ${i + 1} / ${urls.length}${countryLabel}`,
      "Lecture des noms sur BoxRec…"
    );
    document.title = `InfoBox ${i + 1}/${urls.length}…`;
    const doc =
      i === 0 && firstDoc
        ? firstDoc
        : await fetchPageDoc(urls[i]);
    if (!doc) continue;
    extractListFromDoc(doc, role, searchCountry).forEach((p) => byProfile.set(p.profile_url, p));
    if (i < urls.length - 1 && !(await waitCancellable(listPageDelayMs()))) break;
  }

  const count = byProfile.size;
  if (total && count < total * 0.5) {
    const pageSize = extractListFromDoc(firstDoc, role, searchCountry).length || 20;
    for (let off = 0; off < total; off += pageSize) {
      if (infoboxCancelled()) break;
      const doc = await fetchPageDoc(urlWithOffset(base, off));
      if (!doc) continue;
      extractListFromDoc(doc, role, searchCountry).forEach((p) => byProfile.set(p.profile_url, p));
      if (!(await waitCancellable(900))) break;
    }
  }

  return [...byProfile.values()];
}

async function collectAllListPages(role, searchCountry) {
  const base = listBaseUrlFromPage();
  const people = await collectAllListPagesForBase(base, role, searchCountry, document);
  document.title = document.title.replace(/^InfoBox.*/, "BoxRec");
  return people;
}

function decodeHtmlJsonAttr(value) {
  if (!value) return null;
  const ta = document.createElement("textarea");
  ta.innerHTML = value;
  try {
    return JSON.parse(ta.value);
  } catch (_) {
    try {
      return JSON.parse(value);
    } catch (e2) {
      return null;
    }
  }
}

function extractLocationPickerProps(doc) {
  const el = doc.querySelector('[data-live-name-value="LocationPicker"]');
  if (!el) return null;
  return decodeHtmlJsonAttr(el.getAttribute("data-live-props-value"));
}

function parseCountriesFromPickerHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const countries = [];
  const seen = new Set();
  const skip = /^(back|worldwide|all locations?)$/i;
  doc
    .querySelectorAll(
      '[data-action*="locationpicker#optionDrillDown"], [data-action*="locationpicker#optionSelect"]'
    )
    .forEach((el) => {
      const display = (el.dataset.display || el.textContent || "").replace(/\s+/g, " ").trim();
      if (!display || skip.test(display)) return;
      const level = (el.dataset.level || "").trim().toLowerCase();
      if (level && !["", "country", "c", "nation"].includes(level)) return;
      const key = display.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      const value = (el.dataset.value || "").trim();
      const addressId = value ? `${value}|||||${display}` : `|||||${display}`;
      countries.push({ label: display, addressId });
    });
  return countries.sort((a, b) => a.label.localeCompare(b.label, "en"));
}

async function requestLocationPicker(props, updated, refererUrl) {
  const formData = new FormData();
  formData.append("data", JSON.stringify({ props, updated }));
  const res = await fetch("https://boxrec.com/en/_components/LocationPicker", {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/vnd.live-component+html",
      "X-Requested-With": "XMLHttpRequest",
      "X-Live-Url": refererUrl || location.pathname + location.search,
    },
    body: formData,
  });
  if (res.status === 403 || res.status === 429) {
    markCaptchaMode();
    await promptCaptchaResolved(
      "BoxRec bloque la lecture de la liste des pays. Résolvez le reCAPTCHA.",
      location.href
    );
    throw new Error("captcha");
  }
  if (!res.ok) throw new Error(`LocationPicker HTTP ${res.status}`);
  const html = await res.text();
  if (isBlockedFetchHtml(html, location.href)) {
    markCaptchaMode();
    await promptCaptchaResolved("reCAPTCHA lors du chargement des pays BoxRec.", location.href);
    throw new Error("captcha");
  }
  return html;
}

async function fetchAllBoxRecCountries(doc) {
  let props = extractLocationPickerProps(doc);
  const referer = location.pathname + location.search;

  if (!props) {
    const res = await fetch(location.href, { credentials: "include", cache: "no-store" });
    if (!res.ok) throw new Error("page");
    const pageDoc = new DOMParser().parseFromString(await res.text(), "text/html");
    props = extractLocationPickerProps(pageDoc);
  }

  if (!props || !props["@checksum"]) throw new Error("LocationPicker absent");

  const pickerHtml = await requestLocationPicker(
    props,
    { initialLoadData: true, query: "", level: "", levelid: "", parent: "" },
    referer
  );
  return parseCountriesFromPickerHtml(pickerHtml);
}

function normalizeCountrySpec(spec) {
  if (!spec) return null;
  if (typeof spec === "string") {
    const label = spec.trim();
    return label ? { label, addressId: `|||||${label}` } : null;
  }
  const label = String(spec.label || "").trim();
  if (!label) return null;
  return {
    label,
    addressId: spec.addressId || spec.address_id || `|||||${label}`,
  };
}

function setCountryOnListUrl(templateUrl, countrySpec) {
  const spec = normalizeCountrySpec(countrySpec);
  const u = new URL(templateUrl.replace(/#.*$/, ""), "https://boxrec.com");
  u.searchParams.delete("offset");
  if (spec.addressId) {
    u.searchParams.set("addressId", spec.addressId);
    u.searchParams.delete("locations_filter[addressId]");
  }
  u.searchParams.set("l[loc_txt]", spec.label);
  return u.toString();
}

async function countriesForWorldwideCollect(doc, currentCountry) {
  infoboxProgressShow(
    "Pays BoxRec",
    "Chargement de la liste officielle des pays (LocationPicker)…",
    { showStop: true }
  );
  let fromBoxRec = [];
  try {
    fromBoxRec = await fetchAllBoxRecCountries(doc);
  } catch (err) {
    console.warn("InfoBox: pays BoxRec", err);
  }
  const seen = new Set();
  const out = [];
  const add = (spec) => {
    const norm = normalizeCountrySpec(spec);
    if (!norm) return;
    const key = norm.label.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(norm);
  };
  if (currentCountry) add(currentCountry);
  fromBoxRec.forEach(add);
  if (!fromBoxRec.length) {
    throw new Error(
      "Impossible de charger les pays depuis BoxRec. Restez connecté sur boxrec.com et réessayez."
    );
  }
  return out;
}

async function collectWorldwideListPages(role, templateUrl, startCountry) {
  const byProfile = new Map();
  const countries = await countriesForWorldwideCollect(document, startCountry);
  infoboxProgressShow(
    "Mode monde entier",
    `${countries.length} pays BoxRec à parcourir — cela peut prendre longtemps. Ne fermez pas l’onglet.`
  );
  await waitCancellable(500);

  for (let ci = 0; ci < countries.length; ci++) {
    if (infoboxCancelled()) break;
    const country = countries[ci];
    const base = setCountryOnListUrl(templateUrl, country);
    infoboxProgressShow(
      `Pays ${ci + 1} / ${countries.length}`,
      `${country.label} — lecture des listes…`
    );
    document.title = `InfoBox ${country.label} (${ci + 1}/${countries.length})`;
    const batch = await collectAllListPagesForBase(base, role, country.label);
    batch.forEach((p) => {
      if (!p.search_country) p.search_country = country.label;
      byProfile.set(p.profile_url, p);
    });
    if (ci < countries.length - 1 && !(await waitCancellable(1100))) break;
  }
  document.title = document.title.replace(/^InfoBox.*/, "BoxRec");
  return [...byProfile.values()];
}

async function enrichAllProfiles(people) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const captchaMode = !!window.__infoboxCaptchaMode;

  async function runPass(labelSuffix, useIframe) {
    for (let i = 0; i < people.length; i++) {
      if (infoboxCancelled()) break;
      const p = people[i];
      infoboxProgressShow(
        `Profils ${i + 1} / ${people.length}${labelSuffix}`,
        (captchaMode || useIframe
          ? "Mode onglet (reCAPTCHA actif) — "
          : "") + `${p.name || "Contact"} — e-mails et téléphones…`
      );
      document.title = `InfoBox ${i + 1}/${people.length}`;
      await enrichOneProfile(p, { useIframe: useIframe || captchaMode });
      if (i < people.length - 1 && !(await waitCancellable(profileFetchDelayMs()))) break;
    }
  }

  await runPass(captchaMode ? " (onglet)" : "", captchaMode);
  if (infoboxCancelled()) return;
  const incomplete = people.filter((p) => !p.email || !p.phone);
  if (incomplete.length && !infoboxCancelled()) {
    infoboxProgressShow(
      `Nouvelle passe (${incomplete.length} fiches)`,
      "Certaines fiches n’avaient pas tout — nouvel essai…"
    );
    await wait(1500);
    for (let i = 0; i < incomplete.length; i++) {
      if (infoboxCancelled()) break;
      const p = incomplete[i];
      infoboxProgressShow(
        `Reprise ${i + 1} / ${incomplete.length}`,
        p.name || "Contact"
      );
      await enrichOneProfile(p, { useIframe: true });
      if (i < incomplete.length - 1 && !(await waitCancellable(PROFILE_RETRY_DELAY_MS + 400))) break;
    }
  }
}

async function handleCancelledExport(people, role, searchCountry, prevTitle) {
  document.title = prevTitle;
  infoboxProgressHide(0);
  window.__infoboxRun = 0;
  if (!people.length) {
    alert("Collecte annulée.");
    return;
  }
  const ok = confirm(
    "Collecte arrêtée.\n\n" +
      people.length +
      " contact(s) déjà récupéré(s).\n\nExporter CSV + PDF maintenant ?"
  );
  if (ok) {
    try {
      await exportFiles(people, role, searchCountry);
      alert(people.length + " contacts exportés (CSV + PDF).");
    } catch (_) {
      downloadCsv(people, role, searchCountry);
      alert("CSV exporté. PDF non généré.");
    }
  }
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

function downloadCsv(people, role, searchCountry) {
  const sep = ";";
  const esc = (c) => `"${String(c || "").replace(/"/g, '""')}"`;
  const country = searchCountry || people[0]?.search_country || "";
  const csv =
    "\uFEFFsep=" +
    sep +
    "\n" +
    [
      "nom",
      "email",
      "telephone",
      "adresse",
      "role",
      "pays_recherche",
      "localisation",
      "url_profil",
    ].join(sep) +
    "\n" +
    people
      .map((p) =>
        [
          p.name,
          p.email,
          p.phone,
          p.address,
          p.role,
          p.search_country || country,
          p.location,
          p.profile_url,
        ]
          .map(esc)
          .join(sep)
      )
      .join("\n");
  const slug = exportFileSlug(country);
  downloadBlob(csvToUtf16LeBlob(csv), `boxrec_${role}_${slug}.csv`, "text/csv;charset=utf-16le");
}

function loadScript(url) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${url}"]`)) {
      resolve();
      return;
    }
    const s = document.createElement("script");
    s.src = url;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("script"));
    document.head.appendChild(s);
  });
}

async function infoboxStaticRoot() {
  const tag = document.querySelector('script[src*="bookmarklet.js"]');
  if (tag && tag.src) return tag.src.replace(/\/static\/js\/bookmarklet\.js.*$/, "");
  return "http://127.0.0.1:5000";
}

async function ensurePdfLibs() {
  if (!window.jspdf) {
    await loadScript("https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js");
    await loadScript(
      "https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.8.2/jspdf.plugin.autotable.min.js"
    );
  }
  if (!window.renderContactsPdf) {
    await loadScript((await infoboxStaticRoot()) + "/static/js/pdf-utils.js");
  }
}

async function downloadPdf(people, role, searchCountry) {
  await ensurePdfLibs();
  const country = searchCountry || people[0]?.search_country || "";
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const title = country ? `BoxRec — ${role} — ${country}` : `BoxRec — ${role}`;
  renderContactsPdf(doc, people, title, searchCountry);
  doc.save(`boxrec_${role}_${exportFileSlug(country)}.pdf`);
}

async function exportFiles(people, role, searchCountry) {
  downloadCsv(people, role, searchCountry);
  await downloadPdf(people, role, searchCountry);
}

async function infoboxExtractFromPage() {
  try {
    await infoboxExtractFromPageCore();
  } catch (err) {
    infoboxProgressHide(0);
    window.__infoboxRun = 0;
    alert("InfoBox erreur : " + (err && err.message ? err.message : err));
  } finally {
    window.__infoboxRun = 0;
  }
}

async function infoboxExtractFromPageCore() {
  window.__infoboxCancel = false;
  window.__infoboxCaptchaMode = false;
  if (!/boxrec\.com/i.test(location.hostname)) {
    alert("InfoBox : utilisez ce favori sur boxrec.com (page liste), pas sur InfoBox.");
    return;
  }
  const role = getRoleFromUrl(location.href);
  let searchCountry = getSearchCountryFromUrl(location.href) || getSearchCountryFromPage(document);

  infoboxProgressShow("InfoBox v3.9", "Détection de la liste BoxRec…", { showStop: false });
  if (isBoxRecErrorDocument(document)) {
    markBoxRecThrottle();
    await promptBoxRecBlocked(
      "BoxRec affiche « Something went wrong (TSB1) » sur cette page.",
      location.href
    );
  }
  const listReady = await waitForListContent(document);
  if (!listReady) {
    infoboxProgressHide(0);
    const captchaHint = isBoxRecErrorDocument(document)
      ? "BoxRec affiche une erreur TSB1 (trop de requêtes). Attendez quelques minutes, retournez à l’accueil BoxRec, rouvrez la liste, puis relancez le favori.\n\n"
      : isChallengeDocument(document)
        ? "Un reCAPTCHA BoxRec est affiché — résolvez-le puis relancez le favori.\n\n"
        : "";
    alert(
      captchaHint +
        "InfoBox : liste non détectée.\n\n" +
        "Attendez que les noms s’affichent sur boxrec.com, puis relancez le favori."
    );
    return;
  }
  if (!searchCountry) searchCountry = getSearchCountryFromPage(document);

  const worldwide = confirm(
    "Mode de collecte BoxRec\n\n" +
      "OK = TOUS les pays BoxRec (liste officielle du site — très long)\n" +
      "Annuler = uniquement le pays actuel" +
      (searchCountry ? ` (${searchCountry})` : "")
  );

  if (!worldwide && !searchCountry) {
    infoboxProgressHide(0);
    alert(
      "InfoBox : pays de recherche non détecté.\n\n" +
        "Filtrez par pays sur BoxRec (ex. Grenada, United Kingdom) ou choisissez « tous les pays »."
    );
    return;
  }

  infoboxProgressShow(
    "InfoBox démarré",
    worldwide
      ? `Monde entier — rôle : ${role}`
      : searchCountry
        ? `Pays : ${searchCountry} — préparation…`
        : "Préparation de la sauvegarde…"
  );
  if (!(await waitCancellable(400))) {
    infoboxProgressHide(0);
    window.__infoboxRun = 0;
    return;
  }

  const prevTitle = document.title;
  document.title = "InfoBox — collecte…";

  infoboxProgressShow(
    "Sauvegarde en cours",
    worldwide ? "Lecture pays par pays…" : "Lecture de toutes les pages de la liste…"
  );
  let people;
  try {
    people = worldwide
      ? await collectWorldwideListPages(role, listBaseUrlFromPage(), searchCountry)
      : await collectAllListPages(role, searchCountry);
  } catch (err) {
    document.title = prevTitle;
    infoboxProgressHide(0);
    alert(
      "InfoBox : " +
        (err && err.message
          ? err.message
          : "échec du chargement des pays BoxRec.")
    );
    return;
  }
  const exportCountry = worldwide ? "worldwide" : searchCountry;
  if (infoboxCancelled()) {
    await handleCancelledExport(people, role, exportCountry, prevTitle);
    return;
  }
  if (!people.length) {
    document.title = prevTitle;
    infoboxProgressHide(0);
    alert("Aucun contact trouvé.");
    return;
  }

  infoboxProgressShow(
    `${people.length} contacts trouvés`,
    "Récupération des e-mails et téléphones sur chaque fiche…"
  );
  await enrichAllProfiles(people);
  if (infoboxCancelled()) {
    await handleCancelledExport(people, role, exportCountry, prevTitle);
    return;
  }

  const withEmail = people.filter((p) => p.email).length;
  const withPhone = people.filter((p) => p.phone).length;
  const withBoth = people.filter((p) => p.email && p.phone).length;
  const missingAny = people.filter((p) => !p.email || !p.phone).length;

  infoboxProgressShow("Export CSV et PDF…", "Création des fichiers sur votre ordinateur…");
  document.title = "InfoBox — export…";
  try {
    await exportFiles(people, role, exportCountry);
  } catch (err) {
    document.title = prevTitle;
    infoboxProgressHide(0);
    alert("InfoBox : échec du PDF (" + (err && err.message ? err.message : err) + "). CSV peut être déjà téléchargé.");
    downloadCsv(people, role, exportCountry);
    return;
  }

  infoboxProgressShow(
    "Sauvegarde terminée",
    `${people.length} contacts — ${withEmail} e-mails — ${withPhone} téléphones. CSV et PDF téléchargés.`
  );
  document.title = `InfoBox — ${people.length} contacts (CSV + PDF)`;
  setTimeout(() => {
    document.title = prevTitle;
  }, 4000);
  infoboxProgressHide(6000);
  alert(
    "InfoBox — export terminé\n\n" +
      "Périmètre : " +
      (worldwide ? "tous les pays" : searchCountry) +
      "\n" +
      people.length +
      " contacts\n" +
      withEmail +
      " avec e-mail\n" +
      withPhone +
      " avec téléphone\n" +
      withBoth +
      " avec les deux\n\n" +
      (missingAny
        ? missingAny +
          " fiche(s) sans e-mail ou tél. : souvent pas renseigné sur BoxRec, ou page non chargée (restez connecté, ne fermez pas l’onglet).\n\n"
        : "") +
      "Fichiers dans Téléchargements (CSV + PDF)."
  );
}

if (typeof window !== "undefined") {
  window.infoboxExtractFromPage = infoboxExtractFromPage;
}
