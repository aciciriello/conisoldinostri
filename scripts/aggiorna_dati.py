"""Scarica i dati ufficiali del Bilancio dello Stato da OpenBDAP (Ragioneria
Generale dello Stato) e la popolazione residente da Eurostat, e li salva in un
unico file JSON letto dal cruscotto.

Uso:  python3 scripts/aggiorna_dati.py
Output: site/data/spesa.json

Prima di sovrascrivere il file esegue i controlli di coerenza: se un totale non
torna il file resta quello precedente e lo script termina con errore.
"""

import hashlib
import json
import re
import shutil
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

API = "https://openbdap.rgs.mef.gov.it/api/api/bds/"
EUROSTAT = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
            "demo_gind?geo=IT&indic_de=JAN&sinceTimePeriod=2013&format=JSON")
OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "spesa.json"
# Cache di un solo giorno: rilanciare lo script in giornata è veloce, l'esecuzione settimanale scarica dati freschi
CACHE = Path(__file__).resolve().parent / ".cache" / date.today().isoformat()
TOLLERANZA = 0.005  # scarto massimo ammesso tra un totale e la somma delle sue parti (0,5%)
MANCANTI = []

FASI = {2: "Legge di Bilancio", 3: "Legge di Assestamento", 4: "Rendiconto"}


def get(url, tentativi=3, opzionale=False):
    cache = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    for i in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cruscotto-spesa-stato/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.15)
                dati = json.loads(r.read().decode("utf-8"))
            CACHE.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(dati), encoding="utf-8")
            return dati
        except Exception as e:  # rete instabile: riprova
            if getattr(e, "code", None) == 429 and i < tentativi - 1:  # il servizio chiede di rallentare
                time.sleep(15 * (i + 1))
                continue
            if i == tentativi - 1:
                if opzionale:  # dettaglio non disponibile sul server: si prosegue senza
                    MANCANTI.append(url)
                    return None
                raise RuntimeError(f"{url}: {e}")
            time.sleep(2 * (i + 1))


