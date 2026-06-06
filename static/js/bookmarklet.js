/**
 * Favori InfoBox — boxrec.com (utilisateur connecté).
 * v3.4 — profils flex-row (phones/email) + listes humanContainer
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
      '<div class="infobox-overlay" style="position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,0.78);display:flex;align-items:center;justify-content:center;padding:1rem;font-family:Segoe UI,system-ui,sans-serif">' +
      '<div style="background:#fff;padding:1.75rem 2rem;border-radius:12px;max-width:28rem;width:100%;text-align:center;border:2px solid #2563eb;box-shadow:0 16px 48px rgba(37,99,235,0.25)">' +
      '<div style="font-size:1.25rem;font-weight:700;color:#1d4ed8;margin-bottom:0.75rem">InfoBox</div>' +
      '<div id="infobox-progress-msg" style="font-size:1rem;color:#1c1917;font-weight:600"></div>' +
      '<div id="infobox-progress-sub" style="font-size:0.9rem;color:#57534e;margin-top:0.65rem;line-height:1.45"></div>' +
      '<div id="infobox-progress-actions" style="margin-top:1.25rem"></div>' +
      "</div></div>";
    document.body.appendChild(root);
    m = document.getElementById("infobox-progress-msg");
  }
  const s = document.getElementById("infobox-progress-sub");
  const actions = document.getElementById("infobox-progress-actions");
  if (m) m.textContent = msg;
  if (s) s.textContent = sub || "Ne fermez pas cet onglet BoxRec.";
  if (actions) {
    if (showStop && !infoboxCancelled()) {
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
  }, delayMs || 0);
}

function isLoginHtml(html) {
  return (
    /please\s+login/i.test(html) &&
    (/_username|name="password"|connectez-vous/i.test(html) || /\/en\/login/i.test(html))
  );
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
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url, opts);
      if (!res.ok) {
        await new Promise((r) => setTimeout(r, PROFILE_RETRY_DELAY_MS));
        continue;
      }
      const html = await res.text();
      if (isLoginHtml(html) && attempt < 2) {
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
  if (!useIframe) {
    const html = await fetchProfileHtml(person.profile_url);
    if (html) extractContactsFromHtml(html, person);
  }
  if (useIframe || !person.email || !person.phone) {
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
  const step = 350;
  for (let elapsed = 0; elapsed < maxMs; elapsed += step) {
    if (hasListPageContent(doc)) return true;
    if (extractListFromDoc(doc, "manager", "").length > 0) return true;
    await new Promise((r) => setTimeout(r, step));
  }
  return hasListPageContent(doc);
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

function gatherAllListUrls() {
  const base = listBaseUrlFromPage();
  const baseKey = listSearchKey(base);
  const urls = new Set([base]);
  const role = getRoleFromUrl(base);
  const searchCountry = getSearchCountryFromUrl(base);
  const onPage = extractListFromDoc(document, role, searchCountry).length;
  const pageSize = Math.max(onPage || 0, 12, 20);

  document.querySelectorAll('a[href*="offset="]').forEach((a) => {
    try {
      const full = new URL(a.href || a.getAttribute("href"), base).href.replace(/#.*$/, "");
      if (isListPaginationLink(full, base) || listSearchKey(full) === baseKey) urls.add(full);
    } catch (_) {
      /* ignore */
    }
  });

  const total = parseTotalPeople(document);
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

async function fetchPageDoc(url) {
  const same =
    url.replace(/#.*$/, "") === location.href.replace(/#.*$/, "") &&
    getOffsetFromUrl(url) === getOffsetFromUrl(location.href);
  if (same) return document;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) return null;
  return new DOMParser().parseFromString(await res.text(), "text/html");
}

