"""Cerca un nuovo conto consuntivo della Camera dei deputati (Doc. VIII) e, se
lo trova, ne legge le cifre e aggiorna site/data/parlamento.json.

I documenti hanno indirizzi prevedibili:
  https://documenti.camera.it/_dati/leg{L}/lavori/documentiparlamentari/IndiceETesti/008/{NNN}/INTERO.pdf
Si leggono la tabella "Riclassificazione funzionale della spesa" (allegato 1)
e i capitoli 1000-1005 (indennità e rimborsi dei deputati). Il file viene
aggiornato solo se le voci sommano esattamente al totale dichiarato.

Il Senato non consente lo scaricamento automatico: i suoi dati restano manuali.

Uso:  python3 scripts/aggiorna_parlamento.py            (cerca documenti nuovi)
      python3 scripts/aggiorna_parlamento.py FILE.pdf   (legge un PDF già scaricato, senza salvare)
Richiede: pypdf (vedi requirements.txt)
"""

import io
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pypdf import PdfReader

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "parlamento.json"
URL = "https://documenti.camera.it/_dati/leg{leg}/lavori/documentiparlamentari/IndiceETesti/008/{n:03d}/INTERO.pdf"

# Righe della riclassificazione funzionale -> voci del cruscotto (le altre confluiscono in "funzionamento")
VOCI = {
    "Deputati": ("membri", "Deputati in carica"),
    "Commissioni": ("commissioni", "Commissioni, giunte e comitati"),
    "Gruppi parlamentari": ("gruppi", "Contributo ai gruppi parlamentari"),
    "Ex Deputati": ("ex_membri", "Vitalizi e pensioni degli ex deputati"),
    "Personale": ("personale", "Personale dipendente"),
    "Altro personale": ("altro_personale", "Collaboratori e altro personale"),
    "Pensionati": ("pensionati", "Pensioni degli ex dipendenti"),
}
FUNZIONAMENTO = ("funzionamento", "Sedi, servizi, informatica, imposte e altre spese")
# Voci dei capitoli 1000 e 1005 (indennità e rimborsi), nell'ordine mostrato nel cruscotto
VOCI_MEMBRO = [
    ("Indennità parlamentare", "Indennità parlamentare (lorda)"),
    ("Rimborso delle spese di soggiorno", "Rimborso spese di soggiorno (diaria)"),
    ("Rimborso delle spese per l’esercizio del mandato", "Rimborso spese per l'esercizio del mandato"),
    ("Rimborso spese di viaggio ai deputati", "Rimborso spese di viaggio"),
    ("Indennità d’ufficio", "Indennità d'ufficio (cariche interne)"),
    ("Rimborso spese telefoniche", "Rimborso spese telefoniche"),
]


def euro(t):
    """'81.954.164' o '50.140.000,00' -> numero."""
    return float(t.replace(".", "").replace(",", "."))


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cruscotto-spesa-stato/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dati = r.read()
    return dati if dati[:4] == b"%PDF" else None


def testo(pdf_bytes):
    pagine = [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages]
    return pagine, "\n".join(pagine)


def leggi_consuntivo(pdf_bytes):
    """Estrae le cifre da un conto consuntivo della Camera. Solleva ValueError se qualcosa non torna."""
    pagine, tutto = testo(pdf_bytes)
    intestazione = re.sub(r"\s+", " ", " ".join(pagine[:1]))
    m = re.search(r"CONTO CONSUNTIVO.*?ANNO FINANZIARIO (\d{4})", intestazione)
    if not m:
        raise ValueError("non è un conto consuntivo")
    anno = int(m.group(1))
    m = re.search(r"deliberato dall.Uf\s?ficio di Presidenza\s+nella riunione del ([^\n_]+)", intestazione, re.I)
    data = m.group(1).strip() if m else None

    # Tabella di riclassificazione funzionale
    pag = next((p for p in pagine if "RICLASSIFICAZIONE FUNZIONALE DELLA SPESA" in p and "CONTO CONSUNTIVO" in p and "Totale complessivo" in p), None)
    if not pag:
        raise ValueError("tabella di riclassificazione funzionale non trovata")
    righe, totale = {}, None
    for riga in pag.splitlines():
        r = re.match(r"^(\d{1,2}) (.+?) ((?:\d{1,3}(?:\.\d{3})+ ?)+)\d+,\d+%$", riga.strip())
        if r:
            numeri = r.group(3).split()
            righe[r.group(2).strip()] = euro(numeri[-1])  # ultima colonna: totale della voce
        t = re.match(r"^Totale complessivo .*?(\d{1,3}(?:\.\d{3})+) 100,00%", riga.strip())
        if t:
            totale = euro(t.group(1))
    if not totale or len(righe) < 15:
        raise ValueError(f"tabella letta in modo incompleto ({len(righe)} righe)")
    voci = {}
    for nome, valore in righe.items():
        chiave = next((v for k, v in VOCI.items() if re.match(re.escape(k) + r"\b", nome)), FUNZIONAMENTO)
        voci.setdefault(chiave, 0)
        voci[chiave] += valore
    if any(v not in voci for v in VOCI.values()):
        mancanti = [v[1] for v in VOCI.values() if v not in voci]
        raise ValueError(f"voci non trovate nella tabella: {', '.join(mancanti)}")
    if abs(sum(voci.values()) - totale) > 1:
        raise ValueError(f"le voci sommano a {sum(voci.values()):,.0f} invece di {totale:,.0f}")

    # Indennità e rimborsi dei deputati (previsioni definitive dei capitoli 1000 e 1005)
    blocco = tutto[tutto.index("CATEGORIA I\nDEPUTATI"):][:2500]
    blocco = re.sub(r"\s+", " ", re.sub(r"-\n", "", blocco)).replace("’", "'")  # parole spezzate a fine riga
    membro = []
    for cerca, etichetta in VOCI_MEMBRO:
        r = re.search(re.escape(cerca.replace("’", "'")) + r"[^\d]{0,20}?(\d{1,3}(?:\.\d{3})+,\d{2})", blocco)
        if not r:
            raise ValueError(f"voce dei deputati non trovata: {cerca}")
        membro.append({"nome": etichetta, "valore": euro(r.group(1))})

    piano = re.sub(r"\s+", " ", re.sub(r"-\n", "", tutto))
    m = re.search(r"dotazione annuale, prevista in ([\d,]+) milioni", piano)
    dotazione = round(float(m.group(1).replace(",", ".")) * 1e6) if m else None
    return {
        "anno": anno,
        "data": data,
        "totale": round(totale),
        "voci": [{"id": k, "nome": n, "valore": round(v)} for (k, n), v in sorted(voci.items(), key=lambda x: -x[1])],
        "membro_annuo": membro,
        "dotazione_stato": dotazione,
    }


