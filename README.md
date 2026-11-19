# Exportify to M3U

`exportify_to_m3u.py` importa gli export CSV di Spotify/Exportify, genera playlist M3U per Navidrome e svolge manutenzione della libreria musicale. Gestisce anche metadati bilingui, copertine, diagnosi dei brani mancanti e sincronizzazione degli album con Lidarr.

**Versione documentata: v0.151.** Per tutte le opzioni aggiornate e per lo storico completo delle modifiche, lo script resta la fonte autorevole:

```bash
python3 exportify_to_m3u.py --help
python3 exportify_to_m3u.py --version
python3 exportify_to_m3u.py --changelog
```

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

Le descrizioni playlist Spotify disponibili vengono copiate nel campo commento di Navidrome, con in fondo l'attribuzione al file `.m3u` e al repository GitHub. Spotify può però restituire `null` per le descrizioni non esposte dall'API: in quel caso lo script mantiene il commento già presente in Navidrome, invece di cancellarlo.

## 5. Lidarr: criteri e comportamento

`--lidarr-sync` raccoglie tutti gli album distinti presenti nelle playlist attive (anche quando i brani sono già trovati nella libreria), gli album salvati da Spotify (`saved_albums.csv`) e gli album originali Spotify dei brani trovati sotto un'edizione locale diversa. La risoluzione prova prima l'URI Spotify dell'Album Artist, poi il collegamento dell'album Spotify e infine le ricerche MusicBrainz per nome/crediti e il catalogo locale Lidarr. Per selezionare un album richiede comunque un titolo compatibile e un credito artista verificabile; quando servono più edizioni considera anche la data di prima pubblicazione. Le compilation/Various Artists, gli artisti ambigui e i risultati non dimostrabili restano nel report: non vengono aggiunti alla cieca.

La ricerca riconosce anche varianti esplicite in coda al titolo, ad esempio `Original Soundtrack`, `Official Special Edition Soundtrack`, `The Definitive Soundtrack` e `OST`. Queste varianti ampliano le query, ma **non** eliminano i controlli finali su artista, release-group e data: non sono un via libera al fuzzy matching. Se l'`Album Artist` Spotify non è risolvibile (caso comune quando contiene il publisher anziché il compositore), il secondo tentativo può usare gli artisti delle tracce mancanti; il fallback è accettato solo se il release-group MusicBrainz riporta proprio quell'artista e il titolo resta esatto.

Con `--apply` la sync:

- aggiunge gli artisti e gli album risolti che non sono già nel catalogo;
- abilita il monitoraggio degli album richiesti che erano presenti ma non monitorati;
- può accodare `AlbumSearch` per gli album richiesti e incompleti, rispettando `LIDARR_SYNC_RESEARCH_DAYS`;
- preserva il monitoraggio già attivo sugli altri album. L'assenza da Spotify o dalle playlist **non** è un comando per disattivare un monitoraggio impostato manualmente in Lidarr.

Per includere mixtape, soundtrack, live, compilation, EP e altre tipologie nel catalogo, controlla il **Metadata Profile** in Lidarr. Il profilo predefinito può escludere alcuni tipi di release-group. Puoi impostare `LIDARR_METADATA_PROFILE_NAME` (preferito) oppure `LIDARR_METADATA_PROFILE_ID` nel file `env`; il profilo deve esistere già in Lidarr. La libreria host vista dal processo e il root visto dal container devono coincidere (`LIDARR_MUSIC_ROOT` / `E2M_LIBRARY_ROOT` e `LIDARR_CONTAINER_ROOT`).

La sync usa il database SQLite host-side di Lidarr in sola lettura per evitare gli endpoint globali lenti. Configura `LIDARR_DB_PATH` se il database non si trova nel path predefinito sotto `E2M_CONFIG_ROOT`. Se il database non è leggibile, le aggiunte vengono sospese invece di procedere con identità non verificate.

Gli album irrisolti da Lidarr e quelli deduplicati su uno stesso MBID vengono salvati nel report giornaliero. La fase `star_liked` aggiunge una sezione separata con ogni album salvato su Spotify che non ha un match per titolo nel catalogo Navidrome locale. Dopo una run controlla `logs/e2m_mancanti_<GG-MM-AAAA>.txt` e le righe `[SKIP]`, `[warn]` e `[ERRORE]` del log.

## 6. Artwork: recupero e confronto delle copertine

La fase artwork distingue due compiti:

1. Recuperare una copertina quando manca oppure quando quella locale è più piccola della soglia (32 KiB predefiniti). Prima controlla le immagini già incorporate nelle tracce; se non trova una cover valida consulta i cataloghi online.
2. Verificare le copertine locali già sane. La verifica confronta l'immagine locale con il front approvato della release esatta nel Cover Art Archive e con immagini da cataloghi indipendenti. Una sostituzione di una cover locale già sana richiede una release MusicBrainz esatta e accordo visivo tra almeno due fonti artwork indipendenti; un risultato ambiguo viene segnalato per revisione, non sovrascritto. Per una cover mancante, da v0.144 Apple/iTunes, Deezer, TheAudioDB e Wikimedia Commons possono proporre immagini: viene accettata una cover soltanto se almeno due cataloghi restituiscono immagini con hash percettivo entro la soglia configurata. I risultati Google Images restano suggerimenti di revisione, non una seconda fonte catalogo.

