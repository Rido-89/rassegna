# Rassegna stampa: Napoli e area vesuviana

Ogni ora GitHub scarica i feed RSS elencati in `feeds.json`, rigenera la pagina e la pubblica.

## Messa online (una volta sola, circa 5 minuti)
1. Crea un account su github.com e un nuovo repository (pubblico), per esempio `rassegna`.
2. Carica tutti i file di questa cartella, comprese `.github/workflows/update.yml`.
3. Vai in Settings → Pages → Build and deployment → Source: **GitHub Actions**.
4. Vai in Actions → "Aggiorna rassegna" → Run workflow. Dopo un minuto trovi il link in Settings → Pages.

## Personalizzare
In `feeds.json`: `keywords` sono le parole che una notizia deve contenere per passare il filtro (vale per i feed con `"filter": true`, cioè quelli nazionali). `exclude` serve a scartare argomenti, per esempio `["calcio", "serie a"]` per togliere il Napoli sportivo.

Modifica `feeds.json`: aggiungi o togli fonti e categorie. Un feed che non risponde viene saltato.
Per trovare il feed di un sito prova `/feed`, `/rss` o cerca "RSS" nel footer.

## Da sapere
- "Tempo reale" qui significa ogni ora. Per cambiare frequenza modifica `cron` nel workflow.
- GitHub sospende i workflow programmati dopo 60 giorni senza attività sul repository: basta riattivarlo da Actions.
