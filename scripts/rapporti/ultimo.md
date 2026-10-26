# Aggiornamento del 26/10/2026 21:36

Esito: **ERRORI: alcuni dati non sono stati aggiornati**

## aggiorna_dati
**Errori**
- RuntimeError: https://opencoesione.gov.it/it/api/aggregati/?format=json: HTTP Error 403: Forbidden
```
Traceback (most recent call last):
  File "/home/runner/work/conisoldinostri/conisoldinostri/scripts/aggiorna_dati.py", line 41, in get
    with urllib.request.urlopen(req, timeout=60) as r:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/urllib/request.py", line 215, in urlopen
    return opener.open(url, data, timeout)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/urllib/request.py", line 521, in open
    response = meth(req, response)
               ^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/urllib/request.py", line 630, in http_response
    response = self.parent.error(
               ^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/urllib/request.py", line 559, in error
    return self._call_chain(*args)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/urllib/request.py", line 492, in _call_chain
    result = func(*args)
             ^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.15/x64/lib/python3.12/urllib/request.py", line 639, in http_error_default
    raise HTTPError(req.full_url, code, msg, hdrs, fp)
urllib.error.HTTPError: HTTP Error 403: Forbidden

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/runner/work/conisoldinostri/conisoldinostri/scripts/aggiorna.py", line 35, in passo
    return modulo.aggiorna()
           ^^^^^^^^^^^^^^^^^
  File "/home/runner/work/conisoldinostri/conisoldinostri/scripts/aggiorna_dati.py", line 368, in aggiorna
    "coesione": coesione(),
                ^^^^^^^^^^
  File "/home/runner/work/conisoldinostri/conisoldinostri/scripts/aggiorna_dati.py", line 202, in coesione
    a = get("https://opencoesione.gov.it/it/api/aggregati/?format=json")
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/conisoldinostri/conisoldinostri/scripts/aggiorna_dati.py", line 55, in get
    raise RuntimeError(f"{url}: {e}")
RuntimeError: https://opencoesione.gov.it/it/api/aggregati/?format=json: HTTP Error 403: Forbidden

```

## Bilancio interno della Camera
**Avvisi**
- dati del Senato fermi al 2025 (previsione): quando esce un nuovo bilancio interno va inserito a mano (il sito del Senato blocca lo scaricamento automatico; vedi README)
Nessuna novità.
