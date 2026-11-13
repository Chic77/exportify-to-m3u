# Exportify to M3U

`exportify_to_m3u.py` importa gli export CSV di Spotify/Exportify, genera playlist M3U per Navidrome e svolge manutenzione della libreria musicale. Gestisce anche metadati bilingui, copertine, diagnosi dei brani mancanti e sincronizzazione degli album con Lidarr.

**Versione documentata: v0.128.** Per tutte le opzioni aggiornate e per lo storico completo delle modifiche, lo script resta la fonte autorevole:

```bash
python3 exportify_to_m3u.py --help
python3 exportify_to_m3u.py --version
python3 exportify_to_m3u.py --changelog
```

## v0.128 — affidabilità artwork, ripresa e riparazione FLAC

- I circuit breaker artwork sono separati per MusicBrainz, Cover Art Archive, Apple/iTunes e Deezer. Un provider in errore non spegne gli altri; HTTP 429/5xx e problemi di rete applicano un backoff limitato al provider interessato.
- Errori temporanei di catalogo o download non diventano risultati negativi permanenti: gli album restano riprovabili. Il limite `MISSING_ARTWORK_MAX_PER_RUN` usa un cursore round-robin, così le cartelle successive non restano in attesa dietro a un gruppo iniziale irrisolto.
- Anche una copertina folder già sana viene propagata ai file audio dell'album che non hanno un'immagine embedded sana. Le immagini embedded esistenti sopra soglia non vengono sovrascritte.
- Il repair `[Unknown Artist]` esamina i commenti FLAC raw, inclusi i nomi legacy e i valori ripetuti. Se `ARTIST` è placeholder, recupera i crediti reali da `ARTISTS`; conserva i crediti dei brani e rimuove il placeholder da tutte le varianti `ALBUMARTIST`.
- La sync Lidarr confronta i MBID con lo snapshot SQLite globale prima di un nuovo POST e gestisce i conflitti `AlbumExistsValidator` senza ripetere aggiunte duplicate. L'import slskd resta distinto dal riallineamento accessorio dei path artista.
- In `--all`, la sincronizzazione automatica del catalogo proxy Spotify viene omessa quando mancano le credenziali OAuth; gli album automatici già configurati sono preservati e la generazione dei proxy manuali continua.

## 1. Avvio rapido

Esegui i comandi dalla directory che contiene `exportify_to_m3u.py`, `env` (o `.env`) ed `exportify_names.json`:

```bash
cd ~/homelab/scripts
python3 exportify_to_m3u.py --all --dry-run
```

Esamina il log e il report dei mancanti. Quando il risultato è corretto, applica le modifiche:

```bash
python3 exportify_to_m3u.py --all --apply
```

La prima esecuzione completa può richiedere tempo: indicizzazione, controlli MusicBrainz e confronto delle copertine lavorano sulla libreria condivisa. `--dry-run` evita le scritture operative previste dalle fasi, ma alcune attività di sola lettura, cache e preparazione temporanea possono comunque avvenire.

## 2. Cosa fa la pipeline

```text
Spotify
  └─ Exportify: ZIP con CSV per utente
       └─ estrazione e normalizzazione CSV
            └─ matching con i file audio locali
                 └─ playlist M3U + report .missing.txt
                      └─ scan Navidrome

Manutenzione opzionale/integrata:
  tag e date · album artist · duplicati · artwork · Lidarr · proxy Spotify
```

Senza opzioni viene eseguita la normale pipeline playlist e manutenzione tag prevista dalla modalità predefinita. `--all` seleziona tutte le fasi disponibili, inclusi Lidarr, artwork, dedupe, diagnosi/riparazione album e proxy Spotify. `--sync-only` è la modalità quotidiana leggera: fetch, playlist, proprietari e preferiti; salta la manutenzione massiva di tag e file.