def bds(endpoint, opzionale=False, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return get(f"{API}{endpoint}?{q}", opzionale=opzionale)


def num(x):
    return round(float(str(x).replace(",", ".")), 2) if x not in (None, "") else 0.0


def natura(anno, fase, codice):
    """Albero titoli -> categorie economiche (es. personale, interessi...)."""
    rows = bds("data_e15", opzionale=True, entrateSpese=1, anno=anno, fase=fase, navigazione=1, codice=codice)
    if rows is None and isinstance(codice, str):  # il server a volte accetta solo il codice senza zeri
        rows = bds("data_e15", opzionale=True, entrateSpese=1, anno=anno, fase=fase, navigazione=1, codice=int(codice))
    rows = rows or []
    titoli = {}
    for r in rows:
        if r["parent"] == "0":
            titoli.setdefault(r["name"], {"valore": num(r["value"]), "categorie": {}})["valore"] = num(r["value"])
        else:
            titoli.setdefault(r["parent"], {"valore": 0, "categorie": {}})["categorie"][r["name"]] = num(r["value"])
    return titoli


def esercizio(anno, fase, missioni):
    tot = bds("data_e1", anno=anno, fase=fase)
    e3 = bds("data_e3_tutti_spese", anno=anno, codice=0, fase=fase, navigazione=1) or {}
    per_missione = bds("data_e2", entrateSpese=1, anno=anno, fase=fase, navigazione=1, dettaglio=0) or []
    per_ministero = bds("data_e2", entrateSpese=1, anno=anno, fase=fase, navigazione=2, dettaglio=0) or []
    # Entrate: per singola voce (imposte, proventi...) e per titolo (tributarie, extra-tributarie, prestiti...)
    entrate_voci = bds("data_e2", entrateSpese=2, anno=anno, fase=fase, navigazione=1, dettaglio=0) or []
    entrate_titoli = bds("data_e2", entrateSpese=2, anno=anno, fase=fase, navigazione=2, dettaglio=0) or []

    out_missioni = []
    for r in per_missione:
        cod = int(r["id"])
        voce = {
            "codice": cod,
            "nome": missioni.get(cod, r["missione"]),
            "valore": num(r["pagato"]),
            "var_pct": num(r["variazione"]) if r["variazione"] not in (None, "") else None,
            "natura": natura(anno, fase, f"{cod:03d}"),
            # Titoli (correnti / capitale / rimborso debito): endpoint più affidabile della natura
            "titoli": {r["label_field"]: num(r["value_field"]) for r in
                       bds("data_e7_spese", anno=anno, fase=fase, codiceMissione=cod, spese_navigazione=1) or []},
        }
        if fase == 4:  # solo a consuntivo ha senso il confronto stanziato / pagato
            s = bds("data_e3_tutti_spese", opzionale=True, anno=anno, codice=f"{cod:03d}", fase=fase, navigazione=1) or {}
            voce["stanziato"] = num(s.get("valore1"))
        out_missioni.append(voce)

    return {
        "anno": anno,
        "fase": fase,
        "fase_nome": FASI[fase],
        "misura": "pagato" if fase == 4 else "stanziamento",
        "spese": num(tot["spese"]),
        "entrate": num(tot["entrate"]),
        "saldo": num(tot["saldo"]),
        "stanziato": num(e3.get("valore1")) if fase == 4 else None,
        "natura": natura(anno, fase, 0),
        "missioni": sorted(out_missioni, key=lambda m: -m["valore"]),
        "ministeri": sorted(
            [{"nome": r["missione"], "valore": num(r["pagato"])} for r in per_ministero],
            key=lambda m: -m["valore"]),
        "entrate_voci": sorted(
            [{"id": r["id"], "nome": r["missione"], "valore": num(r["pagato"])} for r in entrate_voci],
            key=lambda m: -m["valore"]),
        "entrate_titoli": {r["missione"]: num(r["pagato"]) for r in entrate_titoli},
    }


def popolazione():
    d = get(EUROSTAT)
    idx, val = d["dimension"]["time"]["category"]["index"], d["value"]
    return {anno: val[str(i)] for anno, i in idx.items() if str(i) in val}


def eurostat(dataset, scala=1, **filtri):
    """Serie annuale Eurostat per l'Italia: {anno: valore}. I filtri devono ridurre ogni dimensione a un solo valore."""
    q = "&".join(f"{k}={v}" for k, v in filtri.items())
    d = get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
            f"?geo=IT&sinceTimePeriod=2013&format=JSON&lang=EN&{q}")
    idx, val = d["dimension"]["time"]["category"]["index"], d["value"]
    return {anno: round(val[str(i)] * scala, 1) for anno, i in idx.items() if str(i) in val}


def eurostat_multi(dataset, dims, **filtri):
    """Serie Eurostat con più valori per alcune dimensioni: {valore_dim1: {valore_dim2: {anno: v}}}.
    `dims` sono le dimensioni da tenere separate (es. ["geo", "cofog99"]); i filtri possono essere liste."""
    q = "&".join(f"{k}={x}" for k, v in filtri.items() for x in (v if isinstance(v, list) else [v]))
    d = get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?format=JSON&lang=EN&{q}")
    ids, size = d["id"], d["size"]
    idx = {k: {i: c for c, i in d["dimension"][k]["category"]["index"].items()} for k in ids}
    out = {}
    for pos, val in d["value"].items():
        pos, coord = int(pos), {}
        for k, n in zip(reversed(ids), reversed(size)):
            coord[k] = idx[k][pos % n]
            pos //= n
        nodo = out
        for k in dims:
            nodo = nodo.setdefault(coord[k], {})
        nodo[coord["time"]] = val
    return out


# Funzioni di spesa pubblica (COFOG) confrontabili tra Paesi UE
COFOG = {"GF01": "Servizi generali (compresi interessi)", "GF02": "Difesa", "GF03": "Ordine pubblico e giustizia",
         "GF04": "Economia e trasporti", "GF05": "Ambiente", "GF06": "Casa e territorio", "GF07": "Sanità",
         "GF08": "Cultura e sport", "GF09": "Istruzione", "GF10": "Pensioni e protezione sociale"}