**Da v0.126 la verifica delle copertine sane non è limitata a 50 album:** `MISSING_ARTWORK_MAX_VERIFICATIONS_PER_RUN=0` (predefinito) significa tutti gli album candidati nella run. Le verifiche già valide nella cache vengono saltate finché il fingerprint della cover e la finestra di cache non scadono. Un valore positivo imposta un tetto per run. Questo limite è distinto da `MISSING_ARTWORK_MAX_PER_RUN`, che limita soltanto le ricerche/download di nuove copertine (250 predefinito; `0` = senza limite).

La fase può essere disattivata con `MISSING_ARTWORK_ENABLED=false` oppure saltata per una singola run con `--no-artwork-download`. La preview è inclusa in `--all --dry-run`. Da v0.128 le cover folder già sane vengono anche controllate per l'embedding: vengono aggiunte solo alle tracce che non hanno già una cover embedded sopra soglia.

Le fonti online hanno circuit breaker indipendenti per MusicBrainz, Cover Art Archive, Apple/iTunes, Deezer, TheAudioDB, Wikimedia Commons e Google Images. Un `503` o una connessione rifiutata non interrompe gli altri cataloghi; gli errori temporanei non vengono inseriti nella cache `not_found`. TheAudioDB usa il key pubblico di test e viene interrogato al massimo una volta ogni 2,1 secondi. Se i cataloghi non sono sufficienti a formare una coppia visivamente concorde, l'album resta senza cover automatica e viene riprovato secondo la cache/cursore.

Da v0.129, quando i cataloghi non trovano una cover valida, `MISSING_ARTWORK_GOOGLE_IMAGES=true` (predefinito) cerca su Google Images con `album_name album cover` e, come seconda query, `artist album_name album cover`. Google è un fallback, non la fonte principale: vengono rifiutati thumbnail, URL non HTTPS/pubblici, immagini non valide, file troppo piccoli e copertine con proporzioni non plausibili. La ricerca parte solo per album con cover mancante o sotto soglia.

La stessa fase cerca le immagini artista mancanti. `MISSING_ARTWORK_ARTIST_ENABLED=true` abilita il recupero (nome corretto da v0.130); `MISSING_ARTWORK_MAX_ARTIST_PER_RUN=250` limita il numero di artisti per esecuzione (`0` = tutti; il cursore si aggiorna solo sugli elementi completati); `MISSING_ARTWORK_RETRY_DAYS=14` controlla la cache dei nomi senza risultati e dei cataloghi incompleti. Per le cartelle bilingui viene provato prima il nome inglese tra parentesi, `NAME_TRANSLATIONS` o la traduzione automatica; il nome originale è l’unico fallback successivo. Ogni identità viene cercata su Deezer e poi su Google Images prima di passare alla successiva. Le immagini album devono essere almeno `MISSING_ARTWORK_MIN_GOOGLE_ALBUM_DIMENSION=400` px sul lato corto; per gli artisti la soglia è `MISSING_ARTWORK_MIN_GOOGLE_ARTIST_DIMENSION=300`. L'immagine artista viene salvata come `artist.jpg`, `artist.png` o `artist.webp` nella cartella artista: Navidrome riconosce il prefisso `artist.*` nella priorità artwork locale predefinita (`ArtistArtPriority=artist.*, album/artist.*, external`). Dopo lo scan, dalla v0.131 lo script rimette automaticamente in coda con la CLI Navidrome gli artisti e gli album ancora senza artwork, così il server rilegge i nuovi file locali.

## 7. Metadati, artista sconosciuto e nomi bilingui

La normalizzazione dei tag mantiene distinti i crediti del singolo brano (`ARTIST` / `ARTISTS`) e quelli dell'album (`ALBUMARTIST` / `ALBUMARTISTS`). La correzione di `[Unknown Artist]` usa i crediti coerenti delle tracce e il contesto dell'album; non trasforma automaticamente una compilation o una collaborazione ambigua in un album di un solo artista.

Per i FLAC la pulizia considera anche le varianti legacy dei commenti Vorbis (`ALBUMARTIST`, `ALBUM_ARTIST`, `ALBUMARTISTS`, `ALBUM_ARTISTS`) e le occorrenze ripetute. Quando rimuove un placeholder, conserva i crediti aggiuntivi reali e non sovrascrive i nomi degli artisti delle singole tracce. La correzione è integrata nelle fasi `album_unify` e `fix_unknown_artists` della pipeline completa. Da v0.128 il controllo raw avviene anche quando ffprobe mostra già un valore apparentemente valido: questo intercetta commenti ripetuti `ALBUM_ARTIST=[Unknown Artist]` che altrimenti rimangono nascosti. Quando `ARTIST` contiene il placeholder, i crediti multipli conservati in `ARTISTS` vengono usati come sorgente di riparazione; i crediti reali non vengono eliminati.