| Obiettivo | Comando | Effetto |
|---|---|---|
| Aggiornamento completo in anteprima | `python3 exportify_to_m3u.py --all --dry-run` | Mostra le modifiche previste senza applicare le scritture operative. |
| Aggiornamento completo | `python3 exportify_to_m3u.py --all --apply` | Applica le fasi selezionate, inclusa la sync Lidarr. |
| Solo playlist quotidiane | `python3 exportify_to_m3u.py --sync-only` | Scarica gli export disponibili e aggiorna le M3U senza manutenzione massiva. |
| Solo conversione playlist | `python3 exportify_to_m3u.py --playlists` | Forza la fase playlist quando si combinano altre fasi. |
| Solo Lidarr, anteprima | `python3 exportify_to_m3u.py --lidarr-sync` | Risolve album mancanti e saved albums, senza scrivere su Lidarr. |
| Applicare la sync Lidarr | `python3 exportify_to_m3u.py --lidarr-sync --apply` | Aggiunge/monitora gli album risolti e salva il report degli irrisolti. |
| Ricostruire l'indice file | `python3 exportify_to_m3u.py --rebuild-cache` | Ignora l'indice filesystem memorizzato e lo ricrea. |
| Forzare la riscrittura M3U | `python3 exportify_to_m3u.py --force` | Riscrive le playlist selezionate anche se il CSV non è cambiato. |
| Saltare la scansione finale | aggiungi `--no-scan` | Non invia lo scan FULL a Navidrome a fine run. |

Le opzioni si possono combinare. Per esempio:

```bash
python3 exportify_to_m3u.py --users chic --only liked --fetch --no-scan
```

`--users` limita le fasi per-utente; la manutenzione della libreria condivisa resta condivisa. `--only` importa soltanto le playlist indicate (nomi separati da virgola), mentre `--skip` le esclude.

## 3. Installazione su Debian

Su Debian 12/13 usa una virtualenv: `pip install --user` è bloccato dall'ambiente Python gestito dal sistema (PEP 668).

```bash
sudo apt install python3-venv ffmpeg flac
cd ~/homelab/scripts
python3 -m venv .venv
.venv/bin/pip install pykakasi hangul-romanize numpy mutagen
```

Servono `ffmpeg`, `ffprobe` e `metaflac`. Le librerie Python sono facoltative per le funzioni che le usano: `pykakasi` per la lettura giapponese, `hangul-romanize` per Hangul, `numpy` per i confronti waveform e `mutagen` per la lettura/scrittura di alcuni metadati e l'embedding artwork. FLAC, MP3 e M4A hanno fallback nativi per l'embedding delle copertine. Per Ogg/Opus/WAV è necessario Mutagen.

Per il fetch automatico da Exportify installa anche Playwright e Chromium:

```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```

Se `.venv` esiste accanto allo script viene usata automaticamente, anche da cron. `EXPORTIFY_NO_VENV=1` disabilita questo comportamento.

## 4. Exportify: login, download e utenti

Il login è da eseguire una volta per ogni utente Navidrome:

```bash
python3 exportify_to_m3u.py --fetch-login chic
```

Si apre un browser visibile per autorizzare Spotify/Exportify. In alternativa puoi importare cookie esportati dal browser:

```bash
python3 exportify_to_m3u.py --fetch-login chic --fetch-cookies chic_cookies.json
```

I cookie sono credenziali temporanee: importa il file e poi cancellalo. Non committare sessioni, cookie o file `env`.

Comandi utili:

```bash
python3 exportify_to_m3u.py --fetch-status  # stato login di tutti gli utenti Navidrome
python3 exportify_to_m3u.py --fetch-check   # verifica headless delle sessioni salvate
python3 exportify_to_m3u.py --fetch-list    # sessioni e ZIP disponibili
python3 exportify_to_m3u.py --fetch-only    # scarica gli ZIP ed esce
python3 exportify_to_m3u.py --fetch         # scarica prima di elaborare
```

Per associare uno ZIP a un utente, il nome dovrebbe iniziare con il nome Navidrome seguito da un separatore, ad esempio `chic_spotify_playlists.zip`. In assenza di un nome riconoscibile, `SPOTIFY_USERS` in `exportify_names.json` può collegare l'identità Spotify (colonna `Added By`) all'utente Navidrome.

## 5. Lidarr: criteri e comportamento

`--lidarr-sync` raccoglie gli album delle tracce mancanti nelle playlist attive e gli album salvati da Spotify (`saved_albums.csv`). La risoluzione usa MusicBrainz e il catalogo locale Lidarr; per selezionare un album richiede un titolo compatibile, crediti artista verificabili e, quando servono più edizioni, la data di prima pubblicazione. Le compilation/Various Artists, gli artisti ambigui e i risultati non dimostrabili restano nel report: non vengono aggiunti alla cieca.