PAESI = {"IT": "Italia", "EU27_2020": "Media UE", "DE": "Germania", "FR": "Francia", "ES": "Spagna"}
# Regioni: slug OpenCoesione -> codici NUTS2 Eurostat (il Trentino-Alto Adige è la somma delle due province autonome)
REGIONI = {"abruzzo-regione": ["ITF1"], "basilicata-regione": ["ITF5"], "calabria-regione": ["ITF6"], "campania-regione": ["ITF3"],
           "emilia-romagna-regione": ["ITH5"], "friuli-venezia-giulia-regione": ["ITH4"], "lazio-regione": ["ITI4"],
           "liguria-regione": ["ITC3"], "lombardia-regione": ["ITC4"], "marche-regione": ["ITI3"], "molise-regione": ["ITF2"],
           "piemonte-regione": ["ITC1"], "puglia-regione": ["ITF4"], "sardegna-regione": ["ITG2"], "sicilia-regione": ["ITG1"],
           "toscana-regione": ["ITI1"], "trentino-alto-adigesudtirol-regione": ["ITH1", "ITH2"], "umbria-regione": ["ITI2"],
           "valle-daostavallee-daoste-regione": ["ITC2"], "veneto-regione": ["ITH3"]}


def macro():
    """Debito, PIL e inflazione (Eurostat)."""
    return {
        "debito": eurostat("gov_10dd_edpt1", scala=1e6, na_item="GD", sector="S13", unit="MIO_EUR"),
        "debito_pil": eurostat("gov_10dd_edpt1", na_item="GD", sector="S13", unit="PC_GDP"),
        "deficit_pil": eurostat("gov_10dd_edpt1", na_item="B9", sector="S13", unit="PC_GDP"),
        "interessi_pil": eurostat("gov_10dd_edpt1", na_item="D41PAY", sector="S13", unit="PC_GDP"),
        "pil": eurostat("nama_10_gdp", scala=1e6, na_item="B1GQ", unit="CP_MEUR"),
        "prezzi": eurostat("prc_hicp_aind", coicop="CP00", unit="INX_A_AVG"),
    }


def europa():
    """Spesa di tutta la pubblica amministrazione per funzione, in % del PIL, Italia e altri Paesi."""
    d = eurostat_multi("gov_10a_exp", ["geo", "cofog99"], geo=list(PAESI), cofog99=list(COFOG) + ["TOTAL"],
                       na_item="TE", sector="S13", unit="PC_GDP", sinceTimePeriod=2013)
    debito = eurostat_multi("gov_10dd_edpt1", ["geo"], geo=list(PAESI), na_item="GD", sector="S13", unit="PC_GDP", sinceTimePeriod=2013)
    return {"paesi": PAESI, "funzioni": COFOG, "spesa_pil": d, "debito_pil": debito}


def coesione():
    """Progetti finanziati con fondi europei e nazionali per la coesione (OpenCoesione), per tema e per regione."""
    a = get("https://opencoesione.gov.it/it/api/aggregati/?format=json")
    agg = a["aggregati"]
    euro = lambda x: float(str(x).replace(".", "").replace(",", "."))
    tot = lambda t: {"costo": euro(t["costo_pubblico"]), "pagato": euro(t["pagamenti"]), "progetti": int(t["progetti"])}
    pop = eurostat_multi("demo_r_d2jan", ["geo"], geo=[c for v in REGIONI.values() for c in v], sex="T", age="TOTAL", unit="NR",
                         sinceTimePeriod=date.today().year - 4)
    def abitanti(codici):
        anni = sorted(set.intersection(*[set(pop.get(c, {})) for c in codici]))
        return (sum(pop[c][anni[-1]] for c in codici), anni[-1]) if anni else (None, None)
    # Il totale "regionale" di OpenCoesione include progetti nazionali e multiregionali attribuiti per intero a ogni regione:
    # per non contare due volte gli stessi soldi usiamo la somma delle province della regione (progetti localizzati).
    regioni = {}
    for slug, r in agg["territori"]["regioni"].items():
        time.sleep(1.5)  # OpenCoesione limita le richieste ravvicinate
        dett = get(r["link"], tentativi=5)["aggregati"]["territori"]["province"]
        somma = {"costo": 0.0, "pagato": 0.0, "progetti": 0}
        for pv in dett.values():
            for k, v in tot(pv["totali"]).items():
                somma[k] += v
        ab, anno = abitanti(REGIONI.get(slug, []))
        regioni[slug] = {"nome": r["label"].title().replace("D'", "d'"), **somma, "abitanti": ab, "anno_abitanti": anno}
    return {
        "aggiornato": a.get("data_aggiornamento"),
        "totali": tot(agg["totali"]),
        "temi": {k: {"nome": v["label"], **tot(v["totali"])} for k, v in agg["temi"].items()},
        "regioni": regioni,
    }


