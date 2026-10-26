# Con i soldi nostri — conisoldinostri.it

Cruscotto pubblico che rende leggibili le spese e le entrate dello Stato italiano a partire dai dati ufficiali in open data.

## Fonti

- **Ragioneria Generale dello Stato – OpenBDAP** (`openbdap.rgs.mef.gov.it`): API JSON pubblica del portale "Esplora il Bilancio dello Stato". Legge di Bilancio, Assestamento e Rendiconto dal 2013, spese ed entrate.
- **Eurostat** (dati ISTAT): popolazione, età, occupati, famiglie, pensionati, studenti; debito pubblico, deficit e interessi (gov_10dd_edpt1), PIL (nama_10_gdp), inflazione (prc_hicp_aind), spesa pubblica per funzione nei Paesi UE (gov_10a_exp, COFOG).
- **OpenCoesione**: valore dei progetti finanziati con fondi europei e nazionali per la coesione, per tema e per regione (per ogni regione si sommano le sue province, per non contare due volte i progetti multiregionali).
- **Camera dei deputati**: conto consuntivo interno (Doc. VIII), letto automaticamente dal PDF.
- **Senato della Repubblica**: bilancio interno (Doc. VIII), da inserire a mano (vedi sotto).

## Struttura

```
scripts/aggiorna.py               aggiornamento completo con rapporto (da usare questo)
scripts/aggiorna_dati.py          bilancio dello Stato ed Eurostat -> site/data/spesa.json
scripts/aggiorna_parlamento.py    bilancio della Camera            -> site/data/parlamento.json
scripts/programma_settimanale.sh  installa l'esecuzione automatica del lunedì (macOS)
scripts/rapporti/                 rapporti di ogni aggiornamento (ultimo.md = il più recente)
site/                             il sito statico (index.html + data/)
```

## Aggiornare i dati

```bash
.venv/bin/python scripts/aggiorna.py
```

Ogni fonte viene salvata **solo se supera i controlli di coerenza**: per esempio la somma delle missioni deve dare la spesa totale, la somma delle voci della Camera deve dare il totale dichiarato. Se un controllo fallisce, i dati precedenti restano al loro posto e il rapporto spiega il motivo. Il rapporto elenca anche le novità (nuovo Rendiconto, nuovi dati demografici, nuovo bilancio della Camera).

Prima installazione dell'ambiente Python:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Aggiornamento automatico settimanale

```bash
bash scripts/programma_settimanale.sh
```

Esegue `aggiorna.py` ogni lunedì alle 7:30 e mostra una notifica sul Mac se ci sono novità o errori. Per toglierlo: `bash scripts/programma_settimanale.sh rimuovi`.

Sul server di pubblicazione si usa invece cron:

```
30 7 * * 1 cd /percorso/CruscottoSpesaStato && .venv/bin/python scripts/aggiorna.py
```

Se la variabile `PUBBLICA_CMD` è impostata (per esempio un `rsync` della cartella `site/` verso il server), viene eseguita automaticamente quando ci sono novità e nessun errore.

## Senato: procedura manuale annuale

Il sito del Senato non consente lo scaricamento automatico dei documenti. Quando esce il nuovo bilancio interno (Doc. VIII, di solito a dicembre), scaricarlo da senato.it → Cittadini → Spese e trasparenza → Bilancio interno, e inserire le cifre nella sezione `"senato"` di `site/data/parlamento.json` con la stessa struttura della Camera.

## Pubblicare

La cartella `site/` è un sito statico: basta copiarla su qualsiasi hosting (nginx, Netlify, GitHub Pages). Non serve un backend.

## Scelte di metodo

- Di base è escluso il **rimborso dei titoli di Stato in scadenza** (Titolo III della spesa) e, simmetricamente, l'**accensione di nuovi prestiti** (Titolo IV delle entrate); gli interessi restano inclusi.
- Le 34 missioni sono raggruppate in 7 **aree** per la lettura; il raggruppamento è redazionale ed è dichiarato nella pagina.
- Le entrate sono raggruppate per imposta riconoscendo il nome della voce, perché la classificazione RGS cambia dal 2023.
- I valori sono in euro correnti (non deflazionati).