La ricerca riconosce anche varianti esplicite in coda al titolo, ad esempio `Original Soundtrack`, `Official Special Edition Soundtrack`, `The Definitive Soundtrack` e `OST`. Queste varianti ampliano le query, ma **non** eliminano i controlli finali su artista, release-group e data: non sono un via libera al fuzzy matching. Se l'`Album Artist` Spotify non è risolvibile (caso comune quando contiene il publisher anziché il compositore), il secondo tentativo può usare gli artisti delle tracce mancanti; il fallback è accettato solo se il release-group MusicBrainz riporta proprio quell'artista e il titolo resta esatto.

Con `--apply` la sync:

- aggiunge gli artisti e gli album risolti che non sono già nel catalogo;
- abilita il monitoraggio degli album richiesti che erano presenti ma non monitorati;
- può accodare `AlbumSearch` per gli album richiesti e incompleti, rispettando `LIDARR_SYNC_RESEARCH_DAYS`;
- preserva il monitoraggio già attivo sugli altri album. L'assenza da Spotify o dalle playlist **non** è un comando per disattivare un monitoraggio impostato manualmente in Lidarr.

Per includere mixtape, soundtrack, live, compilation, EP e altre tipologie nel catalogo, controlla il **Metadata Profile** in Lidarr. Il profilo predefinito può escludere alcuni tipi di release-group. Puoi impostare `LIDARR_METADATA_PROFILE_NAME` (preferito) oppure `LIDARR_METADATA_PROFILE_ID` nel file `env`; il profilo deve esistere già in Lidarr. La libreria host vista dal processo e il root visto dal container devono coincidere (`LIDARR_MUSIC_ROOT` / `E2M_LIBRARY_ROOT` e `LIDARR_CONTAINER_ROOT`).

La sync usa il database SQLite host-side di Lidarr in sola lettura per evitare gli endpoint globali lenti. Configura `LIDARR_DB_PATH` se il database non si trova nel path predefinito sotto `E2M_CONFIG_ROOT`. Se il database non è leggibile, le aggiunte vengono sospese invece di procedere con identità non verificate.

Gli album irrisolti e quelli deduplicati su uno stesso MBID vengono salvati nel report giornaliero. Dopo una run controlla `logs/e2m_mancanti_<GG-MM-AAAA>.txt` e le righe `[SKIP]`, `[warn]` e `[ERRORE]` del log.

## 6. Artwork: recupero e confronto delle copertine

La fase artwork distingue due compiti:

1. Recuperare una copertina quando manca oppure quando quella locale è più piccola della soglia (32 KiB predefiniti). Prima controlla le immagini già incorporate nelle tracce; se non trova una cover valida consulta le fonti online.
2. Verificare le copertine locali già sane. La verifica confronta l'immagine locale con il front approvato della release esatta nel Cover Art Archive e con cataloghi indipendenti. Una sostituzione richiede prove concordi e una release MusicBrainz esatta; un risultato ambiguo viene segnalato per revisione, non sovrascritto.

**Da v0.126 la verifica delle copertine sane non è limitata a 50 album:** `MISSING_ARTWORK_MAX_VERIFICATIONS_PER_RUN=0` (predefinito) significa tutti gli album candidati nella run. Le verifiche già valide nella cache vengono saltate finché il fingerprint della cover e la finestra di cache non scadono. Un valore positivo imposta un tetto per run. Questo limite è distinto da `MISSING_ARTWORK_MAX_PER_RUN`, che limita soltanto le ricerche/download di nuove copertine (250 predefinito; `0` = senza limite).

La fase può essere disattivata con `MISSING_ARTWORK_ENABLED=false` oppure saltata per una singola run con `--no-artwork-download`. La preview è inclusa in `--all --dry-run`. Da v0.128 le cover folder già sane vengono anche controllate per l'embedding: vengono aggiunte solo alle tracce che non hanno già una cover embedded sopra soglia.