def demografia(pop):
    over65_pct = eurostat("demo_pjanind", indic_de="PC_Y65_MAX")
    studenti = [eurostat("educ_uoe_enra02", age="TOTAL", sex="T", isced11=ed) for ed in ("ED1", "ED2", "ED3")]
    return {
        "over65": {a: round(pop[a] * v / 100) for a, v in over65_pct.items() if a in pop},
        "anziani_ogni_100": eurostat("demo_pjanind", indic_de="OLDDEP1"),
        "occupati": eurostat("lfsa_egan", scala=1000, sex="T", age="Y_GE15", unit="THS_PER", citizen="TOTAL"),
        "famiglie": eurostat("lfst_hhnhtych", scala=1000, agechild="TOTAL", n_child="TOTAL", phhcomp="TOTAL"),
        "pensionati": eurostat("spr_pns_ben", spdepm="TOTAL", spdepb="TOTAL", sex="T"),
        "studenti": {a: sum(s[a] for s in studenti) for a in studenti[0] if all(a in s for s in studenti)},
        "universitari": eurostat("educ_uoe_enrt01", worktime="TOTAL", sector="TOT_SEC", sex="T", isced11="ED5-8"),
    }


def scarto(parte, totale):
    return abs(parte - totale) / abs(totale) if totale else (0 if not parte else 1)


def controlli(dati):
    """Errori (bloccano la pubblicazione) e avvisi (da guardare, ma non bloccano)."""
    errori, avvisi = [], []
    tit3 = "TITOLO III - RIMBORSO PASSIVITA' FINANZIARIE"
    if not dati["esercizi"]:
        errori.append("nessun esercizio scaricato")
    for e in dati["esercizi"]:
        nome = f"{e['anno']} {e['fase_nome']}"
        verifiche = [
            ("somma delle missioni", sum(m["valore"] for m in e["missioni"]), e["spese"]),
            ("somma dei ministeri", sum(m["valore"] for m in e["ministeri"]), e["spese"]),
            ("somma per natura", sum(t["valore"] for t in e["natura"].values()), e["spese"]),
            ("somma delle voci di entrata", sum(v["valore"] for v in e["entrate_voci"]), e["entrate"]),
            ("somma dei titoli di entrata", sum(e["entrate_titoli"].values()), e["entrate"]),
        ]
        for cosa, parte, totale in verifiche:
            if scarto(parte, totale) > TOLLERANZA:
                errori.append(f"{nome}: {cosa} {parte / 1e9:.1f} mld contro un totale di {totale / 1e9:.1f} mld")
        if len(e["missioni"]) != 34:
            avvisi.append(f"{nome}: {len(e['missioni'])} missioni invece di 34 (cambio di classificazione?)")
        for m in e["missioni"]:
            if m["titoli"] and scarto(sum(m["titoli"].values()), m["valore"]) > 0.01:
                avvisi.append(f"{nome}: la missione {m['codice']} non torna con i suoi titoli")
        if e["fase"] == 4:  # a consuntivo entrate finali − spese finali deve dare il saldo ufficiale
            finali_e = sum(v for k, v in e["entrate_titoli"].items() if not k.startswith("TITOLO IV"))
            finali_s = e["spese"] - sum(m["titoli"].get(tit3, 0) for m in e["missioni"])
            if scarto(finali_e - finali_s, e["saldo"]) > 0.01:
                avvisi.append(f"{nome}: entrate − spese = {(finali_e - finali_s) / 1e9:.1f} mld, saldo ufficiale {e['saldo'] / 1e9:.1f} mld")
    for k, serie in dati["demografia"].items():
        if not serie:
            errori.append(f"serie demografica vuota: {k}")
    for k, serie in dati["macro"].items():
        if not serie:
            errori.append(f"serie macroeconomica vuota: {k}")
    if "IT" not in dati["europa"]["spesa_pil"] or "EU27_2020" not in dati["europa"]["spesa_pil"]:
        errori.append("confronto europeo: mancano Italia o media UE")
    reg = dati["coesione"]["regioni"]
    if len(reg) != 20 or any(r["abitanti"] is None for r in reg.values()):
        avvisi.append("fondi di coesione: dati regionali incompleti")
    somma_reg = sum(r["costo"] for r in reg.values())
    if somma_reg > dati["coesione"]["totali"]["costo"] * 1.001:
        errori.append("fondi di coesione: la somma delle regioni supera il totale nazionale (progetti contati due volte)")
    elif somma_reg < dati["coesione"]["totali"]["costo"] * 0.8:
        avvisi.append("fondi di coesione: oltre il 20% del valore non è attribuito a nessuna provincia")
    return errori, avvisi


