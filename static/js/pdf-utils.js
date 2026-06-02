/**
 * Export PDF InfoBox — texte lisible + tableau avec lignes.
 */
(function (global) {
  const LATIN_MAP = {
    à: "a",
    á: "a",
    â: "a",
    ã: "a",
    ä: "a",
    å: "a",
    æ: "ae",
    ç: "c",
    è: "e",
    é: "e",
    ê: "e",
    ë: "e",
    ì: "i",
    í: "i",
    î: "i",
    ï: "i",
    ñ: "n",
    ò: "o",
    ó: "o",
    ô: "o",
    õ: "o",
    ö: "o",
    ø: "o",
    ù: "u",
    ú: "u",
    û: "u",
    ü: "u",
    ý: "y",
    ÿ: "y",
    œ: "oe",
    ß: "ss",
    À: "A",
    Á: "A",
    Â: "A",
    Ä: "A",
    Ç: "C",
    È: "E",
    É: "E",
    Ê: "E",
    Ë: "E",
    Ì: "I",
    Í: "I",
    Î: "I",
    Ï: "I",
    Ñ: "N",
    Ò: "O",
    Ó: "O",
    Ô: "O",
    Ö: "O",
    Ù: "U",
    Ú: "U",
    Û: "U",
    Ü: "U",
    "–": "-",
    "—": "-",
    "'": "'",
    "'": "'",
    '"': '"',
    '"': '"',
  };

  function pdfSafeText(value) {
    if (value == null) return "";
    let s = String(value);
    while (/&[A-Za-z0-9.,'()\-À-ÿ ]&/.test(s)) {
      s = s.replace(/&([^&;\s])&/g, "$1");
    }
    s = s
      .normalize("NFC")
      .replace(/\uFEFF/g, "")
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
    return s.replace(/[^\x09\x0A\x0D\x20-\x7E]/g, (ch) => LATIN_MAP[ch] ?? "");
  }

  function personToPdfRow(p, country) {
    return [
      pdfSafeText(p.name),
      pdfSafeText(p.email),
      pdfSafeText(p.phone),
      pdfSafeText(p.address),
      pdfSafeText(p.role),
      pdfSafeText(p.search_country || country),
      pdfSafeText(p.location),
    ];
  }

  const PDF_HEADERS = [
    "Nom",
    "Email",
    "Telephone",
    "Adresse",
    "Role",
    "Pays (recherche)",
    "Localisation",
  ];

  function renderContactsPdf(doc, people, title, searchCountry) {
    const country = searchCountry || (people[0] && people[0].search_country) || "";
    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.setTextColor(28, 25, 23);
    doc.text(pdfSafeText(title), 12, 12);
    doc.autoTable({
      startY: 18,
      theme: "grid",
      head: [PDF_HEADERS],
      body: people.map((p) => personToPdfRow(p, country)),
      styles: {
        font: "helvetica",
        fontSize: 8,
        cellPadding: 3,
        lineColor: [87, 83, 78],
        lineWidth: 0.25,
        textColor: [28, 25, 23],
        overflow: "linebreak",
      },
      headStyles: {
        fillColor: [159, 18, 57],
        textColor: [255, 255, 255],
        fontStyle: "bold",
        fontSize: 8,
        lineWidth: 0.35,
        lineColor: [120, 14, 43],
      },
      alternateRowStyles: {
        fillColor: [255, 253, 248],
      },
      bodyStyles: {
        valign: "top",
      },
      columnStyles: {
        0: { cellWidth: 30 },
        1: { cellWidth: 40 },
        2: { cellWidth: 26 },
        3: { cellWidth: 32 },
        4: { cellWidth: 14 },
        5: { cellWidth: 28 },
        6: { cellWidth: 34 },
      },
      margin: { left: 10, right: 10, top: 18 },
      tableLineColor: [87, 83, 78],
      tableLineWidth: 0.25,
    });
  }

  global.pdfSafeText = pdfSafeText;
  global.renderContactsPdf = renderContactsPdf;
  global.personToPdfRow = personToPdfRow;
})(typeof window !== "undefined" ? window : globalThis);