Le fonti online hanno circuit breaker indipendenti. Un `503` MusicBrainz o una connessione rifiutata da Apple/Deezer non interrompe gli altri cataloghi; gli errori temporanei non vengono inseriti nella cache `not_found`. Se il provider resta indisponibile, gli album vengono rinviati e il cursore round-robin fa avanzare il batch alla run successiva.

## 7. Metadati, artista sconosciuto e nomi bilingui

La normalizzazione dei tag mantiene distinti i crediti del singolo brano (`ARTIST` / `ARTISTS`) e quelli dell'album (`ALBUMARTIST` / `ALBUMARTISTS`). La correzione di `[Unknown Artist]` usa i crediti coerenti delle tracce e il contesto dell'album; non trasforma automaticamente una compilation o una collaborazione ambigua in un album di un solo artista.

Per i FLAC la pulizia considera anche le varianti legacy dei commenti Vorbis (`ALBUMARTIST`, `ALBUM_ARTIST`, `ALBUMARTISTS`, `ALBUM_ARTISTS`) e le occorrenze ripetute. Quando rimuove un placeholder, conserva i crediti aggiuntivi reali e non sovrascrive i nomi degli artisti delle singole tracce. La correzione è integrata nelle fasi `album_unify` e `fix_unknown_artists` della pipeline completa. Da v0.128 il controllo raw avviene anche quando ffprobe mostra già un valore apparentemente valido: questo intercetta commenti ripetuti `ALBUM_ARTIST=[Unknown Artist]` che altrimenti rimangono nascosti. Quando `ARTIST` contiene il placeholder, i crediti multipli conservati in `ARTISTS` vengono usati come sorgente di riparazione; i crediti reali non vengono eliminati.

I nomi CJK, Hangul e cirillici possono essere conservati in forma bilingue. Per il russo è disponibile una traslitterazione offline dell'alfabeto cirillico: per esempio `Тоска` diventa `Тоска (Toska)` e `Я сошла с ума` diventa `Я сошла с ума (Ya soshla s uma)`. Le regole curate di `NAME_TRANSLATIONS` e `NAME_FIXES` hanno precedenza nella risoluzione e nel matching; la romanizzazione automatica è un fallback.

## 8. Diagnostica e manutenzione selettiva

```bash
# Tutte le tracce mancanti ricalcolate dai CSV attivi
python3 exportify_to_m3u.py --missing logs/missing-now.txt

# Spiega perché una riga Spotify non è stata abbinata
python3 exportify_to_m3u.py --explain "ARTIST|||ALBUM|||TITLE"

# Diagnostica album duplicati/spezzati e possibili problemi di separatori
python3 exportify_to_m3u.py --diagnose-album-splits

# Riparazione gruppi album: prima anteprima, poi applicazione
python3 exportify_to_m3u.py --repair-album-groups
python3 exportify_to_m3u.py --repair-album-groups --apply

# Riparazione prudente dei nomi file FLAC
python3 exportify_to_m3u.py --fix-flac-safe
python3 exportify_to_m3u.py --fix-flac-safe --apply

# Allineamento cartelle Lidarr e import download slskd
python3 exportify_to_m3u.py --lidarr-folder-fix
python3 exportify_to_m3u.py --lidarr-import-slskd

# Confronto duplicati audio; le operazioni distruttive richiedono --apply
python3 exportify_to_m3u.py --dedupe-tracks
python3 exportify_to_m3u.py --dedupe-tracks --apply
```

Per dedupe, senza `--hard-delete` i file confermati vengono spostati nel cestino configurato. `--hard-delete` è irreversibile: usalo soltanto dopo aver controllato il log.

## 9. Fasi e contatore

Le fasi condizionali (per esempio scan Navidrome, report Lidarr o attività artwork) vengono aggiunte o rimosse dal piano quando la pipeline scopre quali rami verranno davvero eseguiti. Per questo il totale pianificato può cambiare durante la run. Da v0.126 l'intestazione e la barra mostrano il numero progressivo esatto (`#1`, `#2`, …), anziché un rapporto `X/Y` con denominatore mobile. Il riepilogo finale stampa `Fasi eseguite: N` e una riga temporale per ogni fase completata; il totale finale è quindi verificabile e non dipende dalle stime iniziali.

## 10. Log, report e cache

Percorsi predefiniti (personalizzabili nel file `env`):