def novita(vecchi, nuovi):
    """Cosa cambia rispetto all'ultima versione, in frasi comprensibili: finiscono nel rapporto e nella striscia "Cosa è cambiato" del sito."""
    tit3 = "TITOLO III - RIMBORSO PASSIVITA' FINANZIARIE"
    finali = lambda e: e["spese"] - sum(m["titoli"].get(tit3, 0) for m in e["missioni"])
    mld = lambda v: f"{v / 1e9:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " miliardi"
    pct = lambda v: ("+" if v >= 0 else "−") + f"{abs(v):.1f}".replace(".", ",") + "%"
    righe = []
    chiave = lambda e: (e["anno"], e["fase"])
    prima = {chiave(e): e for e in (vecchi or {}).get("esercizi", [])}
    dopo = {chiave(e): e for e in nuovi["esercizi"]}
    for anno, fase in sorted(set(dopo) - set(prima)):
        e = dopo[(anno, fase)]
        if fase == 4:
            p = dopo.get((anno - 1, 4))
            confronto = f" ({pct((finali(e) / finali(p) - 1) * 100)} rispetto al {anno - 1})" if p else ""
            righe.append(f"Sono usciti i conti definitivi del {anno} (Rendiconto): lo Stato ha speso {mld(finali(e))}{confronto}.")
        elif fase == 2:
            righe.append(f"È stata approvata la Legge di Bilancio {anno}: previsti {mld(finali(e))} di spesa.")
        else:
            righe.append(f"È stato approvato l'Assestamento {anno}: le previsioni di spesa sono ora di {mld(finali(e))}.")
    for k in sorted(set(prima) & set(dopo)):
        if scarto(dopo[k]["spese"], prima[k]["spese"]) > 0.001:
            righe.append(f"La Ragioneria ha rivisto i conti del {k[0]} ({dopo[k]['fase_nome']}): spesa da {mld(finali(prima[k]))} a {mld(finali(dopo[k]))}.")
    vd = (vecchi or {}).get("demografia", {})
    nomi = {"occupati": "occupati", "famiglie": "famiglie", "pensionati": "pensionati", "studenti": "studenti", "universitari": "iscritti all'università"}
    for nome, etichetta in nomi.items():
        nuovi_anni = sorted(set(nuovi["demografia"].get(nome, {})) - set(vd.get(nome, {})))
        if nuovi_anni and vd:
            righe.append(f"Nuovi dati ISTAT sul numero di {etichetta} ({', '.join(nuovi_anni)}).")
    vm, nm = (vecchi or {}).get("macro", {}), nuovi["macro"]
    for anno in sorted(set(nm["debito"]) - set(vm.get("debito", {}))):
        if vm:
            righe.append(f"Eurostat ha pubblicato il debito pubblico del {anno}: {mld(nm['debito'][anno])}, il {str(nm['debito_pil'].get(anno, '')).replace('.', ',')}% del PIL.")
    va = ((vecchi or {}).get("europa") or {}).get("spesa_pil", {}).get("IT", {}).get("TOTAL", {})
    for anno in sorted(set(nuovi["europa"]["spesa_pil"]["IT"]["TOTAL"]) - set(va)):
        if va and nuovi["europa"]["spesa_pil"]["IT"]["TOTAL"][anno] is not None:
            righe.append(f"Nuovo confronto europeo della spesa pubblica per il {anno}.")
    vc = (vecchi or {}).get("coesione") or {}
    if vc and vc.get("aggiornato") != nuovi["coesione"].get("aggiornato"):
        righe.append("OpenCoesione ha aggiornato i dati dei fondi per lo sviluppo nelle regioni.")
    return righe