I nomi CJK, Hangul e cirillici possono essere conservati in forma bilingue. Per il russo lo script prova ora la traduzione inglese semantica con lo stesso controllo di confidenza usato per kanji/Hangul; se il provider non traduce, restituisce solo una traslitterazione fonetica, che resta il fallback. Le regole curate di `NAME_TRANSLATIONS` e `NAME_FIXES` hanno sempre precedenza. Per l'artwork, quando esiste una forma bilingue, la parte inglese viene cercata prima della grafia originale.

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
| Artwork | `MISSING_ARTWORK_ENABLED`, `MISSING_ARTWORK_MAX_PER_RUN`, `MISSING_ARTWORK_GOOGLE_IMAGES`, `MISSING_ARTWORK_ARTIST_ENABLED`, `MISSING_ARTWORK_MAX_ARTIST_PER_RUN`, `MISSING_ARTWORK_MIN_GOOGLE_ALBUM_DIMENSION`, `MISSING_ARTWORK_MIN_GOOGLE_ARTIST_DIMENSION`, `MISSING_ARTWORK_RETRY_DAYS`, `MISSING_ARTWORK_VERIFY_EXISTING`, `MISSING_ARTWORK_MAX_VERIFICATIONS_PER_RUN`, `MISSING_ARTWORK_MIN_EXISTING_COVER_BYTES`, `MISSING_ARTWORK_EMBED_AUDIO` |
| Traduzione automatica CJK/Hangul/cirillico | `AUTO_NAME_TRANSLATION_ENABLED`, `AUTO_NAME_TRANSLATION_MIN_CONFIDENCE`, `AUTO_NAME_TRANSLATION_MAX_NEW_PER_RUN`, `AUTO_NAME_TRANSLATION_CACHE_DAYS`, `AUTO_NAME_TRANSLATION_TIMEOUT` |
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
| `SPOTIFY_LOCAL_PROXY` | Configurazione per MP3 proxy e playlist Local Files (`auto_sync` abilita la scansione automatica in `--all`). |

Le regole hanno scopi distinti: `ARTIST_CANONICAL_NAMES` decide la grafia tag, `NAME_TRANSLATIONS` / `NAME_FIXES` forniscono alias per ricerca e matching, `ARTIST_GROUPS` dichiara equivalenze bidirezionali e `ALIASES` collega una grafia Spotify a quella locale in una sola direzione.

## 12. Sicurezza e risoluzione problemi

- Lo script controlla il mount persistente e rifiuta operazioni se la libreria o i percorsi protetti non sono accessibili. Non crea una directory musicale vuota per mascherare un disco smontato.
- Prima di una manutenzione estesa usa `--dry-run` e leggi il log. `--all --apply` abilita più operazioni insieme, inclusi dedupe, Lidarr e proxy Spotify.
- Se una traccia presente risulta mancante, usa `--explain` con artista, album e titolo esattamente come compaiono nel CSV.
- Se Lidarr non risolve un album, controlla il Metadata Profile, il report degli irrisolti e la corrispondenza tra root host e container. Non forzare un match ambiguo solo per ridurre il numero di mancanti.
- Se `star_liked` segnala una password Navidrome rifiutata (nel log v0.135 era `octochic`), aggiorna `ND_PASS_<UTENTE>` nel file `env`/`.env` con la password effettiva di quell'account: lo script non può correggere una credenziale remota. Un utente senza password configurata viene saltato e segnalato.
- Se la riparazione tag segnala un file audio non più disponibile, il percorso è diventato obsoleto fra indicizzazione e scrittura (per esempio perché un'altra fase l'ha spostato/eliminato): viene saltato e contato separatamente, senza far fallire la fase per un file già assente.
- Le cartelle in `SLKSD_FAILED_FOLDER` richiedono revisione/import manuale. Il completamento di `DownloadedAlbumsScan` non garantisce che Lidarr abbia importato automaticamente ogni cartella in `failed_imports`.
- `SPOTIFY_LOCAL_PROXY.auto_sync=true` (predefinito) aggiorna `auto_albums` dentro `--all --apply`; configura `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET` per le query non presenti in cache. Con `auto_sync=false` la scansione automatica viene saltata, ma i proxy manuali continuano a essere elaborati.
- Se Exportify non scarica, controlla `--fetch-status` e `--fetch-check`; per vedere il browser usa `--fetch-headed`.
- I messaggi `[ERRORE]`, `[warn]`, `[review]` e `[SKIP]` nel log spiegano le operazioni non completate o sospese.

La cronologia dettagliata delle release è mantenuta nel blocco `CHANGELOG` dello script: `python3 exportify_to_m3u.py --changelog`.