- `logs/e2m_v<VERSIONE>_<GG-MM-AAAA>.log`: log giornaliero, accodato dalle run della stessa versione;
- `logs/e2m_mancanti_<GG-MM-AAAA>.txt`: copertura playlist, album più carenti, elenco brani mancanti e report Lidarr;
- `arr-config/cache/`: indice filesystem, cache MusicBrainz, artwork e altri dati di servizio;
- `arr-config/exportify_sessions/`: sessioni Exportify;
- `arr-config/spotify_cookies/`: cookie importati temporaneamente.

Le cache evitano richieste ripetute e scansioni non necessarie. Usa `--rebuild-cache` quando hai spostato o sostituito una parte significativa della libreria oppure sospetti un indice filesystem obsoleto.

## 11. Configurazione

I due file hanno scopi diversi:

- **`env` / `.env`**: credenziali, percorsi host/container, URL dei servizi e parametri operativi. Le variabili già esportate nel processo hanno precedenza. Il file `ND_ENV_FILE`, se impostato, viene letto per primo; poi lo script cerca `.env` e `env` accanto a sé e nei percorsi legacy.
- **`exportify_names.json`**: configurazione persistente utente in formato JSONC (supporta commenti `//` e `/* ... */`). Contiene alias, correzioni dei nomi, associazioni utenti/Spotify e regole playlist/proxy.

Mantieni `env` privato e con permessi restrittivi:

```bash
chmod 600 env
```

Non inserire credenziali in `exportify_names.json`, README, log condivisi o repository. Le variabili più importanti sono:

| Area | Variabili principali |
|---|---|
| Navidrome | `ND_URL`, `ND_USER`, `ND_PASS`, `ND_PASS_<UTENTE>`, `ND_DEFAULT_USER`, `ND_MUSIC_ROOT` |
| Percorsi | `E2M_STORAGE_MOUNT`, `E2M_HOMELAB_ROOT`, `E2M_CONFIG_ROOT`, `E2M_LIBRARY_ROOT`, `E2M_NAVIDROME_DB`, `E2M_PLAYLIST_DIR`, `E2M_EXPORTIFY_DIR`, `E2M_ZIP_DIR`, `E2M_LOG_DIR`, `E2M_CACHE_DIR` |
| Lidarr | `LIDARR_URL`, `LIDARR_API_KEY`, `LIDARR_MUSIC_ROOT`, `LIDARR_CONTAINER_ROOT`, `LIDARR_DB_PATH`, `LIDARR_SYNC_SEARCH`, `LIDARR_SYNC_RESEARCH_DAYS`, `LIDARR_SYNC_MB_MAX_GROUPS`, `LIDARR_METADATA_PROFILE_NAME` / `LIDARR_METADATA_PROFILE_ID` |
| Artwork | `MISSING_ARTWORK_ENABLED`, `MISSING_ARTWORK_MAX_PER_RUN`, `MISSING_ARTWORK_VERIFY_EXISTING`, `MISSING_ARTWORK_MAX_VERIFICATIONS_PER_RUN`, `MISSING_ARTWORK_MIN_EXISTING_COVER_BYTES`, `MISSING_ARTWORK_EMBED_AUDIO` |
| Traduzione automatica CJK/Hangul | `AUTO_NAME_TRANSLATION_ENABLED`, `AUTO_NAME_TRANSLATION_MIN_CONFIDENCE`, `AUTO_NAME_TRANSLATION_MAX_NEW_PER_RUN`, `AUTO_NAME_TRANSLATION_CACHE_DAYS`, `AUTO_NAME_TRANSLATION_TIMEOUT` |
| Prestazioni | `EXPORTIFY_PROBE_WORKERS`, `EXPORTIFY_WAVEFORM_WORKERS`, `EXPORTIFY_FLAC_PROBE_TIMEOUT`, `EXPORTIFY_FLAC_COMPRESSION_LEVEL` |

Il file `env` distribuito con la tua installazione contiene commenti per le singole variabili e i valori accettati. Un override di percorso vuoto mantiene il default calcolato dallo script; per cron preferisci percorsi assoluti.

### Percorso del database Navidrome