def aggiorna():
    """Scarica, controlla e salva. Restituisce (ok, rapporto) per lo script di aggiornamento settimanale."""
    missioni = {int(m["id"]): m["descrizione"] for m in get(API + "missioni") if m["id"] != "0"}
    anni_rendiconto = sorted(int(a) for a in get(API + "anni/?fase=4&entrateSpese=1&speseNavigazione=1"))
    anni_previsione = sorted(int(a) for a in get(API + "anni/?fase=2&entrateSpese=1&speseNavigazione=1"))
    ultimo = max(anni_previsione)

    piani = [(a, 4) for a in anni_rendiconto]
    piani += [(a, 2) for a in anni_previsione if a > max(anni_rendiconto)]
    piani += [(a, 3) for a in anni_previsione if a > max(anni_rendiconto)]

    esercizi = []
    for anno, fase in piani:
        print(f"  {anno} - {FASI[fase]}...", flush=True)
        esercizi.append(esercizio(anno, fase, missioni))

    dati = {
        "aggiornato_il": date.today().isoformat(),
        "fonti": {
            "bilancio": "Ragioneria Generale dello Stato - OpenBDAP (openbdap.rgs.mef.gov.it)",
            "popolazione": "Eurostat demo_gind, popolazione residente al 1 gennaio (dati ISTAT)",
            "demografia": "Eurostat: demo_pjanind (età), lfsa_egan (occupati), lfst_hhnhtych (famiglie), "
                          "spr_pns_ben (pensionati), educ_uoe_enra02 / educ_uoe_enrt01 (studenti)",
        },
        "ultimo_anno": ultimo,
        "popolazione": (pop := popolazione()),
        "demografia": demografia(pop),
        "macro": macro(),
        "europa": europa(),
        "coesione": coesione(),
        "esercizi": esercizi,
    }

    errori, avvisi = controlli(dati)
    if MANCANTI:  # problema noto del server RGS (errore 500 su alcune missioni): una riga sola nel rapporto
        coppie = sorted({re.search(r"anno=(\d+).*codice=0*(\d+)", u).groups() for u in MANCANTI})
        avvisi.append(f"dettaglio per natura non fornito dal server RGS per {len(coppie)} combinazioni anno/missione "
                      f"(es. {', '.join(f'{a}/missione {c}' for a, c in coppie[:3])}): i totali non ne risentono")
    vecchi = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    rapporto = {"fonte": "Bilancio dello Stato ed Eurostat", "errori": errori, "avvisi": avvisi, "novita": novita(vecchi, dati)}
    if errori:
        return False, rapporto

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)  # sostituzione atomica: il sito non legge mai un file a metà
    for vecchia in CACHE.parent.glob("*"):
        if vecchia != CACHE and vecchia.is_dir():
            shutil.rmtree(vecchia, ignore_errors=True)
    print(f"Salvato {OUT} ({OUT.stat().st_size // 1024} KB, {len(esercizi)} esercizi)")
    return True, rapporto


def main():
    ok, rapporto = aggiorna()
    for chiave in ("errori", "avvisi", "novita"):
        for r in rapporto[chiave]:
            print(f"  [{chiave}] {r}")
    if not ok:
        print("Controlli non superati: il file dei dati NON è stato aggiornato.")
        sys.exit(1)


if __name__ == "__main__":
    main()