def cerca_nuovi(attuale):
    """Prova i Doc. VIII successivi a quello già letto, nella legislatura corrente e nella successiva."""
    leg, n = attuale.get("leg", 19), attuale.get("doc_n", 0)
    for l, start in ((leg, n + 1), (leg + 1, 1)):
        for k in range(start, start + 4):
            url = URL.format(leg=l, n=k)
            try:
                pdf = scarica(url)
            except urllib.error.HTTPError:
                continue
            if pdf:
                yield l, k, url, pdf


def aggiorna():
    """Restituisce (ok, rapporto) per lo script di aggiornamento settimanale."""
    rapporto = {"fonte": "Bilancio interno della Camera", "errori": [], "avvisi": [], "novita": []}
    dati = json.loads(OUT.read_text(encoding="utf-8"))
    cam = dati["camera"]
    for leg, n, url, pdf in cerca_nuovi(cam):
        try:
            letto = leggi_consuntivo(pdf)
        except ValueError as e:
            if "non è un conto consuntivo" in str(e):  # es. progetto di bilancio: si salta
                cam.update(leg=leg, doc_n=max(n, cam.get("doc_n", 0)) if leg == cam.get("leg", 19) else n)
                continue
            rapporto["errori"].append(f"Doc. VIII n. {n} (leg. {leg}) non letto correttamente: {e}. Dati della Camera non aggiornati.")
            return False, rapporto
        if letto["anno"] <= cam["anno"]:
            continue
        cam.update(
            anno=letto["anno"], leg=leg, doc_n=n, url=url, totale=letto["totale"], voci=letto["voci"],
            documento=f"Conto consuntivo della Camera dei deputati per l'anno finanziario {letto['anno']} (Doc. VIII n. {n})"
                      + (f", deliberato il {letto['data']}" if letto["data"] else ""),
        )
        cam["membro_annuo"]["voci"] = letto["membro_annuo"]
        cam["membro_annuo"]["_fonte"] = f"Capitoli 1000 e 1005, previsioni definitive {letto['anno']}"
        if letto["dotazione_stato"]:
            cam["dotazione_stato"] = letto["dotazione_stato"]
        rapporto["novita"].append(f"È uscito il bilancio consuntivo {letto['anno']} della Camera dei deputati: "
                                  f"{letto['totale'] / 1e6:,.1f} milioni di spesa.".replace(",", "X").replace(".", ",").replace("X", ".").replace("deputati: ", "deputati: "))
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    sen = dati.get("senato")
    if sen is None or sen["anno"] < cam["anno"] or sen.get("previsione"):
        stato = "assenti" if sen is None else f"fermi al {sen['anno']}" + (" (previsione)" if sen.get("previsione") else "")
        rapporto["avvisi"].append(f"dati del Senato {stato}: quando esce un nuovo bilancio interno va inserito a mano "
                                  "(il sito del Senato blocca lo scaricamento automatico; vedi README)")
    return True, rapporto


if __name__ == "__main__":
    if len(sys.argv) > 1:  # prova di lettura di un PDF locale
        print(json.dumps(leggi_consuntivo(Path(sys.argv[1]).read_bytes()), ensure_ascii=False, indent=2))
    else:
        ok, r = aggiorna()
        for chiave in ("errori", "avvisi", "novita"):
            for riga in r[chiave]:
                print(f"  [{chiave}] {riga}")
        sys.exit(0 if ok else 1)
