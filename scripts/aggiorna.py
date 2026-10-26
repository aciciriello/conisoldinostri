"""Aggiornamento settimanale di conisoldinostri.it.

Esegue in sequenza:
  1. aggiorna_dati.py       bilancio dello Stato (OpenBDAP) ed Eurostat
  2. aggiorna_parlamento.py nuovo conto consuntivo della Camera, se uscito

Ogni passo salva i nuovi dati solo se supera i controlli di coerenza; se un
passo fallisce, i dati precedenti restano al loro posto.
Scrive il rapporto in scripts/rapporti/ e, su Mac, mostra una notifica.
Se la variabile d'ambiente PUBBLICA_CMD è impostata (es. un rsync verso il
server), la esegue quando ci sono novità e nessun errore.

Uso:  .venv/bin/python scripts/aggiorna.py
"""

import json
import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
import aggiorna_dati  # noqa: E402
import aggiorna_parlamento  # noqa: E402

RAPPORTI = QUI / "rapporti"


def passo(modulo):
    try:
        return modulo.aggiorna()
    except Exception as e:  # rete giù, sito cambiato...: il passo fallisce ma gli altri proseguono
        return False, {"fonte": modulo.__name__, "errori": [f"{type(e).__name__}: {e}"], "avvisi": [],
                       "novita": [], "traccia": traceback.format_exc()}


def notifica(titolo, testo):
    if platform.system() == "Darwin":
        testo = testo.replace('"', "'")[:200]
        subprocess.run(["osascript", "-e", f'display notification "{testo}" with title "{titolo}"'], check=False)


def main():
    inizio = datetime.now()
    esiti = [passo(aggiorna_dati), passo(aggiorna_parlamento)]
    ok = all(e[0] for e in esiti)
    novita = [n for _, r in esiti for n in r["novita"]]

    righe = [f"# Aggiornamento del {inizio:%d/%m/%Y %H:%M}", "",
             f"Esito: **{'tutto regolare' if ok else 'ERRORI: alcuni dati non sono stati aggiornati'}**", ""]
    for _, r in esiti:
        righe.append(f"## {r['fonte']}")
        for titolo, chiave in (("Errori", "errori"), ("Novità", "novita"), ("Avvisi", "avvisi")):
            if r[chiave]:
                righe.append(f"**{titolo}**")
                righe += [f"- {x}" for x in r[chiave]]
        if not (r["errori"] or r["novita"]):
            righe.append("Nessuna novità.")
        if r.get("traccia"):
            righe += ["```", r["traccia"], "```"]
        righe.append("")

    # le novità finiscono anche sul sito, nella striscia "Cosa è cambiato" (le ultime 30, dalla più recente)
    if novita:
        f = QUI.parent / "site" / "data" / "novita.json"
        elenco = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        oggi = inizio.date().isoformat()
        nuove = [{"data": oggi, "testo": t} for t in novita if not any(x["testo"] == t for x in elenco)]
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps((nuove + elenco)[:30], ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(f)

    if ok and novita and os.environ.get("PUBBLICA_CMD"):
        esito = subprocess.run(os.environ["PUBBLICA_CMD"], shell=True, capture_output=True, text=True)
        righe.append(f"Pubblicazione: {'riuscita' if esito.returncode == 0 else 'NON riuscita'}")
        if esito.returncode:
            righe += ["```", esito.stderr[-2000:], "```"]
            ok = False

    RAPPORTI.mkdir(exist_ok=True)
    testo = "\n".join(righe)
    (RAPPORTI / f"{inizio:%Y-%m-%d}.md").write_text(testo, encoding="utf-8")
    (RAPPORTI / "ultimo.md").write_text(testo, encoding="utf-8")
    print(testo)

    if not ok:
        notifica("Con i soldi nostri: aggiornamento con errori", "Apri scripts/rapporti/ultimo.md per i dettagli.")
    elif novita:
        notifica("Con i soldi nostri: nuovi dati", "; ".join(novita))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