async function collectAllListPages(role, searchCountry) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const base = listBaseUrlFromPage();
  const byProfile = new Map();
  const urls = gatherAllListUrls();
  const total = parseTotalPeople(document);
  const countryLabel = searchCountry ? ` — ${searchCountry}` : "";

  infoboxProgressShow(
    `Liste — ${urls.length} page(s) à lire`,
    total ? `Environ ${total} contacts${countryLabel}` : `Collecte des noms${countryLabel}`
  );
  await new Promise((r) => setTimeout(r, 300));

  for (let i = 0; i < urls.length; i++) {
    if (infoboxCancelled()) break;
    infoboxProgressShow(
      `Page liste ${i + 1} / ${urls.length}`,
      `Lecture des noms sur BoxRec${countryLabel}…`
    );
    document.title = `InfoBox ${i + 1}/${urls.length}…`;
    const doc = await fetchPageDoc(urls[i]);
    if (!doc) continue;
    extractListFromDoc(doc, role, searchCountry).forEach((p) => byProfile.set(p.profile_url, p));
    if (i < urls.length - 1 && !(await waitCancellable(900))) break;
  }
  document.title = document.title.replace(/^InfoBox.*/, "BoxRec");

  const count = byProfile.size;
  if (total && count < total * 0.5) {
    const pageSize = extractListFromDoc(document, role, searchCountry).length || 20;
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

async function enrichAllProfiles(people) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  async function runPass(labelSuffix) {
    for (let i = 0; i < people.length; i++) {
      if (infoboxCancelled()) break;
      const p = people[i];
      infoboxProgressShow(
        `Profils ${i + 1} / ${people.length}${labelSuffix}`,
        `${p.name || "Contact"} — e-mails et téléphones…`
      );
      document.title = `InfoBox ${i + 1}/${people.length}`;
      await enrichOneProfile(p, { useIframe: false });
      if (i < people.length - 1 && !(await waitCancellable(PROFILE_FETCH_DELAY_MS))) break;
    }
  }

  await runPass("");
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
    ["nom", "email", "telephone", "adresse", "role", "pays_recherche", "localisation"].join(sep) +
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
  if (!/boxrec\.com/i.test(location.hostname)) {
    alert("InfoBox : utilisez ce favori sur boxrec.com (page liste), pas sur InfoBox.");
    return;
  }
  const role = getRoleFromUrl(location.href);
  let searchCountry = getSearchCountryFromUrl(location.href) || getSearchCountryFromPage(document);

  infoboxProgressShow("InfoBox v3.4", "Détection de la liste BoxRec…", { showStop: false });
  const listReady = await waitForListContent(document);
  if (!listReady) {
    infoboxProgressHide(0);
    alert(
      "InfoBox : liste non détectée.\n\n" +
        "Attendez que les noms s’affichent sur boxrec.com, puis relancez le favori."
    );
    return;
  }
  if (!searchCountry) searchCountry = getSearchCountryFromPage(document);
  if (!searchCountry) {
    infoboxProgressHide(0);
    alert(
      "InfoBox : pays de recherche non détecté.\n\n" +
        "Filtrez par pays sur BoxRec (ex. Grenada, United Kingdom) puis relancez le favori."
    );
    return;
  }

  infoboxProgressShow(
    "InfoBox démarré",
    searchCountry ? `Pays : ${searchCountry} — préparation…` : "Préparation de la sauvegarde…"
  );
  if (!(await waitCancellable(400))) {
    infoboxProgressHide(0);
    window.__infoboxRun = 0;
    return;
  }

  const prevTitle = document.title;
  document.title = "InfoBox — collecte…";

  infoboxProgressShow("Sauvegarde en cours", "Lecture de toutes les pages de la liste…");
  let people = await collectAllListPages(role, searchCountry);
  if (infoboxCancelled()) {
    await handleCancelledExport(people, role, searchCountry, prevTitle);
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
    await handleCancelledExport(people, role, searchCountry, prevTitle);
    return;
  }

  const withEmail = people.filter((p) => p.email).length;
  const withPhone = people.filter((p) => p.phone).length;
  const withBoth = people.filter((p) => p.email && p.phone).length;
  const missingAny = people.filter((p) => !p.email || !p.phone).length;

  infoboxProgressShow("Export CSV et PDF…", "Création des fichiers sur votre ordinateur…");
  document.title = "InfoBox — export…";
  try {
    await exportFiles(people, role, searchCountry);
  } catch (err) {
    document.title = prevTitle;
    infoboxProgressHide(0);
    alert("InfoBox : échec du PDF (" + (err && err.message ? err.message : err) + "). CSV peut être déjà téléchargé.");
    downloadCsv(people, role, searchCountry);
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
      "Pays : " +
      searchCountry +
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