`E2M_NAVIDROME_DB` è indipendente da `E2M_STORAGE_MOUNT`: il database può risiedere nel bind mount host usato dal container Navidrome per `/data`, anche se si trova su un altro filesystem o il percorso passa da un symlink. La directory padre deve già esistere. Gli altri percorsi persistenti (libreria, cache, ZIP e configurazione) continuano invece a essere verificati rispetto al mount dati.

Nel compose mostrato, il bind mount host di Navidrome è `/homelab/arr-config/navidrome:/data`; quindi il percorso host del database è normalmente:

```bash
E2M_NAVIDROME_DB=/homelab/arr-config/navidrome/navidrome.db
```

Usa sempre la parte host a sinistra dei due punti del bind mount, non `/data/navidrome.db` (che esiste solo dentro il container). Verifica il file effettivo con `readlink -f` prima di impostare l'override.

### Chiavi principali di `exportify_names.json`

| Chiave | Funzione |
|---|---|
| `NAME_TRANSLATIONS` | Nome inglese/latino ufficiale per matching e ricerca. |
| `NAME_FIXES` | Alias o romanizzazione corretta manualmente. |
| `ARTIST_CANONICAL_NAMES` | Grafia canonica da scrivere nei tag, comprese le forme bilingui. |
| `ALIASES` | Ponte direzionale fra grafia Spotify e grafia locale. |
| `ARTIST_GROUPS` | Equivalenze bidirezionali fra nomi dello stesso artista; non unire collaboratori distinti. |
| `FORCE_ARTIST` | Override artista per una traccia specifica nel matching. |
| `CSV_FIX` | Correzioni persistenti dei campi di alcune righe CSV. |
| `SPOTIFY_USERS` | Mappa ID Spotify → utente Navidrome. |
| `SKIP_PLAYLISTS` | Playlist escluse per utente. |
| `PLAYLIST_FOLDERS` | Sottocartella di destinazione per playlist selezionate. |
| `FETCH_IGNORED_USERS` | Utenti per cui saltare il fetch automatico, senza ignorare gli export locali. |
| `SPOTIFY_LOCAL_PROXY` | Configurazione per MP3 proxy e playlist Local Files. |

Le regole hanno scopi distinti: `ARTIST_CANONICAL_NAMES` decide la grafia tag, `NAME_TRANSLATIONS` / `NAME_FIXES` forniscono alias per ricerca e matching, `ARTIST_GROUPS` dichiara equivalenze bidirezionali e `ALIASES` collega una grafia Spotify a quella locale in una sola direzione.

## 12. Sicurezza e risoluzione problemi

- Lo script controlla il mount persistente e rifiuta operazioni se la libreria o i percorsi protetti non sono accessibili. Non crea una directory musicale vuota per mascherare un disco smontato.
- Prima di una manutenzione estesa usa `--dry-run` e leggi il log. `--all --apply` abilita più operazioni insieme, inclusi dedupe, Lidarr e proxy Spotify.
- Se una traccia presente risulta mancante, usa `--explain` con artista, album e titolo esattamente come compaiono nel CSV.
- Se Lidarr non risolve un album, controlla il Metadata Profile, il report degli irrisolti e la corrispondenza tra root host e container. Non forzare un match ambiguo solo per ridurre il numero di mancanti.
- Se `star_liked` segnala una password Navidrome rifiutata, aggiorna `ND_PASS_<UTENTE>` nel file `env`/`.env`: lo script non può correggere una credenziale remota. Un utente senza password configurata viene saltato e segnalato.
- Le cartelle in `SLKSD_FAILED_FOLDER` richiedono revisione/import manuale. Il completamento di `DownloadedAlbumsScan` non garantisce che Lidarr abbia importato automaticamente ogni cartella in `failed_imports`.
- Se la sync automatica dei proxy viene saltata in `--all`, configura `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`; i proxy manuali continuano a essere elaborati anche senza queste credenziali.
- Se Exportify non scarica, controlla `--fetch-status` e `--fetch-check`; per vedere il browser usa `--fetch-headed`.
- I messaggi `[ERRORE]`, `[warn]`, `[review]` e `[SKIP]` nel log spiegano le operazioni non completate o sospese.

La cronologia dettagliata delle release è mantenuta nel blocco `CHANGELOG` dello script: `python3 exportify_to_m3u.py --changelog`.
