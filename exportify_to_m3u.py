#!/usr/bin/env python3
"""
exportify_to_m3u.py - Exportify CSV -> playlist .m3u con path reali della libreria.

Sostituisce il vecchio script crontab. Migliorie:
  - intestazioni CSV italiane E inglesi, BOM-safe (utf-8-sig)
  - fallisce LOUD se un CSV non produce nemmeno un brano (niente piu' m3u vuoti)
  - normalizzazione seria (accenti, (Remastered), feat., punteggiatura)
  - indice da FILESYSTEM (Artista/Album/Brano.ext), non piu' dal DB beets
  - nomi file 'Artista - Album - 01 - Titolo' gestiti; kanji/unicode conservati;
    album multi-disco (Artista/Album/CD1/Traccia) indicizzati sotto l'artista vero
  - ARTIST_GROUPS: piu' nomi per lo stesso artista (aka), in entrambe le direzioni
  - virgole nel nome gestite via libreria ('Tyler, The Creator' resta intero)
  - nomi asiatici: NAME_TRANSLATIONS (traduzione/forma inglese ufficiale), NAME_FIXES,
    traduzione inglese automatica sopra soglia, poi romanizzazione fonetica pykakasi/Hangul
    (es. ワールドイズユアーズ -> World Is Yours); l'inglese prevale sulla lettura fonetica
  - matching: esatto (artista,album,titolo) -> esatto (artista,titolo) ->
    primo artista -> contenimento -> fuzzy difflib entro l'artista
  - report .missing.txt accanto a ogni playlist

Requisiti (Debian 12+/13: 'pip install --user' e' bloccato da PEP 668 -> venv):
    cd ~/homelab/scripts && python3 -m venv .venv
    .venv/bin/pip install pykakasi hangul-romanize numpy mutagen
  Se .venv esiste accanto allo script viene usato in automatico (cron compreso);
  EXPORTIFY_NO_VENV=1 lo disattiva. Servono anche ffmpeg/ffprobe e metaflac.

==============================================================================
GUIDA PER CHI USA LO SCRIPT (leggi questa parte se sei nuovo)
==============================================================================
Tutti gli esempi si lanciano da questa cartella:  python3 exportify_to_m3u.py <opzioni>
Senza opzioni lo script esegue la pipeline playlist completa (vedi 1). Ogni esecuzione
scrive UN log in logs/e2m_<opzioni>_<data>.log (le opzioni usate senza '--', unite da '+':
es. e2m_fetch+all+apply_20261018_023002.log; senza opzioni e2m_playlists_...); a fine
lavoro avvia uno scan FULL di
Navidrome (disattivabile con --no-scan, e saltato con --dry-run).

------------------------------------------------------------------------------
1. COSA FA (la pipeline)
------------------------------------------------------------------------------
  Spotify --(Exportify)--> zip di CSV, uno per utente
        --> questo script: abbina ogni brano alla tua libreria e scrive le playlist .m3u
        --> Navidrome le importa con lo scan --> ogni utente le vede tra le sue playlist.
  In piu' fa manutenzione della libreria (duplicati, tag, album incompleti...).
  Sono integrate anche utilita' esterne opzionali: --fix-flac-safe ripara i nomi .flac.flac,
  --lidarr-folder-fix riallinea i path artisti Lidarr, --lidarr-import-slskd lancia l'import slskd,
  --lb-dedup controlla i doppi ascolti ListenBrainz. Sono operazioni indipendenti dalla sync
  playlist e non vengono eseguite automaticamente da --all o --sync-only.

  Una run SENZA opzioni fa, in ordine:
    a. (con --fetch; --all lo accende da solo se esistono sessioni salvate) scarica gli zip
       da exportify.app per ogni utente
    b. estrae gli zip in EXPORTIFY_DIR/<utente>/ e cancella i CSV che non sono piu' nello zip
       (e i CSV 'storici' del vecchio layout, direttamente in EXPORTIFY_DIR)
    c. indicizza la libreria (usa una cache; --rebuild-cache la rifa)
    d. per ogni CSV abbina i brani e scrive la .m3u (solo se e' cambiata) + il suo
       .missing.txt con i brani non trovati; con --fetch importa titolo originale e cover Spotify
    e. scrive logs/mancanti_<data>.txt (totali, per utente, playlist e album piu'
       carenti, elenco completo in fondo). X/Y = brani TROVATI/totale con la % dei
       trovati, e 'N brani rimasti' = quelli ancora da trovare
    f. fasi sui tag: date_heal -> romaji_tags -> artist_names -> album_unify -> fix_date_tags
    g. scrive Playlists/_report.txt (dai .missing.txt: brani assenti dalla libreria e brani
       presenti ma non abbinati)
    h. scan FULL di Navidrome
  Se invece passi una o piu' fasi di manutenzione (vedi 5), la parte playlist NON parte,
  a meno che tu aggiunga --playlists (o usi --all). Unica eccezione: --flac-16bit.

  Dove stanno le cose (costanti in testa al file, modificale per la tua installazione):
    ZIP_DIR            cartella con gli zip di Exportify (uno per utente):
                       /home/chic/homelab/scripts/spotify_csv. Gli zip Exportify rimasti
                       nelle vecchie cartelle (ZIP_LEGACY_DIRS) vengono spostati qui da
                       soli alla prima esecuzione (con --dry-run solo letti)
    EXPORTIFY_DIR      CSV estratti: EXPORTIFY_DIR/<utente>/<playlist>.csv
    LIBRARY_ROOT       la tua libreria musicale (sul host)
    PLAYLIST_DIR       le .m3u: PLAYLIST_DIR/ per l'utente di default (DEFAULT_USER),
                       PLAYLIST_DIR/<utente>/ per gli altri; sottocartelle tematiche
                       con PLAYLIST_FOLDERS. Dentro le m3u i percorsi sono quelli visti
                       dal container (JELLYFIN_ROOT al posto di MUSIC_ROOT)
    NAVIDROME_DB       il file navidrome.db (lo script lo legge e, per alcune fasi, lo
                       scrive fermando il container 'navidrome' per pochi secondi)
    DEDUPE_TRASH       cestino dei file spostati dai dedupe (senza --hard-delete)
    logs/              log di ogni run (e2m_<opzioni>_<data>.log), mancanti_<data>.txt;
                        i report diagnostici completi sono incorporati nel log e2m
    .exportify_sessions/  sessioni Spotify salvate da --fetch-login (riservate, permessi 600)
                       (consigliato nel .gitignore: .exportify_sessions/ spotify_cookies/
                       spotify_csv/)
    spotify_cookies/   (facoltativa) dove mettere i cookie esportati per --fetch-cookies
    exportify_names.json  la TUA configurazione (vedi 6)

------------------------------------------------------------------------------
2. PRIMA INSTALLAZIONE (una volta sola)
------------------------------------------------------------------------------
    cd ~/homelab/scripts && python3 -m venv .venv
    .venv/bin/pip install pykakasi hangul-romanize numpy mutagen
    sudo apt install ffmpeg flac                      # ffmpeg, ffprobe, metaflac
    # SOLO se vuoi scaricare gli zip in automatico (--fetch*):
    .venv/bin/pip install playwright && .venv/bin/playwright install chromium
    # (Debian: potrebbe servire anche  sudo .venv/bin/playwright install-deps chromium)
  Se .venv esiste accanto allo script viene usato da solo (cron compreso).
  Poi controlla i percorsi in testa al file e scrivi exportify_names.json (vedi 6).
  Prova sempre prima con --dry-run: calcola e stampa senza toccare m3u, tag, DB o file.

------------------------------------------------------------------------------
3. AGGIUNGERE UN NUOVO UTENTE ALLA PIPELINE (passo per passo)
------------------------------------------------------------------------------
  Esempio: l'utente Navidrome si chiama  stello.
  Passo 1 - L'utente deve esistere in Navidrome (Impostazioni > Utenti). Il nome che
           usi nello script e' ESATTAMENTE quello di Navidrome (maiuscole ininfluenti).
  Passo 2 - Procurati i suoi CSV: ha due strade.
     A) A MANO: stello apre exportify.app, fa il login Spotify e "Export All". Tu
        rinomini lo zip in  stello_spotify_playlists.zip  e lo metti in ZIP_DIR.
        REGOLA: il nome dello zip deve INIZIARE col nome utente Navidrome, seguito da un
        carattere non alfanumerico (stello_x.zip, stello-x.zip, stello.zip; NON
        stello2024.zip e 'chic' non riconosce chicco_x.zip).
     B) IN AUTOMATICO (poi non devi piu' toccare niente):
          python3 exportify_to_m3u.py --fetch-login stello
        Si apre un browser: stello fa il login su Spotify e autorizza Exportify; lo
        script salva la sessione e si ferma da solo. Se Spotify blocca il browser
        (captcha impossibili, 'something went wrong'): stello fa il login nel SUO browser
        normale (meglio in finestra privata), esporta i cookie di spotify.com con
        l'estensione Cookie-Editor (Export > JSON), chiude la finestra SENZA fare logout,
        metti il file in spotify_cookies/ e lancia:
          python3 exportify_to_m3u.py --fetch-login stello --fetch-cookies stello_cookies.json
        (senza nome file prende il piu' recente  stello*.json  in spotify_cookies/).
        Lo script verifica subito la sessione. Poi CANCELLA il file dei cookie: da' accesso
        all'account Spotify. Server senza schermo: fai il login su un PC con Playwright e
        copia .exportify_sessions/stello.json sul server.
  Passo 3 - Se lo zip NON inizia col nome utente (es. l'hai scaricato e lasciato
           spotify_playlists.zip), lo script legge i CSV, prende l'ID Spotify piu'
           frequente nella colonna 'Added By' e lo cerca in exportify_names.json, chiave
           "SPOTIFY_USERS": {"<id spotify>": "stello"}. Se non c'e': da terminale ti
           chiede a quale utente appartiene e salva il legame nel JSON; da cron salta lo
           zip e stampa la riga da aggiungere. (Gli zip senza CSV Exportify sono ignorati.)
  Passo 4 - Prova a secco, SOLO per lui:
          python3 exportify_to_m3u.py --users stello --dry-run
        Guarda le righe 'X/Y match' di ogni playlist e logs/mancanti_<data>.txt. Se ci sono
        playlist che non vuoi importare (daylist, mix automatici...) aggiungile a
        "SKIP_PLAYLISTS" nel JSON (vedi 6) e ripeti.
  Passo 5 - Run vera, sempre solo per lui:
          python3 exportify_to_m3u.py --users stello
        Le m3u finiscono in PLAYLIST_DIR/stello/ e lo scan di Navidrome le importa.
  Passo 6 - Assegna le playlist a stello. Navidrome le importa col proprietario che
           sceglie lui (di solito il primo admin): serve riassegnarle. Dopo lo scan:
          python3 exportify_to_m3u.py --fix-owners --users stello --no-scan
        (Con --all lo fa da solo all'INIZIO della run successiva.) Assegna per cartella:
        PLAYLIST_DIR/stello/ -> stello; il resto -> DEFAULT_USER. Non tocca le playlist
        create a mano nell'interfaccia.
  Passo 7 - (Facoltativo) Preferiti Navidrome: per stellare i brani di 'liked', gli album di
           'saved albums' e gli artisti presenti in queste playlist serve la password Subsonic:
          export ND_PASS_STELLO='la-sua-password'
          python3 exportify_to_m3u.py --star-liked --users stello
        le playlist 'liked'/'liked songs' e 'saved albums' devono gia' essere importate in Navidrome.
  Passo 8 - Cron: da ora basta la riga di sempre (vedi 4); con --users puoi comunque
           lanciare le fasi per-utente su una persona sola.
  Per RIMUOVERE un utente dalla pipeline: togli il suo zip da ZIP_DIR E cancella la
  cartella EXPORTIFY_DIR/<utente>/ (altrimenti i suoi vecchi CSV vengono elaborati a ogni
  run); se usavi --fetch cancella anche .exportify_sessions/<utente>.json. Le sue
  playlist e le m3u in PLAYLIST_DIR/<utente>/ restano finche' non le cancelli tu
  (da Navidrome e dal disco).

------------------------------------------------------------------------------
4. USO QUOTIDIANO E CRON
------------------------------------------------------------------------------
    python3 exportify_to_m3u.py --sync-only          # fetch + playlist + proprietari + star-liked, senza manutenzione pesante
    python3 exportify_to_m3u.py --fetch               # scarica gli zip, aggiorna playlist e tag
    python3 exportify_to_m3u.py --fetch --all --apply # tutto, comprese le fasi che cancellano
  ATTENZIONE: --all --apply esegue anche dedupe e mp3-vs-flac sul serio (i file vanno nel
  cestino DEDUPE_TRASH salvo --hard-delete). Prima lancia --all SENZA --apply: le fasi
  distruttive restano a secco e ti mostrano cosa farebbero.
  Con --fetch, se uno zip non si aggiorna da piu' di 3 giorni compare un avviso [!] (sessione scaduta?
  interfaccia di Exportify cambiata?). Controllo esplicito, adatto al cron:
    python3 exportify_to_m3u.py --fetch-check || <la tua notifica>
  (codice di uscita 2 = almeno una sessione scaduta: rifai --fetch-login per quell'utente;
  il cookie di login ha una scadenza lunga ma Spotify puo' invalidarlo prima.)

------------------------------------------------------------------------------
5. RIFERIMENTO DEI COMANDI
------------------------------------------------------------------------------
  Regola generale: --dry-run = niente scritture (m3u, tag, DB, file) e niente scan; le
  fasi che CANCELLANO o RISCRIVONO in modo pesante (dedupe-playlists, dedupe-releases,
  dedupe-tracks, mp3-vs-flac, fix-collab-artists) sono a secco anche senza --dry-run:
  servono --apply per eseguirle. Eccezioni da sapere:
  l'estrazione degli zip in EXPORTIFY_DIR avviene comunque (sono file di lavoro) e
  --star-liked agisce anche con --dry-run.

  --- Scegliere cosa fare ---------------------------------------------------
  (nessuna opzione)     pipeline playlist completa (vedi 1).
  --all                 TUTTE le fasi in ordine: fix-owners, dedupe-playlists,
                        dedupe-releases, dedupe-tracks, mp3-vs-flac, fix-collab-artists,
                        flac-16bit, clean-empty, poi playlist+tag, poi star-liked, scan.
                        Le fasi distruttive restano a secco senza --apply. Se esistono
                        sessioni Exportify salvate (.exportify_sessions/) scarica anche
                        gli zip, come --fetch: un cron con solo --all --apply li aggiorna.
  --playlists           aggiungi la fase playlist quando combini fasi di manutenzione.
  --apply               esegui davvero le fasi distruttive (default: dry-run).
  --dry-run             prova a secco di tutto (vedi la regola sopra).
  --no-scan             non avviare lo scan FULL di Navidrome a fine lavoro.
  --version             stampa la versione.
  --help                mostra l'elenco dettagliato e aggiornato delle opzioni.
  --changelog           stampa tutto il changelog incorporato nello script.

  --- Utenti ------------------------------------------------------------------
  --users a,b           (anche --user, ripetibile) limita le fasi PER-UTENTE agli utenti
                        scelti: playlist, fix-owners, dedupe-playlists, star-liked, fetch.
                        Senza --users valgono per TUTTI gli utenti. Le fasi sulla libreria
                        condivisa (dedupe release/tracce, mp3-vs-flac, tag...) non sono
                        filtrate. Nome sconosciuto = errore con l'elenco degli utenti.
  --zip ZIP|DIR         usa questo zip (o tutti gli zip di quella cartella) al posto di
                        ZIP_DIR; ripetibile. Per ogni utente contano solo i CSV degli zip
                        letti in questa run: quelli non presenti vengono cancellati.
  --no-unzip            non estrarre: usa i CSV gia' presenti in EXPORTIFY_DIR/<utente>/.
  --clean               opzione legacy: i CSV obsoleti vengono rimossi dopo estrazione riuscita.
  csv ...               (argomenti posizionali) elabora SOLO questi file CSV; appartengono
                        a UN utente: quello di --users (uno solo) o DEFAULT_USER.

  --- Scaricare gli zip da Exportify (serve Playwright) -------------------------
  --fetch-login UTENTE  login una tantum (browser visibile) per UTENTE Navidrome.
  --fetch-cookies [FILE] con --fetch-login: importa i cookie esportati da un browser
                        normale invece di aprire un browser. Cerca il file anche in
                        spotify_cookies/; senza nome prende il piu' recente UTENTE*.json/.txt.
  --fetch               prima di elaborare, scarica gli zip di tutti gli utenti con una
                        sessione (o solo quelli di --users). Se fallisce, usa gli zip gia'
                        presenti. Saltato con --dry-run. Con --all e' implicito se esistono
                        sessioni salvate.
  --fetch-only          scarica gli zip e basta (codice 2 = sessione scaduta).
  --fetch-check         verifica che le sessioni siano ancora valide, senza scaricare.
  --fetch-list          mostra sessioni (eta', scadenza del cookie di login) e zip (eta',
                        numero di CSV).
  --fetch-headed        con --fetch/--fetch-only mostra il browser (debug).
  --fetch-timeout MIN   minuti massimi per l'export di un utente (default 30).
  Uno zip troppo piccolo rispetto all'ultimo buono (meno della meta' dei CSV, es. export
  interrotto) non lo sostituisce: va in <nome>.zip.suspect.

  --- Scelta e abbinamento delle playlist ---------------------------------------
  --only a,b            importa SOLO queste playlist (nomi come i file CSV).
  --skip a,b            escludi queste playlist (si somma a SKIP_PLAYLISTS del JSON).
                        I nomi si confrontano ignorando maiuscole, punteggiatura, '_'
                        ed emoji; nel JSON una voce puo' finire con '*' (jolly).
  --pick                scegli le playlist da una lista interattiva.
  --force               riscrive TUTTE le m3u, anche quelle invariate (di norma una m3u
                        gia' scritta e non cambiata non viene toccata, cosi' le modifiche
                        fatte dai client restano).
  --threshold N         soglia del confronto fuzzy (0-1, default 0.8) tra Spotify e file.
  --rebuild-cache       rifa l'indice della libreria (dopo aver aggiunto/spostato file).

  --- Playlist nel DB di Navidrome (per-utente) -----------------------------------
  --fix-owners [USER]   assegna ogni playlist importata da m3u al proprietario giusto
                        in base alla cartella (PLAYLIST_DIR/<utente>/ -> quell'utente).
                        USER (facoltativo) = proprietario delle playlist fuori dalle
                        cartelle utente (default DEFAULT_USER). Ferma il container
                        navidrome per scrivere il DB. Rispetta --dry-run.
  --fix-all-playlist-owners [USER]
                        forza TUTTE le playlist (incluse quelle create nella UI) al proprietario
                        indicato (default DEFAULT_USER). Preview di default; --apply modifica il DB.
                        Usare solo se si vuole davvero un unico proprietario per ogni playlist.
  --dedupe-playlists    elimina dal DB le playlist con lo STESSO nome esatto e lo stesso
                        proprietario, tenendo la piu' recente. A secco senza --apply.
  --star-liked          stella le tracce di 'liked'/'liked songs', gli album di 'saved albums'
                        e gli artisti rappresentati in queste raccolte. Password in ND_PASS_<UTENTE>
                        (per ND_USER basta ND_PASS); chi non ce l'ha viene saltato.

  --- Manutenzione della libreria (condivisa, non dipende dall'utente) --------------
  --dedupe-releases     unifica release duplicate (originale vs remaster/deluxe).
  --dedupe-tracks       duplicati della stessa traccia nella STESSA cartella album.
  --mp3-vs-flac         elimina gli mp3 la cui traccia esiste gia' in FLAC (stesso
                        artista+album, titolo uguale, durata compatibile, verifica della
                        forma d'onda).
    opzioni dei dedupe: --corr 0.95 (soglia di correlazione), --trust-format (stesso
    titolo + durate compatibili = duplicato, senza forma d'onda), --max-dur-diff 10
    (secondi di differenza ammessi), --hard-delete (cancella invece di spostare nel
    cestino), --artist NOME (solo questa cartella artista).
  --fix-collab-artists  album collab che Navidrome mostra come 'A • A & B': riscrive
                        ALBUMARTIST come ['A', 'B'] nei FLAC. A secco senza --apply;
                        restringi con --album e --artist. Dopo --apply serve uno scan.
  --flac-16bit          converte/ricomprime i FLAC (24 -> 16 bit livello 8, 16 bit mal
                        compressi). Nota: da sola NON esclude la fase playlist.
  --clean-empty         rimuove le cartelle senza audio vuote da piu' di 24 ore.
  --fix-flac-safe        ripara <brano>.flac.flac se il doppione e' un FLAC valido, quindi pulisce
                        i .backup col rispettivo originale presente. Preview di default; --apply.
  --lidarr-folder-fix    riallinea i path artisti Lidarr alle cartelle disco; preview di default;
                        --apply scrive via API e avvia RescanFolders. Richiede LIDARR_API_KEY.
  --lidarr-import-slskd  invia DownloadedAlbumsScan (/downloads/slskd), controlla failed_imports
                        e propone correzioni cartelle; --apply applica anche i path trovati.
  --lb-dedup UTENTE      trova ascolti ListenBrainz dello stesso artista/titolo entro 5s. Solo
                        preview; --lb-delete cancella gli ascolti in eccesso (irreversibile).
                        Richiede LISTENBRAINZ_TOKEN nell'ambiente o nel .env.
  --unify-only          esegue SOLO album_unify (niente playlist). --skip-unify lo salta.
  --skip-date-heal, --skip-romaji, --skip-artist-names, --skip-fix-dates
                        saltano la rispettiva fase tag della pipeline playlist.

  --- Report e diagnostica (a sola lettura) ------------------------------------------
  --diagnose-album-splits
                        report di sola lettura sui gruppi album probabilmente separati nel DB;
                        le coppie fuzzy sono suggerimenti da rivedere, non fusioni automatiche.
  --repair-album-groups
                        ripara tag e gruppi album. Da sola: anteprima, --apply per scrivere;
                        in --all e' integrata nella pipeline e segue --dry-run per le scritture.
  --check-albums        confronta gli album del DB con MusicBrainz e scrive
                        report completo integrato in logs/mancanti_<data>.txt. Usa MUSICBRAINZ_ALBUMID se c'e',
                        altrimenti cerca per artista+album (--mb-no-search lo evita).
                        In --all, la fase automatica controlla SOLO album con MBID.
                        1 richiesta/secondo: la prima run e' lunga, poi c'e' la cache.
  --missing [FILE]      elenca TUTTE le tracce mancanti, ricalcolate ora dai CSV contro la
                        libreria. Con FILE le salva li', senza le stampa.
  --explain "ARTISTA|||ALBUM|||TITOLO"
                        mostra candidati e punteggi dell'abbinamento per UNA riga (album
                        e titolo come nel CSV): serve a capire perche' un brano non
                        viene trovato.
  --compare FILE1 FILE2 confronta due file audio (durate + forma d'onda) e dice se sono
                        la stessa incisione.
  --build-spotify-proxies
                        crea MP3 proxy compatti (default 64k) per gli album di SPOTIFY_LOCAL_PROXY.albums
                        e auto_albums; non modifica i FLAC. Aggiorna anche il manifest dei preferiti
                        Navidrome e la playlist locale liked.m3u quando l'API Navidrome e' disponibile.
  --sync-proxy-favorites
                        rilegge i preferiti (cuore) di Navidrome e aggiorna la lista proxy liked.m3u;
                        preview predefinita, --apply scrive i file. Non puo' creare una playlist Spotify
                        nativa automaticamente: Spotify Web API non supporta l'aggiunta di file locali.
  --sync-spotify-proxy-config
                        confronta gli album della libreria con il catalogo Spotify (market da
                        SPOTIFY_LOCAL_PROXY.market). Di default fa un dry-run: scrive report e
                        JSON proposta, non modifica exportify_names.json; --apply aggiorna auto_albums.
                        Richiede SPOTIFY_CLIENT_ID/SECRET nel .env per le query non in cache.
  --proxy-limit N       limita a N album nuovi da interrogare (scan parziale additivo, default: tutti).
  --proxy-force-refresh ignora la cache del catalogo Spotify e rifà le query.
  --proxy-report FILE   percorso del report per --sync-spotify-proxy-config.
  --album TESTO         con --fix-collab-artists/--check-albums: solo gli album il cui nome
                        contiene TESTO.

  --- Interventi su Navidrome --------------------------------------------------------
  --rebuild-album NOME  cancella l'album (corrispondenza parziale) dal DB di Navidrome;
                        al prossimo scan viene ricostruito dai tag dei file (lo fa la
                        run successiva, o lancialo dall'interfaccia di Navidrome).

------------------------------------------------------------------------------
6. CONFIGURAZIONE: exportify_names.json (accanto allo script)
------------------------------------------------------------------------------
  E' il posto per le TUE regole: sopravvive agli aggiornamenti dello script. Un JSON
  non valido ferma lo script (meglio che importare playlist indesiderate). Chiavi:
    SKIP_PLAYLISTS   oggetto per utente: {"chic": ["daylist*", "nome playlist"],
                     "stello": ["altra playlist"]}. Le voci si applicano solo a quell'utente;
                     '*' finale = tutte quelle che iniziano cosi': "daylist*"
    SPOTIFY_USERS    {"<id spotify>": "<utente navidrome>"}: lega gli zip senza il nome
                     utente (lo script puo' aggiungere voci da solo, vedi passo 3)
    FETCH_IGNORED_USERS ["octochic", ...]: utenti da NON aggiornare con Exportify;
                     i loro CSV/ZIP locali possono comunque essere usati
    PLAYLIST_FOLDERS {"nome playlist": "sottocartella"}: dove mettere certe m3u
    I nomi playlist vengono importati come sono in Spotify; rinominali direttamente li'.
    NAME_TRANSLATIONS traduzione inglese o nome latino ufficiale per testo CJK/Hangul; precede gli altri
    NAME_FIXES       alias/romanizzazione manuale, compatibile con i JSON precedenti; precede il fallback fonetico
    ALIASES          artista scritto diversamente su Spotify e in libreria
    ARTIST_GROUPS    gruppi di nomi dello STESSO artista (aka): [["a", "b"], ...]
    FORCE_ARTIST     "artista - titolo" -> artista da cercare al posto di quello del CSV
    CSV_FIX          correzioni per riga CSV (album/artista) che sopravvivono ai nuovi
                     export: {"playlist": {"artista - titolo": {"album": "..."}}}
    UNIFY_FORCE      valori da forzare per album in album_unify ("cartella artista /
                     cartella album": {campo: valore})
    EMOJI_WORDS      parole usate al posto di un'emoji nei titoli Spotify
    SPOTIFY_LOCAL_PROXY output_dir (cartella Local Files fuori da MUSIC_ROOT), bitrate MP3
                        e albums=[{"artist": "...", "album": "..."}]. Solo gli album
                        elencati sono convertiti; dopo averli importati in Spotify Desktop,
                        aggiungili alle playlist desiderate. Exportify ne esporta i metadati.
    TERMINAL_COLORS   palette ANSI configurabile per intestazioni, contatori, info/review, stati, barra e spinner;
                      usa nomi (blue, bright_cyan), #RRGGBB, 256:N o sgr:...; il valore
                      none disattiva un singolo accento, enabled=false disattiva tutti i colori.
                      Ogni ruolo può essere una stringa colore oppure {"color": "#RRGGBB",
                      "bold": true, "dim": false, "italic": false, "underline": false,
                      "reverse": false, "background": "#RRGGBB"}. Vedi il JSON distribuito.

------------------------------------------------------------------------------
7. VARIABILI D'AMBIENTE
------------------------------------------------------------------------------
    ND_USER / ND_PASS / ND_URL   utente, password e indirizzo Subsonic di Navidrome
                                 (ND_PASS richiesto per scan; usati anche da --star-liked)
    ND_PASS_<UTENTE>             password Subsonic di un utente (UTENTE in maiuscolo,
                                 caratteri speciali -> '_'): ND_PASS_STELLO
    ND_DEFAULT_USER              utente di default (default: ND_USER, poi 'chic')
    ND_MUSIC_ROOT                prefisso della musica DENTRO il container Navidrome
                                 (es. /music); di solito viene riconosciuto da solo
    ND_ARTIST_JOINER             separatore degli artisti di Navidrome (default ' • ')
    EXPORTIFY_URL                indirizzo di Exportify (default https://exportify.app/)
    EXPORTIFY_STATE_DIR          dove salvare le sessioni (default .exportify_sessions/)
    EXPORTIFY_NO_VENV=1          non usare il .venv accanto allo script
    EXPORTIFY_PROBE_WORKERS      processi paralleli per leggere i tag con ffprobe
    EXPORTIFY_WAVEFORM_WORKERS  confronti waveform paralleli per dedupe (default 2, max 4)
    MB_BASE                      indirizzo dell'API MusicBrainz (per prove/mirror)
    LIDARR_URL / LIDARR_API_KEY   URL e API key per --lidarr-folder-fix / --lidarr-import-slskd
    LIDARR_MUSIC_ROOT             root host libreria per trovare le cartelle (default LIBRARY_ROOT)
    LIDARR_CONTAINER_ROOT         prefisso path artisti nel container Lidarr (default /music)
    SLKSD_IMPORT_FOLDER           cartella vista da Lidarr per DownloadedAlbumsScan (default /downloads/slskd)
    SLKSD_FAILED_FOLDER           cartella host failed_imports (default /downloads/slskd/failed_imports)
    LISTENBRAINZ_TOKEN            token API per --lb-dedup; mai passato come argomento CLI

------------------------------------------------------------------------------
8. SE QUALCOSA NON VA
------------------------------------------------------------------------------
  - 'utente Navidrome non determinato' per uno zip: rinominalo <utente>_...zip oppure
    aggiungi l'ID Spotify a SPOTIFY_USERS (passo 3).
  - Le playlist del nuovo utente risultano dell'admin: manca il passo 6, lancia
    --fix-owners --users <utente> dopo uno scan.
  - Il cron non aggiorna i CSV: gli zip si riscaricano solo con --fetch (o con --all se
    esistono sessioni salvate). Nel log, la riga 'estratti N CSV da ... zip di X ore fa' dice
    quanto e' vecchio lo zip usato.
  - Uno zip non si aggiorna: --fetch-list (eta'), --fetch-check (sessione), poi
    --fetch-only --fetch-headed per vedere il browser; se l'interfaccia di Exportify e'
    cambiata, screenshot e HTML sono in logs/fetch_<utente>_*.png/.html.
  - Una playlist indesiderata continua a comparire in mancanti_*.txt: a fine selezione
    lo script elenca le voci di SKIP_PLAYLISTS senza nessun CSV corrispondente: controlla
    come e' scritto il nome.
  - Un brano che c'e' in libreria risulta 'mancante': --explain "ARTISTA|||ALBUM|||TITOLO".
  - Controlla sempre il log della run (logs/) e i messaggi [ERRORE] / [!].

==============================================================================
CHANGELOG
==============================================================================

Novita' 0.83 (ruoli colore per riepiloghi e diagnostica):
  - aggiunti cinque ruoli JSON indipendenti: waveform_compare, run_mode, release_summary,
    total_label e total_duration; le righe waveform compare, modo e gruppi release sono
    colorate come blocchi distinti, mentre TOTALE e il relativo tempo hanno colori separati.
  - === riepilogo tempi === e === fine riepilogo tempi === usano phase; ogni nome fase nella
    tabella tempi usa phase e ogni valore elapsed usa duration.
  - === interrotta: ... === e [!] RUN INTERROTTA usano entrambi phase_failure.
  - il JSON distribuito conserva la palette personalizzata aggiornata dall'utente, incluso
    progress_unit verde #77FF94, e aggiunge i cinque ruoli con fallback coerenti.

Novita' 0.82 (shutdown pulito della barra e intestazioni fase uniformi):
  - la barra pinned viene rimossa e la regione di scrolling ripristinata su completamento,
    eccezioni, Ctrl+C, SIGTERM e SIGHUP; atexit fornisce un ulteriore fallback. SIGKILL e
    terminazioni forzate non intercettabili restano, per definizione, non gestibili dal processo.
  - le intestazioni fase usano ora `=== fase nome === X/Y`, con ruolo `phase` e ruolo `counter`
    indipendenti; le chiusure usano `=== fine fase nome === durata` e riutilizzano esattamente
    il ruolo `phase`, mentre la durata usa `duration`.
  - aggiunti i prefissi `[info]` e `[review]`; `[i]` e `[INFO]` sono alias di `info`.
  - la palette viene precaricata prima delle prime righe e della fase `load_user_config`, cosi'
    anche banner iniziale, messaggio --all e prima intestazione rispettano subito il JSON.
  - il JSON distribuito usa la palette personalizzata fornita dall'utente, con `review` amber.

Novita' beta-0.81 (palette terminale configurabile dal JSON):
  - tutti gli accenti terminale sono configurabili in TERMINAL_COLORS di exportify_names.json:
    titoli/fallimenti di fase, contatori, prefissi info/warning/error/dry-run/success, tempi,
    label/contatore/unita' della barra, spinner, bordo, celle piene/vuote e percentuali.
  - supporta nomi ANSI (es. blue, bright_cyan), colori truecolor #RRGGBB, indice 256-color
    (256:81), SGR avanzato (sgr:1;38;5;81), sfondo e attributi bold/dim/italic/underline/reverse.
    Il valore none disattiva il colore di quel ruolo; TERMINAL_COLORS.enabled=false disattiva tutto.
  - i ruoli dettagliati hanno fallback sui ruoli base per mantenere compatibilita' con JSON vecchi;
    NO_COLOR, CLICOLOR=0 e TERM=dumb continuano ad avere la precedenza. Il log e2m resta semplice.
  - validazione rigorosa dei valori colore: un errore indica il nome del ruolo non valido e blocca
    il caricamento della configurazione, evitando di avviare una run con palette inaspettata.

Novita' beta-0.81 (palette terminale configurabile da JSON):
  - aggiunto TERMINAL_COLORS in exportify_names.json: tutti i ruoli colore del terminale possono
    essere modificati indipendentemente, inclusi stato delle fasi, messaggi, durata, label/counter
    della barra, spinner, bordo, celle piene/vuote e percentuale al 100%.
  - supportati nomi ANSI, #RRGGBB, 256:N e sgr:N;..., oltre a colori di sfondo e attributi bold,
    dim, italic, underline e reverse. none rimuove l'accento di un singolo ruolo; enabled=false
    spegne la palette. Il JSON distribuito usa un insieme iniziale più morbido e meno acceso.
  - la configurazione dei colori e' validata all'avvio, con errori che indicano il ruolo difettoso;
    i JSON vecchi senza TERMINAL_COLORS continuano a usare i colori predefiniti del codice.
  - confermati il rispetto di NO_COLOR/CLICOLOR/TERM, il rilevamento TTY e i log e2m senza ANSI.

Novita' 0.80 (spinner compatto, righe terminali atomiche e scansioni piu' rapide):
  - spinner sostituito con frame Braille a singola colonna (⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏),
    mantenendo il refresh a 100 ms e senza cambiare la larghezza interna della barra a 50 caratteri.
  - Tee accumula i frammenti console fino al newline/flush e scrive ogni messaggio completo in un'unica
    sezione critica: evita che il ticker si inserisca tra il testo di print() e il suo newline, causa
    delle righe artwork fuse con la barra. Il log e2m continua a ricevere testo semplice.
  - la scansione artwork aggiorna il denominatore con il numero effettivamente osservato se la cache
    ffprobe sovrastima i file, così una scansione conclusa non resta al 99% per una stima obsoleta.
  - _audio_files usa il walker os.scandir condiviso invece di Path.rglob ripetuto per ogni album;
    riduce le scansioni ricorsive ridondanti nelle fasi di dedupe senza cambiare l'ordine dei file.
  - dedupe_releases raggruppa prima i nomi delle cartelle e visita i file solo per titoli d'album ripetuti;
    nel log allegato la fase impiegava 2m40 trovando zero gruppi. dedupe_tracks decodifica i fingerprint
    di ogni gruppo in parallelo (EXPORTIFY_WAVEFORM_WORKERS, default 2, massimo 4), senza cambiare
    la logica di correlazione o le regole di cancellazione.
  - flac_16bit esegue i probe ffprobe in parallelo, con limite configurabile EXPORTIFY_FLAC_PROBE_TIMEOUT
    (default 30 s, massimo 120) e conteggio esplicito dei timeout/errori; evita che probe sequenziali
    lenti blocchino per decine di minuti la pipeline. La conversione e l'ordine di applicazione restano sequenziali.
  - ffprobe seleziona esplicitamente il primo stream audio durante la lettura dei bit: una copertina
    embedded esposta come stream video non puo' essere scambiata per lo stream audio.

Novita' 0.79 (colori terminale):
  - colori ANSI adattivi: titoli di fase in ciano/grassetto, contatori e spinner magenta,
    barra con bordo ciano, avanzamento verde e parte residua grigio tenue; le percentuali
    sono in ciano e diventano verdi al 100%.
  - messaggi [i], [warn], [ERRORE], [dry] e gli esiti delle fasi hanno accenti coerenti.
  - i colori sono soltanto per un terminale interattivo; NO_COLOR, CLICOLOR=0 e TERM=dumb
    disabilitano la decorazione. I codici ANSI vengono sempre rimossi dai log e2m.
  - la barra rimane fissata all'ultima riga, conserva i 50 caratteri interni e il refresh
    dello spinner resta ogni 100 ms. I colori non influenzano allineamento o rilevamento wrap.

Novita' beta-0.78 (split artisti generico e barra sempre visibile):
  - rimossa la dipendenza da ARTIST_SPLIT_OVERRIDES: le virgole senza spazio sono delimitatori
    generici; le virgole con spazio vengono divise quando il catalogo conferma i componenti o
    quando una componente coincide con una cartella-artista della traccia.
  - corretta la causa principale: split_artists accettava prima il nome composto gia' presente
    nel DB; il riparatore tag inoltre rifiutava collaborazioni se i singoli artisti non erano
    gia' indicizzati. Ora separatori e contesto del path sono evidenze indipendenti; i nomi reali
    noti come 'Tyler, The Creator' restano protetti.
  - corretta una collisione del catalogo: norm() rimuove le parentesi quadre, per cui
    'The Cure, [Unknown Artist]' collideva con 'The Cure' e la stringa corrotta poteva vincere
    come grafia canonica. La mappa ignora righe artista che contengono componenti placeholder.
  - la normalizzazione artisti riusa il contesto di cartella gia' calcolato per file, e quando
    una lista confermata contiene un artista reale piu' [Unknown Artist], rimuove il placeholder.
  - barra TTY fissata all'ultima riga fisica: il terminale scrolla nella regione superiore,
    il ridisegno salva/ripristina il cursore e clear() non cancella piu' la barra prima di ogni
    messaggio. Anche dopo un ridimensionamento verticale, il cursore di output viene riportato
    nella regione di scroll prima di riprendere la stampa. I controlli ANSI restano esclusi dal log.
  - rimossa un'implementazione duplicata di _split_artist_tag_if_known. Il vecchio campo JSON
    ARTIST_SPLIT_OVERRIDES viene ignorato e segnalato come legacy, mai usato per decidere lo split.

Novita' beta-0.77 (spinner regolare, alias canonici e date coerenti per album):
  - spinner a ciclo regolare di quattro frame (/ -> ── -> \\ -> |), avanzamento con indice
    monotono ogni 100 ms; niente salti legati al clock assoluto, mantenuta la casella a due colonne.
  - la forma bilingue CJK riusa anche la capitalizzazione esatta della voce canonica gia' nel catalogo;
    la title-case non crea piu' varianti artificiali come '高中正義 (Masayoshi Takanaka)' rispetto a
    '高中正義 (masayoshi takanaka)'.
  - M.O.O.N e' ora un alias canonico forte: il nome gia' presente nel DB non puo' reintrodurre
    il punto finale in M.O.O.N. o ripristinare M_O_O_N. La grafia finale resta M.O.O.N.
  - fix_date_tags calcola una data originale affidabile a livello di album logico (incluse cartelle CD1/CD2)
    usando solo una maggioranza datata >=60% con almeno due tracce. Se esiste, uniforma ORIGINALDATE
    sulle tracce FLAC dell'album e rimuove DATE discordanti; nel dry-run mostra ogni modifica proposta.
  - quando ORIGINALDATE esiste, DATE viene rimosso anche se i due valori sono identici: elimina il doppio
    campo in coerenza con la regola documentata e rende deterministica la data letta da Navidrome.
  - il rapporto di verifica distingue i fix proposti dalla convergenza del DB: --dry-run non scrive tag
    e non esegue la scansione Navidrome, quindi non puo' attestare che gli album siano gia' fusi nel DB.

Novita' beta-0.76 (split artisti, deduplica e consolidamento album):
  - barra fissa da 50 caratteri con spinner a due colonne (trattino lungo incluso), refresh ogni
    100 ms; la fase/contatore resta a sinistra e spinner + barra + percentuale a destra.
  - split esplicito e configurabile dei tag composti 'Afro Medusa,West Way' e
    'Chiello,Powv_FSK', anche se Navidrome ha gia' indicizzato la stringa unita.
  - canonizzazione stabile M_O_O_N/M.O.O.N e unificazione dei nomi CJK puri con la forma
    bilingue in catalogo; le collaborazioni non si affidano piu' soltanto al catalogo preesistente.
  - album_unify sceglie ORIGINALDATE soltanto quando l'anno dominante compare in almeno due
    tracce e copre il 60% dei tag datati; rimuove ID MusicBrainz non uniformabili anche su M4A/MP4
    e cancella ALBUMVERSION discordanti quando un titolo/artista esatti vengono consolidati.
  - dedupe_tracks usa il fallback conservativo FLAC/lossy con titolo esatto e durata quasi uguale
    anche quando manca un numero traccia; una nuova fase post-unificazione in --all trova doppioni
    tra cartelle album diverse e li sposta nel cestino solo con --apply. Qualificatori e marcatori
    espliciti di edizione restano protetti.
  - corretto NameError in _unify_cross_album_dirs (mappa artisti non inizializzata); UNKNOWN-ALBUMARTIST
    ignora i componenti placeholder in 'The Cure; Unknown Artist' solo quando resta un nome concreto.

Novita' beta-0.75 (normalizzazione artisti e riparazione album):
  - barra terminale larga 50 caratteri esatti tra parentesi quadre, spinner animato ogni 100 ms
    e ridisegno temporizzato della stessa riga; i log e2m non ricevono CR né sequenze ANSI.
  - la normalizzazione artisti canonizza anche le varianti di punteggiatura (M_O_O_N/M.O.O.N),
    preferisce il nome bilingue CJK già presente nel catalogo e divide collaborazioni con virgole
    senza spaccare nomi propri con virgola quando il catalogo riconosce il nome completo.
  - la riparazione di [Unknown Artist] interviene anche su ALBUMARTIST/ALBUM_ARTIST espliciti,
    usando cartella e metadati delle tracce solo quando non indicano una compilation.
  - album_unify ora aggiorna DATE anche sui FLAC senza ORIGINALDATE: un ORIGINALDATE trovato
    su un'altra traccia non blocca più il campo DATE dell'intero album e non lascia split evitabili.
  - dedupe_tracks ha un fallback conservativo per doppioni con titolo esatto, stesso numero traccia,
    durata quasi identica e senza qualificatori live/demo/mix; le diverse incisioni restano protette.
  - report album_db_diagnostics e album_cross_folder_review sono scritti direttamente nel log e2m,
    senza creare file autonomi temporanei; il report MusicBrainz resta in mancanti.

Novita' beta-0.74 (progress bar terminale e log consolidati):
  - la progress bar ridisegna la stessa riga ogni 500 ms in terminale, non a soglie del 5%;
    contatore e fase restano a sinistra, barra completa e percentuale sono allineate a destra.
  - Tee rileva se la console e' interattiva e manda i redraw solo al terminale, senza inserire
    caratteri CR nel log e2m. I log reindirizzati mantengono checkpoint temporizzati leggibili.
  - album_db_diagnostics e album_cross_folder_review vengono incorporati nel log e2m e poi
    cancellati come file autonomi; il report MusicBrainz resta incorporato in mancanti.

Novita' beta-0.73 (MP3 ID3 convergenti, exit status e report robusti):
  - MP3: la pulizia dell'alias TXXX albumartist usa mutagen/ID3 invece di tentare di
    cancellarlo con ffmpeg (che nei log continuava a lasciare il frame e riscrivere 168 file
    a ogni run). Conserva gli altri frame ID3 e non ricodifica l'audio.
  - run_phase registra le fasi con ritorno False, eccezioni o risultato con errori>0; la
    pipeline completa continua per produrre tutti i report ma termina con exit code 1 se una
    fase e' fallita, cosi' cron/monitoring non vedono una run fallita come successo.
  - check-albums ritorna un esito coerente con gli errori MusicBrainz e sostituisce anche un
    eventuale blocco MusicBrainz troncato in mancanti, senza duplicarlo.
  - aggiornata la guida per mutagen e chiarito che album_incompleti e' un nome storico: il
    report completo e' consolidato in mancanti_<data>.txt.

Novita' beta-0.72 (ottimizzazione artist split, report persistenti e log piu' chiari):
  - split_known_artist_tags prefiltra i file con i tag ffprobe e invoca metaflac solo sui candidati
    reali, evitando migliaia di processi per file senza separatori utili.
  - aggiunti artists/albumartists alla cache ffprobe e incrementata la versione della cache per
    evitare di riutilizzare voci prive dei campi plurali.
  - un export tag FLAC non leggibile viene segnalato come WARN e saltato; non blocca il repair
    dell'intera libreria. Gli errori di scrittura restano ERROR e fanno fallire la fase.
  - la sezione completa MusicBrainz di mancanti_<data>.txt viene preservata quando il report
    playlist viene rigenerato piu' tardi nella giornata; il controllo album aggiorna il blocco.
  - README aggiornato e configurazione SKIP_PLAYLISTS documentata per utente; PLAYLIST_PREFIXES
    non e' piu' una funzione/configurazione attiva.

Novita' beta-0.71 (skip playlist per utente e report consolidati):
  - SKIP_PLAYLISTS ora e' un oggetto per utente: le esclusioni attuali appartengono solo a chic;
    --skip resta invece un override globale per la singola esecuzione. Accetta ancora la vecchia
    lista JSON assegnandola a DEFAULT_USER con avviso di compatibilita'.
  - rimosso PLAYLIST_PREFIXES: il nome della playlist viene rispettato come arriva da Spotify;
    rinomina le playlist direttamente in Spotify invece di trasformarle durante l'import.
  - i report completi album_db_diagnostics e album_cross_folder_review sono incorporati nel log
    principale e2m, con marcatori di inizio/fine; i file separati vengono eliminati dopo l'incorporazione.
  - il controllo MusicBrainz scrive l'intero report, incluse tracce mancanti e album non trovati,
    in fondo a mancanti_<data>.txt; non crea piu' nuovi album_incompleti_<data>.txt separati.
  - UNKNOWN-ARTIST prova anche ARTISTS per la singola traccia e un suffisso artista attendibile
    nel nome file (es. 'Titolo - Artista') prima di arrendersi per un album multi-artista.
  - i FLAC il cui export dei tag fallisce vengono esclusi dal fallback non-FLAC, evitando una
    seconda riscrittura impropria; l'errore resta esplicito nel log per riparare/verificare il file.
  - star_liked restituisce esito fallito se almeno un utente ha un errore API, anziche' mostrare
    la fase come completata quando il log contiene [ERRORE].

Novita' beta-0.70 (progress bar terminale per scansioni e fasi lunghe):
  - le fasi con un insieme di elementi misurabile usano una barra dinamica su una sola riga:
    contatore corrente/totale, indicatore visuale, percentuale stimata ed elementi rimanenti.
    Su terminale interattivo la riga viene aggiornata con carriage return; nei log non interattivi
    vengono emessi solo aggiornamenti periodici per non riempire i log con una riga per elemento.
  - sostituiti i contatori a righe multiple per scansione libreria, matching playlist, prefetch ffprobe,
    romaji_tags, album_unify, dedupe tracce/release, normalizzazione artisti, MP3-vs-FLAC, scan Navidrome,
    check MusicBrainz, confronto catalogo Spotify, download artwork e fix-flac-safe.
  - aggiunti contatori anche a repair collaborazioni/album artist, repair ownership e dedupe playlist,
    clean-empty e conversione FLAC; le barre avanzano con item controllati, percentuale e rimanenti.
  - su TTY la barra usa carriage return e sovrascrive la riga attiva; nei log non interattivi conserva solo
    checkpoint periodici. Messaggi di errore e modifiche effettivamente applicate restano log separati.

Novita' beta-0.69 (riparazione artisti, contatore fasi e verifica MusicBrainz):
  - i tag ARTIST/ARTISTS/ALBUMARTIST/ALBUMARTISTS riconoscono anche la virgola come separatore,
    ma solo quando almeno due componenti sono confermati dal catalogo Navidrome; nomi propri
    come 'Tyler, The Creator' vengono ricomposti e non spezzati.
  - la normalizzazione artisti armonizza le forme CJK pure e bilingui fra i campi singoli/plurali,
    scegliendo una grafia canonica per evitare duplicati 'kanji' / 'kanji (traduzione)'.
  - UNKNOWN-ARTIST usa prima l'album artist coerente, poi il nome cartella attendibile, quindi
    una maggioranza di artisti traccia solo se chiara e non esplicitamente una compilation.
  - ogni fase mostra il numero progressivo e il totale previsto; il riepilogo finale continua a
    mostrare le durate misurate.
  - --all controlla gli album che hanno MUSICBRAINZ_ALBUMID, elenca i brani mancanti in fondo a
    logs/mancanti_<data>.txt e include li' il report MusicBrainz completo (nessun file album_incompleti separato).
  - dopo lo scan Navidrome confronta lo stato degli album prima/dopo, stampa i nuovi album e le
    voci cambiate/accorpate, riapplica le fasi tag solo ai file degli album interessati e chiude
    con uno scan incrementale. Il confronto usa i path dei brani, non solo gli ID DB volatili.

Novita' beta-0.68 (diagnostica album piu' efficiente e scritture piu' robuste):
  - --diagnose-album-splits genera le coppie candidate tramite un indice inverso degli artisti:
    evita confronti fra album che non condividono alcuna identita' artista e riduce il lavoro
    quadratico sull'intero catalogo; i controlli di similarita' e la regola fuzzy review-only
    restano invariati.
  - le riscritture dei tag non-FLAC ripristinano il file originale se la sostituzione finale del
    file temporaneo fallisce, evitando che un errore I/O lasci il brano mancante dal path atteso.
  - la riparazione dei tag artista separati da ';' combina in modo deterministico i campi alias
    presenti nei metadata non-FLAC, deduplicando i componenti e impedendo che un campo successivo
    sovrascriva silenziosamente il risultato del primo.
  - la cache MusicBrainz aggiornata durante una riparazione in anteprima viene salvata come cache
    ausiliaria: il dry-run non modifica tag o file audio, ma evita di ripetere le stesse richieste.
  - la correzione di [Unknown Artist] non usa piu' una semplice maggioranza di ARTIST per
    indovinare l'artista nelle compilation: un ALBUMARTIST generico/conflittuale blocca il fallback;
    se ALBUMARTIST manca, tutti gli artisti noti delle tracce devono concordare.
  - la riparazione aggrega gli errori di scrittura delle fasi MBID-sanity, artist_names e album_unify;
    non segnala piu' successo se una di queste passate ha avuto errori.
  - l'inferenza degli artisti controlla tutti i campi alias disponibili (artist/artists e albumartist/album_artist/albumartists);
    metadati discordanti sullo stesso file bloccano l'inferenza invece di scegliere il primo campo.

Novita' beta-0.67 (integrazione album repair in --all e correzioni artisti):
  - --all produce automaticamente il report DB di diagnosi album prima delle modifiche e include
    le riparazioni album nella pipeline; --all --apply esegue le scritture. I candidati fuzzy restano
    nel report e non vengono piu' uniti automaticamente, anche quando un frammento e' piccolo.
  - Aggiunta la correzione degli ARTIST='[Unknown Artist]' quando l'album fornisce un unico artista
    attendibile: preferisce ALBUMARTIST, altrimenti un artista non sconosciuto condiviso dalle tracce;
    gli album compilation ambigui restano intatti e sono segnalati per revisione.
  - Aggiunta la separazione condizionata di tag artista separati da ';': si attiva solo se almeno un
    componente corrisponde a un artista gia' presente nel DB Navidrome. FLAC riceve ARTISTS multi-valore;
    gli altri formati ricevono il separatore standard '; ' per lo scanner Navidrome.
  - La riparazione album completa esegue anche queste due correzioni; nell'uso --all riutilizza le fasi
    date_heal/artist_names/album_unify gia' presenti per evitare di ripeterle inutilmente.
  - La diagnostica mostra anche ALBUMVERSION/releasedate/release-group ID dal DB quando disponibili,
    perché possono separare album con lo stesso titolo visibile. ALBUMVERSION viene resa coerente per
    album logico; edizioni/versioni discordanti tra cartelle restano review-only e non si uniscono.

Novita' beta-0.66 (riparazione album frammentati e artisti CJK duplicati):
  - album_base non elimina piu' indiscriminatamente ogni parentesi e la parola "live" interna al titolo.
    Ora rimuove qualificatori di edizione solo quando sono marcatori/ suffissi, preserva titoli
    significativi come "Blackbox Live Recorder" e tratta il gloss romaji CJK come alias.
  - album_unify aggiunge un passaggio cross-folder: raggruppa titoli identici/alias e piccoli
    frammenti supportati da titoli traccia o numerazione contigua, armonizza ALBUM/ALBUMARTIST,
    rimuove ID album discordanti e propaga ID univoci mancanti (Animals, Finger Dancin', Saudade, ecc.).
  - date_heal controlla MUSICBRAINZ_ALBUMID sull'intero album logico, inclusi sottodischi e tutti
    i formati. Se un'unica cartella contiene ID album contrastanti, non sceglie arbitrariamente la
    maggioranza: rimuove quegli ID, conservando un release-group ID solo se e' univoco. Invalida le
    cache dopo le scritture per impedire ad album_unify di ripristinare tag vecchi.
  - artist_names esamina anche tracce che si trovano in cartelle latine/compilation: ogni valore ARTIST/
    ALBUMARTIST CJK diventa la forma bilingue preferita in tag FLAC multipli e non-FLAC. I valori
    duplicati che collassano nella stessa forma vengono deduplicati, poi lo scan Navidrome aggiorna il DB.
  - aggiunti --diagnose-album-splits (DB read-only) e --repair-album-groups (preview predefinita):
    report con album.id/MBID/track count/path e artisti CJK doppi; la riparazione unifica tag fra cartelle,
    rimuove MBID discordanti in tutti i formati e canonizza i valori ARTIST/ALBUMARTIST CJK ovunque.

Novita' beta-0.65 (ottimizzazioni basate sul profilo Tachyon v0.64):
  - artwork: lo stato delle cover embedded viene salvato nella cache ffprobe insieme a tag/durata;
    per le cache preesistenti viene aggiunto al primo controllo. La verifica si ferma appena una
    delle prime tracce contiene una cover, invece di eseguire sempre fino a tre ffprobe per album.
  - traduzione automatica: dopo un errore del provider Google pubblico si attiva un circuit breaker
    persistente per 6 ore (configurabile con AUTO_NAME_TRANSLATION.failure_cooldown_hours). Le
    traduzioni gia' cacheate continuano a funzionare; i nuovi nomi usano la fonetica senza altri timeout.
  - correlazione waveform: controlla prima offset zero e poi gli offset grossolani in ordine di
    distanza, così le copie gia' allineate possono superare la soglia senza percorrere tutta la griglia.
    Le ricerche complete (incl. --compare) conservano la griglia e il massimo diagnostico precedenti.
  - il profiling del 27/10/2026 mostra che la cache ffprobe non e' piu' hotspot dominante; restano
    ~92 s in controlli artwork embedded, ~85 s nella traduzione HTTPS e ~69 s nei tie-break waveform.
    Queste durate sono stime a campionamento; la nuova riduzione end-to-end va verificata sul server.

Novita' beta-0.64 (ottimizzazioni verificate sul profilo Tachyon reale):
  - flush_probe_cache non esegue piu' una os.path.exists su ogni chiave della cache dopo ogni fase.
    Le voci obsolete vengono eliminate in modo lazy quando un percorso richiesto non esiste; la
    cache non viene usata per un file prima di aver verificato stat, quindi i dati obsoleti non
    possono produrre tag di un file mancante. Rimosso il controllo O(numero file) su storage lento.
  - download_missing_album_artwork raccoglie i nomi delle cover gia' durante la passeggiata delle
    directory, evitando una scandir separata per ogni album; controlla la cache negativa prima di
    avviare ffprobe per l'artwork incorporato.
  - le nuove traduzioni automatiche vengono salvate in batch a fine fase, non riscrivendo l'intero
    JSON cache dopo ogni singolo nome; il salvataggio resta atomico e avviene anche dopo errori/interruzioni
    gestite da run_phase.
  - modifiche mirate basate su logs/e2m_sync-only+dry-run+no-scan_20261026_231303.log e sul flame graph
    Tachyon: il profilo ha mostrato ~109 s nel controllo esistenza della cache ffprobe, altri ~23 s in
    un successivo flush, ~75 s nelle verifiche ffprobe dell'artwork, ~29 s nelle scansioni cartella-cover
    e ~69 s nelle traduzioni HTTP.
    I tempi sono stime a campionamento e dipendono dallo storage/rete.

Novita' beta-0.63 (tracciamento dei preferiti per i proxy Spotify e profiling Python 3.15):
  - dopo la generazione dei proxy legge getStarred2 di Navidrome, abbina i brani preferiti ai proxy
    tramite percorso file e metadati, e mantiene .spotify_proxy_manifest.json, liked.m3u e
    spotify_proxy_favorites.json. Gli errori API non cancellano la lista precedente.
  - aggiunto --sync-proxy-favorites (preview predefinita; --apply scrive la lista locale) per
    aggiornare i preferiti senza ricodificare gli MP3. Il manifest consente di collegare i proxy
    ai sorgenti anche nelle run successive.
  - documentato il limite Spotify: la Web API non aggiunge file locali a playlist o Liked Songs;
    liked.m3u e' un elenco locale pronto per consultazione/importazione manuale, non una playlist
    Spotify nativa. Nessun falso stato di completamento viene dichiarato.
  - aggiunte le istruzioni per Python 3.15.2 e profiling.sampling (Tachyon). Il runtime di questo
    ambiente non e' stato aggiornabile perche' i download DNS sono bloccati; nessuna flame graph
    reale viene dichiarata come prodotta.

Novita' beta-0.62 (cache FLAC16 sicura e dedupe piu' efficiente):
  - flac_16bit ora memorizza anche i FLAC gia' efficienti: non rilancia ffprobe su quegli stessi
    file a ogni run se mtime e dimensione non cambiano. La scansione usa il walker os.scandir.
  - corretto un bug di sicurezza: --dry-run non rimuove piu' file .backup e non modifica la cache
    FLAC16; mostra invece quali backup verrebbero rimossi.
  - dedupe_tracks pre-carica i tag di tutti i candidati in una singola fase parallela, invece di
    salvare la cache ffprobe ripetutamente per ogni album: riduce I/O e scritture quadratiche.
  - la correlazione waveform riusa somme cumulative per calcolare le norme delle finestre; mantiene
    la ricerca di offset e velocita' senza cambiare le soglie di deduplicazione.
  - rimosso un insieme old_auto_keys inutilizzato nella scansione proxy e resi piu' espliciti gli
    errori API Spotify quando il proprietario dell'app deve avere Premium in Development Mode.

Novita' beta-0.61 (proxy automatici e traduzioni automatiche prudenti):
  - aggiunto --sync-spotify-proxy-config: confronta gli album della libreria con il catalogo
    Spotify tramite Search API, produce un report e una copia JSON proposta; il JSON attivo
    cambia solo con --apply. Gli album ambigui e gli errori di rete non vengono auto-aggiunti.
  - separati SPOTIFY_LOCAL_PROXY.albums (manuali) e auto_albums (catalogo): la scansione aggiorna
    solo la lista automatica; il builder genera proxy per entrambe senza perdere gli override manuali.
  - aggiunta una cache persistente del catalogo Spotify con TTL e retry 429/5xx per non ripetere
    richieste a ogni run; market IT predefinito, configurabile.
  - introdotto il livello di traduzione inglese automatica per CJK/Hangul dopo NAME_TRANSLATIONS
    e NAME_FIXES e prima della lettura fonetica; solo risultati sopra la soglia euristica vengono
    usati. I risultati vengono memorizzati in cache, senza trasformarli in traduzioni ufficiali.
  - l'affidabilita' della traduzione automatica e' una stima euristica (il provider Google pubblico
    non restituisce una probabilita' calibrata); sotto soglia resta la lettura fonetica.
  - catalog_cache_days=0 disabilita il riuso della cache Spotify; qualunque --proxy-limit resta
    additivo e preserva gli auto_albums esistenti, anche quando tutti gli album entrano nel batch.
  - gli errori imprevisti delle utility proxy ora restituiscono un codice di uscita non-zero;
    prima dell'applicazione viene controllato che il JSON non sia stato modificato durante la scansione.

Novita' beta-0.60 (proxy Spotify MP3 piu' compatti):
  - bitrate predefinito dei proxy Spotify abbassato da 192k a 64k, per ridurre lo spazio audio
    a circa un terzo per la stessa durata; il bitrate resta configurabile tra 64k e 320k in
    SPOTIFY_LOCAL_PROXY.bitrate. A 64k la qualita' e' bassa se si ascoltano i proxy direttamente.

Novita' beta-0.59 (ottimizzazioni mirate su normalizzazione, tag FLAC e clean-empty):
  - cache LRU per norm()/norm_bare(): riusa le normalizzazioni ripetute di artista, album e titolo;
    le cache vengono invalidate subito dopo aver caricato le regole emoji dalla configurazione.
  - romaji_tags: applica tutti i tag cambiati con una sola invocazione di metaflac per file FLAC,
    invece di avviare un processo separato per ogni campo aggiornato.
  - fix_date_tags: legge DATE/ORIGINALDATE dalla cache ffprobe condivisa e pre-carica in parallelo
    i soli FLAC non in cache; scrive ORIGINALDATE e rimuove DATE con una sola invocazione metaflac.
  - clean_empty: determina se ogni cartella contiene audio con un'unica passeggiata bottom-up,
    evitando una scansione ricorsiva dell'intero sottoalbero per ogni cartella.
  - README: aggiunta la procedura di profiling con profiling.sampling (Tachyon) su Python 3.15,
    distinguendo il profilo wall-clock da quello CPU per riconoscere le attese su disco/rete.

Novita' beta-0.58 (integrazione utilita' FLAC, Lidarr e ListenBrainz):
  - integrate --fix-flac-safe: ripara i file .flac.flac solo se il duplicato e' valido, e pulisce
    i .backup quando l'originale esiste; preview predefinita, modifiche solo con --apply.
  - integrate --lidarr-folder-fix: riconcilia i path artisti Lidarr con le cartelle reali usando
    normalizzazione, NAME_TRANSLATIONS/NAME_FIXES/ALIASES/ARTIST_GROUPS e fallback fuzzy; aggiorna
    l'API e avvia RescanFolders solo dopo correzioni riuscite.
  - integrate --lidarr-import-slskd: avvia DownloadedAlbumsScan, riallinea le cartelle e segnala
    le sottocartelle in failed_imports; credenziali Lidarr da LIDARR_API_KEY, mai dal sorgente.
  - integrate --lb-dedup UTENTE: trova ascolti ListenBrainz ripetuti entro 5 secondi, con retry,
    checkpoint e segnalazione delle finestre saltate; e' preview per default, --lb-delete abilita
    le cancellazioni e LISTENBRAINZ_TOKEN resta solo nell'ambiente/.env.
  - mantenuto --fix-owners per-percorso e aggiunto --fix-all-playlist-owners per replicare il vecchio helper
    che forza tutte le playlist, incluse quelle create nella UI, a un solo proprietario.

Novita' beta-0.57 (traduzioni CJK prioritarie con fallback fonetico):
  - aggiunto NAME_TRANSLATIONS per traduzioni inglesi curate e nomi inglesi ufficiali; ha priorita su
    NAME_FIXES e sulla romanizzazione automatica. NAME_FIXES resta il livello di compatibilita per alias
    manuali/romaji e pykakasi/Hangul viene usato solo quando non esiste una forma preferita.
  - applicata la stessa priorita a matching di brani/artisti/album, manutenzione dei tag e proxy Spotify;
    il lookup inverso normalizza anche le maiuscole per collegare la forma inglese alla chiave CJK.
  - spostate nel JSON NAME_TRANSLATIONS le traduzioni/forme inglesi ufficiali gia' curate; le regole
    generiche non presenti nelle tabelle continuano ad avere come fallback la lettura fonetica.
  - invalidata la cache dell'indice (CACHE_VERSION 7) per rendere effettive le nuove regole.

Novita' beta-0.56 (alias inglesi per titoli CJK e provenienza delle tracce mancanti):
  - NAME_FIXES mantiene le maiuscole per i gloss leggibili; il matcher normalizza al confronto.
    Le nuove traduzioni semantiche/forme inglesi ufficiali sono ora separate in NAME_TRANSLATIONS.
  - aggiunte le varianti giapponesi ワールドイズユアーズ / ワールド イズ ユアーズ -> World Is Yours,
    confermate per MASS OF THE FERMENTING DREGS; il matching usa l'alias per titolo E album.
  - se romaji_tags trova un vecchio gloss che coincide esattamente con la lettura fonetica pykakasi,
    lo sostituisce con il mapping inglese curato; non sovrascrive parentesi legittime come (Live).
  - cache dell'indice incrementata per ricostruirla con le nuove regole di alias.
  - la classifica 'ALBUM DA SCARICARE' in mancanti_*.txt mostra ora le playlist attive che originano
    ogni raccomandazione album: gli album suggeriti non vengono confusi con nomi di playlist cancellate.

Novita' beta-0.55 (Spotify Local Files per album assenti dal catalogo):
  - aggiunto --build-spotify-proxies: genera MP3 solo per gli album esplicitamente elencati in
    SPOTIFY_LOCAL_PROXY.albums, mantenendo intatti i FLAC originali
  - output configurabile fuori da MUSIC_ROOT per evitare doppioni in Navidrome; bitrate e dry-run
    configurabili, tag artista/album/titolo e copertina embedded preservati quando supportata
  - Exportify puo' esportare metadata da tracce locali in playlist Spotify (URI spotify:local:...);
    il matcher usa i campi testuali per trovare il file lossless originale

Novita' beta-0.54 (README e changelog CLI):
  - aggiunto README.md con panoramica del progetto, funzionalita' e configurazione; le opzioni
    dettagliate restano nell'help generato direttamente dallo script, che e' la fonte aggiornata
  - aggiunto --changelog: stampa tutto questo changelog e termina senza avviare pipeline o creare log
  - tutte le intestazioni dei rilasci precedenti sono marcate beta- per distinguerle dal rilascio corrente

Novita' beta-5.3 (matching e copertine album):
  - ampliata la penalita' configurabile per versioni alternative, includendo extended/expanded e
    le etichette live, demo, instrumental e rehearsal; il titolo pulito e' favorito quando richiesto
  - aggiunta la ricerca finale delle copertine album mancanti, con controlli per non sovrascrivere
    artwork gia' presente e cache dei risultati negativi

Novita' beta-5.2 (matching piu' semplice e scoring configurabile):
  - riutilizzata la mappa TITLE_MATCH_PENALTIES gia' presente nel JSON anche per la penalita' parentesi;
    il vecchio TITLE_MATCH_PARENTHESES_PENALTY viene ancora letto solo per compatibilita' con JSON v5.1
  - lista dei qualificatori normalizzata/ordinata una sola volta e memorizzata in cache, invece di
    ricostruire e ordinare gli stessi set per ogni candidato; cache invalidata dopo il caricamento config
  - mantenuto il punteggio piu' alto per le versioni esplicitamente richieste (Live/Demo ecc.); i suffissi
    alternativi non richiesti perdono contro il titolo pulito

Novita' beta-5.1 (penalita' delle versioni alternative):
  - penalita' maggiori per titoli tra parentesi o qualificati come live/demo/instrumental/rehearsal
  - conservato il vantaggio per una versione alternativa quando e' esplicitamente richiesta dal CSV
  - aggiunta TANTI AUGURIII!! alla lista delle playlist da ignorare

Novita' beta-5.0 (normalizzazione dei nomi e preferiti):
  - pulizia dei duplicati M3U con nomi equivalenti dopo normalizzazione di maiuscole, spazi e punteggiatura
  - corrispondenza degli album salvati meno restrittiva per applicare le stelle alle edizioni compatibili

Novita' beta-4.9 (fetch fresco e pulizia M3U per utente):
  - FETCH_IGNORED_USERS in exportify_names.json esclude gli account dal fetch Exportify;
  - quando il fetch riesce, l'estrazione usa solo lo ZIP appena scaricato per quell'utente,
    ignorando gli altri ZIP della cartella spotify_csv;
  - dopo una conversione riuscita vengono rimosse le M3U obsolete dell'utente non piu' coperte
    dai CSV selezionati; CSV in errore sospendono la pulizia per sicurezza;
  - pulisce anche dal DB Navidrome le playlist importate col path dei file rimossi (e righe collegate);
  - fetch, pulizia M3U e pulizia DB sono fasi distinte e temporizzate;
  - le cartelle M3U degli altri utenti sono protette anche col layout storico dell'utente default.

Novita' beta-4.8 (sync Navidrome piu' sicura):
  - attesa che l'API Navidrome torni disponibile dopo un riavvio prima di applicare preferiti
  - scan incrementale nella modalita' sync-only e gestione esplicita degli errori di scan

Novita' beta-4.7 (modalita' sync-only e timer):
  - aggiunta la modalita' quotidiana leggera che salta dedupe, FLAC e manutenzione massiva dei tag
  - tempi per fase e riepilogo totale; una fase interrotta non deve essere marcata come completata

Novita' beta-4.6 (CSV album e tempi di fase):
  - riconosciuto saved_albums.csv come raccolta album e non come playlist di brani
  - aggiunti timer e riepilogo finale delle durate delle fasi

Novita' beta-4.5 (revisione bug + pulizia):
  - corretto un bug nel trasferimento di .playlist_meta.json: i nomi originali/cover dal ZIP ora vengono davvero salvati;
  - unzip atomico per CSV: prima mette in staging tutti i file del nuovo ZIP, poi li sostituisce;
    un archivio troncato non puo' cancellare i CSV precedenti o lasciare una pulizia incompleta
  - rilevamento CSV non sensibile alle maiuscole dell'estensione (.csv/.CSV); eliminato il pre-clean
    ridondante --clean (l'opzione resta compatibile, la pulizia avviene solo dopo estrazione riuscita)
  - --star-liked legge una volta getStarred2 e salta anche le canzoni gia' preferite, non solo album/artisti
  - scan Navidrome restituisce l'esito; una scan fallita non viene segnata come completata
  - tolto il fallback a password Subsonic hard-coded: le credenziali vengono da ND_PASS / ND_PASS_<UTENTE>
  - chiusa esplicitamente la risposta HTTP, uniformata la URL base senza slash finale
  - rimossi helper/locali morti e aggiornato lo User-Agent artwork alla versione corrente

Novita' beta-4.4:
  - --star-liked: accetta la playlist 'liked' (e 'liked songs'), stella le tracce; usa 'saved albums'
    per stellare gli album e stella gli artisti presenti nelle due playlist; la scan Navidrome avviene
    prima di questa fase, cosi' vengono lette le playlist appena aggiornate
  - unzip: se ci sono piu' ZIP dello stesso utente, usa solo il piu' recente; i CSV rimasti fuori
    dal nuovo export di quello stesso utente vengono rimossi

Novita' beta-4.3:
  - import playlist: recupera durante --fetch nome Spotify originale (case, emoji, Unicode) e cover;
    conserva i metadati per CSV e usa il nome esatto come basename M3U (slash -> ／, non puo' stare in un filename)
  - importa la cover Spotify come sidecar accanto alla M3U, riconosciuto da Navidrome; aggiorna la cover
    anche quando la playlist non deve essere riscritta; recupero artwork non riuscito non blocca l'import

Novita' beta-4.2:
  - mancanti_*.txt: X/Y ora e' TROVATI/totale con la % dei trovati, piu' "N brani rimasti" (quelli
    ancora da trovare), ovunque: totale, per utente, playlist e album. Il resto non cambia
  - corretto date_heal / MusicBrainz: un errore TEMPORANEO (503, 429, timeout) veniva salvato in cache
    come "nessun dato" e quel release-group non veniva mai piu' ricontrollato (nel log del 18/10: 2
    casi). Ora gli errori temporanei non si memorizzano e _mb_json riprova 3 volte con pausa; al primo
    avvio le voci "nessun dato" gia' salvate si tolgono e vengono richieste di nuovo (una volta sola,
    puo' allungare di qualche minuto la prima notte). Se MusicBrainz e' fuori servizio, dopo 5 richieste
    fallite di fila si smette di insistere per il resto della run (senza questo limite le attese dei
    tentativi allungherebbero la notte di ore); --check-albums si ferma dopo 3 album in errore e salva
    cache e report
  - corretto romaji_tags: se la lettura inizia con una cifra o un simbolo ("17歳" -> "17sai") il valore
    non veniva riconosciuto come gia' romanizzato e a ogni notte si aggiungeva un'altra parentesi
    ("17歳 (17sai) (17sai (17sai))"). Ora lo riconosce e, per sicurezza, non scrive mai un valore che
    una seconda applicazione cambierebbe ancora
  - report SKIP_PLAYLISTS: "entra?" e "entra" (stessa chiave) risultavano "senza corrispondenza": ora
    sono accreditate tutte le voci che combaciano; senza CSV esaminati il riepilogo non compare
  - --check-albums: abbinamento in due passate (prima titoli identici, poi varianti), "Intro" e
    "Intro (Reprise)" non si scambiano piu'
  - cookie malformati (campi col tipo sbagliato) danno un errore leggibile e non un traceback; i link
    simbolici rotti *.zip in ZIP_DIR non fanno piu' fallire la ricerca degli zip

Novita' beta-4.1:
  - corretto --fix-collab-artists: con la gestione multi-libreria Navidrome salva in media_file.path
    percorsi RELATIVI alla libreria (JPEGMAFIA/ALBUM (2023)/x.flac) e la fase li cercava saltando la
    prima cartella: diceva "file non trovati sul disco" e non riscriveva niente
  - gli zip Exportify stanno in ZIP_DIR = /home/chic/homelab/scripts/spotify_csv; quelli rimasti in
    ZIP_LEGACY_DIRS (/home/chic/homelab/docker) vengono spostati li' da soli (solo zip con CSV
    Exportify; con --dry-run non si sposta niente ma si leggono comunque)
  - dopo un'estrazione riuscita i CSV 'storici' direttamente in EXPORTIFY_DIR (vecchio layout)
    vengono cancellati (prima restavano e davano solo un avviso)
  - --all accende da solo --fetch se esistono sessioni Exportify salvate: il cron
    "--all --apply" non riscaricava gli zip e usava quelli del giorno prima
  - nome del log: logs/e2m_<opzione1>+<opzione2>+..._<AAAAMMGG>_<HHMMSS>.log (opzioni senza
    '--'; senza opzioni "playlists")

Novita' beta-4.0 - versione maggiore: pipeline multi-utente completa e guida integrata.
  Riassume le novita' 3.22-3.30 qui sotto: zip e playlist per utente (--users), download
  automatico degli zip da Exportify (--fetch*), dedupe delle playlist, report mancanti
  con statistiche, controllo album incompleti su MusicBrainz, correzione dei collab.
  - aggiunta questa guida in testa al file (uso, nuovo utente, comandi, configurazione)
  - corretto --help: la descrizione di --max-dur-diff (contiene un '%') non veniva
    mostrata e stampava un dizionario Python

Novita' beta-3.30:
  - --fix-collab-artists: album collab che Navidrome mostra come "JPEGMAFIA • JPEGMAFIA &
    Danny Brown" invece di "JPEGMAFIA • Danny Brown". Navidrome unisce con " • " i VALORI
    del tag ALBUMARTIST: se nei FLAC ce n'e' uno che contiene gia' l'altro ("A" e "A & B")
    il nome esce doppio. La fase cerca nel DB gli album con quello schema (album_artist con
    " • " e un valore che ripete un componente di un altro), legge i tag veri dei file e
    riscrive ALBUMARTIST (e ALBUMARTISTS, se c'e') con i soli componenti ["A", "B"] in tutti
    i file dell'album. Dry-run salvo --apply; --album/--artist restringono. Solo FLAC (gli
    altri formati sono elencati). Dopo --apply serve uno scan di Navidrome (lo fa la run).
    Percorsi: media_file.path e' quello DENTRO il container; la fase lo riporta sul host
    (ND_MUSIC_ROOT=/music se serve; di solito lo riconosce da sola)
  - --check-albums (vecchie versioni: album_incompleti_<data>.txt): confronta ogni album del DB con
    la tracklist di MusicBrainz; nelle versioni attuali il report intero e' in fondo a
    logs/mancanti_<data>.txt. Include tracce mancanti (X/Y, %), quali tracce e l'elenco
    "Artista - Album - Titolo" da riscaricare. Usa MUSICBRAINZ_ALBUMID del DB
    (release esatta); senza, cerca per artista+album (--mb-no-search = solo gli album
    taggati). 1 richiesta/secondo come chiede MusicBrainz, cache in .mb_albums_cache.json:
    la prima run su una libreria grande e' lunga (si puo' interrompere e riprendere),
    le successive sono quasi istantanee. Solo lettura: non tocca file ne' DB

Novita' beta-3.29:
  - estraendo uno zip, i CSV dell'utente che NON sono nel nuovo zip (playlist cancellate o
    rinominate su Spotify) vengono cancellati: la cartella exportify/<utente>/ rispecchia
    sempre l'ultimo export (--clean e' ora superfluo). Vale solo per gli utenti il cui zip
    e' stato davvero estratto in questa run; con --no-unzip non si tocca nulla
  - SKIP_PLAYLISTS (JSON) e --skip/--only confrontano i nomi in modo tollerante: minuscole,
    NFKC e ogni sequenza di caratteri non alfanumerici (spazi, '_', punteggiatura, emoji)
    vale uno spazio. Cosi' "entra?" combacia con entra_.csv e "Stello + chic<emoji>" con
    "Stello _ chic_.csv" (prima non combaciavano, e le loro tracce finivano nei mancanti)
  - una voce di SKIP_PLAYLISTS puo' avere '*' come jolly ("daylist*" = tutte quelle che
    iniziano con daylist; le daylist di Spotify si chiamano "daylist • ...")
  - a fine selezione: quante playlist sono state ignorate e quali voci di SKIP_PLAYLISTS non
    corrispondono a nessun CSV (utile per accorgersi di nomi scritti male)
  - le playlist ignorate non vengono elaborate, quindi non compaiono in logs/mancanti_*.txt

Novita' beta-3.28 - controllo della sessione Exportify e cartella dei cookie:
  - --fetch-cookies cerca il file anche in spotify_cookies/ (accanto allo script e nella
    cartella corrente); senza nome (--fetch-cookies da solo) prende il file piu' recente
    in spotify_cookies/ il cui nome inizia con l'utente (chic*.json / chic*.txt)
  - --fetch-check: verifica in headless se le sessioni salvate sono ancora valide (codice
    di uscita 2 se una e' scaduta: ideale per cron, es. "... --fetch-check || notifica")
  - --fetch-list mostra anche tra quanti giorni scade il cookie di login (sp_dc) e l'eta'
    di ogni zip; --fetch avvisa se sp_dc scade entro 14 giorni
  - con --fetch, se uno zip e' piu' vecchio di ZIP_STALE_DAYS (3) giorni compare un avviso
    [!]: copre ogni causa (sessione scaduta, interfaccia cambiata, Exportify non risponde)
  - la riga "estratti N CSV" dice quanto e' vecchio lo zip

Novita' beta-3.27 - logs/mancanti_<data>.txt piu' ricco (l'elenco completo resta IN FONDO):
  - totale: X/Y tracce uniche mancanti e percentuale (Y = brani unici letti dai CSV)
  - per utente: mancanti/totale e %, e quante canzoni mancano a quali utenti ("3 canzoni
    mancanti a elena", "1 canzone mancante a chic, stello"); solo con piu' utenti nella run
  - le playlist con piu' canzoni mancanti (X/Y, %)
  - i 10 album da scaricare, per numero di canzoni mancanti (X/Y = mancanti / brani di
    quell'album presenti nelle playlist; non si conosce la tracklist completa dell'album)
  - nell'elenco completo le playlist portano il prefisso "utente:" se gli utenti sono piu' di uno

Novita' beta-3.26 - login Exportify piu' robusto:
  - il browser del login nasconde i segnali di automazione (flag --enable-automation,
    navigator.webdriver) e usa Google Chrome se installato, altrimenti Chromium
  - chiudere il browser a meta' login non produce piu' un traceback
  - se Spotify scambia comunque il browser per un bot (captcha impossibili, "something
    went wrong"): fare il login nel PROPRIO browser, esportare i cookie di spotify.com
    (estensione "Cookie-Editor" -> Export -> JSON, oppure cookies.txt Netscape) e importarli:
        --fetch-login UTENTE --fetch-cookies FILE
    Servono almeno i cookie di login (sp_dc); lo script verifica la sessione subito.
    Consiglio: login in una finestra PRIVATA, esporta, chiudi la finestra SENZA fare logout.

Novita' beta-3.25 - download automatico degli zip da Exportify (tutto in questo script):
  Exportify gira solo nel browser (nessun URL da scaricare con curl): con --fetch lo
  script pilota Chromium headless (Playwright), riusa la sessione Spotify salvata per
  utente (.exportify_sessions/<utente>.json), clicca "Export All" e salva lo zip come
  ZIP_DIR/<utente>_spotify_playlists.zip. Non serve Spotify Premium (si usa l'app
  Exportify pubblica). Playwright e' richiesto SOLO da queste opzioni:
      .venv/bin/pip install playwright && .venv/bin/playwright install chromium
      (Debian: anche  sudo .venv/bin/playwright install-deps chromium)
  1) una volta per utente, su una macchina con schermo:  --fetch-login UTENTE
     (login su Spotify + autorizza Exportify; salva la sessione. Senza schermo: fallo sul
     PC e copia il .json in .exportify_sessions/ sul server)
  2) --fetch            scarica gli zip e poi elabora (cron: --fetch, o --fetch --all --apply)
     --fetch-only       scarica gli zip e basta
     --fetch-list       mostra sessioni e zip presenti
     --users a,b        limita a questi utenti; --fetch-headed mostra il browser (debug)
  - sessione scaduta (Spotify richiede di nuovo il login): l'utente e' segnalato con
    l'errore e si prosegue con gli zip gia' presenti (con --fetch-only: codice di uscita 2)
  - export interrotto (meno della meta' dei CSV dell'ultimo zip buono): il vecchio zip
    resta, il nuovo va in <nome>.zip.suspect (fuori dal pattern *.zip)
  - se l'interfaccia di Exportify cambia: screenshot + HTML in logs/ (pulsanti cercati
    per testo, inglese e italiano); EXPORTIFY_URL cambia l'indirizzo
  - --fetch e' saltato con --dry-run

Novita' beta-3.23 (multi-utente Navidrome - prima tappa):
  - ZIP PER UTENTE: ogni zip Exportify va legato a un utente Navidrome. Il nome del
    file DEVE iniziare col nome utente (es. chic_spotify_playlists.zip). Se non lo fa,
    si prende l'ID Spotify piu' frequente nella colonna "Added By" dei CSV nello zip e
    lo si cerca in exportify_names.json -> "SPOTIFY_USERS": {"id": "utente"}. Se manca:
    da terminale chiede l'utente e salva il legame nel JSON; da cron salta lo zip
    con l'errore e la riga da aggiungere. Senza --zip legge tutti i *.zip di ZIP_DIR.
  - CSV in EXPORTIFY_DIR/<utente>/. m3u in PLAYLIST_DIR/<utente>/ per gli utenti che
    NON sono DEFAULT_USER (lui tiene il layout storico in PLAYLIST_DIR/: nessuna
    migrazione, nessuna playlist duplicata). Sync-state dei non-default: "<utente>::<nome>".
  - --users a,b: limita le fasi PER-UTENTE (playlist, fix-owners, dedupe-playlists,
    star-liked). Senza --users (anche con --all --apply) vale per TUTTI gli utenti.
    Le fasi sulla libreria condivisa (dedupe release/tracce, mp3-vs-flac, ...) non
    dipendono dall'utente e non sono filtrate.
  - --fix-owners assegna per PERCORSO dell'm3u (cartella utente); non tocca piu' le
    playlist create a mano nell'UI (path vuoto) e rispetta --dry-run.
  - nuova fase --dedupe-playlists: stesso nome ESATTO + stesso proprietario -> tiene la
    piu' recente (updated_at), cancella le altre dal DB Navidrome. Dry-run salvo --apply.
  - --star-liked per utente: password in ND_PASS_<UTENTE> (per l'utente ND_USER: ND_PASS).
    Stella i brani di 'liked', gli album di 'saved albums' e gli artisti presenti in entrambe.

Novita' beta-3.22:
  - UN SOLO LOG per esecuzione (logs/exportify_<data>_<ora>.log): prima ogni fase
    scriveva un file suo e il log 'principale' non conteneva le fasi
  - logs/mancanti_<AAAA-MM-GG>.txt: elenco unico delle tracce mancanti, a ogni run
  - nuova fase artist_names: lo stesso artista CJK/coreano non compare piu' con 3 nomi
    (latino / kanji / 'kanji (latino)') su Navidrome; ripara anche gli mp3 con
    ALBUMARTIST doppio (TPE2 + TXXX scritto da write_ffmpeg)
  - nuova fase --mp3-vs-flac: via l'mp3 se la stessa traccia esiste in FLAC
  - bugfix: cache indice non invalidata dalle modifiche a exportify_names.json;
    metaflac senza --no-utf8-convert (tag giapponesi rovinati con locale C/cron);
    _flac_tags case-sensitive; _move_to_trash lasciava il .lrc con --hard-delete

Novita' beta-3.21 (dai log reali del 13/10):
  - album_unify: la riparazione dei tag mancanti (spotyFLAC) dava KeyError 'title' su
    OGNI FLAC (funzionava solo per mp3/m4a); titolo ricostruito meglio
  - stop alle riscritture notturne che non convergono: .m4a (ffmpeg non salva
    albumartist/originaldate/MBID), FLAC con ORIGINALDATE (unify rimetteva DATE e
    fix_date_tags lo toglieva), .opus/.ogg (tag illeggibili)
  - ALBUMARTIST riscritto col nome 'sanificato' della cartella solo per cartelle asiatiche
  - .missing.txt delle playlist 'invariate' ora aggiornato; nuovo --missing [FILE]

Novita' beta-3.20 (ottimizzazioni + bugfix):
  - cache di ffprobe persistente + letture parallele: le fasi notturne non
    rileggono piu' tutta la libreria a ogni esecuzione
  - cache dell'indice in ~/.cache (non /tmp: su Debian 13 e' tmpfs, si svuota a
    ogni riavvio), compatta, con firma che vede anche rinomine/spostamenti
  - matching: risultati memoizzati, fuzzy con prefiltro di lunghezza (identico
    a difflib), ordine DETERMINISTICO nei pareggi (prima dipendeva da PYTHONHASHSEED)
  - fix: hangul-romanize (Transliter vuole la regola), NAME_FIXES applicate anche
    ai tag, album multi-disco, dry-run davvero a secco, clean_empty non cancella
    piu' cartelle di soli .aiff/.ape/.wv/.dsf, ping-pong notturno di ALBUMARTIST
    fra romaji_tags e album_unify, DATE/ORIGINALDATE doppi in date_heal,
    --explain che andava in crash, correlate() None, JSON config rotto = stop
"""

import argparse
import atexit
import base64
import contextlib
import csv
import difflib
import fnmatch
import http.client
import random
import shutil
import signal
import sqlite3
import string
import subprocess
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import traceback
import unicodedata
from datetime import datetime, timezone
import zipfile
from functools import lru_cache
from pathlib import Path
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed


# ANSI colors are configurable through exportify_names.json -> TERMINAL_COLORS.
# Only the interactive terminal receives ANSI escapes; e2m logs always stay plain text.
_ANSI_RESET = '\x1b[0m'
_ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
_ANSI_PALETTE_DEFAULTS = {
    'phase': '1;38;2;119;255;148',          # user's preferred green
    'counter': '1;38;2;255;178;15',         # amber
    'info': '1;38;2;0;161;228',             # blue
    'review': '1;38;2;255;178;15',          # amber review marker
    'warn': '1;38;2;255;178;15',
    'error': '1;38;2;227;23;10',
    'dry': '1;38;2;0;161;228',
    'success': '1;38;2;119;255;148',
    'duration': '38;2;255;178;15',
    'bar_border': '1;38;2;0;161;228',
    'bar_fill': '1;38;2;112;214;255',
    'bar_empty': '38;2;255;178;15',
    'spinner': '1;38;2;255;178;15',
    'percent': '1;38;2;0;161;228',
    'waveform_compare': '1;38;2;0;161;228',
    'run_mode': '1;38;2;0;161;228',
    'release_summary': '1;38;2;255;178;15',
    'total_label': '1;38;2;119;255;148',
    'total_duration': '38;2;255;178;15',
}
_ANSI_PALETTE = dict(_ANSI_PALETTE_DEFAULTS)
_TERMINAL_COLORS_ENABLED = True
_TERMINAL_COLOR_ROLES = frozenset({
    *_ANSI_PALETTE_DEFAULTS,
    'phase_success', 'phase_failure', 'phase_warning',
    'progress_label', 'progress_counter', 'progress_unit', 'percent_complete',
    'waveform_compare', 'run_mode', 'release_summary', 'total_label', 'total_duration',
})
_TERMINAL_COLOR_FALLBACKS = {
    'phase_success': 'success',
    'phase_failure': 'error',
    'phase_warning': 'warn',
    'progress_label': 'phase',
    'progress_counter': 'counter',
    'progress_unit': 'duration',
    'percent_complete': 'success',
    'waveform_compare': 'info',
    'run_mode': 'dry',
    'release_summary': 'warn',
    'total_label': 'phase',
    'total_duration': 'duration',
}

_ANSI_NAMED_COLORS = {
    'black': 30, 'red': 31, 'green': 32, 'yellow': 33,
    'blue': 34, 'magenta': 35, 'cyan': 36, 'white': 37,
    'gray': 90, 'grey': 90,
    'bright_black': 90, 'bright_red': 91, 'bright_green': 92,
    'bright_yellow': 93, 'bright_blue': 94, 'bright_magenta': 95,
    'bright_cyan': 96, 'bright_white': 97,
}


def _ansi_color_component(value, *, background=False, role='color'):
    """Convert a friendly color name, #RRGGBB, 256:N or sgr:N;... to SGR codes."""
    if value is None:
        return []
    if not isinstance(value, str):
        raise ValueError(f'TERMINAL_COLORS.{role}: il colore deve essere una stringa')
    color = value.strip().lower().replace('-', '_').replace(' ', '_')
    if color in ('', 'none', 'off', 'default', 'inherit'):
        return []
    if re.fullmatch(r'#[0-9a-f]{6}', color):
        rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        return [str(48 if background else 38), '2', *(str(x) for x in rgb)]
    match = re.fullmatch(r'(?:256|ansi256):([0-9]{1,3})', color)
    if match:
        index = int(match.group(1))
        if not 0 <= index <= 255:
            raise ValueError(f'TERMINAL_COLORS.{role}: indice 256-color fuori intervallo 0..255')
        return [str(48 if background else 38), '5', str(index)]
    if color.startswith('sgr:'):
        raw = color[4:]
        if not re.fullmatch(r'[0-9]{1,3}(?:;[0-9]{1,3})*', raw):
            raise ValueError(f'TERMINAL_COLORS.{role}: usa solo codici numerici SGR, es. sgr:38;5;81')
        values = [int(part) for part in raw.split(';')]
        if any(value > 255 for value in values):
            raise ValueError(f'TERMINAL_COLORS.{role}: codici SGR fuori intervallo 0..255')
        return [str(x) for x in values]
    if color == 'reset':
        return ['49' if background else '39']
    code = _ANSI_NAMED_COLORS.get(color)
    if code is None:
        raise ValueError(
            f'TERMINAL_COLORS.{role}: colore {value!r} non riconosciuto; usa un nome ANSI, '
            '#RRGGBB, 256:N, sgr:... oppure none'
        )
    if background:
        code = code + 10 if code < 90 else code + 10
    return [str(code)]


def _terminal_style_to_sgr(value, role):
    """Accept a color string or a style object with color/background/attributes."""
    if isinstance(value, str):
        style = {'color': value}
    elif isinstance(value, dict):
        style = value
    else:
        raise ValueError(f'TERMINAL_COLORS.{role}: usa una stringa colore o un oggetto stile')
    allowed = {'color', 'background', 'bold', 'dim', 'italic', 'underline', 'reverse'}
    extra = set(style) - allowed
    if extra:
        raise ValueError(f'TERMINAL_COLORS.{role}: proprietà sconosciute: {sorted(extra)}')
    codes = []
    attrs = {'bold': '1', 'dim': '2', 'italic': '3', 'underline': '4', 'reverse': '7'}
    for attr, code in attrs.items():
        if attr in style and not isinstance(style[attr], bool):
            raise ValueError(f'TERMINAL_COLORS.{role}.{attr} deve essere booleano')
        if style.get(attr, False):
            codes.append(code)
    codes.extend(_ansi_color_component(style.get('color', 'none'), role=role))
    if style.get('background') not in (None, '', 'none', 'off', 'default', 'inherit'):
        codes.extend(_ansi_color_component(style['background'], background=True, role=role + '.background'))
    return ';'.join(codes)


def _apply_terminal_colors_config(config):
    """Reset defaults, then validate/apply JSON terminal color overrides."""
    global _TERMINAL_COLORS_ENABLED
    _ANSI_PALETTE.clear()
    _ANSI_PALETTE.update(_ANSI_PALETTE_DEFAULTS)
    _TERMINAL_COLORS_ENABLED = True
    if config is None:
        return
    if not isinstance(config, dict):
        raise ValueError('TERMINAL_COLORS deve essere un oggetto JSON')
    enabled = config.get('enabled', True)
    if not isinstance(enabled, bool):
        raise ValueError('TERMINAL_COLORS.enabled deve essere booleano')
    _TERMINAL_COLORS_ENABLED = enabled
    unknown = set(config) - {'enabled'} - _TERMINAL_COLOR_ROLES
    if unknown:
        raise ValueError(f'TERMINAL_COLORS contiene ruoli sconosciuti: {sorted(unknown)}')
    for role in _TERMINAL_COLOR_ROLES:
        if role in config:
            _ANSI_PALETTE[role] = _terminal_style_to_sgr(config[role], role)


def _colors_allowed(stream=None):
    """Return True only for a TTY when both JSON settings and environment allow colors."""
    if not _TERMINAL_COLORS_ENABLED:
        return False
    if os.environ.get('NO_COLOR', '') != '' or os.environ.get('CLICOLOR') == '0':
        return False
    if os.environ.get('TERM', '').lower() == 'dumb':
        return False
    stream = sys.stderr if stream is None else stream
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _paint(text, role, enabled=True):
    if not enabled or not text:
        return str(text)
    if role in _ANSI_PALETTE:
        code = _ANSI_PALETTE[role]
    else:
        code = _ANSI_PALETTE.get(_TERMINAL_COLOR_FALLBACKS.get(role, ''), '')
    return f'\x1b[{code}m{text}{_ANSI_RESET}' if code else str(text)


def _colorize_terminal_text(text, stream):
    """Colorize structured console prefixes; leave arbitrary message bodies untouched."""
    if not text or not _colors_allowed(stream):
        return text
    out = []
    for raw_line in text.splitlines(keepends=True):
        ending = ''
        line = raw_line
        if line.endswith('\r\n'):
            line, ending = line[:-2], '\r\n'
        elif line.endswith('\n') or line.endswith('\r'):
            line, ending = line[:-1], line[-1:]
        if not line:
            out.append(raw_line)
            continue

        # Run-mode/status lines have dedicated JSON roles, independent of generic [i] text.
        if re.match(r'^waveform compare:\s*', line, flags=re.IGNORECASE):
            out.append(_paint(line, 'waveform_compare') + ending)
            continue
        if re.match(r'^modo:\s*', line, flags=re.IGNORECASE):
            out.append(_paint(line, 'run_mode') + ending)
            continue
        if re.match(r'^gruppi release:\s*', line, flags=re.IGNORECASE):
            out.append(_paint(line, 'release_summary') + ending)
            continue

        # The total row intentionally has two independent roles: label and elapsed time.
        total_row = re.match(
            r'^(\s*)(TOTALE)(\s+)(\d{2}:\d{2}(?::\d{2})?\.\d{3})$', line,
            flags=re.IGNORECASE)
        if total_row:
            out.append(total_row.group(1) + _paint(total_row.group(2), 'total_label') +
                       total_row.group(3) + _paint(total_row.group(4), 'total_duration') + ending)
            continue

        # Timing-summary phase names and elapsed values use phase/duration independently.
        if re.fullmatch(r'=== (?:riepilogo tempi|fine riepilogo tempi) ===', line,
                        flags=re.IGNORECASE):
            out.append(_paint(line, 'phase') + ending)
            continue
        timing_row = re.match(
            r'^(\s+)(.+?)(\s{2,})(\d{2}:\d{2}(?::\d{2})?\.\d{3})$', line)
        if timing_row:
            out.append(timing_row.group(1) + _paint(timing_row.group(2).rstrip(), 'phase') +
                       timing_row.group(3) + _paint(timing_row.group(4), 'duration') + ending)
            continue

        # Phase heading and its counter are separate palette roles. Counter has no
        # parentheses in the new terminal layout: === fase name === 2/22.
        phase_start = re.match(r'^(=== fase .+? ===)(?:\s+(\d+/\d+))?$', line)
        if phase_start:
            colored = _paint(phase_start.group(1), 'phase')
            if phase_start.group(2):
                colored += ' ' + _paint(phase_start.group(2), 'counter')
            out.append(colored + ending)
            continue

        # Successful phase-end headings deliberately share the exact same `phase`
        # role as opening headings. Only the elapsed time uses `duration`.
        phase_finish = re.match(r'^(=== fine fase .+? ===)(?:\s+(\S+))?$', line)
        if phase_finish:
            colored = _paint(phase_finish.group(1), 'phase')
            if phase_finish.group(2):
                colored += ' ' + _paint(phase_finish.group(2), 'duration')
            out.append(colored + ending)
            continue

        phase_failure = re.match(
            r'^(=== (?:interrotta|fallita|terminata con errore).*? ===)(?:\s+(\S+))?$', line,
            flags=re.IGNORECASE)
        if phase_failure:
            colored = _paint(phase_failure.group(1), 'phase_failure')
            if phase_failure.group(2):
                colored += ' ' + _paint(phase_failure.group(2), 'duration')
            out.append(colored + ending)
            continue
        phase_warning = re.match(r'^(=== uscita anticipata.*? ===)(?:\s+(\S+))?$', line,
                                 flags=re.IGNORECASE)
        if phase_warning:
            colored = _paint(phase_warning.group(1), 'phase_warning')
            if phase_warning.group(2):
                colored += ' ' + _paint(phase_warning.group(2), 'duration')
            out.append(colored + ending)
            continue

        # The complete interruption notice belongs to phase_failure, not only its marker.
        if re.match(r'^\s*\[!\]\s*RUN INTERROTTA\b', line, flags=re.IGNORECASE):
            out.append(_paint(line, 'phase_failure') + ending)
            continue

        # Prefix-only coloring protects artist names, titles, paths, URLs and values.
        patterns = (
            (r'^(\s*)\[ERRORE\]', 'error'),
            (r'^(\s*)\[(?:ERROR|FATAL)\]', 'error'),
            (r'^(\s*)\[(?:warn|WARN|WARNING)\]', 'warn'),
            (r'^(\s*)\[review\]', 'review'),
            (r'^(\s*)\[(?:i|info|INFO)\]', 'info'),
            (r'^(\s*)\[(?:dry|DRY)\]', 'dry'),
            (r'^(\s*)\[(?:ok|OK|SUCCESS)\]', 'success'),
        )
        for pattern, role in patterns:
            line, count = re.subn(
                pattern,
                lambda m: m.group(1) + _paint(m.group(0)[len(m.group(1)):], role),
                line, count=1)
            if count:
                break
        out.append(line + ending)
    return ''.join(out)


_PROGRESS_TTY_STACK = []
_PROGRESS_TTY_MANAGER_LOCK = threading.RLock()
_PROGRESS_TERMINAL_IO_LOCK = threading.RLock()


class _ProgressBar:
    """Pinned terminal progress row with a fixed 50-character bar and 100ms spinner.

    Interactive terminals reserve the last screen row for status and restrict normal
    scrolling to the rows above it. Rendering saves/restores the log cursor, so new
    stdout/stderr messages scroll above the bar instead of covering it. Redirected logs
    remain compact and receive periodic checkpoints.
    """
    BAR_WIDTH = 50
    REFRESH_SECONDS = 0.1
    SPINNER_FRAMES = ('⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏')

    def __init__(self, label, total, unit='brani', stream=None):
        self.label = str(label)
        try:
            self.total = max(0, int(total or 0))
        except (TypeError, ValueError):
            self.total = 0
        self.unit = str(unit)
        self.stream = stream or sys.stderr
        # Tee forwards ordinary output to the console and log file; terminal controls
        # must go directly to the actual TTY, never into the text log.
        self.terminal_stream = self.stream
        try:
            nested_streams = getattr(self.stream, 'streams', None)
            if nested_streams and nested_streams[0].isatty():
                self.terminal_stream = nested_streams[0]
        except Exception:
            pass
        try:
            is_tty = bool(self.terminal_stream.isatty())
        except Exception:
            is_tty = False
        self.tty = bool(is_tty and self.total > 0)
        self.display_label = self.label
        self.display_unit = self.unit
        self.bar_width = self.BAR_WIDTH
        self.last_done = 0
        self.last_pct = None
        self.last_checkpoint = 0
        self.last_render_at = 0.0
        self._spinner_index = 0
        self.last_width = 0
        self.active = False
        self.closed = False
        self._terminal_suspended = False
        self._terminal_parent = None
        self._pin_rows = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None
        if self.tty:
            columns, _rows = self._terminal_size()
            digits = max(1, len(str(max(1, self.total))))
            def minimum_width():
                left = f'{self.display_label}: {"8" * digits}/{"8" * digits} {self.display_unit}'
                right = f'{self.SPINNER_FRAMES[0]} [' + ('#' * self.BAR_WIDTH) + '] 100%'
                return len(left) + 2 + len(right)
            while minimum_width() > columns - 1 and len(self.display_label) > 8:
                self.display_label = self.display_label[:-2].rstrip() + '…'
            while minimum_width() > columns - 1 and len(self.display_unit) > 2:
                self.display_unit = self.display_unit[:-2].rstrip() + '…'
            with _PROGRESS_TTY_MANAGER_LOCK:
                if _PROGRESS_TTY_STACK:
                    self._terminal_parent = _PROGRESS_TTY_STACK[-1]
                    self.terminal_stream = self._terminal_parent.terminal_stream
                    self._pin_rows = self._terminal_parent._pin_rows
                    with self._terminal_parent._lock:
                        self._terminal_parent._terminal_suspended = True
                else:
                    self._configure_terminal_pin()
                _PROGRESS_TTY_STACK.append(self)
            self._thread = threading.Thread(target=self._ticker,
                                            name='exportify-progress', daemon=True)
            self._thread.start()
            self.update(0, force=True)

    def _configure_terminal_pin(self):
        """Reserve the physical last row and leave the log cursor in the row above it."""
        rows = max(3, shutil.get_terminal_size(fallback=(120, 24)).lines)
        self._pin_rows = rows
        # DECSTBM sets the scrolling region to all but the final screen row. Moving to
        # its bottom and issuing LF scrolls ordinary output into a fresh row above status.
        with _PROGRESS_TERMINAL_IO_LOCK:
            self.terminal_stream.write(f'\x1b[1;{rows - 1}r')
            self.terminal_stream.write(f'\x1b[{rows - 1};1H\n')
            self.terminal_stream.flush()

    def _terminal_size(self):
        size = shutil.get_terminal_size(fallback=(120, 24))
        return max(40, size.columns), max(3, size.lines)

    def _restore_terminal_pin(self):
        if not self._pin_rows:
            return
        try:
            with _PROGRESS_TERMINAL_IO_LOCK:
                # Clear the pinned status row, restore normal full-screen scrolling, then
                # return the cursor to where ordinary log output left it.
                self.terminal_stream.write('\x1b[s')
                self.terminal_stream.write(f'\x1b[{self._pin_rows};1H\x1b[2K')
                self.terminal_stream.write('\x1b[r')
                self.terminal_stream.write('\x1b[u')
                self.terminal_stream.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def _format(self, done, spinner):
        pct = min(100, max(0, done * 100 // self.total)) if self.total else 100
        filled = min(self.bar_width, max(1, pct * self.bar_width // 100) if pct > 0 else 0)
        left_plain = f'{self.display_label}: {done}/{self.total} {self.display_unit}'
        bar_plain = '[' + ('#' * filled) + ('-' * (self.bar_width - filled)) + ']'
        right_plain = f'{spinner} {bar_plain} {pct}%'
        if not self.tty:
            return f'{left_plain} {right_plain}', pct

        # Apply color only after measuring the unstyled text: ANSI sequences must not affect
        # right alignment, terminal-width checks or the exact 50-character inner bar.
        enabled = _colors_allowed(self.terminal_stream)
        left = (_paint(self.display_label, 'progress_label', enabled) + ': ' +
                _paint(f'{done}/{self.total}', 'progress_counter', enabled) + ' ' +
                _paint(self.display_unit, 'progress_unit', enabled))
        border_left = _paint('[', 'bar_border', enabled)
        fill = _paint('#' * filled, 'bar_fill', enabled)
        empty = _paint('-' * (self.bar_width - filled), 'bar_empty', enabled)
        border_right = _paint(']', 'bar_border', enabled)
        percent_role = 'percent_complete' if pct >= 100 else 'percent'
        right = (_paint(spinner, 'spinner', enabled) + ' ' + border_left + fill +
                 empty + border_right + ' ' + _paint(f'{pct}%', percent_role, enabled))
        columns, _rows = self._terminal_size()
        gap = max(2, columns - len(left_plain) - len(right_plain) - 1)
        return left + (' ' * gap) + right, pct

    def _render_tty_locked(self, now=None):
        if self.closed or not self.tty or not self.active or self._terminal_suspended:
            return
        now = time.monotonic() if now is None else now
        columns, rows = self._terminal_size()
        # Keep the bar on the physical last row without changing the log-output cursor.
        # Serialize rendering with Tee writes to avoid a warning splitting a spinner frame.
        with _PROGRESS_TERMINAL_IO_LOCK:
            if rows != self._pin_rows:
                old_rows = self._pin_rows or rows
                self.terminal_stream.write('\x1b[s')
                self.terminal_stream.write(f'\x1b[1;{rows - 1}r')
                if rows < old_rows:
                    # On a shrink, the saved cursor may now be exactly on the new
                    # status row. Move it back inside the scrolling region instead of
                    # restoring an out-of-region cursor that could let the next print
                    # overwrite the pinned bar. On growth, the old cursor is still safe.
                    self.terminal_stream.write(f'\x1b[{rows - 1};1H')
                else:
                    self.terminal_stream.write('\x1b[u')
                self.terminal_stream.flush()
                self._pin_rows = rows
            line, pct = self._format(self.last_done, self.SPINNER_FRAMES[self._spinner_index])
            self.terminal_stream.write('\x1b[s')
            self.terminal_stream.write(f'\x1b[{rows};1H\x1b[2K')
            visible_line = _ANSI_RE.sub('', line)
            disable_wrap = len(visible_line) >= columns
            if disable_wrap:
                self.terminal_stream.write('\x1b[?7l')
            try:
                self.terminal_stream.write(line)
            finally:
                if disable_wrap:
                    self.terminal_stream.write('\x1b[?7h')
                self.terminal_stream.write('\x1b[u')
                self.terminal_stream.flush()
        self.last_width = len(_ANSI_RE.sub('', line))
        self.last_render_at = now
        self.last_pct = pct

    def _ticker(self):
        while not self._stop_event.wait(self.REFRESH_SECONDS):
            with self._lock:
                if self.active and not self.closed and not self._terminal_suspended:
                    self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
                    try:
                        self._render_tty_locked()
                    except (BrokenPipeError, OSError, ValueError):
                        self.active = False
                        return

    def clear(self):
        """Keep the status pinned; normal output is emitted in the scrolling region above it."""
        # Previously this erased the bar before every warning/result line, making it vanish
        # for a frame and allowing output to reuse its row. The reserved-row display removes
        # the need to erase/redraw around ordinary messages.
        return

    def update(self, done, force=False):
        if self.closed or self.total <= 0:
            return
        try:
            done = max(0, min(int(done), self.total))
        except (TypeError, ValueError):
            return
        if self.tty:
            with self._lock:
                self.last_done = done
                self.active = True
                if force or not self.last_render_at:
                    self._render_tty_locked()
            return

        self.last_done = done
        line, pct = self._format(done, self.SPINNER_FRAMES[0])
        now = time.monotonic()
        checkpoint = pct // 5
        # Compact non-interactive log snapshots; never emit carriage-return animations.
        if not force and done < self.total and checkpoint == self.last_checkpoint:
            if now - self.last_render_at < 1.0:
                return
        if not force and done == 0:
            return
        if not force and checkpoint == self.last_checkpoint and done < self.total:
            return
        print(line, file=self.stream, flush=True)
        self.last_checkpoint = checkpoint
        self.last_pct = pct
        self.last_render_at = now

    def close(self, complete=False, *, render_final=True, restore_parent=True):
        if self.closed:
            return
        if self.tty:
            with self._lock:
                final_done = self.total if complete else min(self.last_done, self.total)
                self.last_done = final_done
                if render_final:
                    self.active = True
                    self._render_tty_locked()
                self.active = False
                self.closed = True
            self._stop_event.set()
            if self._thread and self._thread is not threading.current_thread():
                self._thread.join(timeout=0.5)
            with _PROGRESS_TTY_MANAGER_LOCK:
                was_top = bool(_PROGRESS_TTY_STACK and _PROGRESS_TTY_STACK[-1] is self)
                try:
                    _PROGRESS_TTY_STACK.remove(self)
                except ValueError:
                    pass
                if was_top and _PROGRESS_TTY_STACK and restore_parent:
                    parent = _PROGRESS_TTY_STACK[-1]
                    with parent._lock:
                        parent._terminal_suspended = False
                        parent.active = True
                        parent._render_tty_locked()
                elif not _PROGRESS_TTY_STACK:
                    self._restore_terminal_pin()
        else:
            if self.total > 0:
                final_pct = (self.total if complete else min(self.last_done, self.total)) * 100 // self.total
                if self.last_pct != final_pct or self.last_checkpoint != final_pct // 5:
                    self.update(self.total if complete else self.last_done, force=True)
            self.closed = True
            self._stop_event.set()



def _cleanup_active_progress_bars():
    """Release every reserved terminal row without leaving a stale progress bar behind."""
    with _PROGRESS_TTY_MANAGER_LOCK:
        bars = list(reversed(_PROGRESS_TTY_STACK))
    for bar in bars:
        try:
            bar.close(complete=False, render_final=False, restore_parent=False)
        except Exception:
            # Last-resort terminal reset: cleanup must not hide the original exception or
            # KeyboardInterrupt. The root bar owns the terminal scrolling-region snapshot.
            try:
                bar._restore_terminal_pin()
            except Exception:
                pass
    with _PROGRESS_TTY_MANAGER_LOCK:
        if _PROGRESS_TTY_STACK:
            root = _PROGRESS_TTY_STACK[0]
            try:
                root._restore_terminal_pin()
            except Exception:
                pass
            _PROGRESS_TTY_STACK.clear()


def _progress_signal_handler(signum, frame):
    """Unpin the terminal immediately on Ctrl+C/SIGTERM/SIGHUP, then exit normally."""
    _cleanup_active_progress_bars()
    if signum == getattr(signal, 'SIGINT', None):
        raise KeyboardInterrupt
    raise SystemExit(128 + int(signum))


def _install_progress_signal_handlers():
    """Install temporary shutdown handlers; return previous handlers for restoration."""
    previous = {}
    for signal_name in ('SIGINT', 'SIGTERM', 'SIGHUP'):
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        try:
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, _progress_signal_handler)
        except (ValueError, OSError):
            # signal.signal is restricted to the main thread and may be unavailable on
            # some platforms; the atexit and KeyboardInterrupt paths still remain active.
            continue
    return previous


def _restore_progress_signal_handlers(previous):
    for signum, handler in (previous or {}).items():
        try:
            signal.signal(signum, handler)
        except (ValueError, OSError):
            pass


# atexit covers ordinary completion and uncaught exceptions. Explicit signal handlers cover
# Ctrl+C and catchable termination signals; SIGKILL cannot be intercepted by any process.
atexit.register(_cleanup_active_progress_bars)

def _maybe_reexec_in_venv():
    """Debian 12+/13 blocca 'pip install --user' (PEP 668): le librerie opzionali
    (pykakasi, hangul-romanize, numpy) vivono in un venv. Se esiste .venv accanto
    allo script e NON stiamo gia' girando li' dentro, rilancia lo script con
    quell'interprete: cosi' cron e ./exportify_to_m3u.py continuano a funzionare
    senza modificare nulla. Disattiva con EXPORTIFY_NO_VENV=1."""
    if os.environ.get('EXPORTIFY_NO_VENV') or os.environ.get('VIRTUAL_ENV'):
        return
    vdir = Path(__file__).resolve().parent / '.venv'
    py = vdir / 'bin' / 'python'
    try:
        if py.exists() and Path(sys.prefix).resolve() != vdir.resolve():
            os.environ['EXPORTIFY_NO_VENV'] = '1'          # anti-loop
            os.execv(str(py), [str(py), *sys.argv])
    except OSError:
        pass


if __name__ == '__main__':
    _maybe_reexec_in_venv()

try:
    from pykakasi import kakasi as _kakasi_cls
    _kks = _kakasi_cls()
    _HAS_KAKASI = True
except Exception:
    _HAS_KAKASI = False

LIBRARY_ROOT = Path("/homelab/MUSICA")


def _cache_dir():
    """Cache persistente in ~/.cache (XDG). NON /tmp: su Debian 13 e' tmpfs, si
    svuota a ogni riavvio e la prima esecuzione dopo il boot riscansionava tutto
    (e un file prevedibile in /tmp e' scrivibile da qualunque utente)."""
    cands = []
    try:
        cands.append(Path(os.environ.get('XDG_CACHE_HOME') or (Path.home() / '.cache'))
                     / 'exportify2m3u')
    except RuntimeError:
        pass
    cands.append(Path(tempfile.gettempdir()) / 'exportify2m3u')
    for d in cands:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            continue
    return Path(tempfile.gettempdir())


CACHE_DIR = _cache_dir()
# metaflac: --no-utf8-convert SEMPRE. Senza, metaflac converte i tag dal charset del
# locale: sotto cron (LANG non impostato) i tag giapponesi/coreani venivano
# rifiutati o scritti male.
METAFLAC = ['metaflac', '--no-utf8-convert']
CACHE = CACHE_DIR / "lib_index.json"  # cache indice filesystem
MUSIC_ROOT = "/homelab/MUSICA"
PLAYLIST_DIR = Path("/homelab/MUSICA/Playlists")
# stato sync: base -> hash del CSV che ha generato l'ultimo .m3u.
# Se lo Spotify non cambia, il file NON viene riscritto: le modifiche fatte
# da client (wavio/Navidrome UI) sulle playlist NON toccate sopravvivono.
SYNC_FILE = PLAYLIST_DIR / '.sync_state.json'
SYNC_STATE = {}
EXPORTIFY_DIR = Path("/homelab/arr-config/exportify")
JELLYFIN_ROOT = "/data/music"          # path della musica DENTRO il container Jellyfin
ZIP_DIR = Path("/home/chic/homelab/scripts/spotify_csv")   # cartella con gli zip Exportify (uno per utente)
# vecchie cartelle: gli zip Exportify trovati qui vengono SPOSTATI in ZIP_DIR alla prima esecuzione
ZIP_LEGACY_DIRS = [Path("/home/chic/homelab/docker")]
# Utente Navidrome "di default": le sue playlist restano nel layout storico
# (PLAYLIST_DIR/ senza sottocartella utente) e a lui --fix-owners assegna le playlist
# importate da fuori delle cartelle utente.
DEFAULT_USER = os.environ.get('ND_DEFAULT_USER') or os.environ.get('ND_USER', 'chic')
# ID Spotify (colonna "Added By" dei CSV) -> utente Navidrome. Dal JSON: "SPOTIFY_USERS".
SPOTIFY_USERS = {}
# Utenti da escludere SOLTANTO dal fetch Exportify; le M3U/CSV gia' presenti restano utilizzabili.
FETCH_IGNORED_USERS = set()
# Utente casefold -> (nome utente della sessione, percorso dello ZIP appena scaricato).
_FETCH_SUCCEEDED_USERS = {}
# Utenti il cui ZIP appena scaricato e' stato estratto senza errori in questa esecuzione.
_FRESH_EXTRACTED_USERS = set()
# M3U effettivamente generate/validate nella run corrente e CSV la cui conversione e' fallita.
_GENERATED_M3U_PATHS = {}
_M3U_GENERATION_FAILED_USERS = set()
_STALE_M3U_REMOVED_PATHS = []

VERSION = "0.83"   # bump a ogni modifica: loggata all'avvio e via --version

# intestazioni Exportify: italiano (prima) e inglese
COLS = {
    'title':  ['Nome della traccia', 'Track Name'],
    'artist': ["Nome dell'artista", 'Artist Name(s)', 'Artist Name', 'Artista'],
    'album':  ["Nome dell'album", 'Album Name', 'Album'],
    'uri':    ['Track URI', 'URI', 'Track URI(s)'],
    # chi ha aggiunto il brano alla playlist (ID/URI utente Spotify): serve a capire
    # di chi e' uno zip il cui nome non inizia con un utente Navidrome
    'added_by': ['Added By', 'Aggiunto da', 'Aggiunta da', 'A\u00f1adido por',
                 'Ajout\u00e9 par', 'Hinzugef\u00fcgt von'],
}

# ===================== multi-utente: zip -> utente Navidrome =====================

def _db_users():
    """Nomi utente Navidrome (lettura sola dal DB). [] se il DB non e' leggibile."""
    if not NAVIDROME_DB.exists():
        return []
    try:
        con = sqlite3.connect(f'{NAVIDROME_DB.as_uri()}?mode=ro', uri=True, timeout=10)
        try:
            return [r[0] for r in con.execute('SELECT user_name FROM user ORDER BY user_name')]
        finally:
            con.close()
    except sqlite3.Error as e:
        print(f"[warn] impossibile leggere gli utenti dal DB Navidrome: {e}", file=sys.stderr)
        return []


def known_users():
    """Utenti Navidrome noti. Se il DB non e' leggibile: DEFAULT_USER + quelli del JSON."""
    names = _db_users()
    if names:
        return names
    out = []
    for n in [DEFAULT_USER, *SPOTIFY_USERS.values()]:
        if n and n.lower() not in {x.lower() for x in out}:
            out.append(n)
    return out


def canon_user(name, users):
    """Nome utente con la maiuscole/minuscole del DB (confronto case-insensitive) o None."""
    low = (name or '').strip().lower()
    for u in users:
        if u.lower() == low:
            return u
    return None


def resolve_selected_users(raw):
    """--users a,b (ripetibile) -> lista di utenti canonici; None = TUTTI."""
    if raw is None:
        return None
    users = known_users()
    out, bad = [], []
    for chunk in raw:
        for name in chunk.split(','):
            name = name.strip()
            if not name:
                continue
            u = canon_user(name, users)
            (out if u else bad).append(u or name)
    if bad:
        sys.exit(f"[ERRORE] utenti sconosciuti in --users: {', '.join(bad)} "
                 f"(noti: {', '.join(users) or 'nessuno'})")
    if not out:
        sys.exit("[ERRORE] --users vuoto (ometti l'opzione per includere tutti gli utenti)")
    return list(dict.fromkeys(out))


def _user_playlist_root(user):
    """Cartella m3u dell'utente: DEFAULT_USER = layout storico, gli altri in <utente>/."""
    return PLAYLIST_DIR if user == DEFAULT_USER else PLAYLIST_DIR / user


def _sync_key(user, base):
    return base if user == DEFAULT_USER else f"{user}::{base}"


def _normal_path(path):
    """Percorso assoluto normalizzato senza dereferenziare eventuali link simbolici."""
    return Path(os.path.abspath(os.fspath(path)))


def _playlist_collision_key(value):
    """Chiave di collisione per alias di nomi playlist: ignora case, spazi e punteggiatura."""
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    if value.endswith('.m3u'):
        value = value[:-4]
    return ''.join(ch for ch in value if ch.isalnum())


def _playlist_relative_collision_key(relative):
    """Chiave relativa che mantiene distinti directory differenti ma tollera alias nei nomi."""
    rel = Path(relative)
    if not rel.parts or any(part in ('', '.', '..') for part in rel.parts):
        return None
    parent = tuple(_playlist_collision_key(part) for part in rel.parts[:-1])
    stem = _playlist_collision_key(rel.stem)
    if not stem:
        return None
    return parent, stem


def _db_playlist_relative_path(db_path):
    """Estrae il percorso relativo a PLAYLIST_DIR da un path host/container nel DB."""
    if not db_path:
        return None
    raw = str(db_path).replace('\\', '/')
    parts = [part for part in raw.split('/') if part]
    root_name = PLAYLIST_DIR.name.casefold()
    indexes = [i for i, part in enumerate(parts) if part.casefold() == root_name]
    if not indexes:
        return None
    rel = parts[indexes[-1] + 1:]
    if not rel:
        return None
    return '/'.join(rel)


def _record_generated_m3u(user, path):
    """Registra solo una playlist CSV convertita senza errori nella run corrente."""
    _GENERATED_M3U_PATHS.setdefault(str(user).casefold(), set()).add(_normal_path(path))


def _csv_user(csv_path):
    """Utente di un CSV: EXPORTIFY_DIR/<utente>/x.csv -> <utente>, altrimenti DEFAULT_USER."""
    p = Path(csv_path)
    try:
        if p.parent.parent.resolve() == EXPORTIFY_DIR.resolve():
            return p.parent.name
    except OSError:
        pass
    return DEFAULT_USER


def zip_name_user(zip_path, users):
    """Utente il cui nome e' l'INIZIO del nome dello zip (chic_x.zip, chic-x.zip, chic.zip).
    Dopo il nome non puo' seguire una lettera/cifra ('chic' NON riconosce 'chicco_x.zip');
    a parita' vince il nome piu' lungo."""
    fn = Path(zip_path).name.lower()
    best = None
    for u in users:
        ul = u.lower()
        if fn.startswith(ul) and (len(fn) == len(ul) or not fn[len(ul)].isalnum()):
            if best is None or len(u) > len(best):
                best = u
    return best


def _playlist_name_keys(value):
    """Chiavi tolleranti per collegare nomi Spotify originali ai nomi CSV sanitizzati.

    Le chiavi di confronto non vengono mai usate come nome visualizzato: servono solo a
    matchare. La chiave compact gestisce Exportify che rimuove invece di sostituire emoji
    o punteggiatura.
    """
    value = unicodedata.normalize('NFKC', str(value or '')).casefold().strip()
    separated = re.sub(r'[\W_]+', ' ', value, flags=re.UNICODE).strip()
    compact = ''.join(ch for ch in value if ch.isalnum())
    return {key for key in (separated, compact) if key}


def _playlist_filename(name):
    """Nome M3U leggibile e Unicode-safe; non converte mai in minuscolo.

    Su POSIX '/' e '\\' non possono essere parte di un basename. I loro equivalenti
    fullwidth mantengono l'aspetto visivo del titolo Spotify. I caratteri di controllo
    vengono eliminati per evitare nomi file problematici.
    """
    value = unicodedata.normalize('NFC', str(name or '')).strip()
    value = value.replace('/', '／').replace('\\', '＼')
    value = ''.join(ch for ch in value if ord(ch) >= 32 and ord(ch) != 127)
    value = value.strip()
    if value in ('', '.', '..'):
        return 'Untitled Playlist'
    return value


def _spotify_image_url(value):
    """Accetta solo URL HTTPS dei CDN immagine Spotify (no URL arbitrari)."""
    try:
        parsed = urllib.parse.urlparse(str(value or ''))
        host = (parsed.hostname or '').lower().rstrip('.')
        spotify_host = (host == 'scdn.co' or host.endswith('.scdn.co') or
                        host == 'spotifycdn.com' or host.endswith('.spotifycdn.com'))
        return str(value) if parsed.scheme == 'https' and spotify_host else ''
    except (TypeError, ValueError):
        return ''


def _spotify_playlist_records(payload):
    """Estrae oggetti playlist da risposte JSON Spotify, preservando l'ordine API."""
    found = {}

    def visit(node):
        if isinstance(node, dict):
            uri = str(node.get('uri') or '')
            ptype = str(node.get('type') or '').lower()
            owner = node.get('owner')
            tracks = node.get('tracks')
            is_playlist = (ptype == 'playlist' or uri.startswith('spotify:playlist:') or
                           (isinstance(owner, dict) and isinstance(tracks, dict) and
                            isinstance(node.get('images'), list)))
            if is_playlist and isinstance(node.get('name'), str):
                pid = str(node.get('id') or uri.rsplit(':', 1)[-1]).strip()
                if pid:
                    image_url = ''
                    for img in node.get('images') or []:
                        if isinstance(img, dict):
                            image_url = _spotify_image_url(img.get('url'))
                            if image_url:
                                break
                    prior = found.get(pid)
                    if prior is None or (not prior.get('image_url') and image_url):
                        found[pid] = {'id': pid, 'name': node['name'], 'image_url': image_url}
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return list(found.values())


def _map_playlist_metadata_to_zip(zip_path, records):
    """Mappa basename CSV -> metadati playlist usando nomi esatti e poi chiavi tolleranti."""
    if not records:
        return {}
    try:
        with zipfile.ZipFile(zip_path) as z:
            filenames = [Path(info.filename).name for info in _zip_csvs(z)]
    except (OSError, zipfile.BadZipFile):
        return {}
    assignments = {}
    used = set()

    # Prima passata: stessa stringa (maiuscole incluse); seconda: stessa stringa senza
    # differenze di case. Si riservano i match univoci prima di considerare la punteggiatura.
    for mode in ('exact', 'casefold'):
        for filename in filenames:
            if filename in assignments:
                continue
            stem = Path(filename).stem
            if mode == 'exact':
                candidates = [i for i, rec in enumerate(records)
                              if i not in used and str(rec.get('name', '')) == stem]
            else:
                candidates = [i for i, rec in enumerate(records)
                              if i not in used and str(rec.get('name', '')).casefold() == stem.casefold()]
            if len(candidates) == 1:
                i = candidates[0]
                assignments[filename] = records[i]
                used.add(i)

    for filename in filenames:
        if filename in assignments:
            continue
        file_keys = _playlist_name_keys(Path(filename).stem)
        candidates = [i for i, rec in enumerate(records) if i not in used and
                      file_keys.intersection(_playlist_name_keys(rec.get('name', '')))]
        if len(candidates) == 1:
            i = candidates[0]
            assignments[filename] = records[i]
            used.add(i)

    return assignments


def _archive_meta_path(zip_path):
    zip_path = Path(zip_path)
    return zip_path.with_name(zip_path.stem + '.meta.json')


def _read_playlist_meta_for_csv(csv_path):
    """Metadati acquisiti dal fetch; None se non esistono o il CSV non e' mappato."""
    meta_file = Path(csv_path).parent / '.playlist_meta.json'
    try:
        data = json.loads(meta_file.read_text(encoding='utf-8'))
        item = data.get('playlists', {}).get(Path(csv_path).name)
        return item if isinstance(item, dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def _zip_csvs(z):
    return [i for i in z.infolist()
            if not i.is_dir() and i.filename.lower().endswith('.csv')
            and '__macosx' not in i.filename.lower().split('/')
            and not Path(i.filename).name.startswith('.')]


def _csv_files(directory, recursive=False):
    """CSV visibili; recursive e' usato per pulire anche eventuali sottocartelle residue."""
    try:
        root = Path(directory)
        candidates = root.rglob('*') if recursive else root.iterdir()
        return sorted(p for p in candidates
                      if p.suffix.casefold() == '.csv' and not p.name.startswith('.')
                      and (p.is_file() or p.is_symlink()))
    except OSError:
        return []


def _looks_like_exportify(z, infos):
    """Riconosce anche gli export contenenti la raccolta album oltre alle normali playlist."""
    for info in infos:
        try:
            with z.open(info) as fh:
                head = fh.read(65536).decode('utf-8-sig', errors='replace')
            fields = next(csv.reader(io.StringIO(head)), [])
        except (OSError, zipfile.BadZipFile, UnicodeError, csv.Error):
            continue
        if pick_col(fields, COLS['title']) and pick_col(fields, COLS['artist']):
            return True
        keys = {re.sub(r'\s+', ' ', (f or '').strip().casefold()) for f in fields}
        # Formato CSV reale della raccolta salvata di Exportify.
        if 'album name' in keys and 'album artist name(s)' in keys:
            return True
    return False


def _pick_added_by(fieldnames):
    want = {c.lower() for c in COLS['added_by']}
    for f in fieldnames:
        if (f or '').strip().lower().replace('_', ' ') in want:
            return f
    return None


def _clean_spotify_id(v):
    """'spotify:user:abc', URL del profilo o ID nudo -> 'abc'. 'spotify' (playlist editoriali) e
    vuoti -> ''."""
    v = (v or '').strip()
    v = re.sub(r'^spotify:user:', '', v, flags=re.I)
    m = re.search(r'open\.spotify\.com/user/([^/?#]+)', v)
    if m:
        v = m.group(1)
    return '' if v.lower() in ('', 'spotify') else v


def zip_spotify_id(z, infos):
    """(id, righe con quell'id, righe con un id) dell'ID Spotify piu' frequente in 'Added By'
    su TUTTI i CSV dello zip, oppure None."""
    cnt = Counter()
    for info in infos:
        try:
            reader = csv.DictReader(io.StringIO(z.read(info).decode('utf-8-sig', errors='replace')))
            col = _pick_added_by(reader.fieldnames or [])
            if not col:
                continue
            for row in reader:
                sid = _clean_spotify_id(row.get(col))
                if sid:
                    cnt[sid] += 1
        except (csv.Error, OSError):
            continue
    if not cnt:
        return None
    sid, n = cnt.most_common(1)[0]
    return sid, n, sum(cnt.values())


_SPOT_BLOCK = re.compile(r'("SPOTIFY_USERS"\s*:\s*)\{([^{}]*)\}')


def _link_spotify_user(sid, user):
    """Memorizza sid -> user in memoria e in exportify_names.json. Ritocca SOLO il blocco
    "SPOTIFY_USERS" (il resto del file, con la sua formattazione, resta com'e').
    Ritorna False se non e' riuscito a scrivere il JSON."""
    SPOTIFY_USERS[sid] = user
    try:
        text = _USER_CFG.read_text(encoding='utf-8')
        m = _SPOT_BLOCK.search(text)
        if not m:
            return False
        cur = json.loads('{' + m.group(2) + '}')
        cur[sid] = user
        body = ',\n'.join(f'    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}'
                          for k, v in cur.items())
        new_text = text[:m.start()] + m.group(1) + '{\n' + body + '\n  }' + text[m.end():]
        json.loads(new_text)                       # validazione prima di scrivere
        tmp = _USER_CFG.with_name(_USER_CFG.name + '.tmp')
        tmp.write_text(new_text, encoding='utf-8')
        os.replace(tmp, _USER_CFG)
        return True
    except (OSError, ValueError) as e:
        print(f"[warn] impossibile aggiornare {_USER_CFG.name}: {e}", file=sys.stderr)
        return False


def _link_hint(sid):
    return (f'aggiungi  "SPOTIFY_USERS": {{"{sid}": "<utente navidrome>"}}  a {_USER_CFG.name} '
            f'oppure rinomina lo zip in "<utente>_<nome>.zip"')


def resolve_zip_user(zp, z, infos, users):
    """-> (utente, come) oppure (None, motivo).
    1) il nome dello zip inizia con un utente Navidrome
    2) ID Spotify piu' frequente nei CSV -> SPOTIFY_USERS nel JSON
    3) da terminale: chiede e salva il legame nel JSON"""
    by_name = zip_name_user(zp, users)
    if by_name:
        return by_name, 'nome file'
    sp = zip_spotify_id(z, infos)
    if not sp:
        return None, ("il nome non inizia con un utente Navidrome e i CSV non hanno ID Spotify "
                      "('Added By'): rinomina lo zip in \"<utente>_<nome>.zip\"")
    sid, n, tot = sp
    mapped = SPOTIFY_USERS.get(sid) or next(
        (v for k, v in SPOTIFY_USERS.items() if k.lower() == sid.lower()), None)
    if mapped:
        u = canon_user(mapped, users)
        if u:
            return u, f'ID Spotify {sid} (JSON)'
        return None, f"SPOTIFY_USERS lega {sid} a '{mapped}', che non e' un utente Navidrome"
    if not sys.stdin.isatty():
        return None, f"ID Spotify piu' frequente: {sid} ({n}/{tot} righe), non collegato: {_link_hint(sid)}"
    print(f"[?] {zp.name}: il nome non inizia con un utente; ID Spotify piu' frequente: "
          f"{sid} ({n}/{tot} righe)")
    for i, u in enumerate(users, 1):
        print(f"      {i}. {u}")
    try:
        ans = input("    utente Navidrome di questo zip (numero o nome, INVIO=salta): ").strip()
    except EOFError:
        ans = ''
    u = (users[int(ans) - 1] if ans.isdigit() and 1 <= int(ans) <= len(users)
         else canon_user(ans, users))
    if not u:
        return None, 'saltato'
    if _link_spotify_user(sid, u):
        print(f"    collegato {sid} -> {u} (salvato in {_USER_CFG.name})")
    else:
        print(f"    collegato {sid} -> {u} SOLO per questa esecuzione: {_link_hint(sid)}")
    return u, f'ID Spotify {sid} (scelto a mano)'


def migrate_legacy_zips(dry_run=False):
    """Sposta in ZIP_DIR gli zip Exportify rimasti nelle vecchie cartelle (ZIP_LEGACY_DIRS): solo
    quelli che contengono CSV Exportify, gli altri zip non si toccano. Con dry_run non sposta
    niente e restituisce i percorsi vecchi, cosi' vengono comunque letti. -> lista di zip."""
    out = []
    for d in ZIP_LEGACY_DIRS:
        try:
            if not d.is_dir() or d.resolve() == ZIP_DIR.resolve():
                continue
        except OSError:
            continue
        for zp in sorted(d.glob('*.zip')):
            try:
                with zipfile.ZipFile(zp) as z:
                    infos = _zip_csvs(z)
                    if not infos or not _looks_like_exportify(z, infos):
                        continue
            except (zipfile.BadZipFile, zlib.error, OSError, RuntimeError, ValueError):
                continue
            if dry_run:
                out.append(zp)
                continue
            dest = ZIP_DIR / zp.name
            try:
                ZIP_DIR.mkdir(parents=True, exist_ok=True)
                if dest.exists() and zp.stat().st_mtime <= dest.stat().st_mtime:
                    print(f"[!] {zp} NON spostato: in {ZIP_DIR} c'e' gia' {dest.name} piu' recente "
                          f"(cancella a mano quello vecchio)", file=sys.stderr)
                    continue
                shutil.move(str(zp), str(dest))
            except OSError as e:
                print(f"[ERRORE] impossibile spostare {zp} in {ZIP_DIR}: {e}", file=sys.stderr)
                continue
            print(f"[i] zip Exportify spostato: {zp} -> {dest}", file=sys.stderr)
            out.append(dest)
    return out


def find_zips(spec, dry_run=False):
    """File .zip o cartelle (tutti i *.zip). Default: ZIP_DIR, dopo aver spostato li' gli zip
    Exportify delle vecchie cartelle (ZIP_LEGACY_DIRS). Ordine: dal piu' vecchio al piu' recente
    (se due zip sono dello stesso utente vince il piu' recente)."""
    cands = []
    if not spec:
        cands += migrate_legacy_zips(dry_run)
        if not dry_run:
            ZIP_DIR.mkdir(parents=True, exist_ok=True)
    for sp in (spec or [str(ZIP_DIR)]):
        p = Path(sp).expanduser()
        if p.is_dir():
            cands += sorted(q for q in p.glob('*.zip') if q.is_file())     # esclude i link rotti
        elif p.is_file():
            cands.append(p)
        elif spec:                           # la cartella predefinita puo' non esistere ancora
            print(f"[i] zip non trovato: {p}", file=sys.stderr)
    return sorted((c for c in dict.fromkeys(cands) if c.is_file()), key=lambda p: p.stat().st_mtime)


def unzip_exportify(zips, dest, selected=None, warn_stale=False, dry_run=False):
    """Estrae l'ultimo ZIP Exportify valido per ogni utente in dest/<utente>/.

    Gli ZIP sono ordinati per data; se in ZIP_DIR sono rimaste copie vecchie dello
    stesso utente, NON si uniscono i loro CSV: il piu' recente e' la fonte di verita'.
    Dopo un'estrazione riuscita, i CSV dello stesso utente non presenti nello ZIP vengono
    eliminati, insieme ai relativi metadati. Se uno ZIP non si riesce ad associare a un
    utente, non si cancella nulla per evitare di eliminare i CSV della persona sbagliata.
    """
    global _FRESH_EXTRACTED_USERS
    _FRESH_EXTRACTED_USERS = set()
    zlist = find_zips(zips, dry_run)
    # Se il fetch e' riuscito in questa run, includi quel preciso ZIP anche quando --zip indica
    # un'altra sorgente. Gli archivi di spotify_csv riconducibili allo stesso utente vengono poi
    # ignorati: non possono sovrascrivere il fetch fresco, anche se hanno un mtime piu' recente.
    for _key, (_fresh_user, _fresh_path) in _FETCH_SUCCEEDED_USERS.items():
        if _fresh_path.is_file() and all(_normal_path(x) != _normal_path(_fresh_path) for x in zlist):
            zlist.append(_fresh_path)
    zlist = sorted((z for z in dict.fromkeys(zlist) if z.is_file()),
                   key=lambda p: p.stat().st_mtime)
    users = known_users()
    wanted = {u.lower() for u in selected} if selected is not None else None

    def warn_unrefreshed(successfully_extracted):
        """Non cancellare CSV senza un export fresco, ma rendere visibili i casi non verificabili."""
        if not dest.is_dir():
            return
        done = {u.casefold() for u in successfully_extracted}
        for folder in sorted(p for p in dest.iterdir() if p.is_dir()):
            canonical = canon_user(folder.name, users)
            if not canonical or (wanted is not None and canonical.lower() not in wanted):
                continue
            if canonical.casefold() in done or not _csv_files(folder, recursive=True):
                continue
            print(f"[!] {canonical}: CSV esistenti lasciati intatti: nessuno ZIP Exportify "
                  f"valido estratto con successo per questo utente in questa run; "
                  f"la pulizia dei CSV obsoleti e' sospesa. Verificare la sessione con "
                  f"--fetch-check e, se manca, eseguire --fetch-login {canonical}.",
                  file=sys.stderr)

    if not zlist:
        print(f"[i] nessuno zip (cerco in {ZIP_DIR}): uso i CSV gia' presenti in {dest}",
              file=sys.stderr)
        warn_unrefreshed(())
        return {}

    latest = {}  # user.casefold() -> (zip path, canonical user, how, mtime)

    # Risolvi prima i proprietari, poi scegli un solo archivio (il piu' recente) per utente.
    # Questo evita che un vecchio ZIP reintroduca CSV di playlist cancellate/rinominate.
    for zp in zlist:
        try:
            with zipfile.ZipFile(zp) as z:
                infos = _zip_csvs(z)
                if not infos or not _looks_like_exportify(z, infos):
                    print(f"[i] {zp.name}: non e' un export Exportify, ignorato", file=sys.stderr)
                    continue
                user, how = resolve_zip_user(zp, z, infos, users)
                if not user:
                    print(f"[ERRORE] {zp.name}: utente Navidrome non determinato - {how}",
                          file=sys.stderr)
                    continue
                if wanted is not None and user.lower() not in wanted:
                    print(f"[i] {zp.name} -> {user}: utente non selezionato, saltato",
                          file=sys.stderr)
                    continue
                fresh = _FETCH_SUCCEEDED_USERS.get(user.casefold())
                if fresh and _normal_path(zp) != _normal_path(fresh[1]):
                    print(f"[i] {zp.name}: ignorato per {user}: fetch riuscito in questa run; "
                          f"uso solo lo ZIP fresco {fresh[1].name} (non gli altri ZIP in {ZIP_DIR})",
                          file=sys.stderr)
                    continue
                mtime = zp.stat().st_mtime
                key = user.casefold()
                prior = latest.get(key)
                if prior is None or mtime >= prior[3]:
                    if prior is not None:
                        print(f"[i] {prior[0].name}: archivio piu' vecchio per {user}; "
                              f"vince {zp.name}", file=sys.stderr)
                    latest[key] = (zp, user, how, mtime)
                else:
                    print(f"[i] {zp.name}: archivio piu' vecchio per {user}; "
                          f"uso {prior[0].name}", file=sys.stderr)
        except (zipfile.BadZipFile, zlib.error, RuntimeError, ValueError) as e:
            print(f"[ERRORE] {zp.name}: zip non valido o illeggibile: {e}", file=sys.stderr)
        except OSError as e:
            print(f"[ERRORE] impossibile leggere {zp.name}: {e}", file=sys.stderr)

    extracted = {}  # utente -> nomi dei CSV estratti dal solo ZIP vincente
    metadata_by_user = {}
    for zp, user, how, _mtime in sorted(latest.values(), key=lambda item: item[3]):
        try:
            with zipfile.ZipFile(zp) as z:
                infos = _zip_csvs(z)
                if not infos or not _looks_like_exportify(z, infos):
                    # ZIP sostituito/corrotto tra la pre-analisi e la lettura: non pulire la cartella.
                    print(f"[ERRORE] {zp.name}: export Exportify non piu' valido; CSV esistenti lasciati intatti",
                          file=sys.stderr)
                    continue
                udir = dest / user
                udir.mkdir(parents=True, exist_ok=True)

                # Estrai prima in una cartella temporanea sullo stesso filesystem. Se ZIP/CRC
                # o scrittura falliscono, i CSV gia' attivi restano intatti e la pulizia non parte.
                staged_names = set()
                with tempfile.TemporaryDirectory(prefix='.exportify-stage-', dir=str(udir)) as stage:
                    stage_dir = Path(stage)
                    staged_files = {}
                    for info in infos:
                        basename = Path(info.filename).name
                        if basename in staged_names:
                            raise ValueError(f"basename CSV duplicato nell'archivio: {basename}")
                        staged_names.add(basename)
                        staged_path = stage_dir / basename
                        with z.open(info) as source, staged_path.open('wb') as target:
                            shutil.copyfileobj(source, target)
                        staged_files[basename] = staged_path
                    for basename, staged_path in staged_files.items():
                        os.replace(staged_path, udir / basename)

                # Accoppia i CSV ai nomi/cover originali salvati da --fetch. Per ZIP manuali
                # senza metadati si rimuove la voce relativa ai CSV rimpiazzati, mai si riusa
                # accidentalmente una cover vecchia per un file dal nome uguale.
                meta_file = udir / '.playlist_meta.json'
                try:
                    existing_meta = json.loads(meta_file.read_text(encoding='utf-8'))
                    meta_map = dict(existing_meta.get('playlists', {}))
                except (OSError, ValueError, AttributeError, TypeError):
                    meta_map = {}
                try:
                    archive_meta = json.loads(_archive_meta_path(zp).read_text(encoding='utf-8'))
                    archive_map = archive_meta.get('playlists', {})
                    if not isinstance(archive_map, dict):
                        archive_map = {}
                except (OSError, ValueError, AttributeError, TypeError):
                    archive_map = {}

                current_names = set(staged_files)
                for basename in staged_files:
                    record = archive_map.get(basename)
                    if isinstance(record, dict) and isinstance(record.get('name'), str):
                        meta_map[basename] = record
                    else:
                        meta_map.pop(basename, None)
                metadata_by_user[user] = meta_map

                extracted[user] = current_names
                fresh = _FETCH_SUCCEEDED_USERS.get(user.casefold())
                if fresh and _normal_path(zp) == _normal_path(fresh[1]):
                    _FRESH_EXTRACTED_USERS.add(user.casefold())
                    print(f"[i] {user}: fetch fresco confermato; gli altri ZIP dello stesso utente "
                          f"in {ZIP_DIR} sono esclusi da questa sync", file=sys.stderr)
                age = time.time() - zp.stat().st_mtime
                print(f"[i] estratti {len(infos)} CSV da {zp.name} -> {udir} "
                      f"(utente {user}, da {how}; ZIP di {_age_txt(age)} fa)", file=sys.stderr)
                if warn_stale and age > ZIP_STALE_DAYS * 86400:
                    print(f"[!] {zp.name}: zip vecchio di {_age_txt(age)}: --fetch non lo sta "
                          f"aggiornando (sessione scaduta? interfaccia cambiata?). Controllare con "
                          f"--fetch-check e i log", file=sys.stderr)
        except (zipfile.BadZipFile, zlib.error, RuntimeError, ValueError) as e:
            print(f"[ERRORE] impossibile estrarre {zp.name}: {e}; CSV esistenti lasciati intatti",
                  file=sys.stderr)
        except OSError as e:
            print(f"[ERRORE] impossibile estrarre {zp.name}: {e}; CSV esistenti lasciati intatti",
                  file=sys.stderr)

    # Per ogni utente estratto con successo, rimuovi CSV e metadati non piu' presenti nell'ultimo ZIP.
    for user, names in extracted.items():
        user_dir = dest / user
        stale = [f for f in _csv_files(user_dir, recursive=True)
                 if f.parent != user_dir or f.name not in names]
        removed = []
        for f in stale:
            try:
                f.unlink()
                removed.append(f)
            except OSError as e:
                print(f"[warn] {user}: CSV obsoleto non rimosso ({f.name}): {e}", file=sys.stderr)
        if removed:
            shown = ', '.join(f.stem for f in removed[:8]) + (' ...' if len(removed) > 8 else '')
            print(f"[i] {user}: rimossi {len(removed)} CSV non piu' presenti nell'ultimo ZIP: {shown}",
                  file=sys.stderr)
        meta_file = user_dir / '.playlist_meta.json'
        mapped = {name: rec for name, rec in metadata_by_user.get(user, {}).items()
                  if name in names}
        try:
            if mapped:
                _write_json_atomic(meta_file, {'version': 1, 'playlists': mapped},
                                   ensure_ascii=False, indent=2)
            else:
                meta_file.unlink(missing_ok=True)
        except OSError as e:
            print(f"[warn] metadati playlist non salvati per {user}: {e}", file=sys.stderr)
    warn_unrefreshed(extracted.keys())
    return extracted


# ===================== fase: download degli zip da Exportify (Playwright) =====================
# Playwright e' un import PIGRO: serve solo a --fetch / --fetch-login / --fetch-list.

EXF_URL = os.environ.get('EXPORTIFY_URL', 'https://exportify.app/')
EXF_STATE_DIR = Path(os.environ.get('EXPORTIFY_STATE_DIR')
                     or Path(__file__).resolve().parent / '.exportify_sessions')
# pulsanti cercati per testo (inglese + italiano)
EXF_RX_EXPORT_ALL = re.compile(r'export\s*all|esporta\s*tutt', re.I)
EXF_RX_START = re.compile(r'get\s*started|log\s*in|inizia|accedi', re.I)
EXF_RX_AGREE = re.compile(r'^\s*(agree|accept|accetto|accetta|consenti)\s*$', re.I)
# nuovo zip con meno della meta' dei CSV dell'ultimo buono = sospetto (rate limiting)
EXF_SUSPECT_RATIO = 0.5
EXF_COOKIE_DIR = Path(__file__).resolve().parent / 'spotify_cookies'   # dove cercare i cookie esportati
EXF_EXPIRY_WARN_DAYS = 14        # avviso se il cookie di login scade entro questi giorni
ZIP_STALE_DAYS = 3               # con --fetch: avviso se uno zip e' piu' vecchio di cosi'


class ExfSessionExpired(Exception):
    pass


def _exf_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("manca playwright: .venv/bin/pip install playwright && "
                           ".venv/bin/playwright install chromium")
    return sync_playwright


def _exf_safe(user):
    return re.sub(r'[\\/:*?"<>|]', '_', user)


def _exf_state_path(user):
    return EXF_STATE_DIR / f'{_exf_safe(user)}.json'


def _exf_btn(page, rx):
    return page.get_by_role('button', name=rx).or_(page.get_by_role('link', name=rx)).first


def _exf_visible(loc):
    try:
        return loc.is_visible()
    except Exception:
        return False


def _exf_on_spotify(page):
    return 'accounts.spotify.com' in page.url


def _exf_logged_out(page):
    if not _exf_on_spotify(page):
        return False
    return '/login' in page.url or _exf_visible(
        page.locator('input[type="password"], #login-username, input[name="username"]').first)


def _exf_reach_export_page(page, url, timeout_s=120):
    """Porta la pagina a 'lista playlist con Export All'; ExfSessionExpired se Spotify
    chiede il login."""
    page.goto(url, wait_until='domcontentloaded')
    start_clicked = False
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if not _exf_on_spotify(page) and _exf_visible(_exf_btn(page, EXF_RX_EXPORT_ALL)):
            return
        if _exf_logged_out(page):
            raise ExfSessionExpired()
        if _exf_on_spotify(page):
            agree = _exf_btn(page, EXF_RX_AGREE)
            if _exf_visible(agree):                  # schermata di consenso, se ricompare
                agree.click()
                page.wait_for_timeout(1000)
                continue
        elif not start_clicked and _exf_visible(_exf_btn(page, EXF_RX_START)):
            _exf_btn(page, EXF_RX_START).click()
            start_clicked = True
        page.wait_for_timeout(500)
    raise RuntimeError(f"il pulsante 'Export All' non e' comparso entro {timeout_s}s "
                       f"(url attuale: {page.url})")


def _exf_count_csv(path):
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"file corrotto nello zip: {bad}")
        return len(_zip_csvs(z))


def _exf_save_state(ctx, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name(path.name + '.tmp')
    ctx.storage_state(path=str(tmp))
    os.chmod(tmp, 0o600)                              # contiene i cookie di Spotify
    os.replace(tmp, path)


def _exf_debug_dump(page, user):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        base = LOG_DIR / f"fetch_{_exf_safe(user)}_{datetime.now():%Y%m%d_%H%M%S}"
        page.screenshot(path=str(base.with_suffix('.png')), full_page=True)
        base.with_suffix('.html').write_text(page.content(), encoding='utf-8')
        print(f"[{user}]   diagnostica: {base}.png / .html", file=sys.stderr)
    except Exception as e:
        print(f"[{user}]   (diagnostica non salvata: {e})", file=sys.stderr)


_EXF_LAUNCH_ARGS = ['--disable-blink-features=AutomationControlled']


def _exf_launch(pw, headless, prefer_chrome=False):
    """Chromium senza i segnali di automazione piu' evidenti. prefer_chrome: prova prima il
    Google Chrome installato (riconosciuto meno spesso come bot), poi ripiega su Chromium."""
    kw = dict(headless=headless, args=_EXF_LAUNCH_ARGS, ignore_default_args=['--enable-automation'])
    if prefer_chrome:
        try:
            return pw.chromium.launch(channel='chrome', **kw)
        except Exception:
            pass
    return pw.chromium.launch(**kw)


def _exf_context(browser, state=None, headed=False):
    kw = dict(accept_downloads=True, locale='en-US')
    if state:
        kw['storage_state'] = str(state)
    if not headed:                      # in headless lo user-agent dice 'HeadlessChrome': lo correggo
        kw['user_agent'] = (f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                            f"Chrome/{browser.version} Safari/537.36")
    ctx = browser.new_context(**kw)
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    return ctx


_EXF_SAMESITE = {'strict': 'Strict', 'lax': 'Lax', 'no_restriction': 'None', 'none': 'None'}


def _exf_parse_cookies(text):
    """Cookie esportati da un browser normale -> lista di cookie Playwright (solo *.spotify.com).
    Formati: JSON (Cookie-Editor / EditThisCookie / storage_state di Playwright) oppure
    Netscape cookies.txt. ValueError/KeyError se il formato non e' riconosciuto."""
    text = text.strip().lstrip('\ufeff')
    raw = []
    if text[:1] in '[{':
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get('cookies', [])
        for c in data:
            if not isinstance(c, dict):
                raise TypeError('voce di cookie non valida')
            raw.append(dict(name=str(c['name']), value=str(c['value']),
                            domain=str(c.get('domain') or c.get('host') or ''),
                            path=str(c.get('path') or '/'),
                            expires=c.get('expirationDate', c.get('expires', -1)),
                            secure=bool(c.get('secure')), httpOnly=bool(c.get('httpOnly')),
                            sameSite=c.get('sameSite')))
    else:
        for line in text.splitlines():
            line = line.strip()
            http_only = line.startswith('#HttpOnly_')
            if http_only:
                line = line[len('#HttpOnly_'):]
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 7:
                continue
            dom, _, path, secure, exp, name, value = parts[:7]
            raw.append(dict(name=name, value=value, domain=dom, path=path,
                            expires=int(exp) if exp.isdigit() else -1,
                            secure=secure.upper() == 'TRUE', httpOnly=http_only, sameSite=None))
    if not raw:
        raise ValueError("nessun cookie riconosciuto nel file")
    out = []
    for c in raw:
        d = (c['domain'] or '').strip().lower().lstrip('.')
        if d != 'spotify.com' and not d.endswith('.spotify.com'):
            continue
        try:
            exp = float(c['expires']) if c['expires'] is not None else -1.0
        except (TypeError, ValueError):
            exp = -1.0
        same = _EXF_SAMESITE.get(str(c['sameSite']).lower(), 'Lax')
        if same == 'None' and not c['secure']:
            same = 'Lax'                              # SameSite=None richiede Secure
        out.append({'name': c['name'], 'value': c['value'], 'domain': c['domain'].strip(),
                    'path': c['path'], 'expires': exp if exp > 0 else -1, 'httpOnly': c['httpOnly'],
                    'secure': c['secure'], 'sameSite': same})
    return out


def _exf_check(user):
    """Apre Exportify in headless con la sessione salvata di `user`: True se arriva alla lista
    delle playlist (e rinnova il file di sessione), False se Spotify chiede il login."""
    sync_playwright = _exf_playwright()
    with sync_playwright() as pw:
        browser = _exf_launch(pw, headless=True)
        try:
            ctx = _exf_context(browser, _exf_state_path(user))
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            try:
                _exf_reach_export_page(page, EXF_URL, 90)
            except ExfSessionExpired:
                return False
            _exf_save_state(ctx, _exf_state_path(user))
            return True
        finally:
            browser.close()


def _age_txt(seconds):
    if seconds < 3600:
        return f"{max(int(seconds // 60), 0)} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} ore"
    return f"{seconds / 86400:.1f} giorni"


def _exf_find_cookie_file(spec, user):
    """File dei cookie esportati. spec = percorso o nome dato a --fetch-cookies ('auto' = nessun
    nome: il file piu' recente in spotify_cookies/ il cui nome inizia con l'utente). Cerca nel
    percorso dato, poi in spotify_cookies/ accanto allo script e nella cartella corrente;
    senza estensione prova anche .json e .txt. -> Path oppure None."""
    dirs = [EXF_COOKIE_DIR, Path.cwd() / 'spotify_cookies']
    if spec and spec != 'auto':
        p = Path(spec).expanduser()
        cands = [p] + [d / p.name for d in dirs]
        if not p.suffix:
            cands += [c.with_name(c.name + ext) for c in list(cands) for ext in ('.json', '.txt')]
        return next((c for c in cands if c.is_file()), None)
    found = [f for d in dirs if d.is_dir() for f in d.iterdir()
             if f.is_file() and f.suffix.lower() in ('.json', '.txt')
             and f.name.lower().startswith(user.lower())]
    return max(found, key=lambda f: f.stat().st_mtime) if found else None


def _exf_sp_dc_expiry(user):
    """Scadenza (epoch) del cookie di login sp_dc nella sessione salvata; None se e' un cookie
    di sessione o il file non si legge."""
    try:
        data = json.loads(_exf_state_path(user).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    exps = [c.get('expires', -1) for c in data.get('cookies', []) if c.get('name') == 'sp_dc']
    exps = [e for e in exps if isinstance(e, (int, float)) and e > 0]
    return min(exps) if exps else None


def _exf_expiry_txt(user):
    exp = _exf_sp_dc_expiry(user)
    if exp is None:
        return "scadenza del cookie di login sconosciuta"
    days = (exp - time.time()) / 86400
    return (f"cookie di login (sp_dc) scade tra {days:.0f} giorni" if days >= 0
            else "cookie di login (sp_dc) GIA' SCADUTO")


def _exf_import_cookies(user, path):
    try:
        text = path.read_text(encoding='utf-8')
    except OSError as e:
        print(f"[ERRORE] impossibile leggere {path}: {e}", file=sys.stderr)
        return 1
    try:
        cookies = _exf_parse_cookies(text)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"[ERRORE] formato cookie non riconosciuto ({type(e).__name__}: {e}): serve JSON "
              f"(Cookie-Editor) o cookies.txt Netscape", file=sys.stderr)
        return 1
    if not any(c['name'] == 'sp_dc' for c in cookies):
        print(f"[ERRORE] nel file ci sono {len(cookies)} cookie di spotify.com ma manca 'sp_dc' (il "
              f"cookie di login): esportare da open.spotify.com DOPO aver fatto il login",
              file=sys.stderr)
        return 1
    st = _exf_state_path(user)
    st.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(st.parent, 0o700)
    except OSError:
        pass
    tmp = st.with_name(st.name + '.tmp')
    tmp.write_text(json.dumps({'cookies': cookies, 'origins': []}), encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, st)
    print(f"[{user}] importati {len(cookies)} cookie di spotify.com in {st}")
    print(f"[{user}] verifico la sessione (headless)...", flush=True)
    try:
        ok = _exf_check(user)
    except Exception as e:
        print(f"[ERRORE] verifica non riuscita: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if ok:
        print(f"[{user}] sessione valida ({_exf_expiry_txt(user)}): si puo' usare --fetch")
        print(f"[{user}] promemoria: {path} contiene la tua sessione Spotify, cancellalo ora che e' "
              f"importato")
        return 0
    print(f"[{user}] [ERRORE] Spotify non riconosce la sessione: cookie scaduti, logout fatto nel "
          f"browser dopo l'export, o verifica aggiuntiva richiesta. Rifare l'export "
          f"(finestra privata, senza logout).", file=sys.stderr)
    return 1


def _exf_fetch_user(pw, user, out_dir, headed, timeout_min):
    """Scarica lo zip di UN utente -> n. di CSV. Solleva ExfSessionExpired / eccezioni."""
    state = _exf_state_path(user)
    browser = _exf_launch(pw, headless=not headed)
    try:
        ctx = _exf_context(browser, state, headed=headed)
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        playlist_records = {}

        def capture_playlist_response(response):
            # La lista Spotify contiene i nomi originali e images[].url. Evita le risposte
            # /tracks, che possono essere molto grandi e non contengono metadati playlist utili.
            try:
                url = response.url.lower()
                if 'playlist' not in url or '/tracks' in url or response.status >= 400:
                    return
                content_type = response.headers.get('content-type', '').lower()
                if 'json' not in content_type:
                    return
                for record in _spotify_playlist_records(response.json()):
                    old_record = playlist_records.get(record['id'])
                    if old_record is None or (not old_record.get('image_url') and record.get('image_url')):
                        playlist_records[record['id']] = record
            except Exception:
                # La cattura metadata e' accessoria: non deve interrompere il download dei CSV.
                pass

        page.on('response', capture_playlist_response)
        try:
            _exf_reach_export_page(page, EXF_URL)
            print(f"[{user}] avvio 'Export All' (puo' richiedere diversi minuti)...", flush=True)
            with page.expect_download(timeout=timeout_min * 60_000) as dl:
                _exf_btn(page, EXF_RX_EXPORT_ALL).click()
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f'.{_exf_safe(user)}.download.part'   # non finisce mai in *.zip
            dl.value.save_as(str(tmp))
            try:
                n = _exf_count_csv(tmp)
                if n == 0:
                    raise ValueError("lo zip scaricato non contiene CSV")
                dest = out_dir / f'{_exf_safe(user)}_spotify_playlists.zip'
                old = 0
                if dest.exists():
                    try:
                        old = _exf_count_csv(dest)
                    except (zipfile.BadZipFile, ValueError, OSError):
                        old = 0
                if old and n < old * EXF_SUSPECT_RATIO:
                    keep = dest.with_name(dest.name + '.suspect')
                    os.replace(tmp, keep)
                    raise RuntimeError(f"zip sospetto: {n} CSV contro i {old} dell'ultimo buono "
                                       f"(export interrotto?). Tenuto quello vecchio; il nuovo "
                                       f"e' in {keep.name}")
                os.replace(tmp, dest)
            finally:
                tmp.unlink(missing_ok=True)

            records = list(playlist_records.values())
            if records:
                mapped_meta = _map_playlist_metadata_to_zip(dest, records)
                if mapped_meta:
                    meta_payload = {
                        'version': 1,
                        'user': user,
                        'captured_at': datetime.now().isoformat(timespec='seconds'),
                        'playlists': mapped_meta,
                    }
                    _write_json_atomic(_archive_meta_path(dest), meta_payload,
                                       ensure_ascii=False, indent=2)
                    print(f"[{user}] metadati Spotify: {len(mapped_meta)}/{n} CSV collegati "
                          f"a nome originale e cover", flush=True)
                else:
                    print(f"[{user}] [warn] ricevute {len(records)} playlist da Spotify ma "
                          f"nessuna corrispondenza affidabile con i nomi CSV; nomi/cover non "
                          f"saranno sovrascritti da questa cattura", file=sys.stderr)
            else:
                print(f"[{user}] [warn] Exportify non ha esposto metadati playlist nelle risposte "
                      f"osservate; i CSV verranno importati col nome disponibile nel filename e "
                      f"senza cover Spotify", file=sys.stderr)
            _exf_save_state(ctx, state)              # rinnova i cookie per la prossima volta
            print(f"[{user}] OK: {n} CSV -> {dest}", flush=True)
            return n
        except ExfSessionExpired:
            raise
        except Exception:
            _exf_debug_dump(page, user)
            raise
    finally:
        browser.close()


def run_fetch(sel=None, headed=False, timeout_min=30):
    """Scarica gli zip Exportify degli utenti con una sessione salvata (sel=None: tutti).

    Gli utenti configurati in FETCH_IGNORED_USERS vengono esclusi dal fetch, anche se una
    sessione esiste o sono passati esplicitamente in --users. Registra i percorsi effettivamente
    scaricati per impedire che ZIP vecchi nella cartella spotify_csv diventino la fonte dati.
    Codice: 0 ok | 1 errori | 2 almeno una sessione scaduta.
    """
    global _FETCH_SUCCEEDED_USERS
    _FETCH_SUCCEEDED_USERS = {}
    sessions = ({p.stem: p for p in sorted(EXF_STATE_DIR.glob('*.json'))}
                if EXF_STATE_DIR.is_dir() else {})
    low = {k.lower(): k for k in sessions}
    ignored = {str(x).strip().casefold() for x in FETCH_IGNORED_USERS if str(x).strip()}
    known = known_users()

    if sel is None:
        ignored_in_scope = []
        for configured_name in sorted({str(x).strip() for x in FETCH_IGNORED_USERS if str(x).strip()},
                                      key=str.casefold):
            ignored_in_scope.append(next((u for u in known if u.casefold() == configured_name.casefold()),
                                         configured_name))
    else:
        ignored_in_scope = [u for u in sel if u.casefold() in ignored]
    for u in ignored_in_scope:
        print(f"[{u}] [i] fetch saltato: presente in FETCH_IGNORED_USERS", file=sys.stderr,
              flush=True)

    if sel is None:
        # Un account senza sessione non deve sembrare aggiornato; gli esclusi sono intenzionali.
        for expected in known:
            if expected.casefold() in ignored:
                continue
            if expected.casefold() not in low:
                print(f"[{expected}] [WARN] nessuna sessione Exportify salvata: ZIP non aggiornato; "
                      f"eseguire --fetch-login {expected}. CSV/ZIP preesistenti non verranno "
                      f"considerati un export fresco.", file=sys.stderr, flush=True)
        users = [u for u in sessions if u.casefold() not in ignored]
        if not users and not sessions:
            print(f"[ERRORE] nessuna sessione in {EXF_STATE_DIR}: eseguire prima "
                  f"--fetch-login UTENTE", file=sys.stderr)
            return 1
    else:
        users = []
        missing_session = False
        for u in sel:
            if u.casefold() in ignored:
                continue
            if u.lower() in low:
                users.append(low[u.lower()])
            else:
                missing_session = True
                print(f"[{u}] [ERRORE] nessuna sessione salvata: eseguire prima "
                      f"--fetch-login {u}", file=sys.stderr)
        if not users:
            # Una selezione costituita esclusivamente da utenti volutamente ignorati e' un no-op ok.
            return 1 if missing_session else 0

    if not users:
        # Tutte le sessioni trovate appartengono a utenti intenzionalmente esclusi.
        return 0

    sync_playwright = _exf_playwright()
    failed = expired = 0
    with sync_playwright() as pw:
        for user in users:
            exp = _exf_sp_dc_expiry(user)
            if exp is not None and exp - time.time() < EXF_EXPIRY_WARN_DAYS * 86400:
                print(f"[{user}] [!] {_exf_expiry_txt(user)}: rifare --fetch-login {user}",
                      file=sys.stderr)
            try:
                n = _exf_fetch_user(pw, user, ZIP_DIR, headed, timeout_min)
                fresh_zip = ZIP_DIR / f'{_exf_safe(user)}_spotify_playlists.zip'
                if not fresh_zip.is_file() or not n:
                    failed += 1
                    print(f"[{user}] [ERRORE] fetch segnalato come riuscito ma ZIP fresco assente/vuoto: "
                          f"{fresh_zip}", file=sys.stderr)
                    continue
                _FETCH_SUCCEEDED_USERS[user.casefold()] = (user, fresh_zip)
            except ExfSessionExpired:
                expired += 1
                print(f"[{user}] [ERRORE] sessione Spotify scaduta: rifare "
                      f"--fetch-login {user}", file=sys.stderr)
            except Exception as e:
                failed += 1
                print(f"[{user}] [ERRORE] {type(e).__name__}: {e}", file=sys.stderr)
    if _FETCH_SUCCEEDED_USERS:
        print("[i] fetch freschi registrati: " + ', '.join(
            f"{name} -> {path.name}" for name, path in _FETCH_SUCCEEDED_USERS.values()),
              file=sys.stderr, flush=True)
    return 2 if expired else (1 if failed else 0)

def _exf_wait_logged_in(page, url, timeout_s):
    page.goto(url, wait_until='domcontentloaded')
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if not _exf_on_spotify(page) and _exf_visible(_exf_btn(page, EXF_RX_EXPORT_ALL)):
            return True
        page.wait_for_timeout(1000)
    return False


_EXF_COOKIE_HINT = (
    "  Se Spotify mostra captcha impossibili o 'something went wrong', sta scambiando il browser\n"
    "  automatizzato per un bot. Alternativa: login nel TUO browser normale (meglio in una finestra\n"
    "  privata), esporta i cookie di spotify.com (estensione 'Cookie-Editor' -> Export -> JSON),\n"
    "  chiudi la finestra SENZA fare logout e importali con:\n"
    "      --fetch-login UTENTE --fetch-cookies FILE.json")


def run_fetch_login(user, wait_min=10, cookies=None):
    """Login una tantum: (a) con --fetch-cookies importa i cookie esportati da un browser normale;
    (b) altrimenti apre un browser VISIBILE, aspetta la lista delle playlist e salva la sessione.
    -> codice di uscita."""
    db = _db_users()
    if db:                                   # il nome diventa il prefisso dello zip: deve esistere
        u = canon_user(user, db)
        if not u:
            print(f"[ERRORE] '{user}' non e' un utente Navidrome (noti: {', '.join(db)})",
                  file=sys.stderr)
            return 1
        user = u
    if cookies:
        cf = _exf_find_cookie_file(cookies, user)
        if not cf:
            where = f"{EXF_COOKIE_DIR} e {Path.cwd() / 'spotify_cookies'}"
            what = (f"nessun file {user}*.json/.txt" if cookies == 'auto' else f"'{cookies}' non trovato")
            print(f"[ERRORE] {what} (cercato anche in {where})", file=sys.stderr)
            return 1
        print(f"[{user}] uso il file di cookie: {cf}")
        return _exf_import_cookies(user, cf)
    sync_playwright = _exf_playwright()
    pw_cm = sync_playwright().start()
    try:
        try:
            browser = _exf_launch(pw_cm, headless=False, prefer_chrome=True)
        except Exception as e:
            print(f"[ERRORE] impossibile aprire un browser visibile ({e}).\n"
                  f"  Senza schermo: usare --fetch-cookies (vedi sotto) oppure eseguire --fetch-login "
                  f"su un PC con Playwright e copiare {_exf_state_path(user)} sul server.\n"
                  f"{_EXF_COOKIE_HINT}", file=sys.stderr)
            return 1
        try:
            ctx = _exf_context(browser, None, headed=True)
            page = ctx.new_page()
            print(f"[{user}] nel browser: cliccare 'Get Started', accedere a Spotify e autorizzare "
                  f"Exportify.\n    Mi fermo da solo quando compare la lista playlist (max "
                  f"{wait_min} min).", flush=True)
            try:
                ok = _exf_wait_logged_in(page, EXF_URL, wait_min * 60)
            except Exception as e:
                if 'closed' not in str(e).lower():
                    raise
                print(f"[ERRORE] il browser e' stato chiuso prima della fine del login.\n"
                      f"{_EXF_COOKIE_HINT}", file=sys.stderr)
                return 1
            if not ok:
                print(f"[ERRORE] timeout: login non completato.\n{_EXF_COOKIE_HINT}", file=sys.stderr)
                return 1
            _exf_save_state(ctx, _exf_state_path(user))
            print(f"[{user}] sessione salvata in {_exf_state_path(user)}")
            return 0
        finally:
            try:
                browser.close()
            except Exception:
                pass
    finally:
        try:
            pw_cm.stop()
        except Exception:
            pass


def run_fetch_check(sel=None):
    """Verifica in headless che le sessioni salvate siano ancora valide (senza scaricare nulla).
    Codice: 0 tutte valide | 1 errori | 2 almeno una scaduta."""
    sessions = ({p.stem: p for p in sorted(EXF_STATE_DIR.glob('*.json'))}
                if EXF_STATE_DIR.is_dir() else {})
    low = {k.lower(): k for k in sessions}
    users = [low[u.lower()] for u in sel if u.lower() in low] if sel is not None else list(sessions)
    if sel is not None:
        for u in sel:
            if u.lower() not in low:
                print(f"[{u}] [ERRORE] nessuna sessione salvata: --fetch-login {u}", file=sys.stderr)
    if not users:
        print(f"[ERRORE] nessuna sessione da verificare in {EXF_STATE_DIR}", file=sys.stderr)
        return 1
    expired = failed = 0
    for user in users:
        try:
            if _exf_check(user):
                print(f"[{user}] sessione VALIDA ({_exf_expiry_txt(user)})")
            else:
                expired += 1
                print(f"[{user}] sessione SCADUTA: rifare --fetch-login {user}", file=sys.stderr)
        except Exception as e:
            failed += 1
            print(f"[{user}] [ERRORE] verifica non riuscita: {type(e).__name__}: {e}", file=sys.stderr)
    return 2 if expired else (1 if failed else 0)


def run_fetch_list():
    print(f"sessioni in {EXF_STATE_DIR}:")
    ss = sorted(EXF_STATE_DIR.glob('*.json')) if EXF_STATE_DIR.is_dir() else []
    for p in ss:
        print(f"  {p.stem:20s} salvata {_age_txt(time.time() - p.stat().st_mtime)} fa; "
              f"{_exf_expiry_txt(p.stem)}")
    if not ss:
        print("  (nessuna)")
    print(f"zip in {ZIP_DIR}:")
    zs = sorted(q for q in ZIP_DIR.glob('*.zip') if q.is_file()) if ZIP_DIR.is_dir() else []
    for z in zs:
        try:
            n = _exf_count_csv(z)
        except Exception:
            n = '?'
        age = time.time() - z.stat().st_mtime
        stale = "  <-- VECCHIO" if age > ZIP_STALE_DAYS * 86400 else ""
        print(f"  {z.name:45s} {n} CSV, {datetime.fromtimestamp(z.stat().st_mtime):%Y-%m-%d %H:%M} "
              f"({_age_txt(age)} fa){stale}")
    if not zs:
        print("  (nessuno)")


def _has_fetch_sessions():
    return EXF_STATE_DIR.is_dir() and any(EXF_STATE_DIR.glob('*.json'))


def _expand_all(args):
    """--all: accende tutte le fasi e, se esistono sessioni Exportify salvate (--fetch-login),
    anche il download degli zip (--fetch): un cron con solo --all --apply riscarica i CSV."""
    if args.fix_owners is None:
        args.fix_owners = ''
    args.dedupe_playlists = True
    args.dedupe_releases = True
    args.dedupe_tracks = True
    args.mp3_vs_flac = True
    args.fix_collab_artists = True
    args.flac_16bit = True
    args.clean_empty = True
    args.star_liked = True
    args.playlists = True
    if not args.fetch and _has_fetch_sessions():
        args.fetch = True
        print("[i] --all: trovate sessioni Exportify, scarico anche gli zip (come --fetch)",
              file=sys.stderr)


def _fetch_for_run(args, sel):
    """--fetch durante un'esecuzione normale: mai fatale (si usano gli zip gia' presenti)."""
    try:
        rc = run_phase('fetch_exportify', run_fetch, sel,
                       headed=getattr(args, 'fetch_headed', False),
                       timeout_min=getattr(args, 'fetch_timeout', 30))
        if rc is None:
            rc = 1
    except Exception as e:
        print(f"[ERRORE] --fetch: {type(e).__name__}: {e}", file=sys.stderr)
        rc = 1
    if rc:
        print("[i] --fetch non completato: uso gli zip gia' presenti", file=sys.stderr)


def collect_user_csvs(args, sel):
    """[(utente, [csv...])] dopo l'eventuale unzip, filtrato da --users."""
    if args.csv:                                   # CSV espliciti: appartengono a UN utente
        if sel is None:
            u = DEFAULT_USER
        elif len(sel) == 1:
            u = sel[0]
        else:
            sys.exit("[ERRORE] con CSV espliciti serve UN solo utente in --users")
        return [(u, [Path(p) for p in args.csv])]
    if not args.no_unzip:
        if getattr(args, 'fetch', False) and not getattr(args, 'dry_run', False):
            _fetch_for_run(args, sel)
        if args.clean:
            print("[i] --clean e' ridondante: i CSV obsoleti vengono rimossi dopo ogni estrazione riuscita",
                  file=sys.stderr)
        got = run_phase('unzip_and_prune_csv', unzip_exportify, args.zip, EXPORTIFY_DIR, sel,
                        warn_stale=getattr(args, 'fetch', False),
                        dry_run=getattr(args, 'dry_run', False)) or {}
    else:
        got = {}
    known = known_users()
    wanted = {u.lower() for u in sel} if sel is not None else None
    groups = []
    if EXPORTIFY_DIR.is_dir():
        for d in sorted(p for p in EXPORTIFY_DIR.iterdir() if p.is_dir()):
            u = canon_user(d.name, known)
            if not u:
                print(f"[i] {d}: non e' un utente Navidrome, ignorata", file=sys.stderr)
                continue
            if wanted is not None and u.lower() not in wanted:
                continue
            fs = _csv_files(d)
            if fs:
                groups.append((u, fs))
        legacy = _csv_files(EXPORTIFY_DIR)
        if legacy and got:
            # vecchio layout (CSV piatti nella radice): non servono piu' e non combaciano con
            # nessun export nuovo. Si cancellano solo dopo un'estrazione riuscita.
            for f in legacy:
                f.unlink()
            print(f"[i] rimossi {len(legacy)} CSV storici direttamente in {EXPORTIFY_DIR} "
                  f"(vecchio layout: ora i CSV stanno in <utente>/)", file=sys.stderr)
        elif legacy:
            print(f"[!] {len(legacy)} CSV storici direttamente in {EXPORTIFY_DIR} ignorati: ora i CSV "
                  f"stanno in <utente>/ (verranno cancellati alla prossima estrazione riuscita)",
                  file=sys.stderr)
    return groups


# Artista scritto diversamente tra Spotify e la tua libreria (es. romaji vs kanji).
# Chiave = nome come appare su Spotify, valore = nome della cartella/tag nella libreria.
ALIASES = {
    # "kaneyori masaru": "\u517c\u983c\u30de\u30b5\u30eb",
}

# Sottocartelle per le playlist: nome playlist (come nel file .csv) -> sottocartella.
# Esempio: {"19 chill": "chill", "canzoni blu": "colori"}. Le voci dal JSON
# sovrascrivono/integrano questa tabella: il cron rigenera SEMPRE nella cartella giusta.
PLAYLIST_FOLDERS = {}

# Playlist da escludere per utente Navidrome. Dal JSON: {"SKIP_PLAYLISTS": {"chic": [...], ...}}.
SKIP_PLAYLISTS = {}

# Penalita' per versioni alternative del brano. A parita' di titolo, una traccia
# con live/demo/instrumental/rehearsal nel titolo del file perde contro l'originale.
# I valori possono essere regolati da exportify_names.json: TITLE_MATCH_PENALTIES.
TITLE_MATCH_PENALTIES = {
    'live': 18.0, 'demo': 22.0, 'instrumental': 18.0, 'rehearsal': 18.0,
    'practice': 16.0, 'rehersal': 18.0, 'outtake': 15.0, 'alternate': 15.0, 'alternative': 15.0,
    'karaoke': 20.0, 'remix': 14.0, 'mix': 9.0, 'cover': 16.0,
    'acoustic': 9.0, 'radio edit': 11.0, 'edit': 4.0, 'extended': 12.0,
    'version': 5.0, 'session': 8.0, 'take': 5.0, 'rough': 7.0,
    'remaster': 4.0, 'remastered': 4.0, 'deluxe': 4.0, 'anniversary': 3.0,
    'expanded': 4.0, 'bonus': 3.0, 'reissue': 4.0,
    # Chiave speciale: penalita' aggiuntiva per parentesi nel filename quando
    # il titolo richiesto e' pulito. Fa parte della stessa mappa configurabile.
    'parentheses': 5.0,
}

# Recupero artwork album alla fine della pipeline, ispirato a MusicBee "Update Missing Artwork".
# L'artwork locale/embedded viene preservato; vengono scaricate solo immagini con match album+artista.
MISSING_ARTWORK_CONFIG = {
    'enabled': True,
    'max_per_run': 100,          # 0 = senza limite; evita che un primo recupero duri ore
    'request_timeout': 15,
    'retry_days': 30,            # cache negativa per evitare query ripetute senza risultati
    'min_image_bytes': 2048,
    'max_image_bytes': 12582912, # 12 MiB per immagine
    'check_embedded_art': True,
    'scan_after_download': True,
    'cover_basename': 'cover',
}

# Proxy MP3 per Spotify Local Files: converte SOLO gli album esplicitamente configurati.
# Output fuori da MUSIC_ROOT: Spotify li legge, ma Navidrome continua a usare i FLAC originali.
SPOTIFY_LOCAL_PROXY_CONFIG = {
    'enabled': True,
    'output_dir': '~/Music/Spotify Local Files',
    'bitrate': '64k',
    'market': 'IT',
    'catalog_cache_days': 90,
    'favorites_user': '',  # vuoto = ND_USER/SUBSONIC_USER; puo' essere sovrascritto nel JSON
    'albums': [],  # [{"artist": "Nome artista", "album": "Nome album"}]
    'auto_albums': [],  # riempito da --sync-spotify-proxy-config; non sovrascrive albums manuale
}

AUTO_NAME_TRANSLATION_CONFIG = {
    'enabled': True,
    'min_confidence': 0.72,
    'max_new_per_run': 100,
    'cache_days': 365,
    'timeout': 8,
    'failure_cooldown_hours': 6,
}
AUTO_NAME_TRANSLATION_CACHE = None
AUTO_NAME_TRANSLATION_NEW = 0
_AUTO_TRANSLATION_CACHE_DIRTY = False

# Parole che stanno al posto di un'emoji nel titolo Spotify ("FLAME EMOJI!" -> "🔥").
# Valgono per artisti E titoli, su entrambi i lati del matching. Estendibile via JSON.
EMOJI_WORDS = {
    'flame emoji': '🔥',
    '100 emoji': '💯',
}

# Nomi multipli dello STESSO artista (aka, cambi di nome, errori di spelling ricorrenti).
# Ogni gruppo viene trattato come un artista solo, in ENTRAMBE le direzioni e su
# ENTRAMBI i lati (libreria e Spotify). Scrivi tutto minuscolo, senza punteggiatura.
ARTIST_GROUPS = []

# Artist-tag splitting is inferred from delimiter syntax and catalog evidence.
# Do not add per-collaboration exceptions here: malformed joined artist tags are open-ended.

# Etichetta stabile per alias che differiscono soltanto per punteggiatura.
ARTIST_CANONICAL_ALIASES = {'m o o n': 'M.O.O.N'}

# Override per-riga dei CSV, applicati DOPO l'unzip (sopravvivono alle
# ri-esportazioni dello zip Exportify). Struttura:
#   "CSV_FIX": { "<playlist>": { "<artista> - <titolo>": {"album": "...", "artist": "..."} } }
# Valori assenti restano invariati. Serve quando una riga del CSV indica
# una versione che non vuoi (es. cover 2002 vs originale 1981: correggi
# l'album e il matcher prende quella giusta).
CSV_FIX = {}

# Pin per-album: override dei valori maggioritari di album_unify, per quando
# la maggioranza dei tag e' semplicemente sbagliata (es. ALONE: spotyFLAC ha
# scritto DATE=2013 su abbastanza file da vincere il voto e azzerare ogni
# correzione manuale). Chiave = "cartella artista / cartella album" (come
# nelle righe UNIFY del log), valori = campi da forzare.
UNIFY_FORCE = {}

# Override per-singolo brano: quando una query (artista - titolo) deve
# puntare a una versione specifica che i metadati non distinguono (es. il
# cover dei Rainbow Goblins vs l'originale di Takanaka: stesso artista
# richiesto? no — artista diverso da quello della cartella giusta).
# Chiave = "artista - titolo" normalizzato, valore = artista da cercare al
# posto di quello della riga (il nome mostrato in playlist resta invariato).
FORCE_ARTIST = {}

NAME_TRANSLATIONS = {}  # traduzioni/nomi inglesi ufficiali; hanno priorita su NAME_FIXES e pykakasi

NAME_FIXES = {
    # letture che pykakasi sbaglia — valgono per artisti E titoli (chiave = stringa normalizzata)
    '高中正義': 'masayoshi takanaka',
}

# --- configurazione utente esterna: exportify_names.json accanto allo script ---
# Contiene le TUE tabelle (NAME_TRANSLATIONS, NAME_FIXES, ALIASES, ARTIST_GROUPS): modifica quello,
# non questo file — sopravvive agli aggiornamenti dello script.
_USER_CFG = Path(__file__).with_name('exportify_names.json')


def _preload_terminal_colors():
    """Load only the palette before the first banner/phase is printed.

    The full user configuration still loads as the first measured pipeline phase. This
    lightweight pre-read ensures the startup [i] lines and load_user_config phase heading
    already honor the palette selected in JSON. Invalid JSON/palette errors are left for
    load_user_config to report through the normal phase/error path.
    """
    try:
        raw = json.loads(_USER_CFG.read_text(encoding='utf-8'))
        if isinstance(raw, dict):
            _apply_terminal_colors_config(raw.get('TERMINAL_COLORS'))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return False
    return True


def load_user_config():
    if not _USER_CFG.exists():
        return
    try:
        _cfg = json.loads(_USER_CFG.read_text(encoding='utf-8'))
        _apply_terminal_colors_config(_cfg.get('TERMINAL_COLORS'))
        if 'ARTIST_SPLIT_OVERRIDES' in _cfg:
            print("[warn] ARTIST_SPLIT_OVERRIDES e\' legacy e viene ignorato: lo split usa separatori, "
                  'catalogo e cartella-artista; puoi rimuovere il campo da exportify_names.json',
                  file=sys.stderr)
        # EMOJI_WORDS PRIMA di tutto: norm() lo usa per normalizzare le chiavi
        # delle tabelle qui sotto (prima veniva applicato dopo)
        EMOJI_WORDS.update(_cfg.get('EMOJI_WORDS', {}))
        # norm() dipende da EMOJI_WORDS: invalida qualsiasi risultato calcolato prima
        # del caricamento (la cache viene definita piu' sotto nel file, quindi controlla).
        if 'norm' in globals():
            norm.cache_clear()
            norm_bare.cache_clear()
        if '_artist_context_from_parent' in globals():
            globals()['_artist_context_from_parent'].cache_clear()
        translations_cfg = _cfg.get('NAME_TRANSLATIONS', {})
        if not isinstance(translations_cfg, dict):
            raise ValueError('NAME_TRANSLATIONS deve essere un oggetto JSON {testo_originale: traduzione_inglese}')
        NAME_TRANSLATIONS.update({norm(k): str(v).strip() for k, v in translations_cfg.items()
                                  if norm(k) and str(v).strip()})
        name_fixes_cfg = _cfg.get('NAME_FIXES', {})
        if not isinstance(name_fixes_cfg, dict):
            raise ValueError('NAME_FIXES deve essere un oggetto JSON {alias_originale: alias_preferito}')
        NAME_FIXES.update({norm(k): str(v).strip() for k, v in name_fixes_cfg.items()
                            if norm(k) and str(v).strip()})
        FORCE_ARTIST.update({norm(k): norm(v) for k, v in _cfg.get('FORCE_ARTIST', {}).items()})
        for pl, rows in _cfg.get('CSV_FIX', {}).items():
            CSV_FIX[norm(pl)] = {norm(k): v for k, v in rows.items()}
        UNIFY_FORCE.update({norm(k): v for k, v in _cfg.get('UNIFY_FORCE', {}).items()})
        ALIASES.update({norm(k): norm(v) for k, v in _cfg.get('ALIASES', {}).items()})
        SPOTIFY_USERS.update({str(k): str(v) for k, v in _cfg.get('SPOTIFY_USERS', {}).items()})
        FETCH_IGNORED_USERS.update(
            str(u).strip().casefold() for u in _cfg.get('FETCH_IGNORED_USERS', [])
            if str(u).strip()
        )
        for phrase, weight in _cfg.get('TITLE_MATCH_PENALTIES', {}).items():
            try:
                TITLE_MATCH_PENALTIES[norm_bare(phrase)] = max(0.0, float(weight))
            except (TypeError, ValueError):
                raise ValueError(f"TITLE_MATCH_PENALTIES: valore non numerico per {phrase!r}")
        # Compatibilita' con JSON v5.1: importa la vecchia impostazione separata
        # nella mappa unica, ma il campo legacy non viene piu' scritto nei nuovi JSON.
        if ('TITLE_MATCH_PARENTHESES_PENALTY' in _cfg and
                'parentheses' not in _cfg.get('TITLE_MATCH_PENALTIES', {})):
            try:
                TITLE_MATCH_PENALTIES['parentheses'] = max(
                    0.0, float(_cfg['TITLE_MATCH_PARENTHESES_PENALTY']))
            except (TypeError, ValueError):
                raise ValueError('TITLE_MATCH_PARENTHESES_PENALTY legacy deve essere numerico')
        artwork_cfg = _cfg.get('MISSING_ARTWORK', {})
        if artwork_cfg is not None:
            if not isinstance(artwork_cfg, dict):
                raise ValueError('MISSING_ARTWORK deve essere un oggetto JSON')
            for key in ('enabled', 'check_embedded_art', 'scan_after_download'):
                if key in artwork_cfg:
                    if not isinstance(artwork_cfg[key], bool):
                        raise ValueError(f'MISSING_ARTWORK.{key} deve essere booleano')
                    MISSING_ARTWORK_CONFIG[key] = artwork_cfg[key]
            for key in ('max_per_run', 'request_timeout', 'retry_days',
                        'min_image_bytes', 'max_image_bytes'):
                if key in artwork_cfg:
                    try:
                        value = int(artwork_cfg[key])
                    except (TypeError, ValueError):
                        raise ValueError(f'MISSING_ARTWORK.{key} deve essere intero')
                    if value < 0 or (key == 'request_timeout' and value == 0):
                        raise ValueError(f'MISSING_ARTWORK.{key} fuori intervallo')
                    MISSING_ARTWORK_CONFIG[key] = value
            if MISSING_ARTWORK_CONFIG['max_image_bytes'] <= MISSING_ARTWORK_CONFIG['min_image_bytes']:
                raise ValueError('MISSING_ARTWORK.max_image_bytes deve superare min_image_bytes')
            if 'cover_basename' in artwork_cfg:
                base = str(artwork_cfg['cover_basename']).strip()
                if (not base or Path(base).name != base or base in ('.', '..') or
                        not re.fullmatch(r'[A-Za-z0-9 _.-]+', base)):
                    raise ValueError('MISSING_ARTWORK.cover_basename deve essere un nome file semplice')
                MISSING_ARTWORK_CONFIG['cover_basename'] = base
        proxy_cfg = _cfg.get('SPOTIFY_LOCAL_PROXY', {})
        if proxy_cfg is not None:
            if not isinstance(proxy_cfg, dict):
                raise ValueError('SPOTIFY_LOCAL_PROXY deve essere un oggetto JSON')
            if 'enabled' in proxy_cfg:
                if not isinstance(proxy_cfg['enabled'], bool):
                    raise ValueError('SPOTIFY_LOCAL_PROXY.enabled deve essere booleano')
                SPOTIFY_LOCAL_PROXY_CONFIG['enabled'] = proxy_cfg['enabled']
            if 'output_dir' in proxy_cfg:
                output_dir = str(proxy_cfg['output_dir']).strip()
                if not output_dir:
                    raise ValueError("SPOTIFY_LOCAL_PROXY.output_dir non puo' essere vuoto")
                SPOTIFY_LOCAL_PROXY_CONFIG['output_dir'] = output_dir
            if 'bitrate' in proxy_cfg:
                bitrate = str(proxy_cfg['bitrate']).strip().lower()
                match = re.fullmatch(r'(\d{2,3})k', bitrate)
                if not match or not 64 <= int(match.group(1)) <= 320:
                    raise ValueError('SPOTIFY_LOCAL_PROXY.bitrate deve essere tra 64k e 320k')
                SPOTIFY_LOCAL_PROXY_CONFIG['bitrate'] = bitrate
            for field in ('albums', 'auto_albums'):
                if field in proxy_cfg:
                    albums = proxy_cfg[field]
                    if not isinstance(albums, list):
                        raise ValueError(f'SPOTIFY_LOCAL_PROXY.{field} deve essere una lista')
                    checked = []
                    for i, item in enumerate(albums, 1):
                        if not isinstance(item, dict):
                            raise ValueError(f'SPOTIFY_LOCAL_PROXY.{field}[{i}] deve contenere artist e album')
                        artist, album = str(item.get('artist', '')).strip(), str(item.get('album', '')).strip()
                        if not artist or not album:
                            raise ValueError(f'SPOTIFY_LOCAL_PROXY.{field}[{i}] richiede artist e album non vuoti')
                        checked.append({'artist': artist, 'album': album})
                    SPOTIFY_LOCAL_PROXY_CONFIG[field] = checked
            if 'market' in proxy_cfg:
                market = str(proxy_cfg['market']).strip().upper()
                if not re.fullmatch(r'[A-Z]{2}', market):
                    raise ValueError('SPOTIFY_LOCAL_PROXY.market deve essere un codice paese ISO a 2 lettere')
                SPOTIFY_LOCAL_PROXY_CONFIG['market'] = market
            if 'catalog_cache_days' in proxy_cfg:
                try:
                    cache_days = int(proxy_cfg['catalog_cache_days'])
                except (TypeError, ValueError):
                    raise ValueError('SPOTIFY_LOCAL_PROXY.catalog_cache_days deve essere intero')
                if not 0 <= cache_days <= 3650:
                    raise ValueError('SPOTIFY_LOCAL_PROXY.catalog_cache_days deve essere tra 0 e 3650')
                SPOTIFY_LOCAL_PROXY_CONFIG['catalog_cache_days'] = cache_days
            if 'favorites_user' in proxy_cfg:
                favorites_user = str(proxy_cfg['favorites_user'] or '').strip()
                if any(ch in favorites_user for ch in '\r\n\x00'):
                    raise ValueError('SPOTIFY_LOCAL_PROXY.favorites_user contiene caratteri di controllo')
                SPOTIFY_LOCAL_PROXY_CONFIG['favorites_user'] = favorites_user
        translation_cfg = _cfg.get('AUTO_NAME_TRANSLATION', {})
        if translation_cfg is not None:
            if not isinstance(translation_cfg, dict):
                raise ValueError('AUTO_NAME_TRANSLATION deve essere un oggetto JSON')
            if 'enabled' in translation_cfg:
                if not isinstance(translation_cfg['enabled'], bool):
                    raise ValueError('AUTO_NAME_TRANSLATION.enabled deve essere booleano')
                AUTO_NAME_TRANSLATION_CONFIG['enabled'] = translation_cfg['enabled']
            if 'min_confidence' in translation_cfg:
                try:
                    score = float(translation_cfg['min_confidence'])
                except (TypeError, ValueError):
                    raise ValueError('AUTO_NAME_TRANSLATION.min_confidence deve essere numerico')
                if not 0 <= score <= 1:
                    raise ValueError('AUTO_NAME_TRANSLATION.min_confidence deve essere tra 0 e 1')
                AUTO_NAME_TRANSLATION_CONFIG['min_confidence'] = score
            for field in ('max_new_per_run', 'cache_days', 'timeout', 'failure_cooldown_hours'):
                if field in translation_cfg:
                    try:
                        val = int(translation_cfg[field])
                    except (TypeError, ValueError):
                        raise ValueError(f'AUTO_NAME_TRANSLATION.{field} deve essere intero')
                    low = 1 if field == 'timeout' else 0
                    high = (86400 if field == 'timeout' else 720 if field == 'failure_cooldown_hours'
                            else 100000 if field == 'max_new_per_run' else 3650)
                    if not low <= val <= high:
                        raise ValueError(f'AUTO_NAME_TRANSLATION.{field} fuori intervallo')
                    AUTO_NAME_TRANSLATION_CONFIG[field] = val
        PLAYLIST_FOLDERS.update(_cfg.get('PLAYLIST_FOLDERS', {}))
        # SKIP_PLAYLISTS e' per-utente. Compatibilita' con i vecchi JSON a lista:
        # le regole esistenti vengono assegnate all'utente di default, mai globalmente.
        skip_cfg = _cfg.get('SKIP_PLAYLISTS', {})
        if isinstance(skip_cfg, list):
            print('[warn] SKIP_PLAYLISTS in formato lista legacy: assegno le voci a '
                  f'{DEFAULT_USER!r}; usa un oggetto per utente nel JSON', file=sys.stderr)
            skip_cfg = {DEFAULT_USER: skip_cfg}
        if not isinstance(skip_cfg, dict):
            raise ValueError('SKIP_PLAYLISTS deve essere un oggetto JSON {utente: [playlist, ...]}')
        for user_name, patterns in skip_cfg.items():
            user_key = str(user_name or '').strip().casefold()
            if not user_key:
                raise ValueError('SKIP_PLAYLISTS contiene un utente vuoto')
            if not isinstance(patterns, list) or any(not isinstance(p, str) for p in patterns):
                raise ValueError(f'SKIP_PLAYLISTS.{user_name} deve essere una lista di stringhe')
            cleaned = [p.strip() for p in patterns if p.strip()]
            SKIP_PLAYLISTS.setdefault(user_key, []).extend(cleaned)
        for g in _cfg.get('ARTIST_GROUPS', []):
            sg = {norm(x) for x in g}
            if sg and sg not in ARTIST_GROUPS:
                ARTIST_GROUPS.append(sg)
        to_romaji.cache_clear()
        _preferred_name_for_key.cache_clear()
        if '_NF_REV' in globals():
            globals()['_NF_REV'] = None
        _title_qualifier_phrases.cache_clear()
        _title_variant_penalty_cached.cache_clear()
        print(f"[i] configurazione utente caricata: {_USER_CFG}", file=sys.stderr)
    except Exception as e:
        # prima: stampava l'errore e andava avanti con la config a meta' (skip-list
        # ignorata => playlist indesiderate importate in Navidrome). Ora: stop.
        sys.exit(f"[ERRORE] configurazione non valida ({_USER_CFG}): {e}")

_CJK = re.compile(r'[぀-ヿ㐀-鿿豈-﫿]')


@lru_cache(maxsize=65536)
def _phonetic_kakasi(s):
    """Lettura fonetica Hepburn pura, senza traduzioni o alias; ripara vecchi gloss."""
    if not s or not _HAS_KAKASI or not _CJK.search(s):
        return ''
    return norm(' '.join(w['hepburn'] for w in _kks.convert(s)))


@lru_cache(maxsize=None)
def to_romaji(s):
    """Forma inglese/alias preferita, poi fallback fonetico per CJK e Hangul."""
    if not s:
        return ''
    fixed = _preferred_name(s)
    if fixed:
        return norm(fixed)
    # Hangul has its own romanizer; pykakasi handles Japanese/Kanji only.
    hangul_pattern = globals().get('_HANGUL')
    hangul_fn = globals().get('_HANGUL_FN')
    if hangul_pattern is not None and hangul_pattern.search(s) and not _CJK.search(s):
        return norm(hangul_fn(s)) if callable(hangul_fn) else ''
    return _phonetic_kakasi(s)


AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.wma'}


@lru_cache(maxsize=131072)
def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize('NFKD', s)
    # togli i diacritici (accenti) MA conserva dakuten/handakuten giapponesi (ド = ト+゛)
    s = ''.join(c for c in s if not unicodedata.combining(c) or c in '\u3099\u309a')
    s = unicodedata.normalize('NFC', s)   # ricomponi: ト+゛ -> ド
    s = s.lower().strip()
    for phrase, emoji in EMOJI_WORDS.items():
        s = s.replace(phrase, emoji)
    s = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', ' ', s)
    s = re.sub(r'\b(feat|ft|featuring)\b\.?.*$', ' ', s)   # 'love feat zacari' -> 'love'
    s = re.sub(r'\bpt\.?\b', 'part', s)                    # 'pt 2' -> 'part 2'
    # \w unicode (kanji ecc.) + range emoji: non cancellare le emoji
    s = re.sub(r'[^\w \U0001F300-\U0001FAFF\U00002600-\U000027BF]+', ' ', s)
    s = s.replace('_', ' ')
    return re.sub(r'\s+', ' ', s).strip()



@lru_cache(maxsize=131072)
def norm_bare(s):
    """Come norm() ma SENZA rimuovere parentesi/feat: '(Nice Dream)' -> 'nice dream'.
    Usato come fallback per titoli che norm() svuoterebbe."""
    if not s:
        return ""
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c) or c in '\u3099\u309a')
    s = unicodedata.normalize('NFC', s)
    s = s.lower().strip()
    s = re.sub(r'[^\w \U0001F300-\U0001FAFF\U00002600-\U000027BF]+', ' ', s)
    s = s.replace('_', ' ')
    return re.sub(r'\s+', ' ', s).strip()

@lru_cache(maxsize=65536)
def _preferred_name_for_key(key):
    """NAME_TRANSLATIONS (traduzione/forma inglese ufficiale) > NAME_FIXES (alias manuale)."""
    return NAME_TRANSLATIONS.get(key) or NAME_FIXES.get(key, '')


def _preferred_name(value):
    """NAME_TRANSLATIONS > NAME_FIXES > traduzione automatica sopra soglia > fonetica."""
    if not value:
        return ''
    forced = _preferred_name_for_key(norm(value))
    if forced:
        return forced
    return _auto_translate_name(value)


_AUTO_TRANSLATABLE_RE = re.compile(r'[぀-ヿ㐀-鿿豈-﫿\uac00-\ud7af]')
_AUTO_TRANSLATION_WARNED = False
# Circuit breaker: se il provider web fallisce, non serializzare timeout per ogni nome CJK.
_AUTO_TRANSLATION_PROVIDER_FAILED = False
_AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL = 0


def _auto_translation_cache_load():
    """Carica cache traduzioni e cooldown del provider, separata dalle regole curate."""
    global AUTO_NAME_TRANSLATION_CACHE, _AUTO_TRANSLATION_PROVIDER_FAILED
    global _AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL
    if AUTO_NAME_TRANSLATION_CACHE is not None:
        return AUTO_NAME_TRANSLATION_CACHE
    path = CACHE_DIR / 'auto_name_translations.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') == 1 and isinstance(data.get('items', {}), dict):
            AUTO_NAME_TRANSLATION_CACHE = data.get('items', {})
            _AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL = int(
                data.get('provider_unavailable_until') or 0)
            if _AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL > int(time.time()):
                _AUTO_TRANSLATION_PROVIDER_FAILED = True
        else:
            AUTO_NAME_TRANSLATION_CACHE = {}
    except (OSError, ValueError, TypeError):
        AUTO_NAME_TRANSLATION_CACHE = {}
    return AUTO_NAME_TRANSLATION_CACHE


def _auto_translation_cache_save():
    global _AUTO_TRANSLATION_CACHE_DIRTY
    if not _AUTO_TRANSLATION_CACHE_DIRTY:
        return
    path = CACHE_DIR / 'auto_name_translations.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f'.tmp-{os.getpid()}')
        payload = {
            'version': 1,
            'provider_unavailable_until': int(_AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL or 0),
            'items': _auto_translation_cache_load(),
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        os.replace(tmp, path)
        _AUTO_TRANSLATION_CACHE_DIRTY = False
    except OSError as e:
        print(f'[warn] cache traduzioni automatiche non salvata: {e}', file=sys.stderr)


def _auto_translation_phonetic(value):
    """Lettura fonetica grezza: aiuta a scartare output che sono soltanto romanizzazioni."""
    if _CJK.search(value):
        return _phonetic_kakasi(value)
    hangul = globals().get('_HANGUL')
    romanizer = globals().get('_HANGUL_FN')
    if hangul is not None and hangul.search(value) and callable(romanizer):
        try:
            return norm(romanizer(value))
        except Exception:
            return ''
    return ''


def _auto_translation_confidence(source, translated, phonetic=''):
    """Stima euristica 0..1, NON probabilita' fornita dal provider.

    Il traduttore web non espone una confidence calibrata per nomi brevi. I criteri conservativi
    richiedono output leggibile in caratteri latini, diverso dalla fonte e dalla lettura fonetica.
    """
    translated = str(translated or '').strip()
    if not translated or len(translated) > 180:
        return 0.0
    letters = [c for c in translated if c.isalpha()]
    if not letters:
        return 0.0
    latin = sum('LATIN' in unicodedata.name(c, '') for c in letters)
    latin_ratio = latin / len(letters)
    if latin_ratio < 0.85 or _AUTO_TRANSLATABLE_RE.search(translated):
        return 0.2
    source_key, translated_key = norm_bare(source), norm_bare(translated)
    if not translated_key:
        return 0.0
    phonetic_key = norm_bare(phonetic)
    if phonetic_key and difflib.SequenceMatcher(None, translated_key, phonetic_key).ratio() >= 0.88:
        return 0.58
    score = 0.64
    if source_key and translated_key != source_key:
        score += 0.08
    if latin_ratio >= 0.98:
        score += 0.07
    if 1 <= len(translated_key.split()) <= 10:
        score += 0.05
    if len(source_key) <= 1:
        score = min(score, 0.60)  # un ideogramma isolato e' spesso un nome proprio
    elif len(translated_key.split()) == 1 and len(source_key) <= 2:
        score = min(score, 0.70)
    return round(min(0.92, score), 3)


def _google_auto_translate_to_english(value):
    """Traduzione inglese senza dipendenze; endpoint pubblico non contrattuale/rate-limited."""
    query = urllib.parse.urlencode({'client': 'gtx', 'sl': 'auto', 'tl': 'en', 'dt': 't', 'q': value})
    url = 'https://translate.googleapis.com/translate_a/single?' + query
    timeout = int(AUTO_NAME_TRANSLATION_CONFIG.get('timeout', 8))
    last_error = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 exportify-to-m3u'})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
            segments = payload[0] if isinstance(payload, list) and payload else []
            translated = ''.join(str(seg[0]) for seg in segments if isinstance(seg, list) and seg and seg[0])
            translated = re.sub(r'\s+', ' ', translated).strip()
            if translated:
                return translated
            last_error = 'risposta senza testo tradotto'
        except Exception as e:
            last_error = f'{type(e).__name__}: {e}'
        if attempt == 0:
            time.sleep(0.4)
    raise RuntimeError(last_error or 'traduzione non riuscita')


def _auto_translate_name(value):
    """Traduzione automatica prudente; provider offline => fonetica senza nuovi timeout."""
    global AUTO_NAME_TRANSLATION_NEW, _AUTO_TRANSLATION_WARNED, _AUTO_TRANSLATION_CACHE_DIRTY
    global _AUTO_TRANSLATION_PROVIDER_FAILED, _AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL
    cfg = AUTO_NAME_TRANSLATION_CONFIG
    if not cfg.get('enabled', True) or not value or not _AUTO_TRANSLATABLE_RE.search(value):
        return ''
    key = norm(value)
    if not key:
        return ''
    cache = _auto_translation_cache_load()
    now = int(time.time())
    entry = cache.get(key)
    if isinstance(entry, dict):
        age = now - int(entry.get('checked_at') or 0)
        ttl = int(cfg.get('cache_days', 365)) * 86400
        if age <= ttl:
            if float(entry.get('confidence') or 0) >= float(cfg.get('min_confidence', 0.72)):
                return str(entry.get('translation') or '')
            if entry.get('error') and age < 7 * 86400:
                return ''
            if not entry.get('error'):
                return ''
    # Le traduzioni gia' in cache si possono usare anche durante il cooldown; non fare
    # richieste HTTP nuove dopo un fallimento, altrimenti 100 nomi possono serializzare minuti.
    if _AUTO_TRANSLATION_PROVIDER_FAILED:
        return ''
    max_new = int(cfg.get('max_new_per_run', 100))
    if max_new and AUTO_NAME_TRANSLATION_NEW >= max_new:
        if not _AUTO_TRANSLATION_WARNED:
            print(f'[i] limite traduzioni automatiche raggiunto ({max_new}); in questa run uso la fonetica',
                  file=sys.stderr)
            _AUTO_TRANSLATION_WARNED = True
        return ''
    AUTO_NAME_TRANSLATION_NEW += 1
    try:
        translated = _google_auto_translate_to_english(value)
    except Exception as e:
        # Circuit breaker persistente: un errore definitivo/rete non deve moltiplicarsi
        # per ogni nome della libreria. Dopo il cooldown una run futura testa di nuovo il provider.
        cooldown_hours = max(1, int(cfg.get('failure_cooldown_hours', 6)))
        _AUTO_TRANSLATION_PROVIDER_FAILED = True
        _AUTO_TRANSLATION_PROVIDER_UNAVAILABLE_UNTIL = now + cooldown_hours * 3600
        if not _AUTO_TRANSLATION_WARNED:
            print(f'[warn] traduzione automatica non disponibile ({type(e).__name__}); '
                  f'uso la fonetica e sospendo le richieste per {cooldown_hours}h',
                  file=sys.stderr)
            _AUTO_TRANSLATION_WARNED = True
        cache[key] = {'source': value, 'translation': '', 'confidence': 0.0,
                      'provider': 'google-web-heuristic', 'checked_at': now, 'error': str(e)[:160]}
        _AUTO_TRANSLATION_CACHE_DIRTY = True
        return ''

    confidence = _auto_translation_confidence(value, translated, _auto_translation_phonetic(value))
    cache[key] = {'source': value, 'translation': translated, 'confidence': confidence,
                  'provider': 'google-web-heuristic', 'checked_at': now}
    _AUTO_TRANSLATION_CACHE_DIRTY = True
    if confidence >= float(cfg.get('min_confidence', 0.72)):
        return translated
    return ''


QUALIFIER_WORDS = {
    'mix', 'remix', 'version', 'acoustic', 'karaoke', 'カラオケ', 'instrumental',
    'live', 'demo', 'cover', 'edit', 'remaster', 'remastered', 'extended',
    'rehearsal', 'rehersal', 'practice', 'outtake', 'alternate', 'alternative', 'session',
    'take', 'rough', 'deluxe', 'anniversary', 'expanded', 'bonus', 'reissue',
}


def _contains_phrase(text, phrase):
    text = norm_bare(text)
    phrase = norm_bare(phrase)
    if not text or not phrase:
        return False
    return re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text) is not None


_PARENTHESIS_PENALTY_KEY = 'parentheses'


@lru_cache(maxsize=1)
def _title_qualifier_phrases():
    """Lista immutabile dei qualificatori, normalizzata e ordinata una sola volta."""
    phrases = {norm_bare(x) for x in QUALIFIER_WORDS if norm_bare(x)}
    phrases.update(norm_bare(x) for x in TITLE_MATCH_PENALTIES
                   if x != _PARENTHESIS_PENALTY_KEY and norm_bare(x))
    return tuple(sorted(phrases, key=lambda x: (-len(x), x)))


# sottoinsieme per il rilevamento dal NOME FILE: niente remaster/live,
# altrimenti tutti i brani delle cartelle "(Remastered)" risulterebbero
# "versioni" e la preferenza puliti/qualificati si svuoterebbe (bug reale:
# 'When You Gonna Learn' perdeva contro '...Cante Hondo Mix' perche' il FLAC
# pulito era marcato qualificato dalla parola Remastered nell'album).
_STRONG_QUALIFIERS = {
    'mix', 'remix', 'version', 'acoustic', 'karaoke', 'カラオケ', 'instrumental',
    'demo', 'cover', 'edit', 'extended', 'live', 'rehearsal', 'rehersal', 'practice',
    'outtake', 'alternate', 'alternative', 'session', 'take', 'rough',
}


def _has_qualifier(nt: str) -> bool:
    """True se il titolo normalizzato contiene parole-tipo/version labels.
    Accetta anche qualificatori composti (es. 'radio edit')."""
    normalized = norm_bare(nt)
    return any(_contains_phrase(normalized, word)
               for word in _title_qualifier_phrases())


def _has_tight_comma_separator(value):
    """True for a comma used as a delimiter without whitespace after it (``A,B``).

    This is a strong generic collaboration cue in exported tags. Unlike a spaced comma,
    it is not normally used in real artist names such as ``Tyler, The Creator``.
    """
    return bool(re.search(r',(?=\S)', str(value or '')))


def split_artists(s, by_artist):
    """Split artist lists before accepting an already-indexed joined artist name.

    ``;`` and tight commas are strong delimiters. For spaced commas, known components are
    tested before the joined key, which fixes the prior precedence bug while preserving a
    known solo artist such as ``Tyler, The Creator`` when its components are not both known.
    """
    raw = str(s or '').strip()
    if not raw:
        return []
    if ';' in raw:
        return [norm(x.strip()) for x in raw.split(';') if norm(x.strip())]
    comma_parts = [x.strip() for x in re.split(r'\s*,\s*', raw) if x.strip()]
    if _has_tight_comma_separator(raw):
        return [norm(x) for x in re.split(r',(?=\S)', raw) if norm(x)]
    ns = norm(raw)
    if len(comma_parts) >= 2:
        component_keys = [norm(part) for part in comma_parts]
        if all(key in by_artist for key in component_keys):
            return component_keys
    if ns in by_artist:
        return [ns]
    parts = [norm(x) for x in re.split(r'[,;/]', raw) if norm(x)]
    out, i = [], 0
    while i < len(parts):
        hit = None
        for j in range(len(parts), i, -1):
            cand = norm(' '.join(parts[i:j]))
            if cand in by_artist:
                hit, i = cand, j
                break
        if hit:
            out.append(hit)
        else:
            out.append(parts[i])
            i += 1
    return out

def _canon(a):
    """Se 'a' appartiene a un ARTIST_GROUPS, ritorna il nome rappresentante
    (il minimo del gruppo: scelta arbitraria ma stabile), altrimenti 'a'."""
    for g in ARTIST_GROUPS:
        if a in g:
            return min(g)
    return a


def clean_artist(s):
    s = (s or '').replace("\\", "").strip().strip('"')
    return s[:-1].strip() if s.endswith(",") else s


def title_candidates(name):
    """Possibili titoli da un nome file.
    Gestisce sia '01 - Titolo.ext' sia 'Artista - Album - 01 - Titolo.ext'."""
    stem = Path(name).stem.strip()
    raw = [stem,
           re.sub(r'^\d{1,3}\s*[-._:]\s*', '', stem),
           re.sub(r'^\d{1,3}\s+', '', stem)]
    parts = stem.split(' - ')
    if len(parts) > 1:
        raw.append(parts[-1])
        raw.append(re.sub(r'^\d{1,3}\s*[-._:]\s*', '', parts[-1]))
        raw.append(parts[0])    # 'Titolo - Album - Artista.ext' (nomi file slskd)
        raw.append(re.sub(r'^\d{1,3}\s*[-._:]\s*', '', parts[0]))
    raw.append(norm_bare(stem))          # fallback per titoli tra parentesi
    if len(parts) > 1:
        raw.append(norm_bare(parts[-1]))
    out, seen = [], set()
    for r in raw:
        for n in (norm(r), norm_bare(r)):   # norm_bare copre i titoli tra parentesi
            if n and n not in seen:
                seen.add(n)
                out.append(n)
    return out or ['']


def strict_titles(name):
    """Titoli 'pieni' di un file (parentesi incluse, maiuscole a parte).
    Distinti dai candidati norm(): 'X (Cante Hondo mix)' != 'X'."""
    stem = Path(name).stem.strip()
    raw = [stem,
           re.sub(r'^\d{1,3}\s*[-._:]\s*', '', stem)]
    parts = stem.split(' - ')
    if len(parts) > 1:
        raw.append(parts[-1])
        raw.append(re.sub(r'^\d{1,3}\s*[-._:]\s*', '', parts[-1]))
        raw.append(parts[0])
        raw.append(re.sub(r'^\d{1,3}\s*[-._:]\s*', '', parts[0]))
    return {norm_bare(x) for x in raw if norm_bare(x)}


_SKIP_DIRS = {'playlists', '@eadir', '.git'}

# Formati che Navidrome riproduce oltre a quelli che il resto dello script sa
# ri-taggare (AUDIO_EXT). Servono SOLO per indicizzare le playlist e per capire
# se una cartella e' davvero "vuota" (clean_empty): una cartella di soli .aiff/
# .ape/.wv/.dsf NON deve mai essere cancellata. Le fasi che scrivono tag
# (romaji/unify/...) restano su AUDIO_EXT: ffmpeg non sa scrivere tutti questi.
INDEX_EXT = AUDIO_EXT | {'.aif', '.aiff', '.ape', '.wv', '.dsf', '.dff', '.mpc',
                         '.mka', '.oga', '.mp2', '.tta', '.m4b'}

# sottocartelle "disco" dentro un album: CD1, Disc 2, Disk 01, Vinyl 01, Side A...
_DISC_DIR = re.compile(r'^(?:cd|dis[ck]|vinyl|lp|side)[\s._-]*(?:\d{1,2}|[a-d])'
                       r'(?:[\s:(\-].*)?$', re.I)


def _walk_audio(root, exts=None):
    """Elenca i file audio sotto root come tuple di parti relative, in ordine
    alfabetico (DETERMINISTICO: il vecchio rglob restituiva l'ordine del
    filesystem, e i pareggi del matching dipendevano da quello). Salta
    Playlists/@eaDir/.git a qualsiasi livello. Usa os.scandir: ~10x piu' veloce
    di Path.rglob + is_file + stat. I symlink a cartelle non vengono seguiti."""
    exts = INDEX_EXT if exts is None else exts
    out = []
    stack = [(str(root), ())]
    while stack:
        base, rel = stack.pop()
        try:
            with os.scandir(base) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            name = e.name
            if name.lower() in _SKIP_DIRS:
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append((e.path, rel + (name,)))
                elif os.path.splitext(name)[1].lower() in exts and e.is_file():
                    out.append(rel + (name,))
            except OSError:
                continue
    out.sort()
    return out


def _library_signature(rels):
    """[n_file, somma crc32 dei path relativi]. A differenza della vecchia firma
    (n_file, byte_totali) cambia anche per RINOMINE e SPOSTAMENTI (stessi file,
    stessi byte): dopo un dedupe 'bonus' o un rename di Lidarr la cache restava
    stale e le m3u puntavano a path morti."""
    s = 0
    for r in rels:
        s += zlib.crc32('/'.join(r).encode('utf-8', 'surrogateescape'))
    return [len(rels), s & 0xFFFFFFFF]


def scan_library(root, rels=None):
    """Indicizza Artist/Album/Track.ext direttamente dal filesystem."""
    by_full, by_artist, by_strict, path_qual = {}, {}, {}, {}
    n = 0
    root_s = str(Path(root))
    if rels is None:
        rels = _walk_audio(root)
    progress = _ProgressBar('indicizzazione libreria', len(rels), 'brani')
    for checked, rel in enumerate(rels, 1):
        progress.update(checked)
        # struttura profonda: indicizza la radice (rel[0], il vero artista).
        # Album multi-disco (Artista/Album/CD1/Traccia): l'album e' la cartella
        # SOPRA il disco (prima rel[-3] finiva indicizzato come "artista" e
        # il nome cartella-disco 'CD1' come album: la preferenza d'album non
        # funzionava e 'Album' e 'Album (Deluxe)' risultavano indistinguibili)
        if len(rel) < 2:
            continue
        p = os.path.join(root_s, *rel)
        deep = len(rel) >= 4
        if deep and _DISC_DIR.match(rel[-2]):
            artists = [rel[0]]
            albums = [rel[-3]] + ([rel[1]] if rel[1] != rel[-3] else [])
            full_alb = rel[-3]
        else:
            artists = [rel[0]] + ([rel[-3]] if deep else [])
            albums = [rel[-2]] + ([rel[1]] if deep else [])
            full_alb = albums[0]
        akeys = set()
        for a in artists:
            na = norm(a)
            if na:
                akeys.add(na)
                akeys.add(_canon(na))
                # componenti dei nomi multi-artista ('JPEGMAFIA, Danny Brown'
                # -> anche 'jpegmafia' e 'danny brown' sono chiavi valide)
                akeys |= set(split_artists(a, {}))
        akeys |= {to_romaji(a) for a in akeys}
        akeys.discard('')
        nals = {norm(a) for a in albums} - {''}
        name = rel[-1]
        cands = title_candidates(name)
        sts = strict_titles(name)
        if any(t in _STRONG_QUALIFIERS for t in norm_bare(Path(name).stem).split()):
            path_qual[p] = True
        # varianti del titolo calcolate UNA volta per brano (non per chiave artista)
        vlist = []
        seen_v = set()
        for nt in cands:
            rn = to_romaji(nt)
            variants = {nt, ''.join(nt.split())}
            if rn:
                variants |= {rn, ''.join(rn.split())}
            for vnt in sorted(variants):
                if vnt not in seen_v:
                    seen_v.add(vnt)
                    vlist.append(vnt)
        for k in sorted(akeys):
            for st in sts:
                by_strict.setdefault((k, st), []).append(p)
            pool = by_artist.setdefault(k, [])
            for vnt in vlist:
                for nal in sorted(nals or {''}):
                    pool.append((vnt, nal, p))
        by_full.setdefault((norm(artists[-1]), norm(full_alb), cands[-1]), []).append(p)
        n += 1
    progress.close(complete=True)
    cjk = sorted({k for k in by_artist if _CJK.search(k)})
    if cjk:
        print(f"[i] {len(cjk)} nomi in kanji rilevati nella libreria (gruppati automaticamente col romaji):",
              file=sys.stderr)
        for k in cjk:
            print(f"      {k} -> {to_romaji(k) or '(nessuna conversione)'}", file=sys.stderr)
    return by_full, by_artist, by_strict, path_qual, n


CACHE_VERSION = 8


def _config_crc():
    try:
        return zlib.crc32(_USER_CFG.read_bytes()) & 0xFFFFFFFF
    except OSError:
        return 0


def _write_json_atomic(path, obj, **kw):
    """Scrittura atomica: un crash a meta' non lascia piu' un JSON troncato."""
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, **kw), encoding='utf-8')
    os.replace(tmp, path)


def _read_index_cache(sig):
    """Ritorna (by_full, by_artist, by_strict, path_qual, n) o None se la cache
    manca / e' vecchia / e' stale (e dice perche')."""
    if not CACHE.exists():
        return None
    try:
        d = json.loads(CACHE.read_text(encoding='utf-8'))
        if d.get('v') != CACHE_VERSION:
            print("[i] cache in formato vecchio: riscansione", file=sys.stderr)
            return None
        if d.get('sig') != sig:
            old = d.get('sig') or []
            if len(old) == 3 and old[:2] == sig[:2]:
                print("[i] exportify_names.json modificato: riscansione automatica",
                      file=sys.stderr)
            else:
                print(f"[i] libreria cambiata ({sig[0]} file vs cache "
                      f"{(old or ['?'])[0]}): riscansione automatica", file=sys.stderr)
            return None
        paths = d['paths']
        by_full = {k: [paths[i] for i in v] for k, v in d['by_full'].items()}
        by_strict = {}
        for k, v in d['by_strict'].items():
            a, _, st = k.partition('\t')
            by_strict[(a, st)] = [paths[i] for i in v]
        by_artist = {a: [(nt, nal, paths[i]) for nt, nal, i in lst]
                     for a, lst in d['by_artist'].items()}
        path_qual = {paths[i]: True for i in d['qual']}
        return by_full, by_artist, by_strict, path_qual, d['n']
    except Exception as e:
        print(f"[i] cache illeggibile ({e}): riscansione", file=sys.stderr)
        return None


def _write_index_cache(sig, n, by_full, by_artist, by_strict, path_qual):
    # i path compaiono centinaia di volte: tabella unica + indici (cache ~3x
    # piu' piccola, caricamento piu' veloce, meno RAM)
    pid = {}
    paths = []

    def P(p):
        i = pid.get(p)
        if i is None:
            i = pid[p] = len(paths)
            paths.append(p)
        return i

    payload = {
        'v': CACHE_VERSION, 'n': n, 'sig': sig,
        'by_full': {'\t'.join(k): [P(x) for x in v] for k, v in by_full.items()},
        'by_strict': {'\t'.join(k): [P(x) for x in v] for k, v in by_strict.items()},
        'by_artist': {a: [[nt, nal, P(p)] for nt, nal, p in lst]
                      for a, lst in by_artist.items()},
        'qual': [P(p) for p in path_qual],
    }
    payload['paths'] = paths
    try:
        _write_json_atomic(CACHE, payload, ensure_ascii=False, separators=(',', ':'))
    except OSError as e:
        print(f"[!] impossibile scrivere la cache {CACHE}: {e}", file=sys.stderr)


def load_library(rebuild=False):
    if not _HAS_KAKASI:
        print("[!] pykakasi non installato: matching kanji<->romaji disattivato "
              "(nel venv dello script: .venv/bin/pip install pykakasi)", file=sys.stderr)
    rels = _walk_audio(LIBRARY_ROOT)
    # la firma include la CONFIGURAZIONE: l'indice contiene chiavi calcolate con
    # NAME_FIXES / ARTIST_GROUPS / ALIASES (norm, _canon, to_romaji). Prima, dopo aver
    # modificato exportify_names.json la cache restava valida e le modifiche non
    # avevano effetto fino a --rebuild-cache.
    sig = _library_signature(rels) + [_config_crc()]
    if not rebuild:
        hit = _read_index_cache(sig)
        if hit:
            by_full, by_artist, by_strict, path_qual, n = hit
            print(f"[i] libreria caricata dalla cache: {n} brani", file=sys.stderr)
            globals()['_LIB_TRACK_COUNT'] = n
            return by_full, by_artist, by_strict, path_qual
    by_full, by_artist, by_strict, path_qual, n = scan_library(LIBRARY_ROOT, rels)
    _write_index_cache(sig, n, by_full, by_artist, by_strict, path_qual)
    print(f"[i] indicizzati {n} brani da {LIBRARY_ROOT} (cache in {CACHE})", file=sys.stderr)
    globals()['_LIB_TRACK_COUNT'] = n
    return by_full, by_artist, by_strict, path_qual


@lru_cache(maxsize=200_000)
def _album_match(nal, lal):
    """Confronto album GRADUATO: 2 = esatto, 1 = base normalizzata
    (album_base toglie anni/(Remaster)/(Deluxe): 'TAKANAKA (2018
    Remaster)' conta come 'TAKANAKA') o contenimento, 0 = diverso.
    Il punteggio alto vince: l'album esatto batte sempre il remaster."""
    if not nal or not lal:
        return 0
    if nal == lal:
        return 2
    try:
        if album_base(nal) and album_base(nal) == album_base(lal):
            return 1
    except Exception:
        pass
    if len(nal) >= 4 and len(lal) >= 4 and (nal in lal or lal in nal):
        return 1
    return 0


@lru_cache(maxsize=None)
def _top_keys(path):
    """(norm(cartella artista), romaji) di un path della libreria, o None se
    il path e' fuori dalla libreria. Sostituisce Path.relative_to (lentissimo
    chiamato decine di migliaia di volte per playlist)."""
    root = str(LIBRARY_ROOT)
    if not path.startswith(root + os.sep):
        return None
    fa = norm(path[len(root) + 1:].split(os.sep, 1)[0])
    return fa, to_romaji(fa)


@lru_cache(maxsize=None)
def _alb_folder(path):
    """norm_bare del nome ALBUM di un file. Usa norm_bare (parentesi INCLUSE):
    norm() le strisce e renderebbe indistinguibili 'TAKANAKA' da 'TAKANAKA
    (2018 Remaster)'. Per i multi-disco (.../Album/CD1/Traccia) l'album e' la
    cartella sopra il disco."""
    d = os.path.dirname(path)
    name = os.path.basename(d)
    if _DISC_DIR.match(name):
        name = os.path.basename(os.path.dirname(d))
    # Prefer a curated English translation/official title, then a legacy alias/romanization.
    fixed = _preferred_name(name)
    return norm_bare(fixed if fixed else name)


def _close1(word, by_len, cutoff):
    """Equivalente di difflib.get_close_matches(word, candidati, n=1, cutoff)
    che scarta PRIMA i candidati la cui lunghezza non puo' raggiungere il
    cutoff (stessa guardia real_quick_ratio che difflib applica comunque, ma
    senza istanziare un confronto per ognuno): risultato identico, molto
    meno lavoro. by_len: {lunghezza: [stringhe distinte]}."""
    la = len(word)
    cands = []
    for lb, lst in by_len.items():
        tot = la + lb
        rq = 2.0 * min(la, lb) / tot if tot else 1.0
        if rq >= cutoff:
            cands.extend(lst)
    if not cands:
        return None
    r = difflib.get_close_matches(word, cands, n=1, cutoff=cutoff)
    return r[0] if r else None


def _by_len(strings):
    out = {}
    for s in strings:
        out.setdefault(len(s), []).append(s)
    return out


class _LibPrep:
    """Strutture derivate dall'indice, costruite pigramente e condivise tra le
    righe di TUTTE le playlist (la libreria non cambia durante l'esecuzione):
    memo dei risultati, indice titolo->path per artista, bucket di lunghezza
    per il fuzzy."""

    def __init__(self, refs):
        self.refs = refs                 # (by_full, by_artist, by_strict, path_qual)
        self.by_artist = refs[1]
        self.memo = {}                   # (artista, album, titolo, soglia) -> path|None
        self._by_lt, self._pos, self._lens, self._lts4 = {}, {}, {}, {}
        self._names = None
        self._fz_t, self._fz_a = {}, {}

    def by_lt(self, a):
        """{titolo-variante: [path distinti, in ordine di scansione]}"""
        idx = self._by_lt.get(a)
        if idx is None:
            idx, posd = {}, {}
            for i, (lt, _lal, path) in enumerate(self.by_artist.get(a, ())):
                lst = idx.setdefault(lt, [])
                if path not in lst:
                    lst.append(path)
                    posd.setdefault(lt, []).append(i)
            self._by_lt[a] = idx
            self._pos[a] = posd
        return idx

    def pos(self, a):
        """{titolo-variante: [posizione nel pool di ciascun path]}: serve a
        riprodurre ESATTAMENTE l'ordine di scansione nello stage 3."""
        self.by_lt(a)
        return self._pos[a]

    def lens(self, a):
        v = self._lens.get(a)
        if v is None:
            v = self._lens[a] = _by_len(self.by_lt(a))
        return v

    def lts4(self, a):
        v = self._lts4.get(a)
        if v is None:
            v = self._lts4[a] = [lt for lt in self.by_lt(a) if len(lt) >= 4]
        return v

    def fz_title(self, a, t, cutoff):
        k = (a, t, cutoff)
        if k not in self._fz_t:
            self._fz_t[k] = _close1(t, self.lens(a), cutoff)
        return self._fz_t[k]

    def fz_artist(self, akey, cutoff):
        if self._names is None:
            self._names = _by_len(x for x in self.by_artist if x)
        k = (akey, cutoff)
        if k not in self._fz_a:
            self._fz_a[k] = _close1(akey, self._names, cutoff)
        return self._fz_a[k]


_PREP = None


def _get_prep(by_full, by_artist, by_strict, path_qual):
    global _PREP
    refs = (by_full, by_artist, by_strict, path_qual)
    if _PREP is None or any(a is not b for a, b in zip(_PREP.refs, refs, strict=True)):
        _PREP = _LibPrep(refs)
        for fn in (_top_keys, _alb_folder, _album_match):
            fn.cache_clear()
    return _PREP


def _strip_match_qualifiers(text):
    """Rimuove solo parole-tipo note per confrontare il nucleo del titolo.
    Non viene usato per la chiave di matching, solo per scegliere fra candidati."""
    out = norm_bare(text)
    for phrase in _title_qualifier_phrases():
        out = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', ' ', out)
    return re.sub(r'\s+', ' ', out).strip()


def _qualifier_only_component(component):
    """True per suffissi separati da trattino tipo '- Live' o '- 2015 Remaster'."""
    normalized = norm_bare(component)
    if not normalized:
        return False
    cleaned = normalized
    found = False
    for phrase in _title_qualifier_phrases():
        if _contains_phrase(cleaned, phrase):
            found = True
            cleaned = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', ' ', cleaned)
    # Un anno/numero davanti a Remaster o Deluxe e' un qualificatore di edizione.
    cleaned = re.sub(r'\b(?:19|20)\d{2}\b|\b\d+\b', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return found and not cleaned


def _candidate_title_segment(path, requested_title):
    """Individua la parte del filename che piu' somiglia al titolo richiesto.

    Supporta sia 'Titolo (Live)' sia 'Artista - Album - Titolo - Live', evitando
    di penalizzare un album remasterizzato quando il titolo della traccia e' pulito.
    """
    stem = Path(path).stem.strip()
    parts = stem.split(' - ')
    if len(parts) == 1:
        return stem

    query_core = _strip_match_qualifiers(requested_title)
    if not query_core:
        query_core = norm_bare(requested_title)
    qtokens = set(query_core.split())
    qcompact = ''.join(query_core.split())

    scored = []
    for idx, part in enumerate(parts):
        core = _strip_match_qualifiers(part)
        if not core:
            core = norm_bare(part)
        ctokens = set(core.split())
        coverage = len(qtokens & ctokens) / max(1, len(qtokens))
        compact = ''.join(core.split())
        exact_compact = int(bool(qcompact) and compact == qcompact)
        ratio = difflib.SequenceMatcher(None, qcompact, compact).ratio() if qcompact and compact else 0.0
        # In parita', scegliere la componente piu' specifica, poi la piu' a destra
        # (utile per nomi 'Artista - Album - Titolo').
        scored.append(((exact_compact, coverage, ratio, len(ctokens), idx), idx))
    _, best_idx = max(scored, key=lambda item: item[0])
    selected = parts[best_idx]
    # Attacca solo i segmenti finali che sono etichette di versione pure:
    # 'Pictures of You - Live', 'Song - 2015 Remaster'.
    for part in parts[best_idx + 1:]:
        if _qualifier_only_component(part):
            selected += ' - ' + part
        else:
            break
    return selected


@lru_cache(maxsize=200_000)
def _title_variant_penalty_cached(path, requested_title):
    segment = _candidate_title_segment(path, requested_title)
    candidate_norm = norm_bare(segment)
    requested_norm = norm_bare(requested_title)
    qualifiers = (q for q in TITLE_MATCH_PENALTIES if q != _PARENTHESIS_PENALTY_KEY)
    requested_quals = {q for q in qualifiers if _contains_phrase(requested_norm, q)}
    candidate_quals = {q for q in TITLE_MATCH_PENALTIES
                       if q != _PARENTHESIS_PENALTY_KEY and _contains_phrase(candidate_norm, q)}

    penalty = 0.0
    raw_query = str(requested_title or '')
    # Extra parentesi nel filename: usa la stessa mappa configurabile delle altre penalita'.
    if not any(ch in raw_query for ch in '([{') and any(ch in segment for ch in '([{'):
        penalty += float(TITLE_MATCH_PENALTIES.get(_PARENTHESIS_PENALTY_KEY, 0.0))

    for qualifier in candidate_quals - requested_quals:
        penalty += float(TITLE_MATCH_PENALTIES.get(qualifier, 0.0))
    # Se Spotify chiede esplicitamente un live/demo, il candidato pulito non deve
    # battere quella versione richiesta.
    for qualifier in requested_quals - candidate_quals:
        penalty += float(TITLE_MATCH_PENALTIES.get(qualifier, 0.0)) * 1.5
    return penalty


def _title_variant_penalty(path, requested_title):
    return _title_variant_penalty_cached(str(path), str(requested_title or ''))


def _match_hit_key(hit, requested_title):
    """Chiave ordinata: qualita' del titolo prima di artista/album/stage."""
    return (_title_variant_penalty(hit[0], requested_title),
            -hit[4], -hit[1], -hit[5], -hit[3], str(hit[0]))


@lru_cache(maxsize=128)
def _match_fingerprint(path_string):
    # Chiamato solo in rarissimi pareggi; cache evita di decodificare due volte
    # lo stesso file quando la canzone ricorre in molte playlist.
    return fingerprint(Path(path_string))


def _waveform_tiebreak(paths):
    """Se due candidati hanno lo stesso punteggio testuale, usa il waveform SOLO
    per verificare se sono la stessa incisione; se lo sono, tiene il file migliore.
    Ritorna None quando il confronto non e' possibile o i file differiscono."""
    unique = sorted({str(p) for p in paths})
    if len(unique) != 2 or not _HAS_NP:
        return None
    p1, p2 = Path(unique[0]), Path(unique[1])
    if not p1.is_file() or not p2.is_file():
        return None
    tags1, dur1 = probe_dur(p1)
    tags2, dur2 = probe_dur(p2)
    if not _dur_compatible(dur1, dur2, 8.0):
        return None
    fp1, fp2 = _match_fingerprint(str(p1)), _match_fingerprint(str(p2))
    corr = correlate(fp1, fp2, stop_at=0.95) if fp1 is not None and fp2 is not None else None
    if corr is None or corr < 0.95:
        return None
    # Stessa incisione verificata: scegli il keeper secondo la politica esistente
    # (titolo, formato lossless e data), senza cancellare nessun file.
    try:
        k1, k2 = _keeper_score(p1, tags1), _keeper_score(p2, tags2)
    except Exception:
        k1, k2 = (len(p1.name), str(p1)), (len(p2.name), str(p2))
    winner = min(((k1, str(p1)), (k2, str(p2))))[1]
    print(f"[i] tie-break waveform: stessa incisione (corr={corr:.3f}); scelto {Path(winner).name}")
    return winner


def _best_match_hit(hits, requested_title, allow_penalized=False, use_waveform=True):
    """Restituisce hit senza qualificatori indesiderati; durante gli stage iniziali
    rinvia i match penalizzati per lasciare agli stage successivi la possibilita'
    di trovare il titolo originale. L'ultimo stage accetta la migliore alternativa."""
    by_path = {}
    for hit in hits:
        p = str(hit[0])
        prev = by_path.get(p)
        if prev is None or _match_hit_key(hit, requested_title) < _match_hit_key(prev, requested_title):
            by_path[p] = hit
    candidates = list(by_path.values())
    if not candidates:
        return None
    candidates.sort(key=lambda h: _match_hit_key(h, requested_title))
    if not allow_penalized:
        clean = [h for h in candidates if _title_variant_penalty(h[0], requested_title) <= 1e-9]
        if not clean:
            return None
        candidates = clean
        candidates.sort(key=lambda h: _match_hit_key(h, requested_title))
    # In caso di parita' su tutte le metriche semantiche, verifica eventuali
    # copie con il waveform; mai piu' di due file per evitare scansioni costose.
    rank = _match_hit_key(candidates[0], requested_title)[:-1]
    tied = [h for h in candidates if _match_hit_key(h, requested_title)[:-1] == rank]
    if use_waveform and len(tied) == 2:
        winner = _waveform_tiebreak([h[0] for h in tied])
        if winner:
            return next(h for h in tied if str(h[0]) == winner)
    return candidates[0]


def find_match(by_full, by_artist, by_strict, path_qual, artist, album, title,
               threshold, _trace=None):
    """Cerca il file della libreria per (artista, album, titolo). I risultati sono
    memoizzati per tutta l'esecuzione: le playlist Spotify si sovrappongono
    molto (stessi brani in 10 playlist) e i mancanti costavano il fuzzy
    ogni volta. Con _trace (diagnostica --explain) niente memo."""
    prep = _get_prep(by_full, by_artist, by_strict, path_qual)
    if _trace is not None:
        return _find_match_impl(prep, by_full, by_artist, by_strict, path_qual,
                                artist, album, title, threshold, _trace)
    key = (artist, album, title, threshold)
    if key in prep.memo:
        return prep.memo[key]
    res = prep.memo[key] = _find_match_impl(prep, by_full, by_artist, by_strict,
                                            path_qual, artist, album, title, threshold)
    return res


def _find_match_impl(prep, by_full, by_artist, by_strict, path_qual, artist, album,
                     title, threshold, _trace=None):
    # override per-singolo brano (FORCE_ARTIST da exportify_names.json)
    _fk = norm(f"{artist} - {title}")
    if _fk in FORCE_ARTIST:
        artist = FORCE_ARTIST[_fk]
    na, nal, nt = norm(artist), norm(album), norm(title)
    na = ALIASES.get(na, na)
    nb = norm_bare(title)   # forma query con parentesi (per varianti e qualificatori)

    # varianti in entrambe le scritture: kanji <-> romaji, con e senza spazi
    def _variants(s):
        out = {s}
        r = to_romaji(s)
        if r:
            out.add(r)                       # 'natsu mado'
            out.add(''.join(r.split()))      # 'natsumado'
        return out

    akeys = set()
    for a in split_artists(artist, by_artist):
        for base in {a, ALIASES.get(a, a), _canon(a)} - {''}:
            akeys |= _variants(base)
    if not nt:
        # titolo che norm() svuota ('(Nice Dream)'): riprova tenendo le parentesi
        nt = norm_bare(title)
        nts = {nt, ''.join(nt.split())} if nt else set()
    else:
        nts = _variants(nt)
        nts |= {''.join(v.split()) for v in list(nts)}
        # 'Orion - Remastered' -> 'orion'; 'Go - Extended Mix' -> 'go'
        first = norm(title.split(' - ')[0])
        if first and first != nt:
            nts |= {first, ''.join(first.split())}
        # la forma CON parentesi cerca anche chiavi che li conservano
        # (es. query "X (Cante Hondo Mix)" -> candidato lt "x cante hondo mix")
        if nb and nb != nt:
            nts |= {nb, ''.join(nb.split())}
    # ordine DETERMINISTICO: set di stringhe = ordine che cambia a ogni
    # esecuzione (PYTHONHASHSEED); nei pareggi il file scelto cambiava e la
    # m3u veniva riscritta (perdendo le modifiche fatte dai client)
    akeys = sorted(akeys)
    nts = sorted(nts)

    nalb = norm_bare(_preferred_name(album) or album)
    na_set = {na}
    _r = to_romaji(na)
    if _r:
        na_set.add(_r)

    def _artist_score(path):
        """2 se l'artista della cartella del file corrisponde ALL'artista
        della query (esatto o romaji), 1 altrimenti (gruppo/alias/fuzzy).
        Evita che un ARTIST_GROUPS che unisce due artisti faccia vincere
        il file sbagliato quando album e titolo coincidono."""
        tk = _top_keys(path)
        if tk is None:
            return 1
        fa, fr = tk
        if fa in na_set:
            return 2
        return 2 if fr and fr in na_set else 1

    def _alb_score(path):
        return _album_match(nalb, _alb_folder(path))

    # fallback conserva la migliore alternativa qualificata se nessuno stage trova
    # una versione pulita; in precedenza veniva scelta troppo presto una versione live/demo.
    fallback = None

    def _remember_fallback(hits):
        nonlocal fallback
        candidate = _best_match_hit(hits, title, allow_penalized=True, use_waveform=False)
        if candidate is not None and (fallback is None or
                _match_hit_key(candidate, title) < _match_hit_key(fallback, title)):
            fallback = candidate

    # 0) STRICT: titolo INTERO identico. Alcuni filename hanno un suffisso
    # separato ('Pictures of You - Live'), quindi possono esporre anche il titolo
    # base nello strict index: il penalty score fa vincere la versione pulita.
    st_full = norm_bare(title)
    if st_full:
        cands = []
        for a in akeys:
            for pth in (by_strict or {}).get((a, st_full), []):
                cands.append((pth, _alb_score(pth),
                              (path_qual or {}).get(pth, False), 0,
                              _artist_score(pth), 2))
        if cands:
            if _trace is not None:
                for c in cands:
                    _trace.append(('0-strict', c[0], c[1], c[2], 0, c[4]))
            best_hit = _best_match_hit(cands, title, allow_penalized=False)
            if best_hit is not None:
                if _trace is not None:
                    _trace.append(('=> vince stage 0', best_hit[0], best_hit[1],
                                   best_hit[2], best_hit[3], best_hit[4]))
                return best_hit[0]
            _remember_fallback(cands)

    # regola qualificatori: il penalty score distingue live/demo/instrumental ecc.
    q_qual = _has_qualifier(nt) or _has_qualifier(nb)

    def _qual(lt, path):
        # qualificato = chiave lt OPPURE filename (titolo puo' essere pulito
        # mentre il file e' la versione remaster: es. 'Fear of the Dark -
        # 2015 Remaster - ...flac' con title tag 'Fear of the Dark')
        return (_has_qualifier(lt)
                or (path_qual or {}).get(path, False)
                or _has_qualifier(norm_bare(Path(path).stem)))

    def _pick(hits):
        if not hits:
            return None
        best = _best_match_hit(hits, title, allow_penalized=False)
        if best is not None:
            if _trace is not None:
                _trace.append(('=> _pick', best[0], best[1], best[2],
                               best[3], best[4],
                               _title_variant_penalty(best[0], title)))
            return best[0]
        _remember_fallback(hits)
        return None

    # 1) esatto artista+album+titolo (anche qui vale la preferenza qualificatori)
    f1 = []
    for a in akeys:
        for pth in (by_full or {}).get((a, nal, nt), []):
            # bonus di specificita': se il NOME FILE contiene la variante
            # lunga della query (nb, parentesi inclusa), il candidato e'
            # piu' specifico degli altri che matchano solo il titolo secco.
            # Es. query "X (Live at...)" colpisce in pieno il file live,
            # non "X - Cante Hondo Mix" che matcha solo "X".
            spec = len(nt)
            if nb and nb != nt and nb in norm_bare(Path(pth).stem):
                spec += len(nb)
            f1.append((pth, _alb_score(pth), (path_qual or {}).get(pth, False), spec,
                       _artist_score(pth), 1))
    if _trace is not None:
        for h in f1:
            _trace.append(('1-art+alb+titolo', h[0], h[1], h[2], h[3], h[4]))
    got = _pick(f1)
    if got:
        if _trace is not None:
            _trace.append(('=> vince stage 1', got, '', '', '', ''))
        return got

    # 2) esatto artista+titolo. Se la query e' "pulita" (senza mix/version/...),
    #    i candidati che CONTENGONO parole-tipo sono deprioritizzati: vincono
    #    solo se non esiste nessun candidato pulito ("match se non trova altro").
    hits = []
    for a in akeys:
        idx = prep.by_lt(a)
        if not idx:
            continue
        for t in nts:
            for pth in idx.get(t, ()):
                hits.append((pth, _alb_score(pth), _qual(t, pth), len(t),
                             _artist_score(pth), 1))   # exact: batte contenimento

    # 3) contenimento del titolo dentro l'artista (stessa preferenza puliti)
    for a in akeys:
        lts4 = prep.lts4(a)
        if not lts4:
            continue
        idx = prep.by_lt(a)
        posd = prep.pos(a)
        for t in nts:
            if len(t) < 4:
                continue
            matched = []
            for lt in lts4:
                if t in lt or lt in t:
                    # specificita' = CIO' che ha matchato: t in lt -> vale tutta
                    # la variante t; lt in t -> vale solo la chiave corta lt.
                    # RANK 0: il contenimento non batte MAI l'exact match —
                    # altrimenti il nome dell'ALBUM dentro il filename (ogni
                    # traccia della cartella) supera il titolo vero (caso
                    # Iron Maiden 'Fear of the Dark - 2015 Remaster').
                    spec = len(t) if t in lt else len(lt)
                    matched.extend(zip(posd[lt], idx[lt], [lt] * len(idx[lt]),
                                       [spec] * len(idx[lt]), strict=True))
            matched.sort(key=lambda m: m[0])      # stesso ordine del pool originale
            for _pos, pth, lt, spec in matched:
                _h = (pth, _alb_score(pth), _qual(lt, pth), spec,
                      _artist_score(pth), 0)
                hits.append(_h)
                if _trace is not None:
                    _trace.append(('3-contenimento',) + _h)
    got = _pick(hits)
    if got:
        return got

    # 4) fuzzy sul titolo dentro l'artista (stessa preferenza puliti)
    hits = []
    for a in akeys:
        idx = prep.by_lt(a)
        if not idx:
            continue
        for t in nts:
            close = prep.fz_title(a, t, threshold)
            if close is not None:
                for pth in idx[close]:
                    _h = (pth, _alb_score(pth), _qual(close, pth), len(t),
                          _artist_score(pth), 1)
                    hits.append(_h)
                    if _trace is not None:
                        _trace.append(('4-fuzzy',) + _h)
    got = _pick(hits)
    if got:
        return got

    # 5) artista approssimativo su tutta la libreria (anche in romaji). Raccoglie
    # tutti i candidati prima di sceglierli, cosi' le versioni live/demo non vincono
    # solo perche' compaiono prima nell'indice fuzzy.
    hits = []
    for akey in akeys:
        if len(akey) < 4 or len(nt) < 5:
            continue
        close_a = prep.fz_artist(akey, 0.85)
        if close_a is not None:
            idx = prep.by_lt(close_a)
            lens = prep.lens(close_a)
            for t in nts:
                close_t = _close1(t, lens, max(threshold, 0.85))
                if close_t is not None:
                    for pth in idx[close_t]:
                        hits.append((pth, _alb_score(pth), _qual(close_t, pth),
                                     len(t), _artist_score(pth), 1))
    got = _best_match_hit(hits, title, allow_penalized=True)
    if got is not None:
        return got[0]
    if fallback is not None:
        return fallback[0]
    return None


def csv_override(csv_stem, artist, title):
    """Override per-riga da CSV_FIX (exportify_names.json): None o dict
    con chiavi 'artist'/'album' da sostituire prima del matching."""
    rows = CSV_FIX.get(norm(csv_stem))
    if not rows:
        return None
    return rows.get(norm(f"{artist} - {title}"))


def pick_col(fieldnames, candidates):
    for c in candidates:
        if c in fieldnames:
            return c
    return None



def _name_key(s):
    """Chiave di confronto dei nomi playlist: NFKC, minuscolo, e ogni sequenza di caratteri non
    alfanumerici (spazi, '_', punteggiatura, emoji) diventa UNO spazio. Exportify cambia i
    caratteri speciali nei nomi file: 'entra?' -> entra_.csv, 'Stello + chic<emoji>' ->
    'Stello _ chic_.csv'; con questa chiave coincidono comunque."""
    return re.sub(r'[\W_]+', ' ', unicodedata.normalize('NFKC', s).casefold()).strip()


def _skip_patterns(extra='', user=None):
    """[(voce originale, pattern)] per l'utente; --skip resta globale alla run. '*' = jolly."""
    user_key = str(user or DEFAULT_USER).strip().casefold()
    configured = SKIP_PLAYLISTS.get(user_key, [])
    raws = [x.strip() for x in extra.split(',') if x.strip()] + [x for x in configured if x.strip()]
    return [(r, '*'.join(_name_key(part) for part in r.split('*'))) for r in raws]


_SKIP_HITS = set()       # (utente casefold, voce) che ha ignorato almeno un CSV
_SKIPPED_NAMES = []      # (utente, nome playlist) ignorati in questa run
_SKIP_FILES_SEEN = [0]   # CSV esaminati da select_playlists in questa run


def report_skips(args, users=None):
    """Riepilogo per utente: le voci JSON sono verificate solo sui CSV del loro utente."""
    user_names = list(dict.fromkeys(str(u or DEFAULT_USER).strip() for u in (users or [DEFAULT_USER])))
    if _SKIPPED_NAMES:
        shown_items = [f'{u}: {name}' for u, name in _SKIPPED_NAMES]
        shown = ', '.join(shown_items[:8]) + (' ...' if len(shown_items) > 8 else '')
        print(f"[i] playlist ignorate (SKIP_PLAYLISTS/--skip): {len(_SKIPPED_NAMES)}: {shown}",
              file=sys.stderr)
    unmatched = []
    for user_name in user_names:
        user_key = user_name.casefold()
        for raw, _pattern in _skip_patterns(args.skip or '', user=user_name):
            if (user_key, raw) not in _SKIP_HITS:
                unmatched.append((user_name, raw))
    if unmatched and not args.only and _SKIP_FILES_SEEN[0]:
        details = ', '.join(f'{user}: {raw}' for user, raw in unmatched)
        print(f"[i] voci di SKIP_PLAYLISTS/--skip senza CSV corrispondente per l'utente in questa run: "
              f"{details}", file=sys.stderr)


def interactive_pick(files):
    """Mostra l'elenco numerato e lascia scegliere: '1,3,5-8' o 'tutte'."""
    for i, f in enumerate(files, 1):
        print(f"  {i:3d}. {f.stem}")
    raw = input("Playlist da importare (es. '1,3,5-9' oppure INVIO=tutte): ").strip()
    if not raw:
        return files
    want = set()
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, _, b = part.partition('-')
            if a.strip().isdigit() and b.strip().isdigit():
                want.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            want.add(int(part))
    chosen = [f for i, f in enumerate(files, 1) if i in want]
    print(f"[i] selezionate {len(chosen)}/{len(files)}")
    return chosen


def select_playlists(files, args, user=None):
    if args.only:
        keep = {_name_key(x) for x in args.only.split(',') if x.strip()}
        files = [f for f in files if _name_key(f.stem) in keep]
    user_key = str(user or DEFAULT_USER).strip().casefold()
    pats = _skip_patterns(args.skip or '', user=user)
    _SKIP_FILES_SEEN[0] += len(files)
    if pats:
        kept = []
        for f in files:
            key = _name_key(f.stem)
            hits = [raw for raw, pat in pats if fnmatch.fnmatchcase(key, pat)]
            if not hits:
                kept.append(f)
            else:
                _SKIP_HITS.update((user_key, raw) for raw in hits)  # tutte le voci corrispondenti
                _SKIPPED_NAMES.append((user or DEFAULT_USER, f.stem.replace('_', ' ').strip()))
        files = kept
    if args.pick and sys.stdin.isatty():
        files = interactive_pick(files)
    return files

def _sync_missing_file(rep: Path, missing):
    """Allinea il .missing.txt di una playlist alla realta' di adesso."""
    if missing:
        txt = '\n'.join(missing) + '\n'
        try:
            if rep.exists() and rep.read_text(encoding='utf-8', errors='replace') == txt:
                return
        except OSError:
            pass
        rep.write_text(txt, encoding='utf-8')
    elif rep.exists():
        rep.unlink()


def report_missing(files, by_full, by_artist, by_strict, path_qual, threshold, out='-'):
    """Elenco di TUTTE le tracce che mancano in libreria, RICALCOLATO adesso dai
    CSV delle playlist attive contro la libreria attuale. Non legge i
    .missing.txt (che possono contenere righe vecchie: playlist saltate, rinominate
    o cancellate), non scrive playlist e non tocca nulla."""
    missing = {}
    n_rows = 0
    for csv_path in files:
        raw = csv_path.read_bytes()
        with io.StringIO(raw.decode('utf-8-sig')) as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []
            ct = pick_col(fieldnames, COLS['title'])
            ca = pick_col(fieldnames, COLS['artist'])
            cal = pick_col(fieldnames, COLS['album'])
            if (not ct or not ca) and not cu:
                print(f"[!] {csv_path.name}: intestazioni non riconosciute, saltato", file=sys.stderr)
                continue
            for row in reader:
                title = (row.get(ct) or '').strip().strip('"')
                artist = clean_artist(row.get(ca))
                album = (row.get(cal) or '').strip().strip('"') if cal else ''
                if not title or not artist:
                    continue
                n_rows += 1
                ov = csv_override(csv_path.stem, artist, title)
                if ov:
                    artist = ov.get('artist', artist)
                    album = ov.get('album', album)
                path = find_match(by_full, by_artist, by_strict, path_qual,
                                  artist, album, title, threshold)
                if not path and album:
                    path = find_match(by_full, by_artist, by_strict, path_qual,
                                      artist, '', title, threshold)
                if not path:
                    cu = _csv_user(csv_path)
                    pl = (f"{cu}: " if cu != DEFAULT_USER else '') + re.sub(r'\s+_\s+', ' / ', csv_path.stem)
                    missing.setdefault((artist, album, title), set()).add(pl)
    rows = sorted(missing, key=lambda k: (k[0].lower(), k[1].lower(), k[2].lower()))
    text = ''.join(f"{a} - {al} - {t}\n" for a, al, t in rows)
    if out and out != '-':
        Path(out).expanduser().write_text(text, encoding='utf-8')
        print(f"[i] elenco scritto in {Path(out).expanduser()}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    arts = Counter(k[0] for k in rows)
    albs = Counter((k[0], k[1]) for k in rows)
    print(f"[i] {len(rows)} tracce mancanti ({len(arts)} artisti, {len(albs)} album) "
          f"su {n_rows} righe di {len(files)} playlist", file=sys.stderr)
    if albs:
        print("[i] album con piu' tracce mancanti:", file=sys.stderr)
        for (a, al), c in albs.most_common(12):
            print(f"      {c:3}  {a} - {al}", file=sys.stderr)


def _playlist_sidecar_paths(m3u_path):
    """Percorsi sidecar artwork con lo stesso basename della M3U (inclusi nomi con punti)."""
    base = str(Path(m3u_path).with_suffix(''))
    return [Path(base + ext) for ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif')]


def _image_extension(data, content_type=''):
    """Estensione per i formati immagine supportati da Navidrome, verificata dai magic bytes."""
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    return ''


def _download_spotify_image(url):
    """Scarica una cover HTTPS dai CDN Spotify con timeout e limite dimensioni."""
    url = _spotify_image_url(url)
    if not url:
        raise ValueError('URL artwork non riconosciuto come CDN Spotify')
    request = urllib.request.Request(url, headers={'User-Agent': f'exportify-to-m3u/{VERSION}'})
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get('Content-Type', '')
        length = response.headers.get('Content-Length')
        if length and length.isdigit() and int(length) > 20 * 1024 * 1024:
            raise ValueError('immagine oltre il limite di 20 MiB')
        data = response.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError('immagine oltre il limite di 20 MiB')
    ext = _image_extension(data, content_type)
    if not ext:
        raise ValueError(f'formato immagine non supportato ({content_type or "tipo sconosciuto"})')
    return data, ext


def _sync_playlist_artwork(m3u_path, image_url, state, dry_run=False, metadata_present=False):
    """Allinea la cover Spotify al sidecar Navidrome senza bloccare l'import playlist."""
    image_url = _spotify_image_url(image_url)
    current_file = state.get('art_file') if isinstance(state, dict) else None
    if not image_url:
        # Se la playlist ha metadati freschi ma Spotify non espone una cover, rimuove solo
        # la cover generata da questa pipeline (non immagini non tracciate nel sync state).
        if metadata_present and current_file and not dry_run:
            candidate = Path(m3u_path).parent / Path(current_file).name
            try:
                if candidate in _playlist_sidecar_paths(m3u_path):
                    candidate.unlink(missing_ok=True)
                if isinstance(state, dict):
                    state.pop('art_url', None)
                    state.pop('art_file', None)
            except OSError as e:
                print(f"[warn] cover playlist non rimossa ({candidate.name}): {e}", file=sys.stderr)
        return

    sidecars = _playlist_sidecar_paths(m3u_path)
    if (isinstance(state, dict) and state.get('art_url') == image_url and
            state.get('art_file') and
            (Path(m3u_path).parent / Path(state['art_file']).name).is_file()):
        return
    if dry_run:
        print(f"[dry-run] cover Spotify: {Path(m3u_path).stem}")
        return
    try:
        data, ext = _download_spotify_image(image_url)
        target = Path(str(Path(m3u_path).with_suffix('')) + ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + '.tmp')
        tmp.write_bytes(data)
        os.replace(tmp, target)
        for old in sidecars:
            if old != target:
                old.unlink(missing_ok=True)
        if isinstance(state, dict):
            state['art_url'] = image_url
            state['art_file'] = target.name
    except Exception as e:
        print(f"[warn] cover Spotify non importata per {Path(m3u_path).name}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)


def _legacy_playlist_basename(csv_stem):
    """Restituisce il basename creato dalla vecchia logica e l'eventuale sottocartella."""
    raw = re.sub(r'\s+_\s+', ' / ', csv_stem)
    base = re.sub(r'\s+', ' ', raw.replace('_', ' ')).strip()
    folder = None
    m_sep = re.match(r'^(.+?)\s+/\s+(.+)$', base)
    if m_sep:
        folder, base = m_sep.group(1).strip(), m_sep.group(2).strip()
    base = base.replace('/', ' - ')
    return base, folder


def _remove_legacy_playlist(root, user, old_base, old_folder, new_path, dry_run):
    """Rimuove la M3U vecchia, sanitizzata, quando viene sostituita dal nome Spotify esatto."""
    if dry_run or not old_base:
        return
    candidates = {Path(root) / f'{old_base}.m3u'}
    if old_folder:
        candidates.add(Path(root) / old_folder / f'{old_base}.m3u')
    for old_path in candidates:
        if old_path == Path(new_path) or not old_path.is_file():
            continue
        try:
            old_path.unlink()
            old_path.with_suffix('.missing.txt').unlink(missing_ok=True)
            for art in _playlist_sidecar_paths(old_path):
                art.unlink(missing_ok=True)
            SYNC_STATE.pop(_sync_key(user, old_base), None)
            print(f"[i] nome playlist corretto: rimossa vecchia M3U {old_path.name}")
        except OSError as e:
            print(f"[warn] vecchia M3U {old_path.name} non rimossa: {e}", file=sys.stderr)


def _spotify_local_uri_metadata(uri):
    """Fallback per CSV che non riportano i tag testuali di una URI spotify:local."""
    value = str(uri or '').strip()
    if not value.lower().startswith('spotify:local:'):
        return None
    parts = value.split(':', 5)
    if len(parts) != 6:
        return None
    try:
        artist = urllib.parse.unquote_plus(parts[2])
        album = urllib.parse.unquote_plus(parts[3])
        title = urllib.parse.unquote_plus(parts[4])
        duration = int(parts[5])
    except (ValueError, TypeError):
        return None
    if not title and not artist:
        return None
    return {'artist': artist, 'album': album, 'title': title, 'duration': duration}


def process_csv(csv_path, by_full, by_artist, by_strict, path_qual, args, user=None):
    user = user or DEFAULT_USER
    root = _user_playlist_root(user)
    tag = f"[{user}] " if user != DEFAULT_USER else ''
    playlist_meta = _read_playlist_meta_for_csv(csv_path)
    metadata_present = isinstance(playlist_meta, dict)
    # Se catturato dal fetch, il report usa il titolo originale Spotify (case/emoji/punteggiatura).
    legacy_report_name = re.sub(r'\s+', ' ', re.sub(r'\s+_\s+', ' / ', csv_path.stem)
                                .replace('_', ' ')).strip()
    pl_name = (str(playlist_meta.get('name')).strip()
               if metadata_present and playlist_meta.get('name') else legacy_report_name)
    raw = csv_path.read_bytes()
    h = hashlib.md5(raw).hexdigest()
    with io.StringIO(raw.decode('utf-8-sig')) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        ct = pick_col(fieldnames, COLS['title'])
        ca = pick_col(fieldnames, COLS['artist'])
        cal = pick_col(fieldnames, COLS['album'])
        cu = pick_col(fieldnames, COLS['uri'])
        if not ct or not ca:
            print(f"[ERRORE] {csv_path.name}: intestazioni non riconosciute: {fieldnames[:8]}",
                  file=sys.stderr)
            return False

        matched, missing, seen, skipped, local_rows = [], [], 0, 0, 0
        seen_paths = set()
        rows = list(reader)
        progress = _ProgressBar('matching playlist', len(rows), 'brani', stream=sys.stdout)
        for row_index, row in enumerate(rows, 1):
            progress.update(row_index)
            local_meta = _spotify_local_uri_metadata(row.get(cu)) if cu else None
            if local_meta:
                local_rows += 1
            title = (row.get(ct) or '').strip().strip('"') or (local_meta or {}).get('title', '')
            artist = clean_artist(row.get(ca) or (local_meta or {}).get('artist', ''))
            album = ((row.get(cal) or '').strip().strip('"') if cal else '') or (local_meta or {}).get('album', '')
            if not title or not artist:
                skipped += 1
                continue
            seen += 1
            ov = csv_override(csv_path.stem, artist, title)
            if ov:
                artist = ov.get('artist', artist)
                album = ov.get('album', album)
            SEEN_ALL.setdefault((artist, album, title), set()).add((user, pl_name))
            path = find_match(by_full, by_artist, by_strict, path_qual,
                              artist, album, title, args.threshold)
            if not path and album:
                # retry senza album: stessa canzone puo' avere stringhe
                # album diverse tra playlist (una matcha, l'altra no)
                path = find_match(by_full, by_artist, by_strict, path_qual,
                                  artist, '', title, args.threshold)
            if path:
                if path in seen_paths:      # niente duplicati nella playlist
                    continue
                seen_paths.add(path)
                matched.append((artist, title, path))
            else:
                missing.append(f"{artist} - {album} - {title}")
                MISSING_ALL.setdefault((artist, album, title), set()).add((user, pl_name))
        progress.close(complete=True)

    # IL FIX CHIAVE: niente piu' playlist vuote senza spiegazione
    if seen == 0:
        print(f"[ERRORE] {csv_path.name}: 0 brani letti dal CSV "
              f"(colonne: {fieldnames[:8]})", file=sys.stderr)
        return False

    # Senza metadati restiamo compatibili con i CSV esistenti. Con --fetch, invece,
    # il nome viene dalla playlist Spotify e non dal filename sanitizzato (che puo' aver
    # perso case, emoji, slash e altri caratteri).
    legacy_base, legacy_folder = _legacy_playlist_basename(csv_path.stem)
    spotify_name = (str(playlist_meta.get('name')).strip()
                    if metadata_present and playlist_meta.get('name') else '')
    auto_folder = None
    if spotify_name:
        original_title = spotify_name
        base = _playlist_filename(original_title)
        orig_base = base
    else:
        original_title = ''
        raw = re.sub(r'\s+_\s+', ' / ', csv_path.stem)
        base = re.sub(r'\s+', ' ', raw.replace('_', ' ')).strip()
        orig_base = base
        # Legacy naming: "cartella / titolo" viene messo in una sottocartella.
        m_sep = re.match(r'^(.+?)\s+/\s+(.+)$', base)
        if m_sep:
            auto_folder, base = m_sep.group(1).strip(), m_sep.group(2).strip()

    if not spotify_name:
        base = base.replace('/', ' - ')  # legacy fallback: '/' non e' ammesso nei basename
    folder = (PLAYLIST_FOLDERS.get(original_title) if original_title else None) or \
             PLAYLIST_FOLDERS.get(base) or PLAYLIST_FOLDERS.get(base.lower()) or auto_folder
    out_dir = (root / folder) if folder else root
    out_path = out_dir / f"{base}.m3u"
    if not args.dry_run:        # il dry-run non crea cartelle ne' cancella nulla
        out_dir.mkdir(parents=True, exist_ok=True)
        if folder:      # spostata in sottocartella: rimuovi i file piatti vecchi (nome nuovo e originale)
            for name in {base, orig_base}:
                for stale in (root / f"{name}.m3u", root / f"{name}.missing.txt"):
                    if stale.exists():
                        stale.unlink()
    cur_paths = [path for _, _, path in matched]
    skey = _sync_key(user, base)
    st = SYNC_STATE.get(skey)
    if isinstance(st, str):          # formato vecchio: solo hash
        st = {'h': st, 'paths': None}
    if not isinstance(st, dict):
        st = {}
    # La cover si sincronizza anche se l'hash CSV non e' cambiato (es. cover modificata su Spotify).
    _sync_playlist_artwork(out_path,
                           playlist_meta.get('image_url') if metadata_present else None,
                           st, dry_run=args.dry_run, metadata_present=metadata_present)
    if (not args.force and st.get('h') == h
            and st.get('paths') == cur_paths and out_path.exists()):
        if not args.dry_run:
            SYNC_STATE[skey] = st
            if spotify_name and base != legacy_base:
                _remove_legacy_playlist(root, user, legacy_base, legacy_folder, out_path, args.dry_run)
        print(f"{tag}{out_path.name}: invariata (modifiche lato client preservate)"
              f"{f', {local_rows} tracce Spotify Local Files' if local_rows else ''}")
        # la m3u non si tocca, ma il .missing.txt si': se una riga prima mancante ora
        # combacia con un file GIA' presente nella playlist (duplicato scartato) i percorsi
        # non cambiano e il vecchio report restava con righe false
        if not args.dry_run:
            _sync_missing_file(out_dir / f"{base}.missing.txt", missing)
        _record_generated_m3u(user, out_path)
        return True

    lines = ['#EXTM3U']
    for artist, title, path in matched:
        # solo il PREFISSO (str.replace sostituiva ogni occorrenza nel path)
        container_path = (JELLYFIN_ROOT + path[len(MUSIC_ROOT):]
                          if path.startswith(MUSIC_ROOT) else path)
        lines.append(f"#EXTINF:-1,{artist} - {title}")
        lines.append(container_path)

    if not args.dry_run:
        out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        st.update({'h': h, 'paths': cur_paths})
        SYNC_STATE[skey] = st
        if spotify_name and base != legacy_base:
            _remove_legacy_playlist(root, user, legacy_base, legacy_folder, out_path, args.dry_run)

    mode = "[dry-run] " if args.dry_run else ""
    print(f"{mode}{tag}{out_path.name}: {len(matched)}/{seen} match"
          f"{f', {len(missing)} mancanti' if missing else ''}"
          f"{f', {skipped} righe vuote saltate' if skipped else ''}"
          f"{f', {local_rows} tracce Spotify Local Files' if local_rows else ''}")
    if missing:
        rep = out_dir / f"{base}.missing.txt"
        if not args.dry_run:
            rep.write_text('\n'.join(missing) + '\n', encoding='utf-8')
        for m in missing[:10]:
            print(f"    MISSING: {m}")
        if len(missing) > 10:
            print(f"    ... e altri {len(missing) - 10} (vedi {rep.name})")
    elif not args.dry_run:
        stale = out_dir / f"{base}.missing.txt"
        if stale.exists():
            stale.unlink()          # non manca piu' nulla: elimina il report stale
    _record_generated_m3u(user, out_path)
    return True



def library_gap_report(root):
    """Classifica i .missing.txt: album ASSENTE in libreria vs PRESENTE ma non
    matchato. Per i presenti ritorna titoli mancanti + elenco file ricorsivo."""
    root = Path(root)
    artist_dirs = {norm(d.name): d.name for d in root.iterdir() if d.is_dir()}
    gaps, order = {}, []
    for mp in sorted(PLAYLIST_DIR.rglob('*.missing.txt')):
        for line in mp.read_text(errors='replace').splitlines():
            parts = line.split(' - ')
            if len(parts) < 2:
                continue
            artist, album = parts[0], parts[1]
            title = ' - '.join(parts[2:]) if len(parts) > 2 else ''
            if (artist, album) not in gaps:
                gaps[(artist, album)] = []
                order.append((artist, album))
            if title and title not in gaps[(artist, album)]:
                gaps[(artist, album)].append(title)
    assenti, presenti = [], []
    for artist, album in order:
        na = norm(artist)
        folder = artist_dirs.get(na)
        if not folder:
            close = difflib.get_close_matches(na, list(artist_dirs), n=1, cutoff=0.7)
            folder = artist_dirs[close[0]] if close else None
        if not folder:
            assenti.append((artist, album))
            continue
        albums = [d for d in (root / folder).iterdir() if d.is_dir()]
        norms = [norm(a.name) for a in albums]
        close_a = difflib.get_close_matches(norm(album), norms, n=1, cutoff=0.6)
        if not close_a:
            assenti.append((artist, album))
            continue
        real = albums[norms.index(close_a[0])]
        files = sorted(str(f.relative_to(real)) for f in real.rglob('*')
                       if f.is_file() and f.suffix.lower() in AUDIO_EXT)
        presenti.append((artist, album, real, files, gaps[(artist, album)]))
    return assenti, presenti


def print_gap_report(root, max_files=40):
    """Scrive il report su PLAYLIST_DIR/_report.txt; in console solo una riga."""
    assenti, presenti = library_gap_report(root)
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    L = [f"===== REPORT LIBRERIA {stamp}: {len(assenti)} assenti, "
         f"{len(presenti)} presenti-ma-non-matchati =====", ""]
    if not assenti and not presenti:
        L.append("Tutto matchato, nessun missing.")
    L.append("--- ASSENTI (album non in libreria) ---")
    for artist, album in assenti:
        L.append(f"  {artist} / {album}")
    L.append("")
    L.append("--- PRESENTI ma non matchati (con file della cartella) ---")
    for artist, album, real, files, titles in presenti:
        L.append(f"{artist} / {album}")
        L.append(f"    mancanti: {', '.join(titles) if titles else '(titolo sconosciuto)'}")
        L.append(f"    -> {real}")
        for f in files[:max_files]:
            L.append(f"       {f}")
        if len(files) > max_files:
            L.append(f"       ... e altri {len(files) - max_files}")
        L.append("")
    out = PLAYLIST_DIR / '_report.txt'
    out.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f"[i] report: {len(assenti)} assenti, {len(presenti)} presenti"
          f" non matchati -> {out}")

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / 'logs'
SKIP_TOP = {'playlists', '.stfolder', '@eadir'}


class Tee(io.TextIOBase):
    """Write atomically to the terminal and a plain-text log.

    ``print()`` normally calls ``write(text)`` and ``write("\n")`` separately.
    Without line buffering, the progress ticker could redraw between those calls,
    leaving a message suffix attached to the pinned status row. Console fragments are
    therefore held until newline/flush and emitted as one locked write. The log still
    receives each fragment immediately, without ANSI controls.
    """
    def __init__(self, *streams):
        self.streams = streams
        self._console_pending = ''
        self._console_lock = threading.RLock()
        self._log_lock = threading.RLock()

    def _flush_console_pending_locked(self, force=False):
        if not self.streams:
            self._console_pending = ''
            return
        pending = self._console_pending
        if not pending:
            return
        if not force and '\n' not in pending:
            return
        if force:
            ready, self._console_pending = pending, ''
        else:
            # Emit all complete lines together; keep only the final partial line buffered.
            end = pending.rfind('\n') + 1
            ready, self._console_pending = pending[:end], pending[end:]
        if not ready:
            return
        st = self.streams[0]
        terminal_text = _colorize_terminal_text(ready, st)
        with _PROGRESS_TERMINAL_IO_LOCK:
            st.write(terminal_text)
            st.flush()

    def write(self, s):
        if not s:
            return 0
        # Legacy carriage-return redraws are console-only. Flush any preceding partial
        # line first so a redraw cannot leapfrog buffered user output.
        is_redraw = ('\r' in s and '\n' not in s) or s in {'\x1b[?7l', '\x1b[?7h'}
        with self._console_lock:
            if is_redraw:
                self._flush_console_pending_locked(force=True)
                if self.streams:
                    with _PROGRESS_TERMINAL_IO_LOCK:
                        self.streams[0].write(s)
                        self.streams[0].flush()
            else:
                self._console_pending += s
                self._flush_console_pending_locked(force=False)
        # Preserve message order in the e2m file and never copy ANSI escapes into it.
        if not is_redraw:
            with self._log_lock:
                for st in self.streams[1:]:
                    try:
                        st.write(_ANSI_RE.sub('', s))
                    except Exception:
                        pass
        return len(s)

    def isatty(self):
        try:
            return bool(self.streams and self.streams[0].isatty())
        except Exception:
            return False

    def flush(self):
        with self._console_lock:
            self._flush_console_pending_locked(force=True)
            for st in self.streams:
                try:
                    st.flush()
                except Exception:
                    pass


RUN_LOG_PATH = None


def _log_command_tag(argv, known_options=()):
    """Opzioni usate, senza '--' e unite da '+': ['--fetch', '--all', '--apply'] -> 'fetch+all+apply'.
    Le abbreviazioni di argparse (--dry) diventano il nome intero (dry-run). Nessuna opzione =
    'playlists' (la pipeline predefinita)."""
    names = []
    for a in argv:
        if not a.startswith('--') or len(a) <= 2:
            continue
        opt = a.split('=', 1)[0]
        if opt not in known_options:
            hit = [o for o in known_options if o.startswith(opt)]
            if len(hit) == 1:
                opt = hit[0]
        name = re.sub(r'[^A-Za-z0-9_-]', '', opt[2:])
        if name and name not in names:
            names.append(name)
    tag = '+'.join(names) or 'playlists'
    return tag if len(tag) <= 150 else tag[:147] + '...'


def open_run_log(tag='playlists'):
    """UN SOLO log per esecuzione: logs/e2m_<opzioni>_AAAAMMGG_HHMMSS.log (es.
    e2m_fetch+all+apply_20261018_023002.log). Contiene tutto: playlist, fasi di manutenzione,
    scan Navidrome, errori e traceback."""
    global RUN_LOG_PATH
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    RUN_LOG_PATH = LOG_DIR / f'e2m_{tag}_{stamp}.log'
    return open(RUN_LOG_PATH, 'a', encoding='utf-8')


def _embed_report_in_main_log(title, lines):
    """Incorpora report lunghi nel log e2m senza riversarli tutti sulla console."""
    body = '\n'.join(str(line) for line in lines).rstrip() + '\n'
    if RUN_LOG_PATH:
        # Flush dei Tee prima di aprire lo stesso file per append evita che output bufferizzato
        # dalle fasi precedenti finisca dopo il report.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        with Path(RUN_LOG_PATH).open('a', encoding='utf-8') as fh:
            fh.write(f"\n\n===== INIZIO REPORT INCORPORATO: {title} =====\n")
            fh.write(body)
            fh.write(f"===== FINE REPORT INCORPORATO: {title} =====\n")
            fh.flush()
        print(f'[i] report completo {title} incorporato nel log principale: {RUN_LOG_PATH}',
              file=sys.stderr, flush=True)
    else:
        # Utile per chiamate di test/import fuori dal normale entrypoint CLI.
        print(f"\n===== INIZIO REPORT: {title} =====")
        print(body, end='')
        print(f"===== FINE REPORT: {title} =====")


# tracce dell'esecuzione: (artista, album, titolo) -> {(utente, playlist)}
MISSING_ALL = {}      # quelle NON trovate in libreria
SEEN_ALL = {}         # TUTTE quelle lette dai CSV (servono ai totali X/Y)
MISSING_TOP_PLAYLISTS = 20
MISSING_TOP_ALBUMS = 10


def _ratio(x, y):
    """'12/340 (3.5%)'"""
    return f"{x}/{y} ({100 * x / y:.1f}%)" if y else f"{x}/{y}"


def _found_ratio(missing, total):
    """'3786/4788 (79.1%), 1002 brani rimasti': TROVATI/totale, percentuale dei trovati e quanti
    ne restano da trovare. Usato da mancanti_*.txt."""
    found = total - missing
    pct = f" ({100 * found / total:.1f}%)" if total else ''
    return f"{found}/{total}{pct}, {_plural(missing, 'brano rimasto', 'brani rimasti')}"


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def write_missing_report(partial=False):
    """logs/mancanti_AAAA-MM-GG.txt, ricalcolato a ogni esecuzione (stesso giorno = file
    sovrascritto). In cima le statistiche (totale, per utente, playlist e album piu' carenti),
    IN FONDO l'elenco completo delle tracce non trovate.
    Una traccia (artista, album, titolo) vale 1 anche se sta in piu' playlist o utenti."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    out = LOG_DIR / f'mancanti_{now:%Y-%m-%d}.txt'
    rows = sorted(MISSING_ALL, key=lambda k: tuple(x.lower() for x in k))
    users = sorted({u for v in SEEN_ALL.values() for u, _ in v}, key=str.lower)
    multi = len(users) > 1

    def label(u, pl):
        return f"{u}: {pl}" if multi else pl

    head = f'# tracce mancanti - esecuzione {now:%Y-%m-%d %H:%M}'
    if partial:
        head += ' (PARZIALE: playlist/utenti filtrati con --only/--skip/--users/CSV specifici)'
    L = [head,
         f"# TOTALE: {_found_ratio(len(MISSING_ALL), len(SEEN_ALL))}"
         + (f" | utenti: {', '.join(users)}" if users else ''),
         "# X/Y = tracce TROVATE in libreria / tracce uniche lette dai CSV (con la percentuale dei trovati); "
         "'brani rimasti' = quelle ancora da trovare (lo stesso brano in piu' playlist o utenti conta 1)", '']

    if MISSING_ALL:
        # ---- per utente
        if multi:
            seen_u, miss_u = Counter(), Counter()
            for v in SEEN_ALL.values():
                for u in {u for u, _ in v}:
                    seen_u[u] += 1
            for v in MISSING_ALL.values():
                for u in {u for u, _ in v}:
                    miss_u[u] += 1
            w = max(len(u) for u in users)
            L.append('=== PER UTENTE (canzoni trovate / canzoni dell\'utente) ===')
            for u in sorted(users, key=lambda u: (-miss_u[u], u.lower())):
                L.append(f"  {u:<{w}}  {_found_ratio(miss_u[u], seen_u[u])}")
            L.append('')
            # per gruppo ESATTO di utenti a cui la canzone manca (prima i gruppi piu' grandi)
            dist = Counter(tuple(sorted({u for u, _ in v}, key=str.lower))
                           for v in MISSING_ALL.values())
            L.append('=== QUANTE CANZONI MANCANO A QUANTI UTENTI ===')
            for grp in sorted(dist, key=lambda g: (-len(g), -dist[g], [x.lower() for x in g])):
                L.append(f"  {_plural(dist[grp], 'canzone mancante', 'canzoni mancanti')} a "
                         f"{', '.join(grp)}")
            L.append('')

        # ---- playlist con piu' canzoni mancanti
        seen_p, miss_p = Counter(), Counter()
        for v in SEEN_ALL.values():
            for up in v:
                seen_p[up] += 1
        for v in MISSING_ALL.values():
            for up in v:
                miss_p[up] += 1
        top_p = sorted(miss_p, key=lambda up: (-miss_p[up], -miss_p[up] / seen_p[up],
                                               up[1].lower(), up[0].lower()))[:MISSING_TOP_PLAYLISTS]
        L.append(f"=== PLAYLIST CON PIU' CANZONI MANCANTI "
                 f"(prime {len(top_p)} su {len(miss_p)} con mancanti) ===")
        for i, up in enumerate(top_p, 1):
            L.append(f"  {i:>2}. {label(*up)}  {_found_ratio(miss_p[up], seen_p[up])}")
        L.append('')

        # ---- album da scaricare (per numero di canzoni mancanti)
        seen_a, miss_a, who_a, name_a, source_a = Counter(), Counter(), {}, {}, {}
        for (a, al, t), sources in SEEN_ALL.items():
            if al:
                ak = (a.lower(), al.lower())
                seen_a[ak] += 1
                name_a.setdefault(ak, (a, al))
                source_a.setdefault(ak, set()).update(sources)
        for (a, al, t), v in MISSING_ALL.items():
            if al:
                ak = (a.lower(), al.lower())
                miss_a[ak] += 1
                who_a.setdefault(ak, set()).update(u for u, _ in v)
        top_a = sorted(miss_a, key=lambda ak: (-miss_a[ak], -miss_a[ak] / seen_a[ak], ak))[:MISSING_TOP_ALBUMS]
        L.append(f"=== {len(top_a)} ALBUM DA SCARICARE (per canzoni mancanti) ===")
        L.append("# X/Y = canzoni trovate / canzoni di quell'album presenti nelle playlist")
        L.append("# Sono album dedotti dalle playlist attive, non nomi di playlist mancanti/cancellate.")
        for i, ak in enumerate(top_a, 1):
            a, al = name_a[ak]
            who = f"  [utenti: {', '.join(sorted(who_a[ak], key=str.lower))}]" if multi else ''
            sources = sorted((label(u, pl) for u, pl in source_a.get(ak, set())), key=str.casefold)
            if len(sources) > 8:
                source_text = ', '.join(sources[:8]) + f", ... (+{len(sources) - 8})"
            else:
                source_text = ', '.join(sources) if sources else '(nessuna fonte)'
            L.append(f"  {i:>2}. {a} - {al}  {_found_ratio(miss_a[ak], seen_a[ak])}"
                     f"{who}  [playlist attive: {source_text}]")
        noalb = sum(1 for k in MISSING_ALL if not k[1])
        if noalb:
            L.append(f"# ({_plural(noalb, 'canzone mancante senza', 'canzoni mancanti senza')} album: "
                     f"non considerate nella classifica)")
        L.append('')

    L.append(f"=== ELENCO COMPLETO ({len(rows)} tracce) ===")
    L.append('# formato: Artista - Album - Titolo  [playlist]')
    if not rows:
        L.append('(nessuna traccia mancante)')
    for a, al, t in rows:
        pls = '; '.join(sorted(label(u, p) for u, p in MISSING_ALL[(a, al, t)]))
        L.append(f"{a} - {al} - {t}  [{pls}]")
    report_text = '\n'.join(L).rstrip() + '\n'
    # The playlist portion is recalculated on every run, but the full MusicBrainz
    # completeness block should survive a later sync on the same day. check-albums
    # replaces this block when it refreshes the report.
    marker_start = '===== INIZIO REPORT COMPLETO MUSICBRAINZ ====='
    marker_end = '===== FINE REPORT COMPLETO MUSICBRAINZ ====='
    try:
        previous = out.read_text(encoding='utf-8', errors='replace') if out.exists() else ''
    except OSError:
        previous = ''
    start = previous.find(marker_start)
    saved_mb = ''
    if start >= 0:
        end = previous.find(marker_end, start)
        if end >= 0:
            saved_mb = previous[start:end + len(marker_end)].strip()
    if saved_mb:
        report_text = report_text.rstrip() + '\n\n' + saved_mb + '\n'
    out.write_text(report_text, encoding='utf-8')
    print(f'[i] mancanti: {_found_ratio(len(MISSING_ALL), len(SEEN_ALL))} -> {out}', file=sys.stderr)



# ===================== fase: romaji tags =====================
# Bilingue kanji+romaji nei tag: TITLE/ARTIST/ALBUMARTIST/ALBUM che
# contengono CJK diventano "kanji (romaji)". Il matching NON cambia
# (norm() strappa le parentesi), la visualizzazione nei client si.
# Idempotente: se il romaji e' gia' tra parentesi non tocca nulla.

_HANGUL = re.compile(r'[\uac00-\ud7af]')

# Romanizzazione coreana, in ordine di preferenza (tutte opzionali, nel venv):
#   1. korean-romanizer  Revised Romanization vera ('baegyerin', 'norae')
#   2. hangul-romanize   regola 'academic' (piu' rozza: 'baeg-yelin', 'nolae')
# Il vecchio codice chiamava Transliter() SENZA la regola obbligatoria:
# TypeError su OGNI tag coreano non appena il pacchetto era installato.
_HANGUL_FN = None
try:
    from korean_romanizer.romanizer import Romanizer as _KoRomanizer

    def _HANGUL_FN(s):
        return _KoRomanizer(s).romanize()
except Exception:
    try:
        from hangul_romanize import Transliter as _HangulTransliter
        from hangul_romanize.rule import academic as _HANGUL_RULE
        _HANGUL_TR = _HangulTransliter(_HANGUL_RULE)

        def _HANGUL_FN(s):
            return _HANGUL_TR.translit(s).replace('-', '')
    except Exception:
        _HANGUL_FN = None
_HAS_HANGUL = _HANGUL_FN is not None
_WARNED_HANGUL = False


def _romkey(x):
    """Chiave per confrontare due romanizzazioni ignorando spazi, punteggiatura e maiuscole."""
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', x).casefold())


def _romanize_core(s):
    """Lettura latina di una stringa con caratteri asiatici ('' se non disponibile)."""
    global _WARNED_HANGUL
    ko = _HANGUL.search(s) and not _CJK.search(s)
    # Traduzione/forma inglese ufficiale (NAME_TRANSLATIONS) e poi alias manuale
    # (NAME_FIXES) battono la romanizzazione fonetica, anche nella manutenzione tag.
    r = _preferred_name(s)
    if r:
        return r
    if ko:
        # coreano puro (kakasi non lo tocca)
        if _HAS_HANGUL:
            return norm(_HANGUL_FN(s))
        if not _WARNED_HANGUL:
            _WARNED_HANGUL = True
            print('[!] tag coreani trovati ma nessuna libreria di romanizzazione: '
                  'nel venv dello script: .venv/bin/pip install hangul-romanize',
                  file=sys.stderr)
        return ''
    # giapponese/kanji: kakasi. Per nomi CINESI (hanzi senza kana)
    # aggiungi la lettura corretta a NAME_FIXES, oppure il nome inglese ufficiale a
    # NAME_TRANSLATIONS: kakasi leggerebbe con pronuncia giapponese, sbagliata per il cinese.
    return to_romaji(s)


def _romanize_tag_value(v, _check=True):
    # niente caratteri asiatici = niente da romanizzare NE' da "riparare". Prima la
    # regola 'X (English) (romaji)' -> 'X (English)' girava su OGNI tag e troncava
    # titoli latini legittimi: 'Swimming Pools (Drank) (Extended Version)' diventava
    # 'Swimming Pools (Drank)', 'A Military Alphabet (five eyes all blind) (4 of 4)'
    # perdeva '(4 of 4)'.
    if not v or not (_CJK.search(v) or _HANGUL.search(v)):
        return v
    # Se un mapping tradotto e' stato aggiunto dopo che romaji_tags aveva scritto
    # una lettura fonetica, sostituisci SOLO il gloss che coincide con la vecchia
    # lettura pykakasi. Parentesi legittime come (Live), (English title) ecc. restano intatte.
    old_gloss = re.match(r'^(.*?)\s*\(([^()]*)\)\s*$', v)
    if old_gloss and _CJK.search(old_gloss.group(1)):
        source, existing_gloss = old_gloss.group(1).strip(), old_gloss.group(2).strip()
        preferred = _preferred_name(source)
        phonetic = _phonetic_kakasi(source)
        if (preferred and phonetic and
                _romkey(existing_gloss) == _romkey(phonetic) and
                _romkey(existing_gloss) != _romkey(preferred)):
            return f'{source} ({preferred})'
    # Se e' gia' bilingue, uniforma parentesi e gloss: varianti come
    # '漢字(nome)' e '漢字 (nome)' non devono diventare artisti distinti in Navidrome.
    # Un NAME_TRANSLATIONS/NAME_FIXES esplicito prevale sul gloss storico.
    existing = re.match(r'^(.*?)\s*[（(]([^()（）]+)[)）]\s*$', v)
    if existing and _CJK.search(existing.group(1)) and re.search(r'[A-Za-z]', existing.group(2)):
        source, gloss = existing.group(1).strip(), existing.group(2).strip()
        preferred = _preferred_name(source)
        if preferred:
            return f'{source} ({preferred})'
        return f'{source} ({gloss})'
    # Ripara le doppie traduzioni scritte dalle versioni precedenti ('X (English) (romaji)').
    m = re.match(r'^(.*\([A-Za-z][^()]*\))\s*\([^()]+\)\s*$', v)
    if m:
        return m.group(1)
    if re.search(r'\([A-Za-z][^()]*\)', v):
        return v
    # gia' romanizzato anche se la lettura NON inizia con una lettera ('2時間 (2 jikan)',
    # '17歳 (17sai)'): la regola sopra non lo riconosce e a ogni run si aggiungeva un'altra
    # parentesi ('2時間 (2 jikan) (2 jikan (2 jikan))', senza fine).
    mt = re.match(r'^(.*\S)\s*\(([^()]+)\)\s*$', v)
    if mt and (_CJK.search(mt.group(1)) or _HANGUL.search(mt.group(1))):
        rb = _romanize_core(mt.group(1))
        if rb and _romkey(rb) == _romkey(mt.group(2)):
            return v
    ko = _HANGUL.search(v) and not _CJK.search(v)
    if not ko and not _CJK.search(v):
        return v                      # latino/cirillico/...: niente da romanizzare
    r = _romanize_core(v)
    if not r or r.lower() in v.lower():
        return v
    out = f'{v} ({r})'
    # rete di sicurezza: se riapplicando la funzione il valore cambierebbe ancora, la
    # romanizzazione non converge: meglio lasciare il tag com'e' che farlo crescere ogni notte.
    if _check and _romanize_tag_value(out, _check=False) != out:
        return v
    return out


def run_romaji_tags(dry_run=False, base=None, files_only=None):
    import shutil as _sh
    if not dry_run and not _sh.which('metaflac'):
        print('[ERRORE] metaflac non trovato: salto romaji_tags')
        return
    base = Path(base) if base else LIBRARY_ROOT
    VORBIS = {'title': 'TITLE', 'artist': 'ARTIST',
              'albumartist': 'ALBUMARTIST', 'album': 'ALBUM'}
    changed = scanned = errors = 0
    files = [base.joinpath(*r) for r in _walk_audio(base, AUDIO_EXT)
             if not r[-1].endswith('.backup')]
    if files_only is not None:
        wanted_files = {Path(f).resolve() for f in files_only}
        files = [f for f in files if f.resolve() in wanted_files]
    prefetch_probe(files, 'romaji')      # ffprobe in parallelo / dalla cache
    progress = _ProgressBar('romaji_tags', len(files), 'file')
    for f in files:
        scanned += 1
        progress.update(scanned)
        try:
            tags = probe(f)   # probe di unify (con alias album_artist)
            newvals = {}
            for k in VORBIS:
                old_v = tags.get(k, '')
                nv = _romanize_tag_value(old_v)
                if nv and nv != old_v:
                    newvals[k] = nv
            if not newvals:
                continue
            desc = ', '.join(f'{k}="{v[:40]}"' for k, v in newvals.items())
            progress.clear()
            print(f'{"[dry] " if dry_run else ""}ROMAJI '
                  f'{f.parent.parent.name} / {f.parent.name}: {desc}')
            if dry_run:
                changed += 1
                continue
            if f.suffix.lower() == '.flac':
                # Un solo processo per file: metaflac accetta piu' operazioni in una chiamata.
                args = []
                for k, v in newvals.items():
                    args.extend((f'--remove-tag={VORBIS[k]}', f'--set-tag={VORBIS[k]}={v}'))
                _metaflac_run(*args, path=f)
            else:
                ffkeys = {'albumartist': 'album_artist'}
                tmp = f.with_name(f.stem + '.tmp' + f.suffix)
                try:
                    write_ffmpeg(f, {ffkeys.get(k, k): v for k, v in newvals.items()}, tmp)
                except Exception:
                    tmp.unlink(missing_ok=True)      # niente .tmp orfani nella libreria
                    raise
                os.replace(f, f.with_name(f.name + '.meta-backup'))
                os.replace(tmp, f)
            changed += 1
        except Exception as e:
            errors += 1
            progress.clear()
            print(f'ERRORE: {f}: {e}', file=sys.stderr)
    progress.close(complete=True)
    backup_candidates = (base.rglob('*.meta-backup') if files_only is None else
                         (b for folder in {Path(f).parent for f in files_only}
                          for b in folder.glob('*.meta-backup')))
    for b in backup_candidates:
        if b.with_name(b.name[:-len('.meta-backup')]).exists():
            b.unlink(missing_ok=True)
    print(f'romaji_tags: {scanned} file scansiti, {changed} modificati, {errors} errori')


# ===================== cache di ffprobe =====================
# Ogni notte date_heal / romaji_tags / album_unify rileggevano con ffprobe TUTTA
# la libreria (~50 ms a file: ~18 min ogni 20.000 brani, PER OGNI fase) anche
# se non era cambiato nulla. Ora i tag letti stanno in una cache persistente
# (path + mtime + dimensione): un file modificato (anche dallo script stesso)
# viene riletto, gli altri no. Le letture a freddo sono parallele.

PROBE_CACHE = CACHE_DIR / 'probe_cache_v4.json'   # tag flussi + track + stato cover embedded opzionale
for _old in ('probe_cache.json', 'probe_cache_v2.json', 'probe_cache_v3.json'):      # formati precedenti
    try:
        (CACHE_DIR / _old).unlink()
    except OSError:
        pass
# thread di ffprobe in parallelo (EXPORTIFY_PROBE_WORKERS=2 se la musica sta su un NAS lento)
PROBE_WORKERS = max(1, int(os.environ.get('EXPORTIFY_PROBE_WORKERS') or min(8, (os.cpu_count() or 2) * 2)))
try:
    WAVEFORM_WORKERS = max(1, min(4, int(os.environ.get('EXPORTIFY_WAVEFORM_WORKERS', '2'))))
except (TypeError, ValueError):
    WAVEFORM_WORKERS = 2
# solo i tag che lo script usa davvero (niente testi/commenti da KB per file)
_PROBE_KEEP = {'title', 'artist', 'artists', 'album', 'albumartist', 'albumartists', 'album_artist', 'date',
               'originaldate', 'albumversion', 'album_version', 'musicbrainz_albumid',
               'musicbrainz_releasegroupid', 'track', 'tracknumber'}
_PROBE_MEM = None        # {path: [mtime_ns, size, tags, durata, embedded_art_opzionale]}
_PROBE_DIRTY = False


def _probe_mem():
    global _PROBE_MEM
    if _PROBE_MEM is None:
        try:
            _PROBE_MEM = json.loads(PROBE_CACHE.read_text(encoding='utf-8'))
        except Exception:
            _PROBE_MEM = {}
    return _PROBE_MEM


def _ffprobe_raw(key):
    """(tags, durata) da ffprobe, o None se fallisce (un errore NON va in cache)."""
    try:
        r = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json',
                            '-show_entries',
                            'format_tags:format=duration:stream=codec_type:stream_tags:stream_disposition=attached_pic', key],
                           capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or '{}')
        fmt = d.get('format')
        if not isinstance(fmt, dict):
            return None
        tags = {k.lower(): str(v) for k, v in (fmt.get('tags') or {}).items()}
        streams = d.get('streams') or []
        # .opus/.ogg: i Vorbis comment stanno nei tag del FLUSSO audio, non del formato
        # (prima probe() non leggeva NESSUN tag di questi file e unify li riscriveva ogni
        # notte). Solo il flusso audio: la copertina incorporata ha tag suoi (title...).
        for st in streams:
            if st.get('codec_type') == 'audio':
                for k, v in (st.get('tags') or {}).items():
                    tags.setdefault(k.lower(), str(v))
                break
        # Conserva lo stato se ffprobe ha incluso il campo disposition.attached_pic.
        # None significa output non compatibile: il caller puo' usare la probe dedicata.
        disposition_known = any(
            isinstance(st.get('disposition'), dict) and 'attached_pic' in st['disposition']
            for st in streams)
        embedded_art = (any(int((st.get('disposition') or {}).get('attached_pic', 0) or 0) == 1
                            for st in streams) if disposition_known else None)
        dur = fmt.get('duration')
        return tags, (float(dur) if dur else None), embedded_art
    except Exception:
        return None


def _probe_entry(path):
    global _PROBE_DIRTY
    key = str(path)
    try:
        st = os.stat(key)
    except OSError:
        # Se una voce gia' caricata punta a un file sparito, eliminala senza forzare
        # il caricamento della cache su disco. La validita' del dato viene sempre
        # verificata con stat PRIMA di leggere tag/durata dalla cache.
        mem = _PROBE_MEM
        if mem is not None and key in mem:
            mem.pop(key, None)
            _PROBE_DIRTY = True
        return None
    mem = _probe_mem()
    ent = mem.get(key)
    if ent and len(ent) >= 4 and ent[0] == st.st_mtime_ns and ent[1] == st.st_size:
        return ent
    res = _ffprobe_raw(key)
    if res is None:
        return None
    tags, dur, embedded_art = res
    ent = [st.st_mtime_ns, st.st_size,
           {k: v for k, v in tags.items() if k in _PROBE_KEEP}, dur, embedded_art]
    mem[key] = ent
    _PROBE_DIRTY = True
    return ent


def probe(path: Path):
    ent = _probe_entry(path)
    if ent is None:
        return {}
    tags = dict(ent[2])
    # ffmpeg scrive 'album_artist', altri tagger 'albumartist': unifica
    if 'album_artist' in tags and 'albumartist' not in tags:
        tags['albumartist'] = tags['album_artist']
    if 'album_version' in tags and 'albumversion' not in tags:
        tags['albumversion'] = tags['album_version']
    return tags


def probe_dur(path: Path):
    """(tags, durata_sec) via ffprobe (con cache)."""
    ent = _probe_entry(path)
    if ent is None:
        return {}, None
    return dict(ent[2]), ent[3]


def invalidate_probe_cache(paths):
    """Invalidate metadata immediately after tag/file rewrites, independent of mtime/size."""
    global _PROBE_DIRTY
    mem = _probe_mem()
    changed = False
    for path in paths:
        key = str(path)
        if key in mem:
            mem.pop(key, None)
            changed = True
    if changed:
        _PROBE_DIRTY = True


def flush_probe_cache():
    """Salva la cache in modo atomico senza scandire tutti i path con stat/exists.

    Su storage lento, validare ogni voce ad ogni confine di fase costa O(numero file)
    ed e' risultato il principale hotspot del profilo Tachyon. Una voce obsoleta non puo'
    essere usata: _probe_entry esegue os.stat prima di accedere ai tag in cache e rimuove
    lazily la voce se il file non esiste. Snapshot e reset anticipato del flag mantengono
    il comportamento sicuro mentre i thread di prefetch scrivono.
    """
    global _PROBE_DIRTY
    if _PROBE_MEM is None or not _PROBE_DIRTY:
        return
    _PROBE_DIRTY = False
    mem = _PROBE_MEM
    snap = list(mem.items())
    try:
        _write_json_atomic(PROBE_CACHE, dict(snap), ensure_ascii=False, separators=(',', ':'))
    except OSError as e:
        _PROBE_DIRTY = True
        print(f"[!] impossibile scrivere la cache ffprobe {PROBE_CACHE}: {e}", file=sys.stderr)


def prefetch_probe(paths, label='probe'):
    """Legge in PARALLELO (ffprobe) i file non ancora in cache. Poi probe()/
    probe_dur() sono istantanee."""
    mem = _probe_mem()
    todo = []
    for p in paths:
        key = str(p)
        try:
            st = os.stat(key)
        except OSError:
            continue
        ent = mem.get(key)
        if not (ent and ent[0] == st.st_mtime_ns and ent[1] == st.st_size):
            todo.append(key)
    if todo:
        print(f'  [{label}] {len(todo)} file da leggere con ffprobe ({PROBE_WORKERS} thread; '
              f'gli altri vengono dalla cache)...', file=sys.stderr, flush=True)
        done = 0
        progress = _ProgressBar(f'ffprobe/{label}', len(todo), 'file')
        with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as ex:
            for _ in ex.map(_probe_entry, todo):
                done += 1
                progress.update(done)
                if done % 10000 == 0:
                    flush_probe_cache()
        progress.close(complete=True)
    flush_probe_cache()


# ===================== album_unify (merge da album_unify.py) =====================
# Uniforma i tag a livello di cartella album: ALBUM/ALBUMARTIST/DATE/
# MUSICBRAINZ_ALBUMID maggioritari per cartella, cosi' Navidrome smette di
# splittare UN album in piu' voci. Nota: agisce DENTRO la singola cartella:
# il merge di due RELEASE diverse (vedi dedupe_releases.py) e' un altro problema.

def majority(tags_list, key):
    vals = [t.get(key, '') for t in tags_list]
    vals = [v for v in vals if v]
    if not vals:
        return None
    return Counter(vals).most_common(1)[0][0]


def write_flac(path: Path, targets: dict):
    args = [*METAFLAC]
    vorbis = {'album': 'ALBUM', 'albumartist': 'ALBUMARTIST',
              'date': 'DATE', 'originaldate': 'ORIGINALDATE',
              'albumversion': 'ALBUMVERSION',
              'musicbrainz_albumid': 'MUSICBRAINZ_ALBUMID',
              'musicbrainz_releasegroupid': 'MUSICBRAINZ_RELEASEGROUPID',
              # title/artist: servono alla riparazione da nome file e alla regola 'artist'
              # di unify. Mancavano: KeyError su OGNI FLAC (la regola 'artist' ripiegava
              # su ffmpeg, la riparazione falliva e riprovava ogni notte)
              'title': 'TITLE', 'artist': 'ARTIST'}
    for k, v in targets.items():
        if v is None:
            args.append(f'--remove-tag={vorbis[k]}')
        else:
            args += [f'--remove-tag={vorbis[k]}', f'--set-tag={vorbis[k]}={v}']
    args.append(str(path))
    subprocess.run(args, capture_output=True, timeout=120, check=True)
    invalidate_probe_cache([path])


CODEC_FOR = {'.flac': 'flac', '.mp3': 'libmp3lame', '.m4a': 'aac',
             '.ogg': 'libvorbis', '.opus': 'libopus'}
UNIFY_FIELDS = ['album', 'albumartist', 'date', 'originaldate', 'musicbrainz_albumid', 'musicbrainz_releasegroupid']


def write_ffmpeg(path: Path, targets: dict, tmp: Path, codec: str = None):
    args = ['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-map', '0']
    args += ['-c:a', codec] if codec else ['-codec', 'copy']
    ext = path.suffix.lower()
    m4a = ext in ('.m4a', '.mp4')
    ogg = ext in ('.ogg', '.opus', '.oga')   # Vorbis comment = tag del FLUSSO: con -metadata
    mp3 = ext == '.mp3'
    for k, v in targets.items():             # globale il muxer Ogg non li salva
        if (m4a or mp3) and k == 'albumartist' and v:    # v='' = 'cancella il frame TXXX'
            # mp4: unica chiave che il muxer salva (aART). mp3: 'albumartist' NON e'
            # mappata da ffmpeg e finiva in un frame TXXX *accanto* al TPE2 originale:
            # l'mp3 aveva due album artist e Navidrome mostrava un artista in piu'.
            k = 'album_artist'
        args += ['-metadata:s:a:0' if ogg else '-metadata', f'{k}={"" if v is None else v}']
    args.append(str(tmp))
    subprocess.run(args, capture_output=True, timeout=600, check=True)


def unify_album_dirs(root: Path):
    for artist in sorted(root.iterdir()):
        if not artist.is_dir() or artist.name.lower() in SKIP_TOP \
           or artist.name.startswith('.'):
            continue
        for album in sorted(artist.iterdir()):
            if not album.is_dir():
                continue
            files = [f for f in album.rglob('*')
                     if f.is_file() and f.suffix.lower() in AUDIO_EXT]
            if files:
                yield album, files


def _filename_repair(f, tags, album_hints=()):
    """spotyFLAC scarica 'Title - Album - Artist.ext' ma a volte lascia ARTIST
    vuoto o 'unknown artist'. Ricostruisco dai segmenti del nome file: l'ultimo
    e' l'artista, il titolo e' tutto cio' che precede il segmento ALBUM (cosi'
    'Second Chance - Cyril Hahn Edit - Our Love - Caribou' non perde
    'Cyril Hahn Edit'; prima restava il solo primo segmento e '01 - 1015
    Saturday Night - ...' diventava il titolo '01')."""
    out = {}
    artist = (tags.get('artist') or '').strip()
    if artist and artist.lower() not in ('unknown artist', 'unknown'):
        return out
    parts = [x.strip() for x in Path(f).stem.split(' - ')]
    parts = [x for x in parts if x]
    # via i segmenti iniziali fatti solo da un numero di traccia ('01', '2-05', 'A1')
    while len(parts) > 3 and re.fullmatch(r'\d{1,3}(?:-\d{1,3})?|[A-Da-d]\d{1,2}', parts[0]):
        parts.pop(0)
    if len(parts) >= 3:
        hints = {norm_bare(h) for h in album_hints if h}
        cut = max(1, len(parts) - 2)          # struttura standard: Titolo - Album - Artista
        for i in range(1, len(parts) - 1):    # album con ' - ' nel nome: lo cerco per nome
            if norm_bare(' - '.join(parts[i:-1])) in hints:
                cut = i
                break
        cand = re.sub(r'^\d{1,3}\s*[-._: ]\s*', '', ' - '.join(parts[:cut]))
        if cand and not re.fullmatch(r'\d{1,3}', cand) and not (tags.get('title') or '').strip():
            out['title'] = cand
        if parts[-1]:
            out['artist'] = parts[-1]
    return out



ROMAJI_TAGS_ACTIVE = True      # main(): --skip-romaji lo mette a False


def _canonical_albumartist(folder_name):
    """Valore da scrivere in ALBUMARTIST quando l'artista e' quello della
    cartella. Con la fase romaji_tags attiva e' la forma BILINGUE ('高中正義
    (masayoshi takanaka)'). Prima unify la riportava al solo kanji e romaji_tags
    la riscriveva col romaji: ogni notte, per ogni artista con cartella in
    kanji/hangul, due riscritture per file (ffmpeg sugli mp3), per sempre."""
    return _romanize_tag_value(folder_name) if ROMAJI_TAGS_ACTIVE else folder_name


def _folder_artist_preference(tags, folder_name):
    """Se i voti di ALBUMARTIST citano l'artista della cartella (esatto o
    dentro un valore multiplo 'A; B'), il valore canonico diventa il NOME
    DELLA CARTELLA: risolve la frammentazione '高中正義' vs
    'masayoshi takanaka' vs '高中正義; masayoshi takanaka'. None = nessun
    segnale, vale la maggioranza semplice."""
    # SOLO per cartelle in kanji/hangul (il caso per cui e' nata: gloss bilingui). Per
    # quelle latine riscriveva ALBUMARTIST col nome SANIFICATO della cartella ('AC/DC'
    # -> 'AC+DC', 'Fred again..' -> 'Fred again'), staccandolo dall'ARTIST dei brani:
    # in Navidrome diventano due artisti diversi.
    if not (_CJK.search(folder_name) or _HANGUL.search(folder_name)):
        return None
    fa = norm(folder_name)
    if not fa:
        return None
    fa_rom = to_romaji(fa) or fa
    votes = [t.get('albumartist', '') for t in tags if t.get('albumartist')]
    if not votes:
        return None
    for v in votes:
        if norm(v) == fa:
            return _canonical_albumartist(folder_name)
    fa_set = {fa, fa_rom}
    for v in votes:
        nv = norm(v)
        if any(a in nv for a in fa_set):
            return _canonical_albumartist(folder_name)
    return None


def _unify_applies(f, t, k, targets):
    """Ha senso scrivere il campo k su questo file? Evita le riscritture notturne
    che non convergono mai:
      - .m4a: ffmpeg non salva originaldate/musicbrainz_albumid (restano 'persi'
        e l'album veniva riscritto OGNI notte: Pink Floyd / Animals ecc.);
      - FLAC che hanno già ORIGINALDATE: non forzare DATE, che viene gestito da fix_date_tags;
        i file senza ORIGINALDATE devono invece ricevere DATE, altrimenti Navidrome li separa."""
    ext = f.suffix.lower()
    if ext in ('.m4a', '.mp4') and k == 'originaldate':
        return False
    # I file M4A/MP4 non propagano in modo affidabile questi ID; la rimozione esplicita
    # (target None) è però consentita, altrimenti un vecchio ID resterebbe e manterrebbe
    # l'album separato in Navidrome anche dopo aver ripulito i file FLAC.
    if (ext in ('.m4a', '.mp4') and
            k in ('musicbrainz_albumid', 'musicbrainz_releasegroupid') and
            targets.get(k) is not None):
        return False
    if k == 'date' and ext == '.flac' and t.get('originaldate'):
        return False
    return True


def _unify_target_matches(actual, target):
    if target is None:
        return not str(actual or '').strip()
    return actual == target


def _dominant_original_date(tags):
    """Pick a reliable album-wide original date from mixed DATE/ORIGINALDATE tags.

    Only returns a date if one year has at least two tracks and >=60% of dated tracks;
    ambiguous release-year conflicts are left untouched for manual review.
    """
    dated = []
    for tag in tags:
        value = str(tag.get('originaldate') or tag.get('date') or '').strip()
        match = re.match(r'^(\d{4})(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?', value)
        if match:
            dated.append((match.group(1), value))
    if not dated:
        return None
    counts = Counter(year for year, _value in dated)
    year, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    if count < 2 or count / len(dated) < 0.60:
        return None
    exact_counts = Counter(value for dated_year, value in dated if dated_year == year)
    # Prefer the most frequent full date; on a tie prefer the most precise representation.
    return sorted(exact_counts, key=lambda value: (-exact_counts[value], -len(value), value))[0]


def run_unify(dry_run=False, base=None, album_dirs_only=None):
    base = Path(base) if base else LIBRARY_ROOT
    known_artist_names = _navidrome_artist_name_map()
    dirs = list(unify_album_dirs(base))   # materializzato: serve il totale per %/rimanenti
    if album_dirs_only is not None:
        wanted_dirs = {Path(d).resolve() for d in album_dirs_only}
        dirs = [(album, files) for album, files in dirs if album.resolve() in wanted_dirs]
    total = len(dirs)
    prefetch_probe((f for _, fl in dirs for f in fl), 'unify')
    changed_albums = changed_files = errors = scanned = 0
    progress = _ProgressBar('album_unify', total, 'album')
    for album, files in dirs:
        scanned += 1
        progress.update(scanned)
        tags = [probe(f) for f in files]
        # repair spotyFLAC: artist/title dai nomi file quando il tag e' rotto
        for f, t in zip(files, tags):
            rep = _filename_repair(f, t, (t.get('album'), album.name))
            if not rep:
                continue
            progress.clear()
            print(f'    [repair] {f.name}: {rep}')
            if not dry_run:
                try:
                    if f.suffix.lower() == '.flac':
                        write_flac(f, rep)
                    else:
                        tmp = f.with_name(f.stem + '.tmp' + f.suffix)
                        write_ffmpeg(f, rep, tmp)
                        os.replace(f, f.with_name(f.name + '.meta-backup'))
                        os.replace(tmp, f)
                        invalidate_probe_cache([f])
                    t.update(rep)
                except Exception as e:
                    progress.clear()
                    print(f'    ERRORE repair {f.name}: {e}', file=sys.stderr)
                    f.with_name(f.stem + '.tmp' + f.suffix).unlink(missing_ok=True)
        targets = {}
        for k in UNIFY_FIELDS + ['artist']:
            if k == 'artist':
                # merge dei gloss bilingui: riscrivo l'artista col NOME
                # CARTELLA solo se i token del tag sono un sottoinsieme di
                # quelli della cartella ('東京酒吐座(Tokyo Shoegazer)' merge,
                # ma 'Gorillaz, Del The Funky Homosapien' NO: ha token extra)
                fa = norm_bare(album.parent.name)   # norm_bare: tiene i gloss
                fa_tok = set(fa.split())
                votes = {norm(t.get('artist', '')) for t in tags}
                votes.discard('')
                if fa_tok and any(v != fa and set(v.split()) <= fa_tok
                                  for v in votes):
                    top = album.parent.name
                else:
                    continue
            else:
                top = majority(tags, k)
                if k == 'originaldate':
                    reliable_date = _dominant_original_date(tags)
                    if reliable_date:
                        top = reliable_date
            if k == 'albumartist':
                pref = _folder_artist_preference(tags, album.parent.name)
                if pref:
                    top = pref
            if top is None:
                continue
            targets[k] = top
        # UNIFY_FORCE: pin per-album dalla configurazione (vincono sul voto)
        forced = UNIFY_FORCE.get(norm(f"{album.parent.name} / {album.name}"), {}) or {}
        if forced:
            for k, v in forced.items():
                if k in UNIFY_FIELDS:
                    progress.clear()
                    print(f'    [force] {k}="{str(v)[:40]}" (pin dalla config)')
                    targets[k] = str(v)
        # If at least one M4A/MP4 lacks MusicBrainz IDs, those IDs cannot be made
        # consistent in every format; clear them from writable files instead of leaving
        # an album split between tagged FLACs and an untagged lossy copy. Conflicting IDs
        # are also unsafe to propagate. Explicit UNIFY_FORCE pins remain authoritative.
        unwritable_missing_album_id = any(
            f.suffix.lower() in ('.m4a', '.mp4') and
            not str(t.get('musicbrainz_albumid') or '').strip()
            for f, t in zip(files, tags))
        album_ids = {str(t.get('musicbrainz_albumid') or '').strip().casefold()
                     for t in tags if str(t.get('musicbrainz_albumid') or '').strip()}
        if 'musicbrainz_albumid' not in forced and (
                len(album_ids) > 1 or (len(album_ids) == 1 and unwritable_missing_album_id)):
            targets['musicbrainz_albumid'] = None
        unwritable_missing_rgid = any(
            f.suffix.lower() in ('.m4a', '.mp4') and
            not str(t.get('musicbrainz_releasegroupid') or '').strip()
            for f, t in zip(files, tags))
        releasegroup_ids = {str(t.get('musicbrainz_releasegroupid') or '').strip().casefold()
                            for t in tags if str(t.get('musicbrainz_releasegroupid') or '').strip()}
        if 'musicbrainz_releasegroupid' not in forced and (
                len(releasegroup_ids) > 1 or (len(releasegroup_ids) == 1 and unwritable_missing_rgid)):
            targets['musicbrainz_releasegroupid'] = None
        for k in list(targets):
            if all(_unify_target_matches(t.get(k, ''), targets[k]) for f, t in zip(files, tags)
                   if _unify_applies(f, t, k, targets)):
                del targets[k]
        if not targets:
            continue
        changed_albums += 1
        desc = ', '.join(f'{k}="{'<rimuovi>' if v is None else str(v)[:40]}"' for k, v in targets.items())
        progress.clear()
        print(f'{"[dry] " if dry_run else ""}UNIFY {album.parent.name} / {album.name}: {desc}')
        if dry_run:
            continue
        for f, t in zip(files, tags):
            diff = {k: v for k, v in targets.items()
                    if not _unify_target_matches(t.get(k, ''), v) and _unify_applies(f, t, k, targets)}
            if not diff:
                continue
            backup = f.with_name(f.name + '.meta-backup')
            try:
                if f.suffix.lower() == '.flac':
                    os.replace(f, backup)
                    try:
                        write_flac(backup, diff)
                    except Exception:
                        os.replace(backup, f)
                        tmp = f.with_name(f.stem + '.tmp' + f.suffix)
                        try:
                            write_ffmpeg(f, diff, tmp)
                        except Exception:
                            tmp.unlink(missing_ok=True)
                            write_ffmpeg(f, diff, tmp,
                                         codec=CODEC_FOR.get(f.suffix.lower(), 'flac'))
                        os.replace(f, backup)
                        os.replace(tmp, f)
                    else:
                        os.replace(backup, f)
                else:
                    tmp = f.with_name(f.stem + '.tmp' + f.suffix)
                    try:
                        write_ffmpeg(f, diff, tmp)
                    except Exception:
                        tmp.unlink(missing_ok=True)
                        write_ffmpeg(f, diff, tmp,
                                     codec=CODEC_FOR.get(f.suffix.lower(), 'flac'))
                    os.replace(f, backup)
                    os.replace(tmp, f)
                invalidate_probe_cache([f])
                changed_files += 1
            except Exception as e:
                errors += 1
                err = getattr(e, 'stderr', '') or ''
                progress.clear()
                print(f'ERRORE: {f}: {e} {str(err).strip()[:300]}', file=sys.stderr)
                if backup.exists() and not f.exists():
                    os.replace(backup, f)
                f.with_name(f.stem + '.tmp' + f.suffix).unlink(missing_ok=True)
    progress.close(complete=True)

    # Passaggio cross-folder: i tag coerenti dentro una cartella non bastano se lo stesso
    # album e' stato importato in due cartelle/edizioni parziali diverse.
    cross_groups, cross_files, cross_errors = _unify_cross_album_dirs(dirs, dry_run=dry_run)
    errors += cross_errors
    changed_files += cross_files
    changed_albums += cross_groups
    removed = 0
    if not dry_run:
        if album_dirs_only is None:
            backup_candidates = base.rglob('*.meta-backup')
        else:
            backup_candidates = (b for album_dir in wanted_dirs for b in album_dir.rglob('*.meta-backup'))
        for b in backup_candidates:
            if b.with_name(b.name[:-len('.meta-backup')]).exists():
                try:
                    b.unlink()
                    removed += 1
                except Exception:
                    pass
    print(f'album esaminati: {scanned} | gruppi modificati: {changed_albums} '
          f'({changed_files} file) | errori: {errors} | backup rimossi: {removed}')
    return {'albums': changed_albums, 'files': changed_files, 'errors': errors}



def _track_number_for_tags(tags):
    raw = str(tags.get('track') or tags.get('tracknumber') or '').strip()
    m = re.match(r'(\d{1,4})', raw)
    return int(m.group(1)) if m else None


def _fragment_album_evidence(a, b):
    # Evidence that a small folder is part of a fuller album, not merely a similarly named release.
    small, large = (a, b) if len(a['files']) <= len(b['files']) else (b, a)
    if not (1 <= len(small['files']) <= 3 and len(large['files']) >= 3):
        return False, ''
    small_titles = small['track_keys']
    large_titles = large['track_keys']
    if (small_titles and len(small_titles) == len(small['files'])
            and small_titles <= large_titles):
        return True, 'fragment track titles contained in fuller album'
    sn, ln = small['track_numbers'], large['track_numbers']
    if sn and ln and not (sn & ln):
        all_nums = sn | ln
        if max(all_nums) - min(all_nums) + 1 == len(all_nums):
            return True, 'non-overlapping contiguous track numbers'
    return False, ''


def _album_explicit_edition_markers(values):
    """Markers that prevent different editions being joined by normalized title aliases.

    A year alone is intentionally ignored because a release year is commonly appended to
    folder names. Explicit remaster/deluxe/expanded/anniversary markers are meaningful.
    """
    marker_re = re.compile(
        r"\b(?:remaster(?:ed)?|deluxe|expanded|anniversary|special|limited|collector(?:'s|s)?|"
        r"tour|complete|bonus tracks?|reissue|mono|stereo|live version|live recording)\b", re.I)
    found = set()
    for value in values:
        for match in marker_re.finditer(str(value or '')):
            found.add(norm_bare(match.group(0)).casefold())
    return found


def _unify_cross_album_dirs(dirs, dry_run=False):
    """Unifica ALBUM/ALBUMARTIST solo per identita' esatta o alias noti.

    Qualsiasi somiglianza fuzzy, anche quando un frammento sembra compatibile per titoli o numeri,
    viene registrata per revisione e MAI unita automaticamente. Evita falsi positivi fra sequel,
    volumi, remaster e album dal nome simile.
    """
    # Usata quando si sceglie un ALBUMARTIST canonico: era una variabile non inizializzata,
    # che provocava NameError appena il cross-folder trovava gruppi da consolidare.
    known_artist_names = _navidrome_artist_name_map()
    records = []
    for album, files in dirs:
        if not files:
            continue
        tags = [probe(f) for f in files]
        album_values = [str(t.get('album') or '').strip() for t in tags if str(t.get('album') or '').strip()]
        # The directory name is the anchor. Only add a tag title when it is a majority value;
        # a single incorrectly tagged track must not create a false alias to an unrelated album.
        title_values = [album.name]
        if album_values:
            album_counts = Counter(album_values)
            dominant_title, dominant_count = album_counts.most_common(1)[0]
            if len(files) == 1 or dominant_count >= max(2, (len(files) + 1) // 2):
                title_values.append(dominant_title)
        title_keys = set().union(*(_album_title_keys(v) for v in title_values))
        artist_keys = _artist_identity_keys(album.parent.name)
        rgids = {t.get('musicbrainz_releasegroupid', '').strip().lower()
                 for t in tags if t.get('musicbrainz_releasegroupid', '').strip()}
        albumversions = {str(t.get('albumversion') or t.get('album_version') or '').strip().casefold()
                         for t in tags if str(t.get('albumversion') or t.get('album_version') or '').strip()}
        edition_markers = _album_explicit_edition_markers(title_values)
        track_keys = {norm_bare(str(t.get('title') or '').strip()) for t in tags
                      if str(t.get('title') or '').strip()}
        track_numbers = {_track_number_for_tags(t) for t in tags}
        track_numbers.discard(None)
        records.append({'album': album, 'files': files, 'tags': tags,
                        'title_values': title_values, 'title_keys': title_keys,
                        'artist_keys': artist_keys, 'rgids': rgids,
                        'albumversions': albumversions, 'edition_markers': edition_markers,
                        'track_keys': track_keys, 'track_numbers': track_numbers})
    n = len(records)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a

    fuzzy_pairs = []
    for i in range(n):
        a = records[i]
        if not a['title_keys'] or not a['artist_keys']:
            continue
        for j in range(i + 1, n):
            b = records[j]
            if not (a['artist_keys'] & b['artist_keys']):
                continue
            rg_conflict = bool(a['rgids'] and b['rgids'] and not (a['rgids'] & b['rgids']))
            sim, label = _album_title_similarity(a['title_keys'], b['title_keys'])
            fragment_evidence, evidence_label = _fragment_album_evidence(a, b)
            exact_title = sim == 1.0
            edition_conflict = (a['edition_markers'] != b['edition_markers'] and
                                bool(a['edition_markers'] or b['edition_markers']))
            version_conflict = (a['albumversions'] != b['albumversions'] and
                                bool(a['albumversions'] or b['albumversions']))
            review_reason = ''
            if edition_conflict:
                review_reason = ('explicit edition marker differs: '
                                 f"{sorted(a['edition_markers'])} vs {sorted(b['edition_markers'])}")
            elif version_conflict:
                review_reason = ('ALBUMVERSION differs: '
                                 f"{sorted(a['albumversions'])} vs {sorted(b['albumversions'])}")
            # A tag ALBUMVERSION discordante, da solo, non basta a tenere separati
            # frammenti dal medesimo titolo/artista: in quel caso verrà rimosso dal
            # gruppo unificato. Un marcatore esplicito nel TITOLO (deluxe/remaster/live…)
            # resta invece una barriera, anche quando la normalizzazione rende i titoli uguali.
            if edition_conflict or (version_conflict and not exact_title):
                if not review_reason:
                    review_reason = ('ALBUMVERSION differs: '
                                     f"{sorted(a['albumversions'])} vs {sorted(b['albumversions'])}")
                fuzzy_pairs.append((a, b, sim, review_reason, evidence_label, rg_conflict))
                continue
            # Exact/known aliases may be unified, even if inconsistent MusicBrainz IDs
            # or ALBUMVERSION tags must be cleared to prevent Navidrome re-splitting them.
            if exact_title:
                union(i, j)
                if rg_conflict:
                    print(f"[i] titolo esatto/alias con RGID discordanti: "
                          f"{a['album'].name} <-> {b['album'].name}; gli ID conflittuali saranno rimossi")
                if version_conflict:
                    print(f"[i] titolo esatto/alias con ALBUMVERSION discordanti: "
                          f"{a['album'].name} <-> {b['album'].name}; il campo conflittuale sarà rimosso")
                continue
            if sim >= 0.88:
                # REVIEW only. Never union fuzzy title pairs.
                fuzzy_pairs.append((a, b, sim, label, evidence_label, rg_conflict))

    components = {}
    for i in range(n):
        components.setdefault(find(i), []).append(records[i])
    groups = [g for g in components.values() if len(g) > 1]
    fixed_groups = changed_files = errors = 0
    for group in groups:
        all_files = [f for r in group for f in r['files']]
        all_tags = [t for r in group for t in r['tags']]
        # Se esistono pin UNIFY_FORCE incompatibili, non sovrascriverli con una regola automatica.
        forced_albums = set()
        forced_albumartists = set()
        for r in group:
            pin = UNIFY_FORCE.get(norm(f"{r['album'].parent.name} / {r['album'].name}"), {})
            if pin.get('album'):
                forced_albums.add(str(pin['album']))
            if pin.get('albumartist'):
                forced_albumartists.add(str(pin['albumartist']))
        if len(forced_albums) > 1 or len(forced_albumartists) > 1:
            print('[review] CROSS-ALBUM saltato: UNIFY_FORCE contiene tag discordanti per '
                  + ', '.join(f'{r["album"].parent.name}/{r["album"].name}' for r in group))
            continue
        if forced_albums:
            target_album = next(iter(forced_albums))
        else:
            counts = Counter(t.get('album', '').strip() for t in all_tags if t.get('album', '').strip())
            if counts:
                max_count = max(counts.values())
                candidates = [v for v, count in counts.items() if count == max_count]
                # Tie-break conservativo: forma bilingue CJK, poi meno marcatori di edizione,
                # poi forma piu' lunga (preserva il nome leggibile), infine deterministico.
                def album_label_score(v):
                    bilingual = _has_asian(v) and bool(re.search(r'\([^()]*[A-Za-z][^()]*\)', v))
                    edition_words = len(_ALBUM_EDITION_QUALIFIER.findall(v)) + len(
                        re.findall(r'\b(?:deluxe|remaster(?:ed)?|anniversary|bonus|reissue)\b', v, re.I))
                    return (int(bilingual), -edition_words, len(v), v.casefold())
                target_album = max(candidates, key=album_label_score)
            else:
                target_album = group[0]['album'].name

        target_albumartist = next(iter(forced_albumartists)) if forced_albumartists else None
        cjk_folders = [r['album'].parent.name for r in group if _has_asian(r['album'].parent.name)]
        if not target_albumartist and cjk_folders and ROMAJI_TAGS_ACTIVE:
            # Se due nomi cartella sono alias della stessa persona, la forma bilingue ha la priorita'.
            folder_name = max(cjk_folders, key=lambda v: (bool(re.search(r'\([^()]*[A-Za-z][^()]*\)', v)), len(v)))
            target_albumartist = _canonical_albumartist(folder_name)
        if not target_albumartist:
            values = [t.get('albumartist', '') for t in all_tags if t.get('albumartist', '').strip()]
            if values:
                target_albumartist = _canonicalize_artist_value(Counter(values).most_common(1)[0][0],
                                                              known_names=known_artist_names)
            else:
                # Se un frammento ha perso ALBUMARTIST, usa il nome della cartella artista
                # condivisa dal gruppo; altrimenti Navidrome può separare proprio quel frammento.
                target_albumartist = _canonicalize_artist_value(group[0]['album'].parent.name,
                                                              known_names=known_artist_names)
        elif target_albumartist:
            target_albumartist = _canonicalize_artist_value(target_albumartist,
                                                            known_names=known_artist_names)

        ids = {str(t.get('musicbrainz_albumid') or '').strip().lower()
               for t in all_tags if str(t.get('musicbrainz_albumid') or '').strip()}
        rgids_all = {str(t.get('musicbrainz_releasegroupid') or '').strip().lower()
                     for t in all_tags if str(t.get('musicbrainz_releasegroupid') or '').strip()}
        albumversion_values = {str(t.get('albumversion') or t.get('album_version') or '').strip()
                               for t in all_tags if str(t.get('albumversion') or t.get('album_version') or '').strip()}
        # Navidrome's default Album PID fallback also uses albumversion and releasedate.
        # A missing MBID on M4A/MP4 cannot reliably be propagated, so clear a lone MBID
        # from the whole exact-alias group instead of creating another split on every scan.
        unwritable_missing_album_id = any(
            f.suffix.lower() in ('.m4a', '.mp4') and
            not str(t.get('musicbrainz_albumid') or '').strip()
            for f, t in zip(all_files, all_tags))
        drop_album_ids = len(ids) > 1 or (len(ids) == 1 and unwritable_missing_album_id)
        unwritable_missing_rgid = any(
            f.suffix.lower() in ('.m4a', '.mp4') and
            not str(t.get('musicbrainz_releasegroupid') or '').strip()
            for f, t in zip(all_files, all_tags))
        drop_rgids = len(rgids_all) > 1 or (len(rgids_all) == 1 and unwritable_missing_rgid)
        common_mbid = next(iter(ids)) if len(ids) == 1 and not drop_album_ids else ''
        common_rgid = next(iter(rgids_all)) if len(rgids_all) == 1 and not drop_rgids else ''
        common_albumversion = next(iter(albumversion_values)) if len(albumversion_values) == 1 else ''
        drop_albumversion = len(albumversion_values) > 1
        date_counts = Counter(str(t.get('date') or '').strip() for t in all_tags if str(t.get('date') or '').strip())
        originaldate_counts = Counter(str(t.get('originaldate') or '').strip() for t in all_tags if str(t.get('originaldate') or '').strip())
        common_date = date_counts.most_common(1)[0][0] if date_counts else ''
        common_originaldate = originaldate_counts.most_common(1)[0][0] if originaldate_counts else ''
        changed = []
        for f, t in zip(all_files, all_tags):
            diff = {}
            if target_album and t.get('album', '') != target_album:
                diff['album'] = target_album
            if target_albumartist and t.get('albumartist', '') != target_albumartist:
                diff['albumartist'] = target_albumartist
            if common_date and t.get('date', '') != common_date and _unify_applies(f, t, 'date', {'originaldate': common_originaldate}):
                diff['date'] = common_date
            if common_originaldate and t.get('originaldate', '') != common_originaldate and _unify_applies(f, t, 'originaldate', {'originaldate': common_originaldate}):
                diff['originaldate'] = common_originaldate
            current_version = str(t.get('albumversion') or t.get('album_version') or '').strip()
            if drop_albumversion and current_version:
                diff['albumversion'] = None
            elif common_albumversion and current_version != common_albumversion:
                diff['albumversion'] = common_albumversion
            current_mbid = str(t.get('musicbrainz_albumid') or '').strip().lower()
            current_rgid = str(t.get('musicbrainz_releasegroupid') or '').strip().lower()
            if drop_album_ids and current_mbid:
                diff['musicbrainz_albumid'] = None
            elif common_mbid and not current_mbid and f.suffix.lower() not in ('.m4a', '.mp4'):
                diff['musicbrainz_albumid'] = common_mbid
            if drop_rgids and current_rgid:
                diff['musicbrainz_releasegroupid'] = None
            elif common_rgid and not current_rgid:
                diff['musicbrainz_releasegroupid'] = common_rgid
            if diff:
                changed.append((f, diff))
        if not changed:
            continue
        label = ' | '.join(f"{r['album'].parent.name}/{r['album'].name} ({len(r['files'])} tracce)"
                           for r in group)
        fields = []
        if target_album:
            fields.append(f'ALBUM="{target_album[:70]}"')
        if target_albumartist:
            fields.append(f'ALBUMARTIST="{target_albumartist[:70]}"')
        if drop_album_ids:
            reason = f'{len(ids)} valori' if len(ids) > 1 else 'MBID non propagabile a M4A/MP4'
            fields.append(f'rimuovi MBID album ({reason})')
        if drop_rgids:
            reason = f'{len(rgids_all)} valori' if len(rgids_all) > 1 else 'RGID non propagabile a M4A/MP4'
            fields.append(f'rimuovi release-group ID ({reason})')
        if common_mbid and any(not str(t.get('musicbrainz_albumid') or '').strip() for t in all_tags):
            fields.append('propaga MBID univoco ai tag mancanti')
        if common_rgid and any(not str(t.get('musicbrainz_releasegroupid') or '').strip() for t in all_tags):
            fields.append('propaga release-group ID univoco ai tag mancanti')
        if drop_albumversion:
            fields.append('rimuovi ALBUMVERSION discordante')
        elif common_albumversion and any(not str(t.get('albumversion') or t.get('album_version') or '').strip() for t in all_tags):
            fields.append('propaga ALBUMVERSION univoco')
        if common_date and len(date_counts) > 1:
            fields.append(f'allinea DATE a {common_date}')
        if common_originaldate and len(originaldate_counts) > 1:
            fields.append(f'allinea ORIGINALDATE a {common_originaldate}')
        print(f"{'[dry] ' if dry_run else ''}CROSS-ALBUM {label}: {', '.join(fields)}; "
              f'{len(changed)} file')
        fixed_groups += 1
        if dry_run:
            changed_files += len(changed)
            continue
        for f, diff in changed:
            try:
                if f.suffix.lower() == '.flac':
                    write_flac(f, diff)
                else:
                    _rewrite_nonflac(f, diff)
                changed_files += 1
            except Exception as e:
                errors += 1
                print(f'[ERRORE] CROSS-ALBUM {f}: {e}', file=sys.stderr)
    if fuzzy_pairs:
        report = [f"Cross-folder fuzzy album candidates — {time.strftime('%Y-%m-%d %H:%M:%S')}",
                  'These pairs are REVIEW ONLY. No fuzzy pair was merged automatically.', '']
        for a, b, sim, label, evidence_label, rg_conflict in sorted(fuzzy_pairs, key=lambda x: -x[2]):
            report.append(f"score={sim:.3f} {a['album'].parent.name}/{a['album'].name} "
                          f"({len(a['files'])} tracks) <-> {b['album'].parent.name}/{b['album'].name} "
                          f"({len(b['files'])} tracks) [{label}; "
                          f"{evidence_label or 'no fragment evidence'}; "
                          f"release-group conflict={'yes' if rg_conflict else 'no'}]")
            report.extend(f'  A: {f}' for f in a['files'][:3])
            report.extend(f'  B: {f}' for f in b['files'][:3])
        _embed_report_in_main_log('album_cross_folder_review', report)
        _cleanup_standalone_album_reports()
        print(f'[review] {len(fuzzy_pairs)} coppie album fuzzy NON unite; report completo solo nel log e2m (nessun file separato)')
    print(f'cross-folder albums: {fixed_groups} gruppi esatti/alias | '
          f'{changed_files} file aggiornati | {len(fuzzy_pairs)} candidati fuzzy solo report | {errors} errori')
    return fixed_groups, changed_files, errors


def _keeper_score(f: Path, tags: dict):
    """Punteggio piu' basso = da tenere. Preferisce: title tag senza
    'remaster/deluxe/...', flac > m4a > mp3 > altro, data piu' vecchia,
    nome piu' corto. ATTENZIONE: il check remaster guarda SOLO il title tag:
    nei nomi file 'Titolo - Album (Remastered) - Artista' l'album farebbe
    penalizzare a torto il file lossless."""
    ext_rank = {'.flac': 0, '.m4a': 1, '.wav': 1, '.mp3': 2, '.ogg': 2, '.opus': 2}
    title = (tags.get('title') or '').strip()
    if not title:
        title = re.sub(r'^\d{1,3}\s*[-._:]\s*', '', f.stem)
    remaster = 1 if re.search(r'remaster|deluxe|anniversary|re-?issue|expanded',
                              title, re.I) else 0
    ext = ext_rank.get(f.suffix.lower(), 3)
    date = (tags.get('date') or '9999')[:4]
    if not date.isdigit():
        date = '9999'
    return (remaster, ext, date, len(f.name))


def _cluster_by_waveform(files, meta, corr, max_dur, trust_format=False):
    """Suddivide i file di un gruppo (stesso titolo) in CLUSTER per versione:
    due file finiscono nello stesso cluster se le durate sono compatibili e
    la correlazione >= corr. Coppie non verificabili (fingerprint None,
    es. file <5s) non vengono MAI unite: sicurezza prima di tutto.
    Ritorna (lista di cluster, dict fingerprint)."""
    # Fingerprinting invokes ffmpeg and dominated the supplied dry-run's 21m54s
    # dedupe_tracks phase. Decode a small group concurrently, with an explicit low default
    # for NAS-friendly behavior. Correlation and clustering order remain deterministic.
    workers = max(1, min(WAVEFORM_WORKERS, len(files)))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            fps = dict(zip(files, executor.map(fingerprint, files)))
    else:
        fps = {f: fingerprint(f) for f in files}
    parent = {f: f for f in files}

    def find(a):
        while parent[a] is not a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, a in enumerate(files):
        for b in files[i + 1:]:
            _, da = meta[a]
            _, db = meta[b]
            if not _dur_compatible(da, db, max_dur):
                continue
            if trust_format:
                # fidati della durata SOLO per coppie miste lossless+lossy
                # (es. mp3 Spotify accanto al flac: stessa canzone, master
                # diverso, vuoi il lossless). Stesso formato (flac+flac):
                # il waveform resta obbligatorio, altrimenti versioni
                # karaoke/instrumental/remix/demo con durata simile
                # verrebbero cancellate per errore.
                _LOSSLESS = {'.flac', '.wav'}
                if (a.suffix.lower() in _LOSSLESS) != (b.suffix.lower() in _LOSSLESS):
                    parent[find(a)] = find(b)
                continue
            if fps[a] is None or fps[b] is None:
                continue
            c = correlate(fps[a], fps[b], stop_at=corr)
            if c is not None and c >= corr:        # None = non confrontabili
                parent[find(a)] = find(b)

    clusters = {}
    for f in files:
        clusters.setdefault(find(f), []).append(f)
    return list(clusters.values()), fps


def _metadata_duplicate_reason(group, meta):
    """Conservative metadata-only fallback for duplicate files with low waveform correlation."""
    if len(group) < 2:
        return None
    strict_titles = {norm_bare(best_title(f, meta[f][0])) for f in group}
    track_numbers = {_track_number_for_tags(meta[f][0]) for f in group}
    durations = [meta[f][1] for f in group]
    qualified = any(_has_qualifier(norm_bare(best_title(f, meta[f][0]))) for f in group)
    durations_close = (all(d for d in durations) and
                       max(durations) - min(durations) <= max(1.0, max(durations) * 0.015))
    lossless_exts = {'.flac', '.wav'}
    lossless_files = [f for f in group if f.suffix.lower() in lossless_exts]
    lossy_files = [f for f in group if f.suffix.lower() not in lossless_exts]
    cross_format_missing_numbers = (
        len(group) == 2 and len(lossless_files) == 1 and len(lossy_files) == 1
        and None in track_numbers and len(track_numbers) <= 2)
    matching_numbers = len(track_numbers) == 1 and None not in track_numbers
    if (len(strict_titles) == 1 and not qualified and durations_close
            and (matching_numbers or cross_format_missing_numbers)):
        return 'crossformat' if cross_format_missing_numbers and not matching_numbers else 'metadata'
    return None


def run_dedupe_tracks(apply=False, hard_delete=False, artist=None, base=None,
                      corr=0.95, max_dur=10.0, trust_format=False):
    """Duplicati di tracce DENTRO la stessa cartella album (es. originale +
    remaster scaricati nella stessa cartella: stesso titolo, due file).
    Il keeper e' scelto da _keeper_score; se il waveform e' disponibile e due
    candidati NON correlano (>0.97), il gruppo viene saltato: potrebbero essere
    incisioni diverse con lo stesso titolo."""
    base = Path(base) if base else LIBRARY_ROOT
    print(f"waveform compare: {'ATTIVO' if _HAS_NP else 'DISATTIVO (attenti ai falsi positivi)'}")
    print(f"modo: {'APPLY' if apply else 'DRY-RUN'}{' (hard delete!)' if hard_delete else ''}")

    stamp = time.strftime('%Y%m%d_%H%M%S')
    n_groups = n_dup = n_distinct = unverifiable = n_review = errors = 0
    skip = SKIP_TOP | {'.git'}

    artists = sorted(d for d in base.iterdir()
                     if d.is_dir() and d.name.lower() not in skip
                     and not d.name.startswith('.'))
    if artist:
        artists = [a for a in artists if norm(a.name) == norm(artist)]
        if not artists:
            print(f"[ERRORE] artista '{artist}' non trovato in {base}")
            return

    # Prepara tutti gli album una volta e fa un solo prefetch. Prima ogni album chiamava
    # prefetch_probe(), che salvava l'intera cache JSON a ogni gruppo di file nuovi: in una
    # libreria fredda questo causava scritture ripetute del file cache, crescenti col tempo.
    album_batches = []
    all_candidate_files = []
    for art in artists:
        for album in sorted(art.iterdir()):
            if not album.is_dir():
                continue
            files = _audio_files(album)
            if len(files) < 2:
                continue
            album_batches.append((art, album, files))
            all_candidate_files.extend(files)
    if all_candidate_files:
        prefetch_probe(all_candidate_files, 'dedupe')

    progress = _ProgressBar('dedupe_tracks', len(album_batches), 'album')
    for batch_index, (art, album, files) in enumerate(album_batches, 1):
        progress.update(batch_index)
        def handle_group(label, group):
            """Verifica waveform + eventuale cestinamento di un gruppo
            di file che condividono il titolo (strict o fuzzy)."""
            nonlocal n_groups, n_dup, n_distinct, unverifiable, errors
            n_groups += 1
            if not _HAS_NP:
                # The conservative metadata check does not need waveform/numpy; retain this
                # safe fallback even on installations without the optional numerical library.
                reason = _metadata_duplicate_reason(group, meta)
                if reason:
                    ordered = sorted(group, key=lambda f: _keeper_score(f, meta[f][0]))
                    keeper, rest = ordered[0], ordered[1:]
                    for f in rest:
                        n_dup += 1
                        progress.clear()
                        tag = 'DUPE-METADATA-CROSSFORMAT' if reason == 'crossformat' else 'DUPE-METADATA'
                        why = ('titolo esatto + durata e formato lossless/lossy (numero traccia assente)'
                               if reason == 'crossformat' else 'titolo, numero traccia e durata coincidono')
                        print(f"    {'[dry] ' if not apply else ''}{tag} {album.name}/{f.name} == {keeper.name} "
                              f"({why}; numpy non disponibile)")
                        if apply:
                            try:
                                _move_to_trash(f, stamp, hard_delete, base)
                            except Exception as e:
                                errors += 1
                                progress.clear()
                                print(f"    ERRORE spostamento {f}: {e}", file=sys.stderr)
                    return
                unverifiable += 1
                progress.clear()
                print(f"    [info] {album.name}: titolo '{label}' x{len(group)} "
                      f"— numpy assente, niente verifica: lascio tutto")
                return
            clusters, fps = _cluster_by_waveform(group, meta, corr, max_dur,
                                                 trust_format=trust_format)
            multi = [c for c in clusters if len(c) > 1]
            if not multi:
                # Different mastering can lower waveform correlation even for duplicated
                # album tracks. Use the same conservative metadata fallback without requiring
                # track numbers for the special two-file lossless/lossy case.
                reason = _metadata_duplicate_reason(group, meta)
                if reason:
                    ordered = sorted(group, key=lambda f: _keeper_score(f, meta[f][0]))
                    keeper, rest = ordered[0], ordered[1:]
                    why = ('titolo esatto + durata e formato lossless/lossy (numero traccia assente)'
                           if reason == 'crossformat' else 'titolo, numero traccia e durata coincidono')
                    tag = 'DUPE-METADATA-CROSSFORMAT' if reason == 'crossformat' else 'DUPE-METADATA'
                    for f in rest:
                        n_dup += 1
                        progress.clear()
                        print(f"    {'[dry] ' if not apply else ''}{tag} {album.name}/{f.name} == {keeper.name} "
                              f"({why}; correlazione audio bassa)")
                        if apply:
                            try:
                                _move_to_trash(f, stamp, hard_delete, base)
                            except Exception as e:
                                errors += 1
                                progress.clear()
                                print(f"    ERRORE spostamento {f}: {e}", file=sys.stderr)
                    return
                n_distinct += 1
                if all(fps[f] is None for f in group):
                    unverifiable += 1
                    progress.clear()
                    print(f"    [info] {album.name}: titolo '{label}' x{len(group)} "
                          f"non verificabile (file <5s o non decodificabili)")
                else:
                    progress.clear()
                    print(f"    [info] {album.name}: titolo '{label}' con "
                          f"{len(group)} file ma versioni distinte (nessuna copia)")
                return
            for cluster in multi:
                cluster = sorted(cluster, key=lambda f: _keeper_score(f, meta[f][0]))
                keeper, rest = cluster[0], cluster[1:]
                for f in rest:
                    n_dup += 1
                    progress.clear()
                    print(f"    {'[dry] ' if not apply else ''}DUPE  {album.name}/"
                          f"{f.name} (tengo {keeper.name})")
                    if apply:
                        try:
                            _move_to_trash(f, stamp, hard_delete, base)
                        except Exception as e:
                            errors += 1
                            progress.clear()
                            print(f"    ERRORE spostamento {f}: {e}",
                                  file=sys.stderr)

        # indicizza: strict (parentesi incluse) e fuzzy (parentesi ignorate)
        meta = {}
        strict_key, fuzzy_key = {}, {}
        for f in files:
            tags, dur = probe_dur(f)
            meta[f] = (tags, dur)
            strict_key[f] = norm_bare(best_title(f, tags))
            fuzzy_key[f] = norm(best_title(f, tags))

        # FASE 1: gruppi STRICT — titoli identici parentesi incluse
        singles = []
        by_strict = {}
        for f in files:
            by_strict.setdefault(strict_key[f], []).append(f)
        for label, group in by_strict.items():
            if len(group) >= 2:
                handle_group(label, group)
            else:
                singles.extend(group)

        # FASE 2: fuzzy SOLO per i singletti — parentesi ignorate.
        # Gate qualificatori: se alcuni file hanno parole-tipo (mix/live/
        # karaoke/...) e altri no, NON cestinare nulla automaticamente:
        # sono versioni diverse della stessa canzone (karaoke vs originale),
        # meglio un occhio umano. Il waveform da solo non li distingue.
        by_fuzzy = {}
        for f in singles:
            by_fuzzy.setdefault(fuzzy_key[f], []).append(f)
        for label, group in by_fuzzy.items():
            if len(group) < 2:
                continue
            qual = {_has_qualifier(strict_key[f]) for f in group}
            if True in qual and False in qual:
                n_review += 1
                progress.clear()
                print(f"    [review] {album.name}: titolo '{label}' con {len(group)} "
                      f"file e versioni qualificate (mix/live/karaoke/...): "
                      f"lascio tutto, verifica a orecchio")
                continue
            handle_group(label, group)

    progress.close(complete=True)

    print(f"\ngruppi titolo esaminati: {n_groups} | duplicati nel cestino: {n_dup} "
          f"| versioni distinte: {n_distinct} | da verificare a orecchio: {n_review} "
          f"| non verificabili: {unverifiable} | errori: {errors}")
    if apply and not hard_delete:
        print(f"[i] duplicati nel cestino: {DEDUPE_TRASH / stamp}")
    if apply:
        print("[i] dopo verifica: scan rapido su Navidrome, poi svuota il cestino.")


def run_dedupe_cross_album_tracks(apply=False, hard_delete=False, base=None):
    """Trova duplicati dello stesso brano tra cartelle album che saranno unite da Navidrome.

    Opera solo fra cartelle con album/album-artist canonici uguali e titolo traccia esatto.
    Richiede numeri traccia uguali oppure la regola stretta FLAC+lossy con numerazione assente,
    durata quasi identica e nessun qualificatore (Live/Demo/Mix ecc.). Le cartelle marcate come
    edizioni diverse restano separate. Senza --apply produce solo un report; con --apply sposta
    i duplicati nel cestino già usato da dedupe_tracks, non li cancella definitivamente.
    """
    base = Path(base) if base else LIBRARY_ROOT
    dirs = list(unify_album_dirs(base))
    all_files = [f for _album, files in dirs for f in files]
    if not all_files:
        print('dedupe_cross_album_tracks: nessun file audio')
        return {'groups': 0, 'duplicates': 0, 'errors': 0}
    prefetch_probe(all_files, 'dedupe_cross_album_tracks')
    known_names = _navidrome_artist_name_map()
    by_title = {}
    for album_dir, files in dirs:
        file_tags = [probe(f) for f in files]
        album_title = majority(file_tags, 'album') or album_dir.name
        artist_values = [str(t.get('albumartist') or t.get('album_artist') or '').strip()
                         for t in file_tags]
        artist_values = [v for v in artist_values if v]
        album_artist = majority(file_tags, 'albumartist') or (
            artist_values[0] if artist_values else album_dir.parent.name)
        album_artist = _canonicalize_artist_value(album_artist, known_names=known_names)
        album_key = norm(album_title)
        artist_key = norm(album_artist)
        if not album_key or not artist_key:
            continue
        markers = frozenset(_album_explicit_edition_markers([album_dir.name, album_title]))
        for f in files:
            tags, duration = probe_dur(f)
            title = best_title(f, tags)
            strict_key = norm_bare(title)
            if not strict_key or not title:
                continue
            by_title.setdefault((artist_key, album_key, strict_key), []).append(
                {'file': f, 'tags': tags, 'duration': duration,
                 'album_dir': album_dir.resolve(), 'markers': markers,
                 'album_artist': album_artist, 'album_title': album_title})

    n_groups = n_duplicates = errors = skipped_editions = 0
    stamp = time.strftime('%Y%m%d_%H%M%S')
    for (_artist_key, _album_key, label), records in by_title.items():
        if len(records) < 2:
            continue
        parent = list(range(len(records)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        def union(i, j):
            a, b = find(i), find(j)
            if a != b:
                parent[b] = a
        meta = {r['file']: (r['tags'], r['duration']) for r in records}
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                a, b = records[i], records[j]
                if a['album_dir'] == b['album_dir']:
                    continue  # intra-folder duplicati sono gestiti da dedupe_tracks
                if a['markers'] != b['markers']:
                    skipped_editions += 1
                    continue
                reason = _metadata_duplicate_reason([a['file'], b['file']], meta)
                if reason:
                    union(i, j)
        clusters = {}
        for i, record in enumerate(records):
            clusters.setdefault(find(i), []).append(record)
        for cluster in clusters.values():
            if len(cluster) < 2 or len({r['album_dir'] for r in cluster}) < 2:
                continue
            n_groups += 1
            ordered = sorted(cluster, key=lambda r: _keeper_score(r['file'], r['tags']))
            keeper = ordered[0]
            for duplicate in ordered[1:]:
                n_duplicates += 1
                reason = _metadata_duplicate_reason([keeper['file'], duplicate['file']], {
                    keeper['file']: (keeper['tags'], keeper['duration']),
                    duplicate['file']: (duplicate['tags'], duplicate['duration'])}) or 'metadata'
                label_reason = ('titolo esatto + durata + formato lossless/lossy, track number assente'
                                if reason == 'crossformat' else 'titolo esatto + track number/durata')
                print(f"    {'[dry] ' if not apply else ''}DUPE-CROSS-ALBUM {duplicate['file']} == "
                      f"{keeper['file']} ({label_reason}; {keeper['album_artist']} / {keeper['album_title']})")
                if apply:
                    try:
                        _move_to_trash(duplicate['file'], stamp, hard_delete, base)
                    except Exception as e:
                        errors += 1
                        print(f'[ERRORE] spostamento duplicato cross-album {duplicate["file"]}: {e}',
                              file=sys.stderr)
    print(f'dedupe cross-album: {n_groups} gruppi, {n_duplicates} duplicati '
          f'{"eliminati in modo definitivo" if apply and hard_delete else ("spostati nel cestino" if apply else "da revisionare/applicare con --apply")}; '
          f'{skipped_editions} confronti saltati per marcatori d’edizione discordanti; errori={errors}')
    return {'groups': n_groups, 'duplicates': n_duplicates, 'errors': errors}


# ===================== infrastruttura fasi (log UNICO + timer) =====================

_PHASE_TIMINGS = []       # [(nome fase, secondi), ...] nell'ordine di esecuzione
_RUN_STARTED_AT = None
_RUN_INTERRUPTED = False
_RUN_FAILED_PHASES = []   # errori visibili anche nel codice di uscita della pipeline
_PHASE_PROGRESS_INDEX = 0
_PHASE_PROGRESS_TOTAL = 1

def _elapsed_text(seconds):
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    millis = int((seconds - whole) * 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"

def _print_timing_summary():
    if _RUN_STARTED_AT is None:
        return
    total = time.perf_counter() - _RUN_STARTED_AT
    print("\n=== riepilogo tempi ===", file=sys.stderr, flush=True)
    if _RUN_INTERRUPTED:
        print("  [!] RUN INTERROTTA: le fasi successive non sono state eseguite",
              file=sys.stderr, flush=True)
    if not _PHASE_TIMINGS:
        print("  nessuna fase misurata", file=sys.stderr)
    else:
        width = min(44, max(len(name) for name, _ in _PHASE_TIMINGS))
        for name, elapsed in _PHASE_TIMINGS:
            print(f"  {name:<{width}}  {_elapsed_text(elapsed):>12s}", file=sys.stderr)
    width = min(44, max([len(n) for n, _ in _PHASE_TIMINGS] or [6]))
    print(f"  {'TOTALE':<{width}}  {_elapsed_text(total):>12s}", file=sys.stderr, flush=True)
    print("=== fine riepilogo tempi ===", file=sys.stderr, flush=True)

def _estimate_phase_total(args):
    """Stima il numero di fasi previste per l'esecuzione selezionata.

    Le due fasi opzionali legate a risultati esterni (pulizia playlist dopo fetch e scan dopo
    download cover) vengono contate solo quando sono richieste/prevedibili; se un provider
    attiva un ramo imprevisto run_phase allarga il totale senza bloccare la run.
    """
    names = ['load_user_config']
    if args.all:
        names.append('diagnose_album_splits')
    # Utility che chiudono la run dopo una sola azione.
    utility = [
        (args.fix_all_playlist_owners is not None, 'fix_all_playlist_owners'),
        (args.fix_flac_safe, 'fix_flac_safe'), (args.lidarr_folder_fix, 'lidarr_folder_fix'),
        (args.lidarr_import_slskd, 'lidarr_import_slskd'),
        (args.lb_dedup is not None, 'listenbrainz_dedup'),
        (args.sync_spotify_proxy_config, 'sync_spotify_proxy_config'),
        (args.build_spotify_proxies, 'build_spotify_local_proxies'),
        (args.sync_proxy_favorites, 'sync_proxy_favorites'),
    ]
    selected_utility = next((n for yes, n in utility if yes), None)
    if selected_utility:
        names.append(selected_utility)
        return len(names)
    if args.diagnose_album_splits and not args.all:
        names.append('diagnose_album_splits')
        if args.repair_album_groups:
            names.append('repair_album_groups')
            if args.apply and not args.dry_run and not args.no_scan:
                names.append('navidrome_scan')
        return len(names)
    if args.repair_album_groups and not args.all:
        names.append('repair_album_groups')
        if args.apply and not args.dry_run and not args.no_scan:
            names.append('navidrome_scan')
        return len(names)
    if args.fetch_login:
        names.append('fetch_login')
        return len(names)
    if args.fetch_list:
        names.append('list_exportify_sessions')
        return len(names)
    if args.fetch_check:
        names.append('check_exportify_sessions')
        return len(names)
    if args.check_albums and not args.all:
        names.append('check_albums')
        return len(names)
    if args.fetch_only:
        names.append('fetch_exportify')
        return len(names)
    if args.missing:
        names.extend(['index_library', 'report_missing_tracks'])
        return len(names)
    if args.explain:
        names.extend(['index_library', 'explain_track_match'])
        return len(names)
    if args.rebuild_album:
        names.append('rebuild_album')
        return len(names)
    maintenance = any([args.fix_owners is not None, args.dedupe_playlists, args.dedupe_releases,
                       args.dedupe_tracks, args.mp3_vs_flac, args.clean_empty,
                       args.fix_collab_artists, args.star_liked])
    if args.unify_only:
        names.append('album_unify')
        if not args.dry_run and not args.no_scan:
            names.append('navidrome_scan')
        return len(names)
    if args.fix_owners is not None: names.append('fix_playlist_owners')
    if args.dedupe_playlists: names.append('dedupe_playlists')
    if args.dedupe_releases: names.append('dedupe_releases')
    if args.dedupe_tracks: names.append('dedupe_tracks')
    if args.mp3_vs_flac: names.append('mp3_vs_flac')
    if args.fix_collab_artists: names.append('fix_collab_artists')
    if args.flac_16bit: names.append('flac_16bit')
    if args.clean_empty: names.append('clean_empty')
    if args.playlists or not maintenance:
        if args.fetch and not args.dry_run and not args.csv and not args.no_unzip:
            names.append('fetch_exportify')
        if not args.csv and not args.no_unzip:
            names.append('unzip_and_prune_csv')
        names.extend(['index_library', 'generate_m3u_playlists'])
        if args.fetch and not args.dry_run and not args.csv and not args.no_unzip:
            names.extend(['prune_stale_m3u', 'prune_stale_m3u_db'])
        if not args.skip_date_heal: names.append('date_heal')
        if not args.skip_romaji: names.append('romaji_tags')
        if not args.skip_artist_names: names.append('artist_names')
        if not args.skip_unify: names.append('album_unify')
        if args.all: names.extend(['repair_album_groups', 'dedupe_cross_album_tracks', 'check_album_completeness'])
        if not args.skip_fix_dates: names.append('fix_date_tags')
        if not args.dry_run and not args.sync_only: names.append('report_library_gaps')
    has_scan_creds = bool(SUBSONIC_PASS or any(k.startswith('ND_PASS_') and v for k, v in os.environ.items()))
    will_scan_before_stars = bool(args.star_liked and not args.dry_run and not args.no_scan and has_scan_creds)
    if will_scan_before_stars:
        names.append('navidrome_scan_before_stars')
        if args.all and not args.sync_only:
            names.extend(['targeted_date_heal', 'targeted_romaji_tags', 'targeted_artist_names',
                          'targeted_album_unify', 'targeted_repair_album_groups',
                          'targeted_fix_date_tags', 'navidrome_scan_after_album_repair',
                          'diagnose_album_splits_after_scan'])
    elif not args.dry_run and not args.no_scan:
        # Senza pre-scan (run normale senza star-liked o credenziali assenti), il percorso
        # principale effettua lo scan finale. In --all segue la stessa riconciliazione mirata.
        names.append('navidrome_scan_final')
        if args.all and not args.sync_only:
            names.extend(['targeted_date_heal', 'targeted_romaji_tags', 'targeted_artist_names',
                          'targeted_album_unify', 'targeted_repair_album_groups',
                          'targeted_fix_date_tags', 'navidrome_scan_after_album_repair',
                          'diagnose_album_splits_after_scan'])
    if args.star_liked and not args.dry_run:
        names.append('star_liked')
    if not args.no_artwork_download and MISSING_ARTWORK_CONFIG.get('enabled', True):
        names.append('download_missing_album_artwork')
    return len(names)


def run_phase(logname, fn, *args, **kwargs):
    """Esegue e misura una fase; distingue completamento, errore e interruzione."""
    global _RUN_INTERRUPTED, _RUN_FAILED_PHASES, _PHASE_PROGRESS_INDEX, _PHASE_PROGRESS_TOTAL
    _PHASE_PROGRESS_INDEX += 1
    if _PHASE_PROGRESS_INDEX > _PHASE_PROGRESS_TOTAL:
        _PHASE_PROGRESS_TOTAL = _PHASE_PROGRESS_INDEX
    print(f'=== fase {logname} === {_PHASE_PROGRESS_INDEX}/{_PHASE_PROGRESS_TOTAL}', flush=True)
    started = time.perf_counter()
    result = None
    status = 'completata'
    try:
        result = fn(*args, **kwargs)
        if result is False:
            status = 'fallita (ritorno False)'
        elif isinstance(result, dict):
            error_count = result.get('errors', 0)
            if isinstance(error_count, (int, float)) and error_count > 0:
                status = f'fallita ({int(error_count)} errori nel risultato)'
    except KeyboardInterrupt:
        status = 'interrotta'
        _RUN_INTERRUPTED = True
        raise
    except SystemExit:
        status = 'uscita anticipata'
        raise
    except Exception as e:
        status = 'terminata con errore'
        print(f'[ERRORE] fase {logname}: {type(e).__name__}: {e}', file=sys.stderr)
        traceback.print_exc()
    finally:
        _auto_translation_cache_save()
        flush_probe_cache()
        elapsed = time.perf_counter() - started
        _PHASE_TIMINGS.append((logname, elapsed))
        if status != 'completata':
            _RUN_FAILED_PHASES.append((logname, status))
        if status == 'completata':
            label = f'fine fase {logname}'
        else:
            label = f'{status}: {logname}'
        print(f'=== {label} === {_elapsed_text(elapsed)}', flush=True)
    return result


# ===================== fase: artist_names (UN nome per artista) =====================
# Su Navidrome lo stesso artista giapponese/coreano compariva con 3 nomi:
#   'masayoshi takanaka'                (latino: spotyFLAC / tagger)
#   '高中正義'                           (kanji: tag originale)
#   '高中正義 (masayoshi takanaka)'      (gloss bilingue scritto da romaji_tags)
# Cause: romaji_tags aggiunge il gloss SOLO ai tag che contengono CJK, e album_unify
# riscriveva ALBUMARTIST ma ARTIST solo se i token del tag erano un sottoinsieme di
# quelli della cartella (mai vero per 'masayoshi takanaka' vs '高中正義').
# Questa fase porta TUTTE le scritture note dello stesso artista (NAME_TRANSLATIONS, NAME_FIXES,
# ARTIST_GROUPS, kakasi) alla forma canonica della cartella, nei tag ARTIST /
# ALBUMARTIST (e ARTISTS / ALBUMARTISTS dei FLAC, che Navidrome legge per i
# multi-artista). Cartelle in kanji/hangul: sempre. Cartelle latine: solo se nei tag
# della cartella compare davvero la scrittura CJK (evita falsi positivi tipo il
# 'Prism' canadese scambiato per 'プリズム').

_NF_REV = None
_FLAC_ARTIST_TAGS = ('ARTIST', 'ALBUMARTIST', 'ARTISTS', 'ALBUMARTISTS')


def _name_fixes_rev():
    """Nome canonico normalizzato -> alias originali da traduzioni e NAME_FIXES."""
    global _NF_REV
    if _NF_REV is None:
        _NF_REV = {}
        for table in (NAME_TRANSLATIONS, NAME_FIXES):
            for k, v in table.items():
                value_key = norm(v)
                if k and value_key:
                    _NF_REV.setdefault(value_key, set()).add(k)
    return _NF_REV


def _has_asian(s):
    return bool(s and (_CJK.search(s) or _HANGUL.search(s)))


def _artist_variants(name):
    """Tutte le scritture (norm) che la configurazione conosce per lo STESSO artista:
    il nome, la traduzione/alias (NAME_TRANSLATIONS/NAME_FIXES) o romaji e la direzione inversa latino->CJK e i
    gruppi ARTIST_GROUPS. norm() toglie le parentesi: 'kanji (latino)' == 'kanji'."""
    n = norm(name)
    if not n:
        return set()
    out = {n}
    rev = _name_fixes_rev()
    for _ in range(2):
        for x in list(out):
            r = to_romaji(x)
            if r:
                out.add(r)
            out |= rev.get(x, set())
        for g in ARTIST_GROUPS:
            if out & g:
                out |= g
    out.discard('')
    return out


def _remap_artist_value(v, variants, canon):
    """'A; B' -> stessa lista con le scritture note dell'artista sostituite da
    canon e senza doppioni ('高中正義; masayoshi takanaka' -> un solo valore)."""
    parts = [p.strip() for p in v.split(';') if p.strip()]
    if not parts:
        return v
    out = []
    for p in parts:
        q = canon if norm(p) in variants else p
        if q not in out:
            out.append(q)
    return '; '.join(out)


def _artist_values_equivalent(a, b):
    """True se due valori sono alias documentati/fonetici dello stesso artista."""
    if str(a or '').strip().casefold() == str(b or '').strip().casefold():
        return True
    # norm() scarta le parentesi: sui nomi solo latini potrebbe confondere un nome reale
    # come 'Artist (Live)' con 'Artist'. Usiamo quella equivalenza solo quando e' coinvolto CJK.
    if _has_asian(a) or _has_asian(b):
        if norm(a) == norm(b):
            return True
        try:
            return bool(_artist_variants(a) & _artist_variants(b))
        except Exception:
            return False
    return False


def _prefer_bilingual_artist(a, b):
    """Sceglie la forma CJK + gloss latino invece del solo CJK/solo alias."""
    def score(v):
        has_cjk = _has_asian(v)
        m = re.search(r'\(([^()]*)\)', v)
        gloss = m.group(1) if m else ''
        has_latin_gloss = bool(re.search(r'[A-Za-z]', gloss))
        has_cjk_latin = has_cjk and has_latin_gloss
        # Se due voci equivalenti sono già bilingui, non convertire inutilmente la grafia
        # leggibile esistente in minuscolo solo perché la fonetica generata lo è.
        titlecase = sum(ch.isupper() for ch in gloss)
        return (int(has_cjk_latin), int(has_cjk), titlecase, len(v))
    return a if score(a) >= score(b) else b


def _titlecase_artist_gloss(value):
    """Capitalizza il gloss latino generato dalla fonetica, senza toccare nomi gia' stilizzati."""
    if not value or not _has_asian(value):
        return value
    match = re.search(r'[\(（]([^()（）]+)[\)）]\s*$', value)
    if not match or not re.search(r'[A-Za-z]', match.group(1)):
        return value
    gloss = match.group(1).strip()
    letters = ''.join(ch for ch in gloss if ch.isalpha())
    if letters and letters == letters.lower():
        return value[:match.start(1)] + gloss.title() + value[match.end(1):]
    return value


def _known_artist_display(value, known_names):
    """Resolve punctuation/translation/romaji variants to one existing catalog display name."""
    if not value or not known_names:
        return None
    key = norm(value)
    direct = known_names.get(key)
    if direct:
        return direct
    try:
        variant_keys = _artist_variants(value)
    except Exception:
        variant_keys = {key}
    candidates = [known_names[k] for k in variant_keys if k in known_names]
    if not candidates:
        return None
    # The existing catalog's bilingual CJK form wins; otherwise prefer a stable spelling
    # with dots over underscores and avoid arbitrary punctuation variants where possible.
    return max(candidates, key=_artist_display_score)


def _canonicalize_artist_value(value, known_names=None, context_names=None):
    """Canonicalize artist aliases and collaboration components.

    ``context_names`` contains folder labels from the track path. Semicolons and tight
    commas are explicit delimiters; spaced commas need catalog or folder evidence.
    """
    if not value:
        return value
    known_names = known_names or {}
    raw_value = str(value)
    # Strip a placeholder suffix even when it is appended without a comma/semicolon.
    # Such brackets are annotations, not a real artist credit. If the value consists only
    # of placeholders, preserve it: the inference phase must decide whether it is safe to
    # clear a genuinely unknown album artist (especially on compilations).
    raw_value = re.sub(r'[\[(]\s*unknown\s+artist\s*[\])]', '', raw_value, flags=re.I)
    if not raw_value.strip():
        return value
    raw_value = re.sub(r'\s*[;,]\s*$', '', raw_value).strip()
    if not raw_value:
        return value
    chunks = [p.strip() for p in raw_value.split(';') if p.strip()]
    parts = []
    for chunk in chunks:
        split = (_split_artist_tag_if_known(chunk, known_names, context_names)
                 if ',' in chunk else None)
        parts.extend(split or [chunk])
    if not parts:
        return value
    out = []
    for part in parts:
        part = part.strip()
        # Se Navidrome conosce gia' la forma bilingue migliore per questo stesso
        # stem CJK, applicala anche alle tracce che hanno ancora solo il kanji puro.
        preferred = _known_artist_display(part, known_names) if known_names else None
        punctuation_alias = ARTIST_CANONICAL_ALIASES.get(norm(part))
        preserve_catalog_spelling = False
        if punctuation_alias:
            # Explicit canonical aliases override the catalog label. Otherwise a stale
            # Navidrome entity called 'M.O.O.N.' wins and recreates the punctuation split
            # despite the configured canonical spelling 'M.O.O.N'.
            canonical = punctuation_alias
        elif preferred and _has_asian(preferred):
            # Reuse the best catalog spelling for CJK + translated/phonetic gloss forms.
            # _romanize_tag_value may replace an outdated gloss using an explicit mapping,
            # but if the catalog gloss is already authoritative keep its exact casing.
            # Title-casing here changed 'kanji (lowercase translation)' into a second
            # artist entity 'kanji (Titlecase Translation)' on every run.
            canonical = _romanize_tag_value(preferred)
            preserve_catalog_spelling = True
        elif preferred:
            # Also canonicalize Latin-only punctuation variants (M_O_O_N / M.O.O.N).
            canonical = preferred
        else:
            canonical = _romanize_tag_value(part) if _has_asian(part) else part
        if not preserve_catalog_spelling:
            canonical = _titlecase_artist_gloss(canonical)
        hit = next((i for i, old in enumerate(out)
                    if _artist_values_equivalent(old, canonical)), None)
        if hit is None:
            out.append(canonical)
        else:
            out[hit] = _prefer_bilingual_artist(out[hit], canonical)
    concrete = [name for name in out if not _is_unknown_artist(name)]
    if concrete:
        out = concrete
    return '; '.join(out)


def _canonicalize_artist_tag_values(values, known_names=None, context_names=None):
    """Canonicalize repeated artist tags, including folder-evidenced collaborations."""
    out = []
    for value in values:
        canonical_value = _canonicalize_artist_value(value, known_names=known_names,
                                                    context_names=context_names)
        parts = [p.strip() for p in str(canonical_value or '').split(';') if p.strip()]
        for canonical in parts:
            hit = next((i for i, old in enumerate(out)
                        if _artist_values_equivalent(old, canonical)), None)
            if hit is None:
                out.append(canonical)
            else:
                out[hit] = _prefer_bilingual_artist(out[hit], canonical)
    # Drop generic placeholders if at least one reliable artist remains among repeated/multi tags.
    concrete = [name for name in out if not _is_unknown_artist(name)]
    if concrete:
        out = concrete
    return out


def _folder_canon(folder_name, values):
    """Nome canonico dell'artista di una cartella, o None se non applicabile."""
    if _has_asian(folder_name):
        return _canonical_albumartist(folder_name)      # stessa regola di album_unify
    if not ROMAJI_TAGS_ACTIVE:
        return None
    variants = _artist_variants(folder_name)
    seen = Counter(v for v in values if _has_asian(v) and norm(v) in variants)
    if not seen:
        return None
    return _romanize_tag_value(seen.most_common(1)[0][0])


def _flac_raw_tags(path):
    """[(NOME_MAIUSCOLO, valore)] con TUTTI i valori (anche i tag ripetuti, che
    ffprobe fonde): serve per ARTISTS/ALBUMARTISTS dei FLAC taggati da MusicBrainz."""
    r = subprocess.run([*METAFLAC, '--export-tags-to=-', str(path)],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f'metaflac exit {r.returncode}: '
                           f'{r.stderr.decode("utf-8", "replace").strip()[:160]}')
    out = []
    for line in r.stdout.decode('utf-8', 'replace').split('\n'):
        k, sep, v = line.partition('=')
        if sep:
            out.append((k.strip().upper(), v.rstrip('\r')))
    return out


def _rewrite_nonflac(f, targets):
    """Riscrive i tag di un mp3/m4a/ogg/opus e ripristina l'originale se lo swap fallisce."""
    tmp = f.with_name(f.stem + '.tmp' + f.suffix)
    backup = f.with_name(f.name + '.meta-backup')
    try:
        write_ffmpeg(f, targets, tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    try:
        os.replace(f, backup)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    try:
        os.replace(tmp, f)
    except Exception:
        # Keep the source path usable if the new file cannot be committed (e.g. disk full,
        # permission change, transient I/O error). Preserve the backup only if restoration fails.
        try:
            if backup.exists() and not f.exists():
                os.replace(backup, f)
        except OSError as restore_error:
            raise RuntimeError(f'swap fallito per {f}; originale ancora in {backup}; '
                               f'ripristino fallito: {restore_error}')
        finally:
            tmp.unlink(missing_ok=True)
        raise
    invalidate_probe_cache([f])



def _rewrite_mp3_albumartist_id3(path, canonical):
    """Scrive il solo album artist ID3 preservando l'audio e gli altri frame.

    FFmpeg non rimuove sempre il TXXX:albumartist legacy anche se gli si passa un valore
    vuoto: la pipeline lo riscopriva in ffprobe e ripeteva la riscrittura a ogni run.
    Mutagen elimina solo i frame TPE2/TXXX relativi ad albumartist e scrive un unico TPE2.
    """
    try:
        from mutagen.id3 import ID3, TPE2, ID3NoHeaderError
    except ImportError as e:
        raise RuntimeError('serve mutagen per riparare i frame ID3 MP3: .venv/bin/pip install mutagen') from e
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall('TPE2')
    for frame in list(tags.getall('TXXX')):
        desc = str(getattr(frame, 'desc', '') or '').strip().casefold().replace('_', ' ')
        if desc in {'albumartist', 'album artist'}:
            tags.delall(frame.HashKey)
    tags.add(TPE2(encoding=3, text=[str(canonical)]))
    tags.save(str(path), v2_version=4)
    invalidate_probe_cache([path])


def run_unify_artists(dry_run=False, base=None, files_only=None):
    """Scrive le forme bilingui CJK/Hangul ovunque nei tag, non solo nelle cartelle CJK.

    La vecchia versione saltava immediatamente le cartelle con nome latino: perciò la stessa
    persona rimaneva come artista CJK puro nei dischi compilation/collaborativi. Ora i valori
    ARTIST/ALBUMARTIST sono normalizzati in tutta la libreria; per i FLAC si leggono i tag grezzi
    solo quando il probe segnala CJK o la cartella e' essa stessa CJK.
    """
    global _NF_REV
    _NF_REV = None
    base = Path(base) if base else LIBRARY_ROOT
    wanted_files = {Path(f).resolve() for f in files_only} if files_only is not None else None
    have_mf = shutil.which('metaflac') is not None
    # Se nel DB convivono CJK puro e CJK(gloss), la mappa sceglie una sola grafia
    # (prima i nomi bilingui). La riutilizziamo anche per i file precedenti allo scan.
    known_artist_names = _navidrome_artist_name_map()
    tg = '[dry] ' if dry_run else ''
    n_art = n_files = n_stray = errors = skipped_unreadable = 0

    # A. Corregge il doppio album artist MP3 (TPE2 + TXXX) prima della normalizzazione globale.
    mp3s = [base.joinpath(*r) for r in _walk_audio(base, {'.mp3'})]
    if wanted_files is not None:
        mp3s = [f for f in mp3s if f.resolve() in wanted_files]
    prefetch_probe(mp3s, 'artist_names/mp3')
    progress = _ProgressBar('artist_names MP3 tag', len(mp3s), 'brani')
    for mp3_index, f in enumerate(mp3s, 1):
        progress.update(mp3_index)
        t = probe(f)
        duplicate_albumartist = bool(t.get('album_artist') and t.get('albumartist') and
                                     t['album_artist'] != t['albumartist'])
        cjk_albumartist_needs_repair = bool(
            (_has_asian(t.get('album_artist', '')) or _has_asian(t.get('albumartist', '')))
            and (t.get('album_artist') or t.get('albumartist'))
            and (_canonicalize_artist_value(t.get('albumartist') or t.get('album_artist', ''),
                                          known_names=known_artist_names,
                                          context_names=_artist_context_from_path(f, base))
                 != (t.get('albumartist') or t.get('album_artist', ''))))
        if duplicate_albumartist or cjk_albumartist_needs_repair:
            new = _canonicalize_artist_value(t.get('albumartist') or t.get('album_artist', ''),
                                                known_names=known_artist_names,
                                                context_names=_artist_context_from_path(f, base))
            progress.clear()
            print(f'{tg}MP3-ALBUMARTIST {f.parent.parent.name} / {f.parent.name}: '
                  f'TPE2="{t.get("album_artist", "")[:30]}" + TXXX="{t.get("albumartist", "")[:30]}" -> "{new[:40]}"')
            if dry_run:
                n_stray += 1
                continue
            try:
                if f.suffix.lower() == '.mp3':
                    _rewrite_mp3_albumartist_id3(f, new)
                else:
                    _rewrite_nonflac(f, {'album_artist': new, 'albumartist': ''})
                n_stray += 1
            except Exception as e:
                errors += 1
                progress.clear()
                print(f'ERRORE: {f}: {e}', file=sys.stderr)
    progress.close(complete=True)

    if wanted_files is None:
        artists = sorted(d for d in base.iterdir()
                         if d.is_dir() and d.name.lower() not in SKIP_TOP
                         and not d.name.startswith('.'))
    else:
        artists = sorted({base / f.relative_to(base).parts[0] for f in map(Path, files_only)
                          if f.is_absolute() and f.is_relative_to(base) and len(f.relative_to(base).parts) >= 2
                          and (base / f.relative_to(base).parts[0]).is_dir()
                          and (base / f.relative_to(base).parts[0]).name.lower() not in SKIP_TOP
                          and not (base / f.relative_to(base).parts[0]).name.startswith('.')})
    progress = _ProgressBar('artist_names', len(artists), 'artisti')
    for artist_index, art in enumerate(artists, 1):
        progress.update(artist_index)
        files = _audio_files(art)
        if wanted_files is not None:
            files = [f for f in files if f.resolve() in wanted_files]
        if not files:
            continue
        folder_is_asian = _has_asian(art.name)
        progress.clear()
        prefetch_probe(files, 'artist_names')
        probes = {f: probe(f) for f in files}
        path_contexts = {f: _artist_context_from_path(f, base) for f in files}
        candidate = {}
        values = []
        for f, t in probes.items():
            relevant = [t.get(k, '') for k in ('artist', 'albumartist', 'album_artist', 'artists', 'albumartists')]
            if folder_is_asian or any(_has_asian(v) for v in relevant):
                candidate[f] = True
            elif any(value and _canonicalize_artist_value(
                    value, known_names=known_artist_names, context_names=path_contexts[f]) != value
                     for value in relevant):
                # Still prefilter with ffprobe, but include Latin tags that need alias,
                # punctuation or comma-collaboration repair (M_O_O_N, Afro Medusa,West Way).
                candidate[f] = True
            for value in relevant:
                values.extend(_artist_parts_for_inference(value, known_artist_names, path_contexts[f]))

        # I valori raw FLAC conservano tag ARTISTS/ALBUMARTISTS ripetuti che ffprobe unisce.
        # Se metaflac non riesce a leggere un FLAC, non deve finire nel fallback non-FLAC.
        raw = {}
        raw_failed = set()
        flacs = [f for f in files if f.suffix.lower() == '.flac'
                 and (folder_is_asian or f in candidate)]
        if flacs and not have_mf:
            progress.clear()
            print(f'[ERRORE] metaflac non trovato: salto i tag FLAC di {art.name}',
                  file=sys.stderr)
            flacs = []
        for f in flacs:
            try:
                raw[f] = _flac_raw_tags(f)
                for k, v in raw[f]:
                    if k in _FLAC_ARTIST_TAGS:
                        values.extend(_artist_parts_for_inference(v, known_artist_names, path_contexts[f]))
            except Exception as e:
                # An unreadable file is excluded from all subsequent rewrites. Keep the
                # problem visible but do not fail every album repair because one FLAC
                # cannot export tags; actual write failures below remain hard errors.
                raw_failed.add(f.resolve())
                skipped_unreadable += 1
                progress.clear()
                print(f'[warn] tag FLAC non leggibili, file saltato: {f}: {e}', file=sys.stderr)

        variants = _artist_variants(art.name)
        canon = _folder_canon(art.name, values)
        if canon:
            variants |= {norm(canon)}

        changed_this_folder = 0
        # FLAC: canonicalizza ogni valore grezzo e rimuove alias duplicati in tutti i tag artista.
        for f, raw_tags in raw.items():
            changes = {}
            for tag in _FLAC_ARTIST_TAGS:
                olds = [v for k, v in raw_tags if k == tag]
                if not olds:
                    continue
                news = []
                for old in olds:
                    new_value = _remap_artist_value(old, variants, canon) if canon else old
                    new_value = _canonicalize_artist_value(
                        new_value, known_names=known_artist_names, context_names=path_contexts[f])
                    news.append(new_value)
                news = _canonicalize_artist_tag_values(
                    news, known_names=known_artist_names, context_names=path_contexts[f])
                if news != olds:
                    changes[tag] = news
            if not changes:
                continue
            if dry_run:
                changed_this_folder += 1
                progress.clear()
                print(f'[dry] ARTIST-TAG {f}: ' + ', '.join(
                    f'{tag}={news}' for tag, news in changes.items()))
                continue
            try:
                args = [*METAFLAC]
                for tag, vals in changes.items():
                    args.append(f'--remove-tag={tag}')
                    args.extend(f'--set-tag={tag}={v}' for v in vals)
                args.append(str(f))
                r = subprocess.run(args, capture_output=True, timeout=120)
                if r.returncode != 0:
                    raise RuntimeError(f'metaflac exit {r.returncode}: '
                                       f'{r.stderr.decode("utf-8", "replace").strip()[:160]}')
                invalidate_probe_cache([f])
                changed_this_folder += 1
            except Exception as e:
                errors += 1
                progress.clear()
                print(f'ERRORE: {f}: {e}', file=sys.stderr)

        # Non-FLAC e FLAC non grezzi: corregge globalmente i campi esposti da ffprobe.
        for f, t in probes.items():
            if f in raw or f.resolve() in raw_failed:
                # FLAC illeggibili da metaflac non devono finire nel fallback ffmpeg per MP3/M4A.
                continue
            aa_key = 'albumartist' if f.suffix.lower() in ('.ogg', '.opus') else 'album_artist'
            changes = {}
            artist_old = t.get('artist', '')
            if artist_old:
                artist_new = _remap_artist_value(artist_old, variants, canon) if canon else artist_old
                artist_new = _canonicalize_artist_value(
                    artist_new, known_names=known_artist_names, context_names=path_contexts[f])
                if artist_new != artist_old:
                    changes['artist'] = artist_new
            # ffprobe exposes MP3/M4A album artist inconsistently as album_artist or
            # albumartist. Read either spelling and write the canonical muxer-specific key.
            albumartist_old = t.get('albumartist') or t.get('album_artist') or ''
            if albumartist_old:
                albumartist_new = _remap_artist_value(albumartist_old, variants, canon) if canon else albumartist_old
                albumartist_new = _canonicalize_artist_value(
                    albumartist_new, known_names=known_artist_names, context_names=path_contexts[f])
                if albumartist_new != albumartist_old:
                    changes[aa_key] = albumartist_new
                if f.suffix.lower() == '.mp3' and t.get('albumartist'):
                    changes['albumartist'] = ''  # elimina l'eventuale TXXX duplicato
            if not changes:
                continue
            if dry_run:
                changed_this_folder += 1
                progress.clear()
                print(f'[dry] ARTIST-TAG {f}: ' + ', '.join(
                    f'{key}={value}' for key, value in changes.items()))
                continue
            try:
                _rewrite_nonflac(f, changes)
                changed_this_folder += 1
            except Exception as e:
                errors += 1
                progress.clear()
                print(f'ERRORE: {f}: {e}', file=sys.stderr)

        if changed_this_folder:
            n_art += 1
            n_files += changed_this_folder
            progress.clear()
            print(f'{tg}ARTIST-NAMES {art.name}: {changed_this_folder} file modificati'
                  + (f' -> "{canon}"' if canon else ' (normalizzazione CJK globale)'))

    progress.close(complete=True)

    # I backup sono cleanup distruttivo: in dry-run non rimuoviamo nulla.
    removed = 0
    if not dry_run:
        if wanted_files is None:
            backup_candidates = base.rglob('*.meta-backup')
        else:
            backup_candidates = (b for folder in {f.parent for f in wanted_files}
                                 for b in folder.glob('*.meta-backup'))
        seen_backups = set()
        for b in backup_candidates:
            if b in seen_backups:
                continue
            seen_backups.add(b)
            if b.with_name(b.name[:-len('.meta-backup')]).exists():
                try:
                    b.unlink()
                    removed += 1
                except OSError:
                    pass
    print(f'artist_names: {n_art} cartelle con tag corretti ({n_files} file) | '
          f'mp3 con doppio album artist riparati: {n_stray} | errori: {errors} | '
          f'FLAC saltati per tag non leggibili: {skipped_unreadable} | backup rimossi: {removed}')
    return {'folders': n_art, 'files': n_files, 'stray_albumartist': n_stray,
            'errors': errors, 'skipped_unreadable': skipped_unreadable}
    if n_art or n_stray:
        print('[i] Navidrome deve completare un full scan per rimuovere le vecchie voci artista dal DB '
              '(lo scan parte a fine pipeline, salvo --no-scan)')


# ===================== fase: mp3 vs flac =====================
# Se la STESSA traccia esiste sia in mp3 sia in FLAC, l'mp3 viene rimosso (cestino
# DEDUPE_TRASH, oppure cancellato con --hard-delete). 'Stessa traccia' =
#   - stesso artista (cartella) e stesso album (cartella uguale o stessa 'base' album:
#     senza anni/(Remaster)/(Deluxe)),
#   - titolo uguale (parentesi incluse; in alternativa titolo senza parentesi ma SOLO
#     se nessuno dei due ha qualificatori mix/live/karaoke/...),
#   - durate note e compatibili (--max-dur-diff),
#   - waveform concorde (>= --corr) salvo --trust-format. Senza numpy e senza
#     --trust-format non si cancella nulla (come dedupe-tracks).
# Un mp3 il cui FLAC sta in un ALTRO album viene solo segnalato ([review]).

def _album_dir(art, f):
    parts = f.relative_to(art).parts
    return parts[0] if len(parts) > 1 else ''


def _same_album(art, a, b):
    da, db = _album_dir(art, a), _album_dir(art, b)
    if da == db:
        return True
    return bool(da and db and album_base(da) and album_base(da) == album_base(db))


def run_mp3_vs_flac(apply=False, hard_delete=False, artist=None, base=None,
                    corr=0.95, max_dur=10.0, trust_format=False):
    base = Path(base) if base else LIBRARY_ROOT
    print(f"waveform compare: {'ATTIVO' if _HAS_NP else 'DISATTIVO'}"
          f"{' | --trust-format: durata+titolo bastano' if trust_format else ''}")
    print(f"modo: {'APPLY' if apply else 'DRY-RUN'}{' (hard delete!)' if hard_delete else ''}")
    stamp = time.strftime('%Y%m%d_%H%M%S')
    n_mp3 = n_del = n_review = n_none = errors = 0
    skip = SKIP_TOP | {'.git'}
    artists = sorted(d for d in base.iterdir()
                     if d.is_dir() and d.name.lower() not in skip
                     and not d.name.startswith('.'))
    if artist:
        artists = [a for a in artists if norm(a.name) == norm(artist)]
        if not artists:
            print(f"[ERRORE] artista '{artist}' non trovato in {base}")
            return

    artist_files = [(art, _audio_files(art)) for art in artists]
    total_mp3s = sum(1 for _art, files in artist_files
                     for f in files if f.suffix.lower() == '.mp3')
    progress = _ProgressBar('mp3_vs_flac', total_mp3s, 'brani')
    checked_mp3s = 0
    for art, files in artist_files:
        mp3s = [f for f in files if f.suffix.lower() == '.mp3']
        flacs = [f for f in files if f.suffix.lower() == '.flac']
        if not mp3s:
            continue
        if not flacs:
            checked_mp3s += len(mp3s)
            progress.update(checked_mp3s)
            continue
        progress.clear()
        prefetch_probe(mp3s + flacs, 'mp3_vs_flac')
        meta = {f: probe_dur(f) for f in mp3s + flacs}
        skey = {f: norm_bare(best_title(f, meta[f][0])) for f in mp3s + flacs}
        fkey = {f: norm(best_title(f, meta[f][0])) for f in mp3s + flacs}
        by_s, by_f = {}, {}
        for fl in flacs:
            by_s.setdefault(skey[fl], []).append(fl)
            by_f.setdefault(fkey[fl], []).append(fl)

        for m in mp3s:
            checked_mp3s += 1
            progress.update(checked_mp3s)
            n_mp3 += 1
            if not skey[m]:
                continue
            cands = by_s.get(skey[m], [])
            if not cands and not _has_qualifier(skey[m]):
                cands = [c for c in by_f.get(fkey[m], []) if not _has_qualifier(skey[c])]
            if not cands:
                n_none += 1
                continue
            rel = m.relative_to(art)
            dm = meta[m][1]
            ok = [c for c in cands
                  if dm and meta[c][1] and _dur_compatible(dm, meta[c][1], max_dur)]
            if not ok:
                n_review += 1
                progress.clear()
                print(f"    [review] {art.name}/{rel}: titolo uguale a un FLAC ma durata "
                      f"ignota o troppo diversa: lascio l'mp3")
                continue
            same = sorted((c for c in ok if _same_album(art, m, c)),
                          key=lambda c: _keeper_score(c, meta[c][0]))
            if not same:
                n_review += 1
                progress.clear()
                print(f"    [review] {art.name}/{rel}: il FLAC sta in un altro album "
                      f"({ok[0].relative_to(art)}): lascio l'mp3")
                continue
            keeper = None
            if trust_format:
                keeper = same[0]
            elif not _HAS_NP:
                n_review += 1
                progress.clear()
                print(f"    [info] {art.name}/{rel}: numpy assente, niente verifica waveform: "
                      f"lascio l'mp3 (usa --trust-format per fidarti di titolo+durata)")
                continue
            else:
                fp_m = fingerprint(m)
                for c in same:
                    cc = correlate(fp_m, fingerprint(c), stop_at=corr)
                    if cc is not None and cc >= corr:
                        keeper = c
                        break
                if keeper is None:
                    n_review += 1
                    progress.clear()
                    print(f"    [review] {art.name}/{rel}: waveform diversa dal FLAC "
                          f"(o non confrontabile): lascio l'mp3")
                    continue
            n_del += 1
            progress.clear()
            print(f"    {'[dry] ' if not apply else ''}MP3-DUPE  {art.name}/{rel} "
                  f"(tengo {keeper.relative_to(art)})")
            if apply:
                try:
                    _move_to_trash(m, stamp, hard_delete, base)
                except Exception as e:
                    errors += 1
                    n_del -= 1
                    progress.clear()
                    print(f"    ERRORE spostamento {m}: {e}", file=sys.stderr)

    progress.close(complete=True)
    print(f"\nmp3 esaminati: {n_mp3} | {'rimossi' if apply else 'da rimuovere'}: {n_del} "
          f"| da verificare: {n_review} | senza FLAC gemello: {n_none} | errori: {errors}")
    if apply and not hard_delete and n_del:
        print(f"[i] mp3 nel cestino: {DEDUPE_TRASH / stamp}")
    if not apply and n_del:
        print("[i] dry-run: rilancia con --apply per rimuoverli")


# ===================== fase: date heal =====================
# Risolve automaticamente le date di pubblicazione sbagliate su TUTTI gli
# album, senza doverle elencare a mano. Fonti di verita', in ordine:
#   1. MusicBrainz: MUSICBRAINZ_RELEASEGROUPID / MUSICBRAINZ_ALBUMID dai
#      tag dei file o dall'album.nfo (Lidarr) -> first-release-date
#      (richieste lente: 1/sec, cache persistente per mbid)
#   2. album.nfo <releasedate>
#   3. anno nella cartella album "(1981)"
# Se l'anno maggioritario dei tag DATE differisce, riscrive DATE e
# ORIGINALDATE con l'anno corretto su tutti i file della cartella.

MBDATE_CACHE = SCRIPT_DIR / '.mbdate_cache.json'
MB_USER_AGENT = {'User-Agent': 'homelab-exportify/3.2 (local library maintenance)'}


def _mb_transient(e):
    """True se l'errore e' TEMPORANEO (503/429/5xx, timeout, rete giu'): non e' una risposta di
    MusicBrainz sul dato e non va mai memorizzato come 'nessun dato'."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (429, 500, 502, 503, 504)
    return isinstance(e, (urllib.error.URLError, TimeoutError, OSError))


class MBUnavailable(OSError):
    """MusicBrainz non risponde da troppe richieste di fila: si salta il resto della run."""


_MB_FAILS = [0]          # richieste di fila fallite per errore temporaneo (dopo i tentativi)
_MB_FAIL_LIMIT = 5


def _mb_json(path, retries=3):
    """GET su MusicBrainz. Sugli errori temporanei riprova (pausa 4 s, poi 10 s) e solo dopo
    solleva l'ultimo errore. Dopo _MB_FAIL_LIMIT richieste fallite di fila (MusicBrainz fuori
    servizio) non ci prova piu' per il resto della run: senza questo limite ogni album costerebbe
    14 secondi di attese e la notte durerebbe ore."""
    if _MB_FAILS[0] >= _MB_FAIL_LIMIT:
        raise MBUnavailable('MusicBrainz non raggiungibile: richieste sospese fino alla prossima run')
    req = urllib.request.Request('https://musicbrainz.org/ws/2/' + path + '?fmt=json',
                                 headers=MB_USER_AGENT)
    for attempt in range(retries):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=30).read())
            _MB_FAILS[0] = 0
            return data
        except Exception as e:
            if not _mb_transient(e):
                raise
            if attempt + 1 >= retries:
                _MB_FAILS[0] += 1
                if _MB_FAILS[0] >= _MB_FAIL_LIMIT:
                    print(f"[warn] MusicBrainz non risponde da {_MB_FAIL_LIMIT} richieste: salto le "
                          f"altre per questa run (gli album saltati si riprovano alla prossima)",
                          file=sys.stderr)
                raise
            time.sleep(4 if attempt == 0 else 10)


def _mb_cache_purge_negatives(cache, tcache):
    """Una volta sola: le versioni <= 4.1 memorizzavano come 'nessun dato' anche gli errori
    temporanei (503, timeout): quel release-group non veniva piu' ricontrollato. Le voci vuote
    si tolgono e vengono richieste di nuovo. -> quante ne ha tolte (0 se gia' fatto)."""
    if cache.get('__v') == 2:
        return 0
    drop = [k for k, v in cache.items() if v is None]
    tdrop = [k for k, v in tcache.items() if v == '']
    for k in drop:
        del cache[k]
    for k in tdrop:
        del tcache[k]
    cache['__v'] = 2
    return len(drop) + len(tdrop)


def _nfo_field(album, field):
    nfo = album / 'album.nfo'
    if not nfo.exists():
        return ''
    m = re.search(rf'<{field}>(.*?)</{field}>', nfo.read_text(errors='replace'))
    return (m.group(1) or '').strip() if m else ''


def _mb_year(rgid, mbid, cache):
    """Anno di prima pubblicazione da MusicBrainz, con cache. None se niente."""
    if rgid:
        if rgid not in cache:
            time.sleep(1.2)     # rate limit MB: max 1 req/sec
            try:
                d = _mb_json(f'release-group/{rgid}')
                cache[rgid] = (d.get('first-release-date') or '')[:4] or None
            except Exception as e:
                print(f'    [warn] MB release-group {rgid}: {e}', file=sys.stderr)
                if _mb_transient(e):
                    return None          # errore temporaneo: NON si memorizza, si riprova alla prossima run
                cache[rgid] = None
        return cache[rgid]
    if mbid:
        if mbid not in cache:
            time.sleep(1.2)
            try:
                d = _mb_json(f'release/{mbid}')
                date = d.get('date') or ''
                if not date:
                    rg = (d.get('release-group') or {}).get('id')
                    if rg:
                        return _mb_year(rg, None, cache)
                cache[mbid] = date[:4] or None
            except Exception as e:
                print(f'    [warn] MB release {mbid}: {e}', file=sys.stderr)
                if _mb_transient(e):
                    return None
                cache[mbid] = None
        return cache[mbid]
    return None


MBTITLE_CACHE = SCRIPT_DIR / '.mbtitle_cache.json'


def _mb_release_info(rgid, mbid, cache, tcache):
    """(anno, titolo) di prima pubblicazione. cache: mbid->anno,
    tcache: mbid->titolo release."""
    year = _mb_year(rgid, mbid, cache)
    key = rgid or mbid
    if key and key not in tcache:
        time.sleep(1.2)
        try:
            if rgid:
                rels = _mb_json(f'release-group/{rgid}').get('releases') or []
            else:
                rels = [mbid]
            if rels:
                time.sleep(1.2)
                d = _mb_json(f'release/{rels[0]["id"] if isinstance(rels[0], dict) else rels[0]}')
                tcache[key] = d.get('title') or ''
            else:
                tcache[key] = ''
        except Exception as e:
            print(f'    [warn] MB titolo {key}: {e}', file=sys.stderr)
            if not _mb_transient(e):         # errore temporaneo: non memorizzare
                tcache[key] = ''
    return year, (tcache.get(key) or '')


def _authoritative_year(album, files, probe_fn, cache):
    rgid = mbid = ''
    for f in files[:12]:
        t = probe_fn(f)
        rgid = rgid or t.get('musicbrainz_releasegroupid', '')
        mbid = mbid or t.get('musicbrainz_albumid', '')
    rgid = rgid or _nfo_field(album, 'musicbrainzreleasegroupid')
    mbid = mbid or _nfo_field(album, 'musicbrainzalbumid')
    year = _mb_year(rgid, mbid, cache)
    if year and year.isdigit():
        return year, 'musicbrainz'
    rd = _nfo_field(album, 'releasedate')
    if rd and rd[-4:].isdigit():
        return rd[-4:], 'nfo'
    m = re.search(r'\((19|20)\d{2}\)', album.name)
    if m:
        return m.group(0).strip('()'), 'cartella'
    return None, None


def _root_album_title_keys(root, files):
    """Titoli di release ricavati da cartella e tag; include il nome parent solo per sottodischi."""
    values = [root.name]
    tags = [probe_dur(f)[0] for f in files]
    values.extend(t.get('album', '') for t in tags if t.get('album'))
    # Quando il nome cartella è Disc/CD/Vinyl + numero, titolo album è spesso il parent.
    if re.fullmatch(r'(?:cd|disc|disk|vinyl|lp)\s*\d+', root.name, re.I):
        values.append(root.parent.name)
    keys = set().union(*(_album_title_keys(v) for v in values)) if values else set()
    return keys, tags


def _remove_musicbrainz_ids(paths, dry_run=False, drop_album=True, drop_releasegroup=True):
    """Rimuove i soli ID richiesti, su tutti i formati; preview senza modifiche."""
    changed = errors = 0
    for f in paths:
        tags = probe_dur(f)[0]
        diff = {}
        if drop_album and tags.get('musicbrainz_albumid'):
            diff['musicbrainz_albumid'] = None
        if drop_releasegroup and tags.get('musicbrainz_releasegroupid'):
            diff['musicbrainz_releasegroupid'] = None
        if not diff:
            continue
        kind = '/'.join(diff)
        print(f"    {'[dry] ' if dry_run else ''}strip {kind}: {f}")
        if dry_run:
            changed += 1
            continue
        try:
            if f.suffix.lower() == '.flac':
                write_flac(f, diff)
            else:
                _rewrite_nonflac(f, diff)
            changed += 1
        except Exception as e:
            errors += 1
            print(f'[ERRORE] rimozione MBID {f}: {e}', file=sys.stderr)
    return changed, errors


def _repair_mbid_sanity(base, cache, tcache, dry_run=False, album_dirs_only=None):
    """Verifica MBID riutilizzati tra release e MBID discordanti dentro un album logico.

    La vecchia logica guardava pochi file e ripuliva soltanto FLAC. Qui il gruppo e' l'album intero
    (inclusi CD1/CD2), si controllano tutti i formati e non si sceglie una release a maggioranza
    quando una singola cartella contiene piu' album-ID incompatibili.
    """
    base = Path(base)
    wanted_dirs = {Path(d).resolve() for d in album_dirs_only} if album_dirs_only else None
    roots = {}
    for rel in _walk_audio(base, AUDIO_EXT):
        if rel[-1].endswith(('.backup', '.meta-backup')) or '.tmp.' in rel[-1]:
            continue
        f = base.joinpath(*rel)
        logical_root = _album_root_for_file(base, f)
        if wanted_dirs is not None and logical_root.resolve() not in wanted_dirs:
            continue
        roots.setdefault(logical_root, []).append(f)
    prefetch_probe((f for fs in roots.values() for f in fs), 'mbid_sanity')

    root_tags = {root: [probe_dur(f)[0] for f in files] for root, files in roots.items()}
    removed_roots = removed_files = errors = reviews = 0
    roots_with_conflicting_mbids = set()

    # Different MUSICBRAINZ_ALBUMID values inside one physical album tree can split it in
    # Navidrome. Do not pick an arbitrary majority: remove those per-release IDs. Preserve a
    # release-group ID when it is common; remove it too only when the root has conflicting groups.
    for root, tags_for_root in root_tags.items():
        ids_here = {str(t.get('musicbrainz_albumid') or '').strip().lower()
                    for t in tags_for_root if str(t.get('musicbrainz_albumid') or '').strip()}
        rgids_here = {str(t.get('musicbrainz_releasegroupid') or '').strip().lower()
                      for t in tags_for_root if str(t.get('musicbrainz_releasegroupid') or '').strip()}
        paths = roots[root]
        # ffmpeg cannot reliably preserve MUSICBRAINZ_ALBUMID in M4A/MP4. A unique ID on
        # FLAC plus an M4A without the field leaves one physical album split in Navidrome.
        # In that case remove the ID from every track in this album root instead of repeatedly
        # attempting an unwritable propagation every night.
        unwritable_missing_album_id = any(
            f.suffix.lower() in ('.m4a', '.mp4')
            and not str(t.get('musicbrainz_albumid') or '').strip()
            for f, t in zip(paths, tags_for_root)
        )
        drop_album = len(ids_here) > 1 or (len(ids_here) == 1 and unwritable_missing_album_id)
        drop_releasegroup = len(rgids_here) > 1
        if not (drop_album or drop_releasegroup):
            continue
        reasons = []
        if len(ids_here) > 1:
            reasons.append(f'{len(ids_here)} album ID diversi')
        elif drop_album and unwritable_missing_album_id:
            reasons.append('album ID presente ma non propagabile ai tag M4A/MP4')
        if drop_releasegroup:
            reasons.append(f'{len(rgids_here)} release-group ID diversi')
        print(f"{'[dry] ' if dry_run else ''}MBID-SPLIT: '{root}' contiene {' e '.join(reasons)}; "
              f"rimuovo solo le famiglie di ID discordanti")
        n, err = _remove_musicbrainz_ids(paths, dry_run=dry_run,
                                         drop_album=drop_album, drop_releasegroup=drop_releasegroup)
        removed_roots += 1
        removed_files += n
        errors += err
        if drop_album:
            roots_with_conflicting_mbids.add(root)

    # Find an MBID incorrectly reused across separate album roots. Roots already handled above
    # are excluded so their stale IDs cannot trigger duplicate work in this pass.
    mbid_roots = {}
    for root, files in roots.items():
        if root in roots_with_conflicting_mbids:
            continue
        for f, tags in zip(files, root_tags[root]):
            mb = (tags.get('musicbrainz_albumid') or '').strip().lower()
            if mb:
                mbid_roots.setdefault(mb, {}).setdefault(root, set()).add(f)

    for mbid, places in sorted(mbid_roots.items()):
        if len(places) < 2:
            continue
        try:
            _, release_title = _mb_release_info(None, mbid, cache, tcache)
        except Exception as e:
            release_title = ''
            print(f'[review] MusicBrainz lookup fallito per {mbid}: {e}', file=sys.stderr)
        release_keys = _album_title_keys(release_title) if release_title else set()
        if not release_keys:
            # Nessun titolo attendibile: non inventiamo quale directory sia quella sbagliata.
            reviews += 1
            print(f'[review] MBID {mbid} appare in {len(places)} cartelle ma MusicBrainz non ha '
                  'un titolo verificabile; nessun ID rimosso')
            for root, files_with_id in places.items():
                print(f'    - {root}: {len(files_with_id)} file con ID')
            continue

        for root, files_with_id in places.items():
            keys, tags = _root_album_title_keys(root, roots[root])
            best, label = _album_title_similarity(release_keys, keys)
            if best >= 0.90:
                continue
            # Rimuove il valore errato da tutti i file che lo portano, non solo il primo campione.
            # In questo modo la fase album_unify non può ripristinarlo da un file rimasto indietro.
            print(f"{'[dry] ' if dry_run else ''}MBID-SANITY: '{root}' contiene MBID {mbid} "
                  f"della release '{release_title}', titolo locale non concorde "
                  f"(similarita' {best:.2f} {label}); rimuovo l'ID dall'intero sottoinsieme")
            n, err = _remove_musicbrainz_ids(sorted(files_with_id), dry_run=dry_run)
            removed_roots += 1
            removed_files += n
            errors += err

    print(f'MBID sanity: {removed_roots} root release con ID errati | '
          f'{removed_files} file tag rimossi | {reviews} gruppi da verificare | {errors} errori')
    return {'roots': removed_roots, 'files': removed_files, 'reviews': reviews, 'errors': errors}


def run_date_heal(dry_run=False, base=None, album_dirs_only=None):
    import shutil as _sh
    if not dry_run and not _sh.which('metaflac'):
        print('[ERRORE] metaflac non trovato: salto date_heal')
        return
    base = Path(base) if base else LIBRARY_ROOT
    try:
        cache = json.loads(MBDATE_CACHE.read_text())
    except Exception:
        cache = {}
    try:
        tcache = json.loads(MBTITLE_CACHE.read_text())
    except Exception:
        tcache = {}
    HEAL_CACHE = SCRIPT_DIR / '.heal_cache.json'
    try:
        heal_cache = json.loads(HEAL_CACHE.read_text())
    except Exception:
        heal_cache = {}
    if not dry_run:
        n_purged = _mb_cache_purge_negatives(cache, tcache)
        if n_purged:
            print(f"  [date_heal] ripulita la cache MusicBrainz da {n_purged} voci 'nessun dato' "
                  f"(potevano essere errori temporanei): verranno richieste di nuovo, una volta sola")
    healed = checked = errors = stripped = failed_write = skipped_cached = 0
    folders = {}
    for r in _walk_audio(base, AUDIO_EXT):
        if not r[-1].endswith('.backup'):
            f = base.joinpath(*r)
            folders.setdefault(f.parent, []).append(f)
    prefetch_probe([f for fl in folders.values() for f in fl], 'date_heal')

    # MBID sanity condivisa con la utility di riparazione album: verifica l'intero album
    # logico, inclusi sottodischi e tutti i formati audio.
    mbid_result = _repair_mbid_sanity(base, cache, tcache, dry_run=dry_run)
    stripped = mbid_result.get('roots', 0)
    errors += mbid_result.get('errors', 0)

    sorted_folders = sorted(folders.items())
    progress = _ProgressBar('date_heal', len(sorted_folders), 'album')
    for album_index, (album, files) in enumerate(sorted_folders, 1):
        progress.update(album_index)
        if len(album.parent.name) < 1:
            continue
        try:
            tags = [probe_dur(f)[0] for f in files]
            years = [t.get('date', '')[:4] for t in tags if t.get('date', '')[:4].isdigit()]
            if not years:
                continue
            checked += 1
            maj = Counter(years).most_common(1)[0][0]
            sig = [len(files), sum(f.stat().st_size for f in files)]
            year, fonte = _authoritative_year(album, files, lambda f: probe_dur(f)[0], cache)
            ck = heal_cache.get(str(album))
            if (not dry_run and ck and ck[0] == maj and ck[1] == year
                    and ck[2] == sig):
                skipped_cached += 1
                continue
            heal_cache[str(album)] = [maj, year or '', sig]
            if not year or year == maj:
                continue
            progress.clear()
            print(f"{'[dry] ' if dry_run else ''}HEAL {album.parent.name} / {album.name}: "
                  f"date {maj} -> {year} ({fonte})")
            if dry_run:
                healed += 1
                continue
            ok = True
            for f in files:
                if f.suffix.lower() != '.flac':
                    continue
                # metaflac --set-tag AGGIUNGE un campo: senza --remove-tag prima
                # restavano DATE/ORIGINALDATE doppi (vecchio + nuovo)
                # ORIGINALDATE che ha gia' l'anno giusto (magari completa, 1982-01-21) si
                # tiene (togliendo gli eventuali doppioni); altrimenti si imposta l'anno
                od = probe_dur(f)[0].get('originaldate', '').split(';')[0].strip()
                new_od = od if od[:4] == str(year) else str(year)
                r = subprocess.run([*METAFLAC, '--remove-tag=DATE', '--remove-tag=ORIGINALDATE',
                                    f'--set-tag=DATE={year}',
                                    f'--set-tag=ORIGINALDATE={new_od}', str(f)],
                                   capture_output=True, timeout=60)
                if r.returncode != 0:
                    ok = False
                    progress.clear()
                    print(f'    [ERRORE] metaflac su {f.name}: '
                          f'{r.stderr.decode()[:150]}', file=sys.stderr)
            if ok:
                healed += 1
            else:
                failed_write += 1
                heal_cache.pop(str(album), None)    # scrittura fallita: si ritenta la notte dopo
        except Exception as e:
            errors += 1
            heal_cache.pop(str(album), None)
            progress.clear()
            print(f'ERRORE: {album}: {e}', file=sys.stderr)
    progress.close(complete=True)
    if not dry_run:
        _write_json_atomic(MBDATE_CACHE, cache)
        _write_json_atomic(MBTITLE_CACHE, tcache)
        _write_json_atomic(HEAL_CACHE, heal_cache)
    print(f'date_heal: {checked} controllati, {healed} corretti, '
          f'{skipped_cached} gia ok (cache), {stripped} MBID rimossi, '
          f'{failed_write} scritture fallite, {errors} errori')


# ===================== fase: fix date tags =====================
# (da fix_date_tags.sh: se ORIGINALDATE esiste elimina DATE; altrimenti crea
# ORIGINALDATE prendendo l'anno dal nome della cartella album "(1979)")

DATE_YEAR_RE = re.compile(r'\((19|20)\d{2}\)')


def _metaflac_run(*args, path):
    """metaflac in scrittura CON controllo dell'esito. Prima l'esito era ignorato:
    con il disco pieno ('No space left on device') fix_date_tags dichiarava
    'file sistemati' senza aver scritto nulla."""
    r = subprocess.run([*METAFLAC, *args, str(path)], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f'metaflac exit {r.returncode}: {(r.stderr or r.stdout).strip()[:160]}')
    invalidate_probe_cache([path])


def _flac_tags(path, *names):
    """Piu' tag con UNA sola chiamata a metaflac (prima ne servivano 2 per file)."""
    r = subprocess.run([*METAFLAC, *[f'--show-tag={n}' for n in names], str(path)],
                       capture_output=True, text=True, timeout=60)
    out = dict.fromkeys(names, '')
    for line in r.stdout.splitlines():
        for n in names:
            if not out[n] and line.upper().startswith(n.upper() + '='):
                out[n] = line[len(n) + 1:]
    return out


def run_fix_dates(dry_run=False, base=None, files_only=None):
    """Uniforma la data originale per album logico e rimuove DATE ridondanti.

    Se >=60% delle tracce con una data (almeno due) concordano su una stessa data/anno,
    quella data diventa il valore ORIGINALDATE condiviso per le tracce FLAC selezionate,
    anche quando alcuni file hanno il campo mancante o una data residua diversa. Questo
    evita che Navidrome divida un singolo album in base a tag discordanti. Se non esiste
    un consenso affidabile, conserva il precedente fallback basato sull'anno nella cartella.
    """
    import shutil as _sh
    if not _sh.which('metaflac'):
        print('[ERRORE] metaflac non trovato: salto fix_date_tags')
        return
    base = Path(base) if base else LIBRARY_ROOT
    fixed = errors = proposed = 0
    files = [base.joinpath(*rel) for rel in _walk_audio(base, {'.flac'})
             if not rel[-1].lower().endswith('.backup')]
    if files_only is not None:
        wanted_files = {Path(f).resolve() for f in files_only}
        files = [f for f in files if f.resolve() in wanted_files]
    prefetch_probe(files, 'fix_date_tags')

    # Use logical album roots so an album split into CD1/CD2 still shares one date.
    groups = {}
    for f in files:
        groups.setdefault(_album_root_for_file(base, f), []).append(f)
    shared_dates = {}
    for root, group_files in groups.items():
        group_tags = [probe(f) for f in group_files]
        target = _dominant_original_date(group_tags)
        if target:
            shared_dates[root] = target

    progress = _ProgressBar('fix_date_tags', len(files), 'file')
    for file_index, f in enumerate(files, 1):
        progress.update(file_index)
        try:
            tags = probe(f)
            date_v = str(tags.get('date') or '').strip()
            orig_v = str(tags.get('originaldate') or '').strip()
            if not tags:
                raw = _flac_tags(f, 'DATE', 'ORIGINALDATE')
                date_v, orig_v = raw['DATE'].strip(), raw['ORIGINALDATE'].strip()

            shared = shared_dates.get(_album_root_for_file(base, f))
            changes = []
            if shared:
                # One agreed release date is more reliable than leaving one-off DATE tags
                # or missing ORIGINALDATE values to create separate Navidrome album rows.
                if orig_v != shared:
                    changes.extend(['--remove-tag=ORIGINALDATE', f'--set-tag=ORIGINALDATE={shared}'])
                if date_v:
                    changes.append('--remove-tag=DATE')
                if not changes:
                    continue
                proposed += 1
                progress.clear()
                actions = []
                if orig_v != shared:
                    actions.append(f"ORIGINALDATE {orig_v or '(assente)'} -> {shared}")
                if date_v:
                    actions.append(f"rimuovo DATE={date_v}")
                print(f"{'[dry] ' if dry_run else ''}FIX(album-date): {f.name}  "
                      f"{' ; '.join(actions)}")
            elif orig_v:
                # The documented invariant is one original-date field only, even if DATE
                # happens to contain the same value. Navidrome should not have two sources.
                if not date_v:
                    continue
                changes = ['--remove-tag=DATE']
                proposed += 1
                progress.clear()
                print(f"{'[dry] ' if dry_run else ''}FIX(rem): {f.name}  "
                      f"DATE={date_v} ORIGINALDATE={orig_v}")
            elif date_v:
                year = ''
                for d in (f.parent, f.parent.parent):
                    m = DATE_YEAR_RE.search(d.name)
                    if m:
                        year = m.group(0).strip('()')
                        break
                if not year or date_v == year:
                    continue
                changes = [f'--set-tag=ORIGINALDATE={year}', '--remove-tag=DATE']
                proposed += 1
                progress.clear()
                print(f"{'[dry] ' if dry_run else ''}FIX(set): {f.name}  "
                      f"DATE={date_v} -> ORIGINALDATE={year}")
            else:
                continue

            if not dry_run:
                _metaflac_run(*changes, path=f)
                fixed += 1
        except Exception as e:
            errors += 1
            progress.clear()
            print(f'ERRORE: {f}: {e}', file=sys.stderr)
    progress.close(complete=True)
    if dry_run:
        print(f'fix_date_tags: {proposed} file con modifiche proposte (--dry-run), {errors} errori')
    else:
        print(f'fix_date_tags: {fixed} file sistemati, {errors} errori')

# ===================== fase: flac 16bit =====================
# (da flac_16bit.py, ottimizzata: 24bit -> 16bit livello 8; 16bit con ratio
# di compressione > 0.80 -> ricompressione livello 8. Cache path+mtime+size:
# i file gia' convertiti vengono saltati: le esecuzioni successive sono
# istantanee e la fase puo' stare nel cron notturno.)

FLAC16_CACHE = SCRIPT_DIR / '.flac16_cache.json'
FLAC16_MAX_RATIO = 0.80      # 16bit: ricomprimi solo se > 80% della dimensione raw
FLAC16_MIN_GAIN = 0.98       # sostituisci solo se il nuovo e' < 98% del vecchio
FLAC16_MIN_FREE = 512 * 1024 * 1024   # spazio libero minimo (oltre alla dimensione del file)


try:
    FLAC16_PROBE_TIMEOUT = max(5, min(120, int(os.environ.get('EXPORTIFY_FLAC_PROBE_TIMEOUT', '30'))))
except (TypeError, ValueError):
    FLAC16_PROBE_TIMEOUT = 30


def _probe_flac_detailed(path):
    """Return bit-depth metadata plus a compact failure reason for batch diagnostics."""
    try:
        r = subprocess.run(['ffprobe', '-v', 'quiet', '-select_streams', 'a:0',
                            '-print_format', 'json', '-show_entries',
                            'format=duration:stream=channels,sample_rate,'
                            'bits_per_raw_sample', str(path)],
                           capture_output=True, text=True, timeout=FLAC16_PROBE_TIMEOUT)
        if r.returncode != 0:
            return 0, 0, 0, 0.0, f'exit_{r.returncode}'
        d = json.loads(r.stdout or '{}')
        streams = d.get('streams') or []
        if not streams:
            return 0, 0, 0, 0.0, 'no_stream'
        st = streams[0]
        result = (int(st.get('bits_per_raw_sample') or 0),
                  int(st.get('channels') or 0),
                  int(st.get('sample_rate') or 0),
                  float(d.get('format', {}).get('duration') or 0))
        if not all(result):
            return (*result, 'incomplete_metadata')
        return (*result, None)
    except subprocess.TimeoutExpired:
        return 0, 0, 0, 0.0, 'timeout'
    except Exception as exc:
        return 0, 0, 0, 0.0, type(exc).__name__


def _probe_flac(path):
    return _probe_flac_detailed(path)[:4]


def _flac16_convert(src, tmp):
    # -map espliciti + '-c:v copy': senza, ffmpeg RICODIFICA la copertina
    # incorporata da JPEG a PNG (file piu' grande, e il controllo FLAC16_MIN_GAIN
    # scartava conversioni utili)
    r = subprocess.run(['ffmpeg', '-y', '-nostdin', '-v', 'error', '-i', str(src),
                        '-map', '0:a', '-map', '0:v?',
                        '-af', 'aformat=sample_fmts=s16',
                        '-c:a', 'flac', '-compression_level', '8',
                        '-c:v', 'copy', str(tmp)],
                       capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f'ffmpeg exit {r.returncode}: {r.stderr.strip()[:300]}')


def run_flac_16bit(dry_run=False, base=None, cache_path=None):
    base = Path(base) if base else LIBRARY_ROOT
    cache_path = Path(cache_path) if cache_path else FLAC16_CACHE
    try:
        cache = json.loads(cache_path.read_text())
        if not isinstance(cache, dict):
            cache = {}
    except Exception:
        cache = {}
    converted = skipped = errors = nogain = 0
    saved = 0
    stopped = ''
    attempts = 0
    cache_updates = 0
    # _walk_audio usa os.scandir: niente rglob annidati per ogni album.
    flac_files = [base.joinpath(*rel) for rel in _walk_audio(base, {'.flac'})]

    # Pre-stat in one pass and prepare only files missing a valid path+mtime+size cache hit.
    # Previously all uncached FLACs were ffprobed sequentially; a handful of 120s probes
    # could hold the entire all/dry-run pipeline for 30 minutes. This read-only preflight
    # uses bounded concurrency and a much shorter, configurable metadata-probe timeout.
    file_stats = {}
    to_probe = []
    for p in flac_files:
        if p.name.casefold().endswith(('.flac.flac', '.backup')):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        file_stats[p] = st
        if cache.get(str(p)) != [st.st_mtime, st.st_size]:
            to_probe.append(p)

    probe_results = {}
    probe_failures = Counter()
    if to_probe:
        probe_progress = _ProgressBar('ffprobe/flac16', len(to_probe), 'file')
        workers = max(1, min(PROBE_WORKERS, 8))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_paths = {executor.submit(_probe_flac_detailed, p): p for p in to_probe}
            for completed, future in enumerate(as_completed(future_paths), 1):
                path = future_paths[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = (0, 0, 0, 0.0, type(exc).__name__)
                probe_results[path] = result[:4]
                if result[4]:
                    probe_failures[result[4]] += 1
                probe_progress.update(completed)
        probe_progress.close(complete=True)
        if probe_failures:
            details = ', '.join(f'{reason}={count}' for reason, count in sorted(probe_failures.items()))
            print(f'[warn] flac_16bit: ffprobe non riuscito su {sum(probe_failures.values())} file '
                  f'({details}); file saltati senza modificarli', file=sys.stderr, flush=True)

    progress = _ProgressBar('flac_16bit', len(flac_files), 'file')
    for file_index, p in enumerate(flac_files, 1):
        progress.update(file_index)
        if p.name.casefold().endswith(('.flac.flac', '.backup')):
            continue
        st = file_stats.get(p)
        if st is None:
            continue
        key = str(p)
        if cache.get(key) == [st.st_mtime, st.st_size]:
            skipped += 1
            continue
        bps, ch, sr, dur = probe_results.get(p, (0, 0, 0, 0.0))
        if not bps or not ch or not sr or not dur:
            skipped += 1
            continue
        raw = dur * sr * ch * bps / 8
        ratio = st.st_size / raw if raw else 1.0
        if bps <= 16 and ratio <= FLAC16_MAX_RATIO:
            skipped += 1
            # Non scrivere cache in dry-run: resta senza effetti collaterali sugli ausiliari.
            if not dry_run:
                cache[key] = [st.st_mtime, st.st_size]
                cache_updates += 1
                if cache_updates % 1000 == 0:
                    _write_json_atomic(cache_path, cache)
            continue
        tag = f'24->16bit ({bps}bit)' if bps > 16 else f'16bit ricomprimo (ratio {ratio:.2f})'
        if dry_run:
            progress.clear()
            print(f'[dry] {tag}: {p.name}')
            converted += 1
            continue
        try:
            free = shutil.disk_usage(p.parent).free
        except OSError:
            free = None
        if free is not None and free < st.st_size + FLAC16_MIN_FREE:
            stopped = f'spazio libero insufficiente ({free // 2**20} MB in {p.parent})'
            break
        fd, tmpname = tempfile.mkstemp(prefix='.flac16_', suffix='.flac', dir=p.parent)
        os.close(fd)
        tmp = Path(tmpname)
        attempts += 1
        try:
            _flac16_convert(p, tmp)
            nb, nch, nsr, ndur = _probe_flac(tmp)
            if not nb:
                raise RuntimeError('output non valido (ffprobe)')
            if nch != ch or nsr != sr or abs((ndur or 0) - dur) > 1.0:
                raise RuntimeError(f'output incoerente (canali/rate/durata {nch}/{nsr}/{ndur} '
                                   f'invece di {ch}/{sr}/{dur})')
            newsize = tmp.stat().st_size
            if bps <= 16 and newsize > st.st_size * FLAC16_MIN_GAIN:
                cache[key] = [st.st_mtime, st.st_size]
                nogain += 1
                continue
            backup = p.with_name(p.name + '.backup')
            os.replace(p, backup)
            os.replace(tmp, p)
            fb, fch, fsr, _fd = _probe_flac(p)
            if not fb or fch != ch or fsr != sr:
                os.replace(backup, p)
                raise RuntimeError('verifica finale fallita: ripristinato l’originale')
            backup.unlink(missing_ok=True)
            cache[key] = [p.stat().st_mtime, p.stat().st_size]
            saved += st.st_size - newsize
            progress.clear()
            print(f'{tag}: {p.name} ({st.st_size // 1024}K -> {newsize // 1024}K)')
            converted += 1
        except Exception as e:
            errors += 1
            msg = str(e)
            progress.clear()
            print(f'ERRORE: {p}: {msg[:300]}', file=sys.stderr)
            if 'No space left' in msg:
                stopped = 'disco pieno (No space left on device)'
                break
        finally:
            tmp.unlink(missing_ok=True)
            if attempts and attempts % 100 == 0:
                _write_json_atomic(cache_path, cache)

    progress.close(complete=(not stopped))
    removed = 0
    # Ricerca backup con una sola visita del filesystem. In dry-run non cancellare e non
    # scrivere la cache: il flag deve essere senza effetti collaterali anche su file ausiliari.
    base_abs = os.path.abspath(base)
    for root_dir, _dirs, names in os.walk(base):
        for name in names:
            if not name.endswith('.backup'):
                continue
            b = Path(root_dir) / name
            original = b.with_name(b.name[:-len('.backup')])
            if not original.exists():
                continue
            if dry_run:
                print(f'[dry] RIMUOVEREI backup ridondante: {b}')
                continue
            try:
                b.unlink()
                removed += 1
            except OSError as e:
                print(f'[warn] backup non rimosso {b}: {e}', file=sys.stderr)
    if not dry_run:
        live_keys = {str(p) for p in flac_files
                     if not p.name.casefold().endswith('.flac.flac')}
        stale = []
        for cached_path in cache:
            try:
                if os.path.commonpath([base_abs, os.path.abspath(cached_path)]) == base_abs and cached_path not in live_keys:
                    stale.append(cached_path)
            except (ValueError, OSError):
                continue
        for cached_path in stale:
            cache.pop(cached_path, None)
        _write_json_atomic(cache_path, cache)
    if stopped:
        print(f'[STOP] fase interrotta: {stopped}. Libera spazio e rilancia.', file=sys.stderr)
    print(f'convertiti: {converted} | saltati (cache o gia ok): {skipped} | '
          f'scartati (nessun guadagno): {nogain} | errori: {errors} | '
          f'probe fallite: {sum(probe_failures.values())} | spazio recuperato: {saved // 1024}K | '
          f'backup residui rimossi: {removed}')


# ===================== pulizia reference playlist morte =====================
# Navidrome NON rimuove dalle playlist le tracce il cui file e' stato
# cancellato: restano visibili in grigio ("unavailable") per sempre. Dopo
# ogni scan FULL eliminiamo le playlist_tracks il cui media_file non esiste
# piu'. Richiede stop di Navidrome (sqlite), come fix_owners.

def prune_playlist_refs():
    if not NAVIDROME_DB.exists():
        return
    ps = _docker('ps', '--filter', 'name=navidrome', '--format', '{{.Names}}')
    running = 'navidrome' in ps.stdout
    if running:
        print('  fermo navidrome per pulizia reference playlist...')
        _docker('stop', 'navidrome')
    try:
        con = sqlite3.connect(str(NAVIDROME_DB))
        cur = con.cursor()
        dangling = cur.execute(
            "SELECT COUNT(*) FROM playlist_tracks WHERE media_file_id "
            "NOT IN (SELECT id FROM media_file)").fetchone()[0]
        if dangling:
            cur.execute(
                "DELETE FROM playlist_tracks WHERE media_file_id "
                "NOT IN (SELECT id FROM media_file)")
            con.commit()
            print(f'  [i] rimosse {dangling} reference a tracce morte dalle playlist')
        else:
            print('  [i] nessuna reference morta nelle playlist')
        # album rimasti senza tracce: righe stale; il full scan successivo
        # li ricostruisce dai tag dei file
        dead_albums = cur.execute(
            "DELETE FROM album WHERE id NOT IN (SELECT DISTINCT album_id "
            "FROM media_file WHERE album_id IS NOT NULL)").rowcount
        con.commit()
        if dead_albums:
            print(f'  [i] rimossi {dead_albums} album senza tracce (stale)')
        con.close()
    except Exception as e:
        print(f'  [ERRORE] pulizia playlist: {e}', file=sys.stderr)
    finally:
        if running:
            print('  riavvio navidrome...')
            _docker('start', 'navidrome')
            # docker start restituisce quando il container e' partito, non quando l'API HTTP
            # e' pronta. Senza attesa, star_liked subito dopo riceveva Connection refused.
            if not _wait_navidrome_api_ready(timeout=120):
                print('  [ERRORE] Navidrome non e' + "'" + ' tornato raggiungibile dopo la pulizia DB.',
                      file=sys.stderr, flush=True)


# ===================== scan Navidrome =====================

def _get_scan_status():
    return _subsonic_req('/getScanStatus').get('scanStatus', {})


def _wait_navidrome_api_ready(timeout=120, user=None, password=None):
    """Attende che l'API Subsonic sia pronta dopo start/restart del container."""
    deadline = time.monotonic() + max(1, timeout)
    last_error = None
    while True:
        try:
            _subsonic_req('/getScanStatus', user=user, password=password)
            return True
        except Exception as e:
            last_error = e
            msg = str(e).casefold()
            # Un errore di autenticazione non si risolve aspettando l'avvio del servizio.
            if any(token in msg for token in ('notauthenticated', 'not authenticated', 'unauthorized',
                                               'forbidden', 'wrong username', 'wrong password')):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(2.0, remaining))
    print(f'[ERRORE] API Navidrome non pronta/raggiungibile dopo {timeout}s: {last_error}',
          file=sys.stderr, flush=True)
    return False


def run_navidrome_scan(full_scan=True, prune_refs=True):
    """Avvia e attende uno scan Navidrome.

    full_scan=True viene usato dalla manutenzione libreria. Per --sync-only si usa uno scan
    incrementale (molto meno invasivo) e non si ferma Navidrome per la pulizia DB. Se uno scan
    e' gia' attivo, si aspetta che termini: non si riavvia il container inutilmente.
    """
    if not SUBSONIC_PASS:
        print("[ERRORE] scan Navidrome saltato: imposta ND_PASS nell'ambiente", file=sys.stderr)
        return False
    if not _wait_navidrome_api_ready(timeout=120):
        return False

    # Non interrompere uno scan esistente riavviando Navidrome: attendi e poi avvia quello
    # richiesto, così le M3U appena aggiornate vengono comunque indicizzate.
    try:
        st = _get_scan_status()
    except Exception as e:
        print(f'[ERRORE] impossibile leggere lo stato di scansione Navidrome: {e}',
              file=sys.stderr, flush=True)
        return False
    if st.get('scanning'):
        print("[i] scan gia' in corso: attendo che termini senza riavviare Navidrome...",
              flush=True)
        wait_deadline = time.monotonic() + 5400
        existing_total = int(globals().get('_LIB_TRACK_COUNT') or 0)
        existing_progress = _ProgressBar('scan preesistente in corso', existing_total, 'brani',
                                         stream=sys.stdout)
        while st.get('scanning') and time.monotonic() < wait_deadline:
            time.sleep(3)
            try:
                st = _get_scan_status()
            except Exception as e:
                existing_progress.clear()
                print(f'  [warn] getScanStatus durante attesa: {e}', flush=True)
                continue
            if st.get('scanning') and existing_total:
                existing_progress.update(st.get('count', 0))
        existing_progress.close(complete=not st.get('scanning'))
        if st.get('scanning'):
            print('[ERRORE] lo scan preesistente non e’ terminato entro 90 minuti',
                  file=sys.stderr, flush=True)
            return False

    mode = 'FULL' if full_scan else 'incrementale'
    scan_path = '/startScan?fullScan=true' if full_scan else '/startScan'
    print(f'[i] avvio scan {mode} su Navidrome...', flush=True)
    try:
        _subsonic_req(scan_path)
    except Exception as e:
        print(f"[ERRORE] startScan fallito: {e} — attendo l'API e riprovo una volta...",
              flush=True)
        if not _wait_navidrome_api_ready(timeout=30):
            return False
        try:
            _subsonic_req(scan_path)
        except Exception as e2:
            print(f'[ERRORE] startScan fallito di nuovo: {e2}', file=sys.stderr, flush=True)
            return False

    timeout = 5400 if full_scan else 1800
    deadline = time.monotonic() + timeout
    last = None
    progress_total = int(globals().get('_LIB_TRACK_COUNT') or 0)
    scan_progress = _ProgressBar('scan in corso', progress_total, 'brani', stream=sys.stdout)
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            st = _get_scan_status()
        except Exception as e:
            print(f'  [warn] getScanStatus: {e}', flush=True)
            continue
        if not st.get('scanning'):
            scan_progress.close(complete=True)
            err = st.get('error')
            if err:
                print(f'[ERRORE] scan Navidrome terminato con errore: {err}',
                      file=sys.stderr, flush=True)
                return False
            print(f"[i] scan Navidrome completato: {st.get('count', '?')} brani, "
                  f"{st.get('folderCount', '?')} cartelle "
                  f"(lastScan {st.get('lastScan', '?')})", flush=True)
            if prune_refs:
                prune_playlist_refs()
                # La pulizia apre il DB SQLite fermando Navidrome. Verifica che il server sia
                # davvero online prima di dichiarare pronta la fase successiva.
                if not _wait_navidrome_api_ready(timeout=120):
                    return False
            return True
        cnt = st.get('count', 0)
        if progress_total:
            scan_progress.update(cnt)
        last = st
    scan_progress.close(complete=False)
    print(f'[ERRORE] scan Navidrome: timeout dopo {timeout // 60} minuti',
          file=sys.stderr, flush=True)
    return False


# ===================== riconciliazione album dopo scan Navidrome =====================
def _snapshot_navidrome_albums():
    """Snapshot DB degli album e dei path brano, usato solo per un diff prima/dopo scan."""
    if not NAVIDROME_DB.exists():
        return None
    try:
        with _nd_db(write=False) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'album', 'media_file'} <= tables:
                return None
            acols = _nd_table_cols(con, 'album')
            mcols = _nd_table_cols(con, 'media_file')
            name_col = 'name' if 'name' in acols else None
            id_col = 'id' if 'id' in acols else None
            artist_col = next((c for c in ('album_artist', 'albumartist', 'artist') if c in acols), None)
            if not name_col or not id_col:
                return None
            artist_expr = f'"{artist_col}"' if artist_col else "''"
            album_rows = con.execute(
                f'SELECT "{id_col}", "{name_col}", {artist_expr} FROM album').fetchall()
            if 'album_id' not in mcols:
                return None
            path_col = next((c for c in ('path', 'file_path') if c in mcols), None)
            title_col = 'title' if 'title' in mcols else None
            if path_col:
                media_rows = con.execute(f'SELECT album_id, "{path_col}" FROM media_file').fetchall()
            elif title_col:
                media_rows = con.execute('SELECT album_id, title FROM media_file').fetchall()
            else:
                media_rows = con.execute('SELECT album_id, id FROM media_file').fetchall()
    except (sqlite3.Error, OSError) as exc:
        print(f'[warn] snapshot album Navidrome non disponibile: {exc}', file=sys.stderr)
        return None

    paths_by_album = {}
    for aid, path_value in media_rows:
        path_value = str(path_value or '').strip()
        if path_value:
            paths_by_album.setdefault(str(aid), set()).add(path_value.replace('\\', '/'))
    snapshot = {}
    for aid, name, artist in album_rows:
        aid = str(aid)
        name, artist = str(name or '').strip(), str(artist or '').strip()
        identity_artist = _artist_entity_cjk_stem(artist)
        paths = paths_by_album.get(aid, set())
        snapshot[aid] = {
            'id': aid, 'name': name, 'artist': artist, 'key': (norm(name), norm(identity_artist)),
            'paths': paths, 'track_count': len(paths),
        }
    return snapshot


def _diff_navidrome_albums(before, after):
    """Classifica nuovi album, cambiamenti e fusioni usando indici per key e path (O(n+t))."""
    old_by_id = {str(k): v for k, v in before.items()}
    old_by_key = {}
    old_by_path = {}
    for rec in old_by_id.values():
        old_by_key.setdefault(rec['key'], []).append(rec)
        for path in rec.get('paths', set()):
            old_by_path.setdefault(path, set()).add(rec['id'])
    changes = {'new': [], 'changed': [], 'merged': [], 'affected': []}
    affected_ids = set()
    for current in after.values():
        overlapping_ids = set()
        for path in current.get('paths', set()):
            overlapping_ids.update(old_by_path.get(path, ()))
        overlaps = [old_by_id[oid] for oid in overlapping_ids if oid in old_by_id]
        exact = old_by_key.get(current['key'], [])
        # Una riga post-scan che contiene file da due o piu' vecchi album e' una fusione.
        if len(overlaps) >= 2:
            changes['merged'].append({'old': overlaps, 'new': current})
            affected_ids.add(current['id'])
            continue
        candidates = exact or overlaps
        old = max(candidates, key=lambda rec: len(rec.get('paths', set()) & current.get('paths', set()))) if candidates else None
        if old is None:
            changes['new'].append(current)
            affected_ids.add(current['id'])
        elif (old['paths'] != current['paths'] or old['track_count'] != current['track_count']
              or old['id'] != current['id'] or old.get('name') != current.get('name')
              or old.get('artist') != current.get('artist') or old.get('key') != current.get('key')):
            # Tag repair can change album/artist labels without changing track paths or DB IDs.
            # Treat display-name edits as changes too, so the requested post-scan report doesn't miss them.
            changes['changed'].append({'old': old, 'new': current})
            affected_ids.add(current['id'])
    changes['affected'] = [after[aid] for aid in sorted(affected_ids) if aid in after]
    return changes


def _print_navidrome_album_diff(changes):
    def label(rec):
        return f"{rec.get('name') or '(album senza nome)'} — {rec.get('artist') or '(artista sconosciuto)'}"
    print(f"=== nuovi album trovati ({len(changes['new'])}) ===", flush=True)
    for rec in sorted(changes['new'], key=lambda x: (x['artist'].casefold(), x['name'].casefold())):
        print(f"  - {label(rec)}", flush=True)
    print(f"=== album cambiati ({len(changes['changed'])}) ===", flush=True)
    for row in sorted(changes['changed'], key=lambda x: (x['new']['artist'].casefold(), x['new']['name'].casefold())):
        print(f"  - {label(row['old'])} -> {label(row['new'])}", flush=True)
    print(f"=== album accorpati / merged ({len(changes['merged'])}) ===", flush=True)
    for row in sorted(changes['merged'], key=lambda x: (x['new']['artist'].casefold(), x['new']['name'].casefold())):
        old_text = ' + '.join(label(old) for old in sorted(row['old'], key=lambda x: (x['artist'].casefold(), x['name'].casefold())))
        print(f"  - {old_text} -> {label(row['new'])}", flush=True)
    if not (changes['new'] or changes['changed'] or changes['merged']):
        print('  (nessun nuovo album, cambiamento o accorpamento rilevato)', flush=True)


def _db_path_to_host(db_path, base):
    """Converte un path Navidrome in path host, rispettando --library-root se fornito."""
    raw = str(db_path or '').replace('\\', '/')
    if not raw:
        return None
    p = Path(raw)
    try:
        if p.is_absolute() and p.is_file():
            return p.resolve()
    except OSError:
        pass
    if ND_MUSIC_ROOT and raw.startswith(ND_MUSIC_ROOT.rstrip('/') + '/'):
        candidate = Path(base) / raw[len(ND_MUSIC_ROOT.rstrip('/')) + 1:]
        if candidate.is_file():
            return candidate.resolve()
    if not p.is_absolute():
        candidate = Path(base) / p
        if candidate.is_file():
            return candidate.resolve()
    parts = p.parts[1:] if p.is_absolute() else p.parts
    for i in range(len(parts)):
        candidate = Path(base).joinpath(*parts[i:])
        if candidate.is_file():
            return candidate.resolve()
    return None


def _affected_album_paths(changes, base):
    """Risolvi i path degli album post-scan in sole cartelle/file effettivamente modificati."""
    dirs = set()
    for rec in changes.get('affected', []):
        for db_path in rec.get('paths', set()):
            path = _db_path_to_host(db_path, base)
            if path:
                dirs.add(_album_root_for_file(Path(base), path).resolve())
    files = set()
    for folder in dirs:
        files.update(f.resolve() for f in _audio_files(folder))
    return sorted(dirs), sorted(files)


# ===================== fase: star Spotify-liked music =====================
# Le stelle Navidrome sono per utente. Le tracce provengono da "liked" (o il vecchio
# nome "liked songs"), gli album da "saved albums", e gli artisti sono quelli presenti
# nelle due raccolte. Spotify non esporta i followed artists in un CSV Exportify standard.
SUBSONIC_BASE = os.environ.get('ND_URL', 'http://192.168.1.7:4533').rstrip('/')
SUBSONIC_USER = os.environ.get('ND_USER', 'chic')
SUBSONIC_PASS = os.environ.get('ND_PASS')

def _load_navidrome_env_file():
    """Carica ND_* e le credenziali delle utility opzionali dal file env; ambiente ha precedenza."""
    candidates = []
    if os.environ.get('ND_ENV_FILE'):
        candidates.append(Path(os.environ['ND_ENV_FILE']).expanduser())
    candidates.extend([
        Path(__file__).resolve().with_name('.env'),
        Path.home() / 'homelab' / '.env',
        Path.home() / 'homelab' / 'docker' / '.env',
        Path.home() / 'homelab' / 'scripts' / '.env',
        Path.home() / '.config' / 'exportify2m3u' / 'navidrome.env',
    ])
    seen = set()
    for env_path in candidates:
        try:
            env_path = env_path.resolve()
            if env_path in seen or not env_path.is_file():
                continue
            seen.add(env_path)
            for line in env_path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('export '):
                    line = line[7:].lstrip()
                m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
                if not m:
                    continue
                key, value = m.groups()
                if not (key in {'ND_URL', 'ND_USER', 'ND_DEFAULT_USER', 'ND_FAVORITES_USER', 'ND_PASS',
                                'LIDARR_URL', 'LIDARR_API_KEY', 'LIDARR_MUSIC_ROOT',
                                'LIDARR_CONTAINER_ROOT', 'SLKSD_IMPORT_FOLDER',
                                'SLKSD_FAILED_FOLDER', 'LISTENBRAINZ_TOKEN',
                                'SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET', 'SPOTIFY_MARKET'} or
                        re.fullmatch(r'ND_PASS_[A-Za-z0-9_]+', key)):
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', "'"):
                    value = value[1:-1]
                if key not in os.environ and value:
                    os.environ[key] = value
        except (OSError, UnicodeError):
            continue
    global SUBSONIC_BASE, SUBSONIC_USER, SUBSONIC_PASS, DEFAULT_USER
    SUBSONIC_BASE = os.environ.get('ND_URL', SUBSONIC_BASE).rstrip('/')
    SUBSONIC_USER = os.environ.get('ND_USER', SUBSONIC_USER)
    SUBSONIC_PASS = os.environ.get('ND_PASS', SUBSONIC_PASS)
    if not SUBSONIC_PASS:
        primary_key = 'ND_PASS_' + re.sub(r'\W', '_', SUBSONIC_USER).upper()
        SUBSONIC_PASS = os.environ.get(primary_key)
    DEFAULT_USER = os.environ.get('ND_DEFAULT_USER', DEFAULT_USER)

LIKED_PLNAMES = ('liked', 'liked songs')
SAVED_ALBUMS_PLNAMES = ('saved albums', 'saved album')
STAR_CHUNK = 100


def _subsonic_req(path, user=None, password=None):
    user = user or SUBSONIC_USER
    password = SUBSONIC_PASS if password is None else password
    if not password:
        raise RuntimeError('password Navidrome mancante: imposta ND_PASS o ND_PASS_<UTENTE>')
    salt = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    token = hashlib.md5((password + salt).encode()).hexdigest()
    auth = (f"u={urllib.parse.quote(user, safe='')}&t={token}"
            f"&s={salt}&v=1.16.1&c=bulkfav&f=json")
    url = SUBSONIC_BASE + "/rest" + path + ("&" if "?" in path else "?") + auth
    with urllib.request.urlopen(url, timeout=15) as response:
        payload = json.load(response)
    d = payload["subsonic-response"]
    if d.get("status") != "ok":
        raise RuntimeError(d)
    return d


def _list_playlists(username=None, user=None, password=None):
    path = "/getPlaylists" + (f"?username={urllib.parse.quote(username, safe='')}" if username else "")
    raw = _subsonic_req(path, user, password).get("playlists", {}).get("playlist")
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _user_password(user):
    """Password Subsonic di un utente: ND_PASS_<UTENTE> (non alfanumerici -> '_'); per
    l'utente ND_USER ripiega su ND_PASS. -> (password o None, nome variabile)."""
    key = 'ND_PASS_' + re.sub(r'\W', '_', user).upper()
    if os.environ.get(key):
        return os.environ[key], key
    if user.lower() == SUBSONIC_USER.lower():
        return SUBSONIC_PASS, key
    return None, key


def _norm_playlist_name(name):
    return re.sub(r'\s+', ' ', str(name or '').strip()).casefold()


def _find_user_playlist(user, password, accepted_names):
    """Trova la playlist dell'utente, preferendo owner esplicito e poi il nome prioritario."""
    names = {_norm_playlist_name(n): i for i, n in enumerate(accepted_names)}
    for attempt in (None, user):
        candidates = []
        for p in _list_playlists(attempt, user, password):
            key = _norm_playlist_name(p.get('name'))
            owner = str(p.get('owner') or '')
            if key not in names or owner.casefold() not in (user.casefold(), ''):
                continue
            candidates.append((0 if owner.casefold() == user.casefold() else 1,
                               names[key], p))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            return candidates[0][2]
    return None


def _playlist_entries(playlist, user, password):
    if not playlist:
        return []
    pid = str(playlist.get('id') or '')
    if not pid:
        return []
    path = '/getPlaylist?' + urllib.parse.urlencode({'id': pid})
    raw = _subsonic_req(path, user, password).get('playlist', {}).get('entry')
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _entry_artist_ids(entry):
    """Estrae artistId del brano e, quando presente, gli ID anche degli artisti collaboratori."""
    out = set()
    aid = entry.get('artistId')
    if aid not in (None, ''):
        out.add(str(aid))
    artists = entry.get('artists')
    if isinstance(artists, dict):
        artists = artists.get('artist', [artists])
    if isinstance(artists, list):
        for artist in artists:
            if isinstance(artist, dict) and artist.get('id') not in (None, ''):
                out.add(str(artist['id']))
    return out


def _star_ids(ids, param, user, password, already=()):
    """Stella ID Subsonic (id, albumId o artistId) in batch sicuri per lunghezza URL."""
    all_ids = sorted({str(i) for i in ids if i not in (None, '')})
    already = {str(i) for i in already if i not in (None, '')}
    todo = [i for i in all_ids if i not in already]
    if not todo:
        return 0, 0
    fails = 0
    for n in range(0, len(todo), STAR_CHUNK):
        chunk = todo[n:n + STAR_CHUNK]
        query = urllib.parse.urlencode([(param, item) for item in chunk])
        try:
            _subsonic_req('/star?' + query, user, password)
        except Exception as e:
            fails += 1
            print(f"  !! {param} chunk at {n}: {type(e).__name__}: {e}")
    return len(todo), fails


def _starred_ids(user, password):
    """Restituisce gli ID gia' preferiti (brani, album, artisti) da una sola richiesta API."""
    data = _subsonic_req('/getStarred2', user, password).get('starred2', {})

    def ids(key):
        raw = data.get(key) or []
        if isinstance(raw, dict):
            raw = [raw]
        return {str(item['id']) for item in raw
                if isinstance(item, dict) and item.get('id') not in (None, '')}

    return ids('song'), ids('album'), ids('artist')


def _csv_header(fields, *names):
    """Colonna CSV case-insensitive e BOM/whitespace-safe."""
    by_key = {re.sub(r'\s+', ' ', (f or '').strip().lstrip('\ufeff').casefold()): f
              for f in fields or []}
    for name in names:
        key = re.sub(r'\s+', ' ', name.strip().casefold())
        if key in by_key:
            return by_key[key]
    return None

def _saved_albums_csv(user):
    user_dir = EXPORTIFY_DIR / user
    for path in _csv_files(user_dir, recursive=True):
        stem = _norm_playlist_name(path.stem.replace('_', ' '))
        if stem in {'saved albums', 'saved album'}:
            return path
    return None

def _read_saved_album_rows(user):
    path = _saved_albums_csv(user)
    if not path:
        return []
    rows = []
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            name_col = _csv_header(fields, 'Album Name', "Nome dell'album", 'Album')
            artist_col = _csv_header(fields, 'Album Artist Name(s)', 'Album Artist Name',
                                     'Album Artist', 'Nome artista album')
            if not name_col:
                print(f"[{user}] [ERRORE] {path.name}: manca la colonna 'Album Name'", file=sys.stderr)
                return []
            for row in reader:
                name = (row.get(name_col) or '').strip()
                artists = (row.get(artist_col) or '').strip() if artist_col else ''
                if name:
                    rows.append({'name': name, 'artists': artists})
    except (OSError, csv.Error, UnicodeError) as e:
        print(f"[{user}] [ERRORE] lettura {path.name}: {e}", file=sys.stderr)
        return []
    print(f"[{user}] raccolta album: letti {len(rows)} album da {path.name}")
    return rows

def _list_container(value, key):
    if not value:
        return []
    raw = value.get(key) if isinstance(value, dict) and key in value else value
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]

def _navidrome_album_catalog(user, password):
    """Legge il catalogo locale a pagine via Subsonic; non modifica nulla."""
    albums = []
    offset, page_size = 0, 500
    for _ in range(100):
        query = urllib.parse.urlencode({'type': 'alphabeticalByName', 'size': page_size, 'offset': offset})
        data = _subsonic_req('/getAlbumList2?' + query, user, password)
        page = _list_container(data.get('albumList2', {}), 'album')
        albums.extend(a for a in page if isinstance(a, dict) and a.get('id'))
        if len(page) < page_size:
            break
        offset += len(page)
    else:
        print(f"[{user}] [warn] catalogo album troncato a {len(albums)} voci", file=sys.stderr)
    return albums

def _navidrome_artist_catalog(user, password):
    data = _subsonic_req('/getArtists', user, password).get('artists', {})
    indexes = data.get('index', []) if isinstance(data, dict) else []
    if isinstance(indexes, dict):
        indexes = [indexes]
    artists = []
    for index in indexes or []:
        artists.extend(_list_container(index, 'artist'))
    return [a for a in artists if isinstance(a, dict) and a.get('id')]

def _saved_album_ids(rows, catalog, user):
    """Match gli album salvati Spotify per titolo e artista; stellare tutte le edizioni compatibili.

    Se il titolo e' presente piu' volte nel catalogo, non scartiamo piu' l'album come
    "ambiguo": se l'artista combacia, vengono scelte tutte le edizioni di quell'artista;
    se i nomi artista non combaciano per differenze di formattazione/alias, si usa il titolo
    esatto normalizzato e si stellano tutte le voci con quel titolo, come richiesto nella
    configurazione di questo utente.
    """
    by_name = {}
    for album in catalog:
        key = norm(album.get('name', ''))
        if key:
            by_name.setdefault(key, []).append(album)
    ids, matched = set(), 0
    for row in rows:
        title_key = norm(row.get('name', ''))
        candidates = by_name.get(title_key, [])
        if not candidates:
            continue
        raw_artists = str(row.get('artists', '') or '')
        source_artist = norm(raw_artists)
        parts = {norm(x) for x in re.split(r'\s*(?:,|;|&|\band\b|•)\s*', raw_artists, flags=re.I)
                 if norm(x)}
        exact_artist = []
        for album in candidates:
            local_artist = norm(album.get('artist', ''))
            if not local_artist:
                continue
            # Copre sia un campo artista con joiner unico sia gli album multi-artista.
            local_parts = {norm(x) for x in re.split(r'\s*(?:,|;|&|\band\b|•)\s*',
                                                       str(album.get('artist', '') or ''), flags=re.I)
                           if norm(x)}
            if (source_artist and local_artist == source_artist) or local_artist in parts \
                    or bool(local_parts and local_parts.issubset(parts)) \
                    or bool(parts and local_parts.intersection(parts)):
                exact_artist.append(album)
        chosen = exact_artist if exact_artist else candidates
        chosen_ids = {str(a['id']) for a in chosen if a.get('id') not in (None, '')}
        if chosen_ids:
            ids.update(chosen_ids)
            matched += 1
            if len(chosen_ids) > 1:
                print(f"[{user}] album con piu' edizioni compatibili: {row.get('artists','')} - "
                      f"{row.get('name','')} ({len(chosen_ids)} album; tutte da stellare)")
            elif not exact_artist and raw_artists:
                print(f"[{user}] [info] artista non riconosciuto esattamente per "
                      f"{row.get('artists','')} - {row.get('name','')}; usato il titolo "
                      "normalizzato per individuare l'album locale")
    if len(rows) > matched:
        print(f"[{user}] album Spotify senza corrispondenza locale: {len(rows)-matched}")
    return ids, matched

def _saved_artist_ids(rows, catalog, user):
    by_name = {}
    for artist in catalog:
        key = norm(artist.get('name', ''))
        if key:
            by_name.setdefault(key, set()).add(str(artist['id']))
    ids, missing = set(), set()
    for row in rows:
        raw = row.get('artists', '')
        names = ([raw] + re.split(r'\s*(?:,|;|&|\band\b)\s*', raw, flags=re.I)) if raw else []
        found = False
        for name in names:
            key = norm(name)
            if key and key in by_name:
                ids.update(by_name[key])
                found = True
        if raw and not found:
            missing.add(raw)
    if missing:
        print(f"[{user}] artisti album non trovati nel catalogo Navidrome: {len(missing)}")
    return ids


def _star_liked_for(user, password):
    liked = _find_user_playlist(user, password, LIKED_PLNAMES)
    saved_playlist = _find_user_playlist(user, password, SAVED_ALBUMS_PLNAMES)  # compatibilita' vecchia
    liked_entries = _playlist_entries(liked, user, password) if liked else []
    legacy_saved_entries = _playlist_entries(saved_playlist, user, password) if saved_playlist else []
    album_rows = _read_saved_album_rows(user)

    if liked:
        print(f"[{user}] trovata playlist '{liked.get('name')}' id={liked.get('id')} ({len(liked_entries)} brani)")
    else:
        print(f"[{user}] [warn] playlist 'liked'/'liked songs' non trovata; salto le tracce")

    song_ids = {str(e['id']) for e in liked_entries
                if isinstance(e, dict) and e.get('id') not in (None, '')}
    try:
        starred_songs, starred_albums, starred_artists = _starred_ids(user, password)
    except Exception as e:
        starred_songs = {str(e['id']) for e in liked_entries
                         if isinstance(e, dict) and e.get('id') not in (None, '') and e.get('starred')}
        starred_albums, starred_artists = set(), set()
        print(f"[{user}] [warn] impossibile leggere getStarred2 ({e}); provo le stelle richieste")
    song_todo, song_fail = _star_ids(song_ids, 'id', user, password, starred_songs)
    print(f"[{user}] tracce liked: {len(song_ids)} in playlist, {song_todo} da stellare, {song_fail} errori")

    artist_ids = set()
    for entry in liked_entries + legacy_saved_entries:
        if isinstance(entry, dict):
            artist_ids.update(_entry_artist_ids(entry))
    album_ids, album_matched = set(), 0
    if album_rows:
        try:
            album_catalog = _navidrome_album_catalog(user, password)
            album_ids, album_matched = _saved_album_ids(album_rows, album_catalog, user)
        except Exception as e:
            print(f"[{user}] [ERRORE] catalogo album Navidrome: {type(e).__name__}: {e}", file=sys.stderr)
        try:
            artist_catalog = _navidrome_artist_catalog(user, password)
            artist_ids.update(_saved_artist_ids(album_rows, artist_catalog, user))
        except Exception as e:
            print(f"[{user}] [ERRORE] catalogo artisti Navidrome: {type(e).__name__}: {e}", file=sys.stderr)
    else:
        # Compatibilita' con la vecchia versione che ricavava albumId da una M3U salvata.
        for entry in legacy_saved_entries:
            if isinstance(entry, dict) and entry.get('albumId') not in (None, ''):
                album_ids.add(str(entry['albumId']))
        if not legacy_saved_entries:
            print(f"[{user}] [warn] CSV 'saved albums' non trovato: nessun album da stellare")

    album_todo, album_fail = _star_ids(album_ids, 'albumId', user, password, starred_albums)
    artist_todo, artist_fail = _star_ids(artist_ids, 'artistId', user, password, starred_artists)
    print(f"[{user}] album salvati: {len(album_ids)} match Navidrome"
          f"{f' ({album_matched}/{len(album_rows)} righe CSV)' if album_rows else ''}, "
          f"{album_todo} da stellare, {album_fail} errori")
    print(f"[{user}] artisti di liked/album salvati: {len(artist_ids)} ID, {artist_todo} da stellare, {artist_fail} errori")
    if not liked and not album_rows and not legacy_saved_entries:
        print(f"[{user}] nessuna fonte Spotify disponibile: nulla da fare")

def run_star_liked(users=None):
    """Stella la musica Spotify importata in Navidrome per utente.

    -- liked / liked songs: tutte le tracce
    -- saved albums: tutti gli album distinti presenti
    -- artists: ogni artista ID presente nei brani di entrambe le playlist

    Limite: Exportify esporta playlist, non la raccolta autonoma di artisti seguiti su Spotify;
    gli artisti seguiti che non compaiono in questi brani non sono disponibili in questa fase.
    Serve ND_PASS_<UTENTE> (per ND_USER basta ND_PASS)."""
    errors = 0
    skipped = 0
    for u in (users if users is not None else (_db_users() or [SUBSONIC_USER])):
        pw, key = _user_password(u)
        if pw is None:
            skipped += 1
            print(f"[{u}] star_liked: nessuna password (imposta {key}), saltato", file=sys.stderr)
            continue
        try:
            _star_liked_for(u, pw)
        except Exception as e:
            errors += 1
            print(f"[{u}] [ERRORE] star_liked: {type(e).__name__}: {e}", file=sys.stderr)
    if errors:
        print(f'star_liked: {errors} utenti con errore API, {skipped} saltati per password assente',
              file=sys.stderr)
        return False
    return True


# ===================== fase: fix playlist owners =====================
# (da fix_playlist_owners.py — proprieta' delle playlist per cartella utente + dedupe)

NAVIDROME_DB = Path('/homelab/arr-config/navidrome/navidrome.db')


def _docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True)


@contextlib.contextmanager
def _nd_db(write=False, reason=''):
    """Connessione al DB Navidrome. write=True: ferma il container, apre in scrittura e lo
    riavvia alla fine; write=False: sola lettura (anche a Navidrome acceso)."""
    running = False
    if write:
        ps = _docker('ps', '--filter', 'name=navidrome', '--format', '{{.Names}}')
        running = 'navidrome' in ps.stdout
        if running:
            print(f'  fermo navidrome ({reason})...')
            _docker('stop', 'navidrome')
    try:
        if write:
            con = sqlite3.connect(str(NAVIDROME_DB), timeout=30)
        else:
            con = sqlite3.connect(f'{NAVIDROME_DB.as_uri()}?mode=ro', uri=True, timeout=30)
        try:
            yield con
        finally:
            con.close()
    finally:
        if running:
            print('  riavvio navidrome...')
            _docker('start', 'navidrome')


def _owner_for_playlist_path(path, users_lower, default):
    """Proprietario atteso di una playlist importata da m3u, dal PERCORSO del file:
      .../Playlists/<utente>/...  -> <utente>
      .../Playlists/...           -> default (layout storico, sottocartelle tematiche)
      fuori da Playlists          -> None (non si tocca)"""
    parts = Path(path).parts
    root = PLAYLIST_DIR.name
    if root not in parts[:-1]:
        return None
    inner = parts[parts.index(root) + 1:-1]
    if inner and inner[0].lower() in users_lower:
        return users_lower[inner[0].lower()]
    return default


def run_fix_owners(default_owner='', dry_run=False, users=None):
    """Assegna ogni playlist IMPORTATA DA M3U (path non vuoto) al proprietario giusto, in base
    alla cartella dell'm3u (vedi _owner_for_playlist_path). Le playlist create a mano
    nell'UI (path vuoto) non si toccano. users: solo le playlist di questi utenti."""
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB non trovato: {NAVIDROME_DB}')
        return
    default_owner = default_owner or DEFAULT_USER
    wanted = {u.lower() for u in users} if users is not None else None
    with _nd_db(write=not dry_run, reason='riassegno proprietari playlist') as con:
        cur = con.cursor()
        ids = {n.lower(): (i, n) for i, n in cur.execute('SELECT id, user_name FROM user')}
        for k, (uid, uname) in ids.items():
            print(f'    utente: id={uid}  name={uname}')
        if default_owner.lower() not in ids:
            print(f'[ERRORE] utente {default_owner!r} non trovato nel DB')
            return
        users_lower = {k: v[1] for k, v in ids.items()}
        default_name = ids[default_owner.lower()][1]
        rows = cur.execute("SELECT id, owner_id, path FROM playlist "
                           "WHERE path IS NOT NULL AND path != ''").fetchall()
        changes = []
        progress = _ProgressBar('fix_playlist_owners', len(rows), 'playlist')
        for row_index, (pid, oid, path) in enumerate(rows, 1):
            progress.update(row_index)
            tgt = _owner_for_playlist_path(path, users_lower, default_name)
            if tgt is None or (wanted is not None and tgt.lower() not in wanted):
                continue
            tid = ids[tgt.lower()][0]
            if oid != tid:
                changes.append((tid, pid, tgt))
        progress.close(complete=True)
        by = Counter(t for _, _, t in changes)
        detail = ', '.join(f'{n} -> {u}' for u, n in sorted(by.items())) or 'nessuna'
        if dry_run:
            print(f'[dry-run] playlist da riassegnare: {detail}')
            return
        if changes:
            cur.executemany('UPDATE playlist SET owner_id=? WHERE id=?',
                            [(t, p) for t, p, _ in changes])
            con.commit()
        print(f'riassegnate {len(changes)} playlist ({detail}); '
              f'esaminate {len(rows)} importate da m3u')



def run_fix_all_playlist_owners(target_owner='', dry_run=False):
    """Force every Navidrome playlist (including UI-created playlists) to one owner.

    This is the legacy helper's exact broad behaviour. It is separate from --fix-owners,
    which intentionally preserves UI-created playlist ownership and maps M3U paths by user.
    """
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB Navidrome non trovato: {NAVIDROME_DB}', file=sys.stderr)
        return False
    target_owner = (target_owner or DEFAULT_USER).strip()
    with _nd_db(write=not dry_run, reason='forzo proprietario di tutte le playlist') as con:
        cur = con.cursor()
        users = cur.execute('SELECT id, user_name FROM user').fetchall()
        for uid, uname in users:
            print(f'    utente: id={uid}  name={uname}')
        target = next(((uid, uname) for uid, uname in users
                       if uname.casefold() == target_owner.casefold()), None)
        if target is None:
            print(f"[ERRORE] utente '{target_owner}' non trovato nel DB Navidrome", file=sys.stderr)
            return False
        target_id, target_name = target
        print('--- proprietari attuali delle playlist:')
        for row in cur.execute("SELECT p.owner_id, u.user_name, COUNT(*) FROM playlist p LEFT JOIN user u ON u.id=p.owner_id GROUP BY p.owner_id, u.user_name"):
            print('   ', row)
        count = cur.execute('SELECT COUNT(*) FROM playlist WHERE owner_id IS NULL OR owner_id != ?',
                            (target_id,)).fetchone()[0]
        if dry_run:
            print(f'[dry-run] {count} playlist verrebbero assegnate a {target_name} (id {target_id}); '
                  'le playlist create nella UI sono incluse.')
            return True
        cur.execute('UPDATE playlist SET owner_id=? WHERE owner_id IS NULL OR owner_id != ?',
                    (target_id, target_id))
        con.commit()
        print(f'Riassegnate {cur.rowcount} playlist a {target_name} (id {target_id}).')
    return True


_TS_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})'
                    r'(?:\.(\d+))?\s*(Z|[+-]\d{2}:?\d{2})?')


def _ts(v):
    """Timestamp testuale di Navidrome -> secondi epoch UTC (-1 se illeggibile)."""
    m = _TS_RE.match(str(v or ''))
    if not m:
        return -1.0
    y, mo, d, h, mi, se = (int(x) for x in m.groups()[:6])
    us = int((m.group(7) or '0')[:6].ljust(6, '0'))
    tz, off = m.group(8), 0
    if tz and tz != 'Z':
        dg = tz[1:].replace(':', '')
        off = (-1 if tz[0] == '-' else 1) * (int(dg[:2]) * 3600 + int(dg[2:4]) * 60)
    try:
        return datetime(y, mo, d, h, mi, se, us, tzinfo=timezone.utc).timestamp() - off
    except ValueError:
        return -1.0


def _playlist_dependents(con):
    """[(tabella, colonna)] che puntano a playlist(id): FK dichiarate + colonne 'playlist_id'."""
    out = set()
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name != 'playlist' AND name NOT LIKE 'sqlite_%'").fetchall():
        qt = '"' + t.replace('"', '""') + '"'
        for fk in con.execute(f'PRAGMA foreign_key_list({qt})').fetchall():
            if fk[2] == 'playlist':
                out.add((t, fk[3]))
        for col in con.execute(f'PRAGMA table_info({qt})').fetchall():
            if col[1] == 'playlist_id':
                out.add((t, col[1]))
    return sorted(out)


def _remove_nav_playlists_for_deleted_m3u(deleted_paths, expected_paths=()):
    """Pulisce dal DB sia le M3U appena rimosse sia vecchi record alias delle playlist correnti.

    Gli alias sono confrontati per percorso relativo a PLAYLIST_DIR, ignorando case, spazi e
    punteggiatura del basename. Questo gestisce anche record DB rimasti da run precedenti,
    quando il file alias era già sparito e quindi non rientrava fra i file cancellati oggi.
    """
    deleted_paths = list(deleted_paths or [])
    expected_paths = [Path(p) for p in (expected_paths or [])]
    if not deleted_paths and not expected_paths:
        return 0
    if not NAVIDROME_DB.exists():
        print(f"[warn] M3U obsolete/alias, ma DB Navidrome non trovato: {NAVIDROME_DB}",
              file=sys.stderr)
        return 0

    playlists_root = _normal_path(PLAYLIST_DIR)
    target_abs = set()
    target_suffixes = set()
    for path in deleted_paths:
        absolute = _normal_path(path)
        try:
            relative = absolute.relative_to(playlists_root).as_posix()
        except ValueError:
            continue
        target_abs.add(str(absolute).replace('\\', '/'))
        target_suffixes.add('/' + playlists_root.name + '/' + relative)

    expected_by_key = {}
    for path in expected_paths:
        absolute = _normal_path(path)
        try:
            rel = absolute.relative_to(playlists_root)
        except ValueError:
            continue
        key = _playlist_relative_collision_key(rel)
        if key:
            bucket = expected_by_key.setdefault(key, {'exact_rel': set(), 'exact_names': set()})
            bucket['exact_rel'].add(rel.as_posix())
            bucket['exact_names'].add(rel.stem)
    if not target_abs and not expected_by_key:
        return 0

    def _db_rel_key(db_path):
        rel = _db_playlist_relative_path(db_path)
        return (rel, _playlist_relative_collision_key(rel)) if rel else (None, None)

    def matching_ids(con):
        cols = {row[1] for row in con.execute('PRAGMA table_info(playlist)')}
        if not {'id', 'path'} <= cols:
            print(f"[warn] schema playlist Navidrome senza id/path: {sorted(cols)}", file=sys.stderr)
            return []
        def c(name):
            return f'"{name}"' if name in cols else 'NULL'
        rows = con.execute(
            f"SELECT {c('id')}, {c('path')}, {c('name')}, {c('owner_id')}, "
            f"{c('updated_at')}, {c('created_at')}, {c('song_count')} FROM playlist"
        ).fetchall()
        by_key = {}
        direct_doomed = {}
        for r in rows:
            pid, db_path, name, owner_id, updated_at, created_at, song_count = r
            db_norm = os.path.normpath(str(db_path or '').replace('\\', '/')) if db_path else ''
            if db_norm and not db_norm.startswith('/'):
                db_norm = '/' + db_norm
            is_deleted_path = bool(db_norm and (db_norm in target_abs or
                                  any(db_norm.endswith(suffix) for suffix in target_suffixes)))
            rel, key = _db_rel_key(db_path)
            if is_deleted_path:
                direct_doomed[pid] = (pid, str(name or ''), str(db_path or ''))
                continue
            if key in expected_by_key:
                # Record esatto del percorso canonico: candidato da preservare. Path alias
                # con nome diverso (case/punteggiatura) viene invece eliminato anche se
                # il corrispondente file era stato cancellato in una run precedente.
                bucket = expected_by_key[key]
                if rel in bucket['exact_rel'] and str(name or '') in bucket['exact_names']:
                    by_key.setdefault((owner_id, key), []).append(r)
                else:
                    # Anche se il path e' canonico, un name DB con case/punteggiatura vecchia
                    # puo' continuare a mostrare il titolo sbagliato in UI: rimuovi la riga,
                    # poi la scan reimportera' il file canonico col nome corretto.
                    direct_doomed[pid] = (pid, str(name or ''), str(db_path or ''))
            elif not db_path and name:
                # Path NULL: solo playlist alla radice, mai assumere una sottocartella ignota.
                name_key = _playlist_collision_key(name)
                root_key = ((), name_key)
                if root_key in expected_by_key:
                    bucket = expected_by_key[root_key]
                    if str(name) in bucket['exact_names']:
                        by_key.setdefault((owner_id, root_key), []).append(r)
                    else:
                        direct_doomed[pid] = (pid, str(name or ''), '')

        # Se Navidrome ha più righe sulla stessa path canonica, tieni la più recente.
        for group_key, group in by_key.items():
            if len(group) <= 1:
                continue
            group.sort(key=lambda r: (_ts(r[4]), _ts(r[5]), r[6] or 0, str(r[0])), reverse=True)
            for r in group[1:]:
                direct_doomed[r[0]] = (r[0], str(r[2] or ''), str(r[1] or ''))
        return list(direct_doomed.values())

    try:
        ro = sqlite3.connect(f'{NAVIDROME_DB.as_uri()}?mode=ro', uri=True, timeout=15)
        try:
            found = matching_ids(ro)
        finally:
            ro.close()
    except sqlite3.Error as e:
        print(f"[warn] pulizia playlist DB alias fallita in lettura: {e}", file=sys.stderr)
        return 0
    if not found:
        print("[i] nessun record Navidrome stale/alias da eliminare", file=sys.stderr)
        return 0

    try:
        with _nd_db(write=True, reason='elimino dal DB playlist M3U obsolete/alias') as con:
            found = matching_ids(con)
            if not found:
                return 0
            ids = [row[0] for row in found]
            deps = _playlist_dependents(con)
            cur = con.cursor()
            try:
                for i in range(0, len(ids), 400):
                    part = ids[i:i + 400]
                    placeholders = ','.join('?' for _ in part)
                    for table, column in deps:
                        qtable = '"' + table.replace('"', '""') + '"'
                        qcolumn = '"' + column.replace('"', '""') + '"'
                        cur.execute(f'DELETE FROM {qtable} WHERE {qcolumn} IN ({placeholders})', part)
                    cur.execute(f'DELETE FROM playlist WHERE id IN ({placeholders})', part)
                con.commit()
            except sqlite3.Error:
                con.rollback()
                raise
        print(f"[i] eliminate {len(found)} playlist record obsolete/alias dal DB Navidrome "
              f"(tabelle collegate pulite: {', '.join(table for table, _ in deps) or 'nessuna'})",
              file=sys.stderr)
        for _pid, name, db_path in found[:8]:
            print(f"    [i] rimossa playlist DB: {name or Path(db_path).name} ({db_path or 'path NULL'})",
                  file=sys.stderr)
        if len(found) > 8:
            print(f"    ... e altre {len(found)-8}", file=sys.stderr)
        return len(found)
    except Exception as e:
        print(f"[ERRORE] pulizia DB playlist M3U obsolete/alias fallita: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 0

def run_dedupe_playlists(apply=False, users=None):
    """Playlist con lo STESSO NOME ESATTO e lo stesso proprietario: tiene la piu' recente
    (updated_at, poi created_at, poi piu' brani) e cancella le altre dal DB Navidrome
    (con le righe collegate, es. playlist_tracks). users: solo i duplicati di questi utenti.
    Senza apply = dry-run (DB aperto in sola lettura)."""
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB non trovato: {NAVIDROME_DB}')
        return
    wanted = {u.lower() for u in users} if users is not None else None
    with _nd_db(write=apply, reason='dedupe playlist') as con:
        cols = {r[1] for r in con.execute('PRAGMA table_info(playlist)')}
        if not {'id', 'name', 'owner_id'} <= cols:
            print(f'[ERRORE] schema playlist inatteso (colonne: {sorted(cols)})')
            return

        def c(name):
            return f'p.{name}' if name in cols else 'NULL'
        rows = con.execute(
            f"SELECT p.id, p.name, p.owner_id, COALESCE(u.user_name, '?'), {c('updated_at')}, "
            f"{c('created_at')}, {c('path')}, {c('song_count')} "
            "FROM playlist p LEFT JOIN user u ON u.id = p.owner_id").fetchall()
        groups = {}
        for r in rows:
            if r[1] is not None:
                groups.setdefault((r[2], r[1]), []).append(r)
        doomed, ngroups = [], 0
        ordered_groups = sorted(groups.items(),
                                key=lambda kv: (str(kv[1][0][3]).lower(), kv[0][1].lower()))
        progress = _ProgressBar('dedupe_playlists', len(ordered_groups), 'gruppi')
        for group_index, ((_, name), grp) in enumerate(ordered_groups, 1):
            progress.update(group_index)
            if len(grp) < 2:
                continue
            uname = grp[0][3]
            if wanted is not None and uname.lower() not in wanted:
                continue
            grp.sort(key=lambda r: (_ts(r[4]), _ts(r[5]), r[7] or 0, str(r[0])), reverse=True)
            keep, drop = grp[0], grp[1:]
            ngroups += 1
            doomed += drop

            def desc(r):
                return f"id={r[0]} agg. {r[4] or '?'}, {r[7] if r[7] is not None else '?'} brani"
            progress.clear()
            print(f"  [{uname}] {name!r}: {len(grp)} copie -> tengo {desc(keep)}")
            for r in drop:
                progress.clear()
                print(f"      elimino {desc(r)}")
            diff = [r for r in drop if r[6] and r[6] != keep[6]]
            if diff:
                progress.clear()
                print(f"      nota: percorsi m3u diversi (tenuto: {keep[6] or '-'}; eliminato: "
                      f"{diff[0][6]}) - se quell'm3u e' ancora su disco, Navidrome lo reimportera'")
        progress.close(complete=True)
        if not doomed:
            print('  [i] nessuna playlist duplicata')
            return
        if not apply:
            print(f'[dry-run] {len(doomed)} playlist da eliminare in {ngroups} gruppi '
                  f'(usa --apply per eseguire)')
            return
        deps = _playlist_dependents(con)
        ids = [r[0] for r in doomed]
        cur = con.cursor()
        try:
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                ph = ','.join('?' * len(part))
                for t, col in deps:
                    cur.execute(f'DELETE FROM "{t}" WHERE "{col}" IN ({ph})', part)
                cur.execute(f'DELETE FROM playlist WHERE id IN ({ph})', part)
            con.commit()
        except sqlite3.Error:
            con.rollback()
            raise
        print(f'  [i] eliminate {len(doomed)} playlist duplicate in {ngroups} gruppi '
              f'(tabelle collegate pulite: {", ".join(t for t, _ in deps) or "nessuna"})')


# ===================== DB Navidrome: percorsi e album =====================

ND_MUSIC_ROOT = os.environ.get('ND_MUSIC_ROOT', '')      # prefisso della musica DENTRO il container
ND_ARTIST_JOINER = os.environ.get('ND_ARTIST_JOINER', ' • ')   # Scanner.ArtistJoiner di Navidrome


def _db_to_host(path):
    """media_file.path -> Path sul host, o None. Navidrome puo' salvare il percorso ASSOLUTO visto dal
    container (/music/Artista/Album/x.flac) oppure RELATIVO alla libreria (Artista/Album/x.flac, e'
    il caso con la gestione multi-libreria): si provano entrambi, poi si tolgono i prefissi uno
    alla volta."""
    p = Path(path)
    if p.is_absolute() and p.exists():
        return p
    sp = str(path)
    if ND_MUSIC_ROOT and sp.startswith(ND_MUSIC_ROOT.rstrip('/') + '/'):
        c = LIBRARY_ROOT / sp[len(ND_MUSIC_ROOT.rstrip('/')) + 1:]
        if c.exists():
            return c
    parts = p.parts[1:] if p.is_absolute() else p.parts      # relativo: parte dalla radice libreria
    for i in range(len(parts)):
        c = LIBRARY_ROOT.joinpath(*parts[i:])
        if c.exists():
            return c
    return None


def _nd_table_cols(con, table):
    return {r[1] for r in con.execute(f'PRAGMA table_info({table})')}


def _album_filter(name, artist, album_q, artist_q):
    return ((not album_q or album_q.lower() in (name or '').lower())
            and (not artist_q or artist_q.lower() in (artist or '').lower()))


def _artist_entity_cjk_stem(name):
    """Unisce artista CJK puro alla stessa forma con gloss latino finale."""
    raw = unicodedata.normalize('NFKC', str(name or '')).strip()
    previous = None
    while raw and raw != previous:
        previous = raw
        match = re.search(r'\s*[\(（\[【]([^\)）\]】]+)[\)）\]】]\s*$', raw)
        if not match:
            break
        inner = match.group(1).strip()
        if _has_asian(inner) or not re.search(r'[A-Za-z]', inner):
            break
        raw = raw[:match.start()].strip()
    return norm(raw)


# ===================== fase: fix collab album artist =====================
# Navidrome mostra l'album artist unendo con " • " i VALORI del tag ALBUMARTIST. Se un FLAC ha
# ALBUMARTIST="JPEGMAFIA" e ALBUMARTIST="JPEGMAFIA & Danny Brown" (due valori: uno e' gia'
# contenuto nell'altro) il risultato e' "JPEGMAFIA • JPEGMAFIA & Danny Brown". Si corregge
# lasciando solo i componenti: ["JPEGMAFIA", "Danny Brown"] -> "JPEGMAFIA • Danny Brown".

_COLLAB_SPLIT = re.compile(r'\s+&\s+|\s*;\s*|\s*,\s*|\s+(?:feat\.?|ft\.?|featuring|and|x|\+)\s+', re.I)


def _collab_components(value):
    return [p.strip() for p in _COLLAB_SPLIT.split(value) if p and p.strip()]


def _collab_values(raw_values):
    """Valori distinti: ogni commento ALBUMARTIST, spezzato su ';' e sul joiner di Navidrome."""
    out = []
    for v in raw_values:
        for part in re.split(r'\s*;\s*|' + re.escape(ND_ARTIST_JOINER.strip()), v):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def _collab_target(values):
    """values: valori distinti di ALBUMARTIST. -> lista corretta ["A", "B"] se c'e' un valore
    composto ("A & B") e un altro valore coincide con un suo componente ("A"); altrimenti None
    (niente da correggere: un composto da solo e' un nome di visualizzazione valido)."""
    comps = [_collab_components(v) or [v] for v in values]
    keys = [[norm(c) for c in cs] for cs in comps]
    redundant = any(len(ks) >= 2 and any(j != i and norm(values[j]) in ks for j in range(len(values)))
                    for i, ks in enumerate(keys))
    if not redundant:
        return None
    out, seen = [], set()
    for i in sorted(range(len(values)), key=lambda i: -len(comps[i])):      # prima i composti: ordine giusto
        for c in comps[i]:
            n = norm(c)
            if n and n not in seen:
                seen.add(n)
                out.append(c)
    return out if len(out) >= 2 else None


def _flac_tag_values(path, names):
    """{NOME: [valori...]} dei commenti Vorbis richiesti (tutti i valori, anche ripetuti)."""
    want = {n.upper() for n in names}
    out = {n: [] for n in want}
    for k, v in _flac_raw_tags(path):
        if k in want:
            out[k].append(v)
    return out


def _flac_set_multi(path, tags):
    """tags: {NOME: [valori]}. Sostituisce TUTTI i commenti di quel nome con i valori dati."""
    args = [*METAFLAC]
    for name, vals in tags.items():
        args.append(f'--remove-tag={name}')
        args += [f'--set-tag={name}={v}' for v in vals]
    args.append(str(path))
    subprocess.run(args, capture_output=True, timeout=120, check=True)


def run_fix_collab_artists(apply=False, album=None, artist=None):
    """Vedi il blocco di commento sopra. Dry-run salvo apply. album/artist: filtri a sottostringa."""
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB non trovato: {NAVIDROME_DB}')
        return
    tg = '' if apply else '[dry] '
    joiner = ND_ARTIST_JOINER
    with _nd_db(write=False) as con:
        acols = _nd_table_cols(con, 'album')
        if 'album_artist' not in acols:
            print('[ERRORE] la tabella album non ha la colonna album_artist')
            return
        miss = ' AND (missing IS NULL OR missing = 0)' if 'missing' in acols else ''
        albums = con.execute(f"SELECT id, name, album_artist FROM album WHERE album_artist LIKE ?{miss}",
                             (f'%{joiner}%',)).fetchall()
        mcols = _nd_table_cols(con, 'media_file')
        mmiss = ' AND (missing IS NULL OR missing = 0)' if 'missing' in mcols else ''
        cand = []
        for aid, name, aa in albums:
            if not _album_filter(name, aa, album, artist):
                continue
            if _collab_target([x.strip() for x in aa.split(joiner) if x.strip()]) is None:
                continue                                  # " • " legittimo (due artisti distinti)
            paths = [r[0] for r in con.execute(f'SELECT path FROM media_file WHERE album_id=?{mmiss}', (aid,))]
            cand.append((aid, name, aa, paths))
    print(f"{tg}album con album_artist sospetto (un valore ripete un componente di un altro): {len(cand)}")
    fixed_albums = fixed_files = skipped_fmt = errors = 0
    progress = _ProgressBar('fix_collab_artists', len(cand), 'album')
    for album_index, (aid, name, aa, paths) in enumerate(cand, 1):
        progress.update(album_index)
        files = [(p, _db_to_host(p)) for p in paths]
        missing_on_disk = [p for p, h in files if h is None]
        flacs = [h for p, h in files if h is not None and h.suffix.lower() == '.flac']
        others = [h for p, h in files if h is not None and h.suffix.lower() != '.flac']
        skipped_fmt += len(others)
        per_file = {}
        for f in flacs:
            try:
                per_file[f] = _flac_tag_values(f, ['ALBUMARTIST', 'ALBUMARTISTS'])
            except Exception as e:
                errors += 1
                progress.clear()
                print(f"  [ERRORE] {f.name}: {type(e).__name__}: {e}", file=sys.stderr)
        values = _collab_values([v for t in per_file.values() for v in t['ALBUMARTIST']])
        target = _collab_target(values)
        progress.clear()
        print(f"  '{name}'  (Navidrome: {aa})")
        if missing_on_disk:
            progress.clear()
            print(f"      [!] {len(missing_on_disk)} file del DB non trovati sul disco "
                  f"(imposta ND_MUSIC_ROOT se il prefisso del container non viene riconosciuto), "
                  f"es. {missing_on_disk[0]}")
        if others:
            progress.clear()
            print(f"      [!] {len(others)} file non FLAC (non modificati): "
                  f"{', '.join(sorted({h.suffix.lower() for h in others}))}")
        if not per_file:
            progress.clear()
            print("      nessun FLAC leggibile: niente da fare")
            continue
        if target is None:
            progress.clear()
            print(f"      i tag dei FLAC sono gia' a posto (ALBUMARTIST: {values}): il DB e' "
                  f"indietro, basta uno scan di Navidrome")
            continue
        todo = []
        for f, t in per_file.items():
            if t['ALBUMARTIST'] != target or (t['ALBUMARTISTS'] and t['ALBUMARTISTS'] != target):
                todo.append(f)
        now = Counter(tuple(t['ALBUMARTIST']) for t in per_file.values())
        for combo, n in now.most_common():
            progress.clear()
            print(f"      ALBUMARTIST ora ({n} file): {list(combo)}")
        progress.clear()
        print(f"      -> {target}  ({len(todo)}/{len(per_file)} file da riscrivere)")
        if not apply:
            continue
        ok = 0
        for f in todo:
            tags = {'ALBUMARTIST': target}
            if per_file[f]['ALBUMARTISTS']:               # se c'e' gia', deve combaciare
                tags['ALBUMARTISTS'] = target
            try:
                _flac_set_multi(f, tags)
                ok += 1
            except Exception as e:
                errors += 1
                progress.clear()
                print(f"      [ERRORE] {f.name}: {type(e).__name__}: {e}", file=sys.stderr)
        fixed_files += ok
        fixed_albums += 1 if ok else 0
    progress.close(complete=True)
    if apply:
        print(f"[i] riscritti {fixed_files} FLAC in {fixed_albums} album"
              + (f"; {skipped_fmt} file non FLAC lasciati com'erano" if skipped_fmt else '')
              + (f"; {errors} errori" if errors else '')
              + ("; serve uno scan di Navidrome per vedere il risultato" if fixed_files else ''))
    elif cand:
        print(f"[dry-run] nessun file modificato (usa --apply). "
              + (f"{skipped_fmt} file non FLAC non sarebbero toccati." if skipped_fmt else ''))


# ===================== fase: album incompleti secondo MusicBrainz =====================
# Per ogni album del DB confronta le tracce locali con la tracklist MusicBrainz. Serve a capire se
# il downloader lascia album "bucati" senza segnalarlo: un brano che fallisce e non viene piu'
# ricercato resta mancante per sempre e nessun log lo dice.

MB_BASE = os.environ.get('MB_BASE', 'https://musicbrainz.org/ws/2/')
MB_ALBUMS_CACHE = SCRIPT_DIR / '.mb_albums_cache.json'
_MB_MIN_INTERVAL = 1.1          # MusicBrainz: al massimo ~1 richiesta/secondo
_MB_LAST = [0.0]
_MB_CALLS = [0]


def _mb_get(path, **params):
    """GET su MusicBrainz con rate limit, retry su 429/503. None se 404."""
    url = MB_BASE + path + '?' + urllib.parse.urlencode({'fmt': 'json', **params})
    req = urllib.request.Request(url, headers=MB_USER_AGENT)
    last = None
    for attempt in range(4):
        wait = _MB_MIN_INTERVAL - (time.time() - _MB_LAST[0])
        if wait > 0:
            time.sleep(wait)
        try:
            _MB_CALLS[0] += 1
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            _MB_LAST[0] = time.time()
            return data
        except urllib.error.HTTPError as e:
            _MB_LAST[0] = time.time()
            if e.code == 404:
                return None
            last = e
            if e.code in (429, 503):
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"MusicBrainz non risponde ({last})")


def _mb_load_cache():
    try:
        return json.loads(MB_ALBUMS_CACHE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'release': {}, 'search': {}}


def _mb_save_cache(cache):
    tmp = MB_ALBUMS_CACHE.with_name(MB_ALBUMS_CACHE.name + '.tmp')
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, MB_ALBUMS_CACHE)


def _mb_release(mbid, cache):
    """Tracklist di una release: {'title','count','tracks':[{'disc','n','title'}]} (cache) o None."""
    if mbid in cache['release']:
        return cache['release'][mbid]
    d = _mb_get(f'release/{mbid}', inc='recordings')
    if d is None:
        cache['release'][mbid] = None
        return None
    tracks = []
    for m_ in d.get('media', []):
        for t in m_.get('tracks', []):
            tracks.append({'disc': m_.get('position', 1), 'n': t.get('position'),
                           'title': t.get('title') or (t.get('recording') or {}).get('title', '')})
    rel = {'title': d.get('title', ''), 'count': len(tracks), 'tracks': tracks}
    cache['release'][mbid] = rel
    return rel


def _lucene(s):
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r'\\\1', s)


def _mb_search_release(artist, album, local_n, cache):
    """Release piu' probabile per artista+album (titolo uguale, score alto, n. tracce piu' vicino a
    quelle locali: tra due edizioni preferisce quella che non ha MENO tracce di quelle che
    abbiamo). -> mbid o None."""
    key = f"{norm(artist)}|{norm(album)}"
    if key in cache['search']:
        return cache['search'][key]
    q = f'release:"{_lucene(album)}"' + (f' AND artist:"{_lucene(artist)}"' if artist else '')
    d = _mb_get('release', query=q, limit='8')
    best = None
    want = _trk_key(album)
    cands = []
    for r in (d or {}).get('releases', []):
        if int(r.get('score', 0)) < 90:
            continue
        if difflib.SequenceMatcher(None, _trk_key(r.get('title', '')), want).ratio() < 0.92:
            continue
        n = r.get('track-count') or sum(m_.get('track-count', 0) for m_ in r.get('media', []))
        cands.append((0 if n >= local_n else 1, abs(n - local_n), r['id']))
    if cands:
        best = sorted(cands)[0][2]
    cache['search'][key] = best
    return best


def _trk_key(s):
    """Chiave di confronto dei titoli: NFKC, minuscolo, solo alfanumerici e spazi singoli."""
    return re.sub(r'[\W_]+', ' ', unicodedata.normalize('NFKC', s or '').casefold()).strip()


def _trk_core(s):
    """Come _trk_key ma senza le parentesi ('(feat. X)', '[Remastered]', '- Remastered 2011')."""
    s = re.sub(r'\([^)]*\)|\[[^\]]*\]', ' ', unicodedata.normalize('NFKC', s or ''))
    s = re.sub(r'\s+-\s+.*$', '', s)
    return _trk_key(s)


def _mb_missing(local_titles, mb_tracks):
    """Tracce MusicBrainz senza corrispondente nei titoli locali: [track dict]. Due passate: prima
    i titoli IDENTICI, poi le varianti (senza parentesi, quasi uguali): cosi' 'Intro' e
    'Intro (Reprise)' non si scambiano."""
    pool = [(_trk_key(t), _trk_core(t)) for t in local_titles]
    rest = []
    for t in mb_tracks:
        k = _trk_key(t['title'])
        hit = next((i for i, (lk, _) in enumerate(pool) if lk == k), None)
        if hit is None:
            rest.append(t)
        else:
            pool.pop(hit)
    missing = []
    for t in rest:
        k, c = _trk_key(t['title']), _trk_core(t['title'])
        hit = next((i for i, (lk, lc) in enumerate(pool)
                    if (c and lc == c) or difflib.SequenceMatcher(None, lk, k).ratio() >= 0.88
                    or (c and lc and difflib.SequenceMatcher(None, lc, c).ratio() >= 0.9)), None)
        if hit is None:
            missing.append(t)
        else:
            pool.pop(hit)
    return missing


def run_check_albums(album=None, artist=None, search=True, mbid_only=False,
                     append_missing_report=True):
    """Confronta gli album con MusicBrainz e integra il report completo in mancanti_<data>.txt.

    mbid_only limita il controllo alle release che hanno MUSICBRAINZ_ALBUMID nel DB.
    Il parametro append_missing_report resta per compatibilita' interna; il report e' sempre consolidato.
    """
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB non trovato: {NAVIDROME_DB}', file=sys.stderr)
        return False
    with _nd_db(write=False) as con:
        acols = _nd_table_cols(con, 'album')
        mcols = _nd_table_cols(con, 'media_file')
        amiss = ' AND (missing IS NULL OR missing = 0)' if 'missing' in acols else ''
        mmiss = ' WHERE (missing IS NULL OR missing = 0)' if 'missing' in mcols else ''
        mbcol = 'mbz_album_id' if 'mbz_album_id' in acols else "''"
        albums = con.execute(f"SELECT id, name, album_artist, {mbcol} FROM album WHERE 1=1{amiss}").fetchall()
        local = {}
        for aid, title in con.execute(f"SELECT album_id, title FROM media_file{mmiss}"):
            local.setdefault(aid, []).append(title or '')
    albums = [a for a in albums
              if _album_filter(a[1], a[2], album, artist) and local.get(a[0])
              and (not mbid_only or str(a[3] or '').strip())]
    cache = _mb_load_cache()
    res = []                      # (artista, album, locali, mb_totale, [mancanti], come)
    notfound, errors = [], 0
    calls0 = _MB_CALLS[0]
    n_mbid = n_name = 0
    consec_err = 0
    last_save = _MB_CALLS[0]
    print(f"[i] check-albums: {len(albums)} album da controllare (1 richiesta/s a MusicBrainz, cache: "
          f"{len(cache['release'])} release)", file=sys.stderr)
    progress = _ProgressBar('check-albums MusicBrainz', len(albums), 'album')
    try:
        for i, (aid, name, aa, mbid) in enumerate(albums, 1):
            progress.update(i)
            titles = local[aid]
            how = 'MBID'
            try:
                rel = _mb_release(mbid, cache) if mbid else None
                if rel is None and search:
                    found = _mb_search_release(aa, name, len(titles), cache)
                    rel = _mb_release(found, cache) if found else None
                    how = 'nome'
                elif rel is None:
                    how = None
            except Exception as e:
                errors += 1
                consec_err += 1
                progress.clear()
                print(f"  [warn] {aa} - {name}: {type(e).__name__}: {e}", file=sys.stderr)
                if consec_err >= 3:
                    print("[ERRORE] MusicBrainz non risponde: interrompo il controllo (la cache e' "
                          "salvata, rilancia piu' tardi per riprendere)", file=sys.stderr)
                    break
                continue
            consec_err = 0
            if rel is None or not rel['tracks']:
                notfound.append((aa, name))
                continue
            if how == 'MBID':
                n_mbid += 1
            else:
                n_name += 1
            res.append((aa, name, len(titles), rel['count'], _mb_missing(titles, rel['tracks']), how))
            if _MB_CALLS[0] - last_save >= 25:
                _mb_save_cache(cache)
                last_save = _MB_CALLS[0]
    finally:
        progress.close(complete=(i >= len(albums) if albums else True))
        _mb_save_cache(cache)
    inc = sorted([r for r in res if r[4]], key=lambda r: (-len(r[4]), -len(r[4]) / max(r[3], 1), r[0].lower(), r[1].lower()))
    tot_missing = sum(len(r[4]) for r in inc)
    tot_mb = sum(r[3] for r in res)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    L = [f'# report MusicBrainz - esecuzione {now:%Y-%m-%d %H:%M}',
         f"# ALBUM: {len(albums)} controllati | confrontati {len(res)} (release esatta da MBID: {n_mbid}, "
         f"trovata per nome: {n_name}) | non trovati su MusicBrainz: {len(notfound)}"
         + (f" | errori di rete: {errors}" if errors else ''),
         f"# INCOMPLETI: {_ratio(len(inc), len(res))} album | tracce mancanti {_ratio(tot_missing, tot_mb)} "
         f"(X/Y = mancanti / tracce totali delle release confrontate)",
         "# 'MBID' = release esatta del tag MUSICBRAINZ_ALBUMID; 'nome' = scelta per artista+album "
         "(puo' essere un'edizione diversa: controllare)", '']
    if inc:
        L.append(f"=== ALBUM CON TRACCE MANCANTI ({len(inc)}) ===")
        for aa, name, nloc, ntot, miss, how in inc:
            L.append(f"{aa} - {name}   mancano {_ratio(len(miss), ntot)}  [{how}]")
            for t in miss:
                L.append(f"    - {t['disc']}-{t['n']}  {t['title']}")
        L.append('')
        L.append("=== ELENCO DA RISCARICARE (Artista - Album - Titolo) ===")
        for aa, name, nloc, ntot, miss, how in inc:
            for t in miss:
                L.append(f"{aa} - {name} - {t['title']}")
        L.append('')
    else:
        L.append('(nessun album incompleto tra quelli confrontati)')
        L.append('')
    if notfound:
        L.append(f"=== NON TROVATI SU MUSICBRAINZ ({len(notfound)}) ===")
        L += [f"{a} - {b}" for a, b in sorted(notfound, key=lambda x: (x[0].lower(), x[1].lower()))]

    # Un solo report canonico: sostituisce l'eventuale precedente se rieseguito lo stesso giorno,
    # e non crea album_incompleti_<data>.txt separati. La parte playlist in cima resta intatta.
    missing_path = LOG_DIR / f'mancanti_{now:%Y-%m-%d}.txt'
    marker_start = '===== INIZIO REPORT COMPLETO MUSICBRAINZ ====='
    marker_end = '===== FINE REPORT COMPLETO MUSICBRAINZ ====='
    try:
        existing = missing_path.read_text(encoding='utf-8', errors='replace') if missing_path.exists() else ''
    except OSError:
        existing = ''
    old_start = existing.find(marker_start)
    if old_start >= 0:
        old_end = existing.find(marker_end, old_start)
        if old_end >= 0:
            existing = (existing[:old_start] + existing[old_end + len(marker_end):]).rstrip()
        else:
            # Blocco vecchio incompleto: elimina il suffisso troncato prima di aggiungere
            # il report nuovo, invece di concatenare due versioni parziali.
            existing = existing[:old_start].rstrip()
    else:
        # Migrazione senza duplicati del vecchio suffisso sintetico prodotto da v0.68-v0.70.
        legacy_start = existing.find('=== TRACCE MANCANTI SECONDO MUSICBRAINZ ')
        if legacy_start >= 0:
            existing = existing[:legacy_start].rstrip()
    block = '\n'.join([marker_start, *L, marker_end])
    combined = (existing.rstrip() + '\n\n' if existing.strip() else
                f'# Report MusicBrainz creato dal controllo album\n\n') + block + '\n'
    missing_path.write_text(combined, encoding='utf-8')
    print(f"[i] album MusicBrainz: {_ratio(len(inc), len(res))} incompleti | "
          f"tracce mancanti {_ratio(tot_missing, tot_mb)} | non trovati: {len(notfound)} "
          f"-> report completo integrato in {missing_path}")
    for aa, name, nloc, ntot, miss, how in inc[:10]:
        print(f"    {aa} - {name}: mancano {_ratio(len(miss), ntot)} [{how}]")
    return errors == 0


# ===================== fase: clean empty albums =====================
# (da clean_empty_albums.py — rimuove cartelle senza audio vuote da >24h)

CLEAN_MARKER = '.ndempty'
CLEAN_MAX_AGE = 24 * 3600


def run_clean_empty(dry_run=False, base=None):
    base = Path(base) if base else LIBRARY_ROOT
    base_key = os.path.normpath(str(base))
    now = time.time()
    removed = marked = waiting = unmarked = 0
    contains_audio = {}
    # In os.walk bottom-up, ogni cartella eredita il risultato dei soli figli diretti.
    # Evita chiamare d.rglob('*') per OGNI cartella, che moltiplicava il costo su librerie
    # con tanti livelli artista/album/disco. Materializzare le entry permette una % attendibile
    # senza fare una seconda visita dell'intero filesystem.
    walk_rows = list(os.walk(base, topdown=False))
    progress = _ProgressBar('clean_empty', len(walk_rows), 'cartelle')
    for walk_index, (root, dirs, files) in enumerate(walk_rows, 1):
        progress.update(walk_index)
        root_key = os.path.normpath(root)
        has_audio = any(
            os.path.splitext(name)[1].lower() in INDEX_EXT and
            os.path.isfile(os.path.join(root, name))
            for name in files
        )
        if not has_audio:
            has_audio = any(
                contains_audio.get(os.path.normpath(os.path.join(root, child)), False)
                for child in dirs
            )
        contains_audio[root_key] = has_audio

        d = Path(root)
        if root_key == base_key or d.name.startswith('.'):
            continue
        rel = d.relative_to(base)
        if rel.parts and rel.parts[0].lower() == 'playlists':
            continue
        if has_audio:
            mk = d / CLEAN_MARKER
            if mk.exists():
                if not dry_run:
                    mk.unlink()
                unmarked += 1
            continue
        mk = d / CLEAN_MARKER
        if not mk.exists():
            if not dry_run:
                mk.write_text(str(now))
                marked += 1
            age = 0
        else:
            age = now - mk.stat().st_mtime
        if age > CLEAN_MAX_AGE:
            progress.clear()
            print(f"{'[dry] ' if dry_run else ''}RIMUOVO {rel} (vuota da {int(age // 3600)}h)")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            removed += 1
        else:
            waiting += 1
    progress.close(complete=True)
    conflicts = 0
    conflict_files = [cf for cf in base.rglob('*.sync-conflict-*') if cf.is_file()]
    conflict_progress = _ProgressBar('clean_empty conflitti', len(conflict_files), 'file')
    for conflict_index, cf in enumerate(conflict_files, 1):
        conflict_progress.update(conflict_index)
        if cf.is_file():
            conflict_progress.clear()
            print(f"{'[dry] ' if dry_run else ''}RIMUOVO conflitto syncthing: {cf.name}")
            if not dry_run:
                try:
                    cf.unlink()
                    conflicts += 1
                except Exception:
                    pass
    conflict_progress.close(complete=True)
    print(f'marcate: {marked} | in attesa (<24h): {waiting} | rimosse: {removed} '
          f'| sbloccate: {unmarked} | conflitti syncthing: {conflicts}')

# ===================== fase: dedupe releases =====================
# (da dedupe_releases.py — unifica release duplicate: duplicati nel cestino,
# bonus spostate nella release canonica = la piu' vecchia)

DEDUPE_TRASH = Path('/homelab/arr-config/dedupe_trash')
try:
    import numpy as np
    _HAS_NP = True
except Exception:
    _HAS_NP = False

_ALBUM_EDITION_QUALIFIER = re.compile(
    r'\b(?:19|20)\d{2}\b|\b(?:remaster(?:ed)?|deluxe|anniversary|'
    r'special edition|limited edition|expanded edition|reissue|bonus tracks?|'
    r'demo(?:s)?|live version|live recording|mono|stereo)\b', re.I)
_ALBUM_TRAILING_QUALIFIERS = re.compile(
    r'(?:\s+|^)(?:(?:19|20)\d{2}|remaster(?:ed)?|deluxe|anniversary|'
    r'edition|version|reissue|expanded|bonus|single|ep|demo(?:s)?|live|'
    r'mono|stereo)(?:\s+(?:edition|version|remaster(?:ed)?|deluxe|'
    r'anniversary|expanded|bonus|tracks?))*$', re.I)


def _album_identity_text(name: str) -> str:
    """Remove only edition annotations; preserve meaningful parenthetical title text."""
    raw = unicodedata.normalize('NFKC', str(name or '')).strip()

    def replace_bracket(match):
        inside = next((g for g in match.groups() if g is not None), '')
        prefix = raw[:match.start()]
        # Release/remaster annotations are safe to ignore for duplicate grouping.
        if _ALBUM_EDITION_QUALIFIER.search(inside):
            return ' '
        # CJK title with an English/romaji gloss: the gloss is an alias, not a second title.
        if _has_asian(prefix) and re.search(r'[A-Za-z]', inside) and not _has_asian(inside):
            return ' '
        # Keep semantic parentheses such as (Part II), (Drank), or (Soundtrack).
        return ' ' + inside + ' '

    raw = re.sub(r'\(([^()]*)\)|\[([^\[\]]*)\]|\{([^{}]*)\}', replace_bracket, raw)
    return raw


def album_base(name: str) -> str:
    """Conservative album identity: ignores edition suffixes/years and CJK glosses.

    Unlike norm(), this does not discard all parenthetical words or remove the word
    'live' from the middle of a meaningful title such as 'Blackbox Live Recorder'.
    """
    original = norm_bare(_album_identity_text(name))
    s = re.sub(r'\b(?:19|20)\d{2}\b', ' ', original)
    # Strip only edition markers at the tail; don't rewrite words in the title body.
    previous = None
    while s and s != previous:
        previous = s
        s = _ALBUM_TRAILING_QUALIFIERS.sub('', s).strip()
    # Do not turn legitimate titles consisting only of a year/qualifier into an empty key.
    if not s.strip():
        s = original
    return re.sub(r'\s+', ' ', s).strip()


def _album_title_keys(value: str):
    """Chiavi identita' album: title normalizzato, alias curati e fonetica CJK offline.

    Non interroga il traduttore automatico durante il grouping, per evitare richieste di rete
    dentro un'operazione di manutenzione che deve essere ripetibile.
    """
    raw = str(value or '').strip()
    if not raw:
        return set()
    cleaned = album_base(raw)
    keys = {norm_bare(cleaned)}
    # NAME_TRANSLATIONS / NAME_FIXES in entrambe le direzioni.
    for candidate in (_preferred_name_for_key(norm(cleaned)),):
        if candidate:
            keys.add(norm_bare(album_base(candidate)))
    reverse = _name_fixes_rev()
    for alias in reverse.get(norm(cleaned), set()):
        keys.add(norm_bare(album_base(alias)))
    # Una traduzione automatica gia' cacheata puo' collegare titoli CJK e inglesi senza
    # generare richieste di rete durante l'analisi o la manutenzione album.
    if _AUTO_TRANSLATABLE_RE.search(raw):
        try:
            entry = _auto_translation_cache_load().get(norm(raw))
            if isinstance(entry, dict):
                age = int(time.time()) - int(entry.get('checked_at') or 0)
                ttl = int(AUTO_NAME_TRANSLATION_CONFIG.get('cache_days', 365)) * 86400
                confidence = float(entry.get('confidence') or 0)
                if age <= ttl and confidence >= float(AUTO_NAME_TRANSLATION_CONFIG.get('min_confidence', 0.72)):
                    cached_translation = str(entry.get('translation') or '')
                    if cached_translation:
                        keys.add(norm_bare(album_base(cached_translation)))
        except Exception:
            pass
    # Alias fonetico solo come chiave secondaria, non come valore da scrivere.
    if _has_asian(raw):
        phonetic = _phonetic_kakasi(cleaned)
        if not phonetic and _HANGUL.search(cleaned) and callable(_HANGUL_FN):
            try:
                phonetic = norm(_HANGUL_FN(cleaned))
            except Exception:
                phonetic = ''
        if phonetic:
            keys.add(norm_bare(album_base(phonetic)))
    return {k for k in keys if k and len(k) >= 2}


def _album_title_similarity(keys_a, keys_b):
    exact = set(keys_a) & set(keys_b)
    if exact:
        return 1.0, next(iter(exact))
    best = (0.0, '')
    for a in keys_a:
        for b in keys_b:
            if min(len(a), len(b)) < 7:
                continue
            score = difflib.SequenceMatcher(None, a, b).ratio()
            if score > best[0]:
                best = (score, f'{a} ~ {b}')
    return best


def _artist_identity_keys(value):
    keys = set(_artist_variants(value))
    if value:
        keys.add(norm(value))
    return {k for k in keys if k}


def _album_root_for_file(base: Path, f: Path):
    """Identifica Artist/Album come radice logica anche per Artist/Album/CD1/track.flac."""
    try:
        parts = f.relative_to(base).parts
    except ValueError:
        return f.parent
    if len(parts) >= 3:
        return base / parts[0] / parts[1]
    if len(parts) >= 2:
        return base / parts[0]
    return f.parent


def _audio_files(folder: Path):
    """Return audio paths in deterministic order using the shared scandir walker.

    Path.rglob()+is_file() recursively restatted every entry and was called once per
    album in dedupe_releases/dedupe_tracks, making a cold NAS run repeatedly traverse
    the same tree. _walk_audio performs one scandir pass per directory and sorts once.
    """
    folder = Path(folder)
    return [folder.joinpath(*parts) for parts in _walk_audio(folder, AUDIO_EXT)]


def folder_year(folder: Path, files) -> int:
    years = []
    for f in files[:60]:
        tags, _ = probe_dur(f)
        d = (tags.get('date') or '')[:4]
        if d.isdigit():
            years.append(int(d))
    m = re.search(r'\b(19|20)\d{2}\b', folder.name)
    if m:
        years.append(int(m.group(0)))
    return min(years) if years else 9999


def best_title(f: Path, tags: dict) -> str:
    t = (tags.get('title') or '').strip()
    if t:
        return t
    stem = f.stem.strip()
    stem = re.sub(r'^\d{1,3}\s*[-._:]\s*', '', stem)
    parts = stem.split(' - ')
    return parts[-1] if len(parts) > 1 and parts[-1] else stem


def fingerprint(path: Path, seconds=25, rate=11025):
    if not _HAS_NP:
        return None
    try:
        r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path),
                            '-af', 'silenceremove=start_periods=1:start_threshold=-45dB',
                            '-t', str(seconds), '-ac', '1', '-ar', str(rate),
                            '-f', 's16le', '-'],
                           capture_output=True, timeout=180)
        if not r.stdout:
            return None
        x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float64)
        return x if len(x) >= rate * 5 else None   # minimo ~5s: tracce piu' corte = no fp
    except Exception:
        return None


def _shift_corr(x, y, n, s, min_len, x_sq_cum=None, y_sq_cum=None):
    """Correlazione normalizzata di finestre traslate.

    Le somme cumulative dei quadrati permettono di ottenere le norme delle finestre in O(1),
    invece di rileggere entrambi i vettori per ogni offset. Il prodotto scalare resta esatto.
    """
    if s >= 0:
        u, v = x[:n - s], y[s:]
        if x_sq_cum is not None and y_sq_cum is not None:
            nx2 = x_sq_cum[n - s] - x_sq_cum[0]
            ny2 = y_sq_cum[n] - y_sq_cum[s]
    else:
        u, v = x[-s:], y[:n + s]
        if x_sq_cum is not None and y_sq_cum is not None:
            nx2 = x_sq_cum[n] - x_sq_cum[-s]
            ny2 = y_sq_cum[n + s] - y_sq_cum[0]
    if len(u) < min_len:
        return None
    if x_sq_cum is None or y_sq_cum is None:
        denom = np.linalg.norm(u) * np.linalg.norm(v) + 1e-9
    else:
        denom = np.sqrt(max(0.0, float(nx2))) * np.sqrt(max(0.0, float(ny2))) + 1e-9
    # abs: una copia a polarita' invertita e' identica al 100%.
    return abs(float(np.dot(u, v) / denom))


def _aligned_corr(x, y, n, rate, stop_at=None):
    """Cerca l'offset con due griglie; le norme per ogni finestra sono O(1).

    In modalita' soglia controlla offset zero per primo: e' il caso comune per copie
    della stessa incisione e puo' evitare l'intera scansione grossolana. Il percorso
    completo continua a calcolare lo stesso massimo sulla griglia gia' usata prima.
    """
    step_c = rate // 10
    step_f = max(1, rate // 200)
    x_sq_cum = np.concatenate(([0.0], np.cumsum(x * x, dtype=np.float64)))
    y_sq_cum = np.concatenate(([0.0], np.cumsum(y * y, dtype=np.float64)))

    c0 = _shift_corr(x, y, n, 0, rate * 5, x_sq_cum, y_sq_cum)
    best, s0 = (c0 or 0.0), 0
    if stop_at is not None and best >= stop_at:
        return best

    # Prima gli offset vicini, per trovare prima eventuali copie con piccolo delay.
    coarse_offsets = sorted(range(-rate, rate + 1, step_c), key=lambda off: (abs(off), off))
    for s in coarse_offsets:
        if s == 0:  # Gia' verificato sopra.
            continue
        c = _shift_corr(x, y, n, s, rate * 5, x_sq_cum, y_sq_cum)
        if c is not None and c > best:
            best, s0 = c, s
            if stop_at is not None and best >= stop_at:
                return best
    cand = set(range(s0 - step_c, s0 + step_c + 1, step_f))
    cand.add(s0)
    cand.discard(0)  # Gia' verificato sopra.
    for s in sorted(cand):
        c = _shift_corr(x, y, n, s, rate * 5, x_sq_cum, y_sq_cum)
        if c is not None and c > best:
            best = c
            if stop_at is not None and best >= stop_at:
                return best
    return best

def correlate(x, y, rate=11025, stop_at=None):
    """Massima correlazione di Pearson, o early-exit se stop_at basta a decidere.
    - offset temporale (due passaggi, fino a 5ms di precisione: copre il
      delay di codifica MP3 ~26ms e i pregaps)
    - velocita' diversa: se i due file girano a velocita' leggermente
      diversa (resample, master diverso), l'offset cresce nel tempo e
      de-correla tutto. In tal caso prova rapporti 0.98-1.02 (warpping
      lineare) e prende il migliore.
    Ritorna il punteggio (0.0-1.0) o None se non confrontabili."""
    if x is None or y is None:
        return None
    n = min(len(x), len(y))
    if n < rate * 5:
        return None
    x, y = x[:n].astype(np.float64), y[:n].astype(np.float64)
    x -= x.mean()
    y -= y.mean()
    if np.linalg.norm(x) == 0 or np.linalg.norm(y) == 0:
        return None
    best = _aligned_corr(x, y, n, rate, stop_at=stop_at)
    if stop_at is not None and best >= stop_at:
        return best
    if best >= 0.98:
        return best
    # ricerca velocita' a due risoluzioni: y[i] ~ x[i*r] per qualche r vicino a 1.
    # Primo giro 0.96-1.04 a 0.005; se ancora basso, raffino intorno al migliore.
    best_r = None
    for r in np.arange(0.96, 1.0401, 0.005):
        m = min(n, int(len(y) / r) - 1)
        if m < rate * 5:
            continue
        yy = np.interp(np.arange(m) * r, np.arange(len(y)), y)
        c = _aligned_corr(x[:m], yy, m, rate, stop_at=stop_at)
        if c > best:
            best, best_r = c, r
        if stop_at is not None and best >= stop_at:
            return best
    if best < 0.95 and best_r is not None:
        for r in np.arange(best_r - 0.005, best_r + 0.0051, 0.001):
            m = min(n, int(len(y) / r) - 1)
            if m < rate * 5:
                continue
            yy = np.interp(np.arange(m) * r, np.arange(len(y)), y)
            c = _aligned_corr(x[:m], yy, m, rate, stop_at=stop_at)
            if c > best:
                best = c
            if stop_at is not None and best >= stop_at:
                return best
    return best


def _dur_compatible(dk, df, max_diff=10.0) -> bool:
    """Durate plausibilmente dello stesso brano: differenza assoluta entro
    max_diff secondi OPPURE entro il 5% relativo (copre sia i pezzi brevi
    sia i lunghi). Se una durata manca, non vincolare."""
    if not dk or not df:
        return True
    diff = abs(dk - df)
    return diff <= max_diff or diff / max(dk, df) <= 0.05


def same_recording(x, y, rate=11025, threshold=0.95) -> bool:
    c = correlate(x, y, rate, stop_at=threshold)
    return c is not None and c >= threshold


def _move_to_trash(f: Path, stamp: str, hard: bool, base: Path):
    if hard:
        f.unlink()
        f.with_suffix('.lrc').unlink(missing_ok=True)
        return
    dest = DEDUPE_TRASH / stamp / f.relative_to(base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(f), str(dest))
    lrc = f.with_suffix('.lrc')
    if lrc.exists():
        shutil.move(str(lrc), str(dest.with_suffix('.lrc')))


def _set_tracknumber(path: Path, n: int):
    if path.suffix.lower() == '.flac':
        _metaflac_run('--remove-tag=TRACKNUMBER', f'--set-tag=TRACKNUMBER={n}', path=path)
    else:
        tmp = path.with_name(path.stem + '.tmp' + path.suffix)
        try:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(path),
                            '-map', '0', '-codec', 'copy',
                            '-metadata', f'track={n}', str(tmp)],
                           capture_output=True, timeout=600, check=True)
            os.replace(tmp, path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise


def _fp_cached(cache, path):
    """fingerprint con cache locale: prima ogni file canonico veniva ri-decodificato
    con ffmpeg per OGNI candidato (N x M esecuzioni di ffmpeg per album)."""
    if path not in cache:
        cache[path] = fingerprint(path)
    return cache[path]


def _max_tracknum(files) -> int:
    """Numero di traccia piu' alto dell'album. Guarda il prefisso del NOME FILE e il TAG
    TRACKNUMBER: con i nomi 'Titolo - Album - Artista' (Lidarr/spotyFLAC) il nome non ha
    numeri, il risultato era 0 e la bonus track diventava '01' (anche nel tag), in
    conflitto con la vera traccia 1 (Bowie / Ziggy Stardust)."""
    best = 0
    for f in files:
        m = re.match(r'^(\d{1,3})\s*[-._ ]', f.name)
        if m:
            best = max(best, int(m.group(1)))
        tg = probe_dur(f)[0]
        m2 = re.match(r'\s*(\d{1,3})', tg.get('track') or tg.get('tracknumber') or '')
        if m2:
            best = max(best, int(m2.group(1)))
    return best


def run_dedupe_releases(apply=False, hard_delete=False, artist=None, base=None,
                        corr=0.95, max_dur=10.0):
    base = Path(base) if base else LIBRARY_ROOT
    print(f"waveform compare: {'ATTIVO' if _HAS_NP else 'DISATTIVO (solo titoli+durata)'}")
    print(f"modo: {'APPLY' if apply else 'DRY-RUN'}{' (hard delete!)' if hard_delete else ''}")

    stamp = time.strftime('%Y%m%d_%H%M%S')
    n_groups = n_dup = n_bonus = errors = 0
    skip = SKIP_TOP | {'.git'}

    artists = sorted(d for d in base.iterdir()
                     if d.is_dir() and d.name.lower() not in skip
                     and not d.name.startswith('.'))
    if artist:
        artists = [a for a in artists if norm(a.name) == norm(artist)]
        if not artists:
            print(f"[ERRORE] artista '{artist}' non trovato in {base}")
            return

    progress = _ProgressBar('dedupe_releases', len(artists), 'artisti')
    for artist_index, art in enumerate(artists, 1):
        progress.update(artist_index)
        # First group only by folder names. The old order scanned every album's files
        # before discovering that its normalized title was unique; the supplied run spent
        # 2m40 in this phase while finding zero release groups. Walk audio files only for
        # names that actually have a possible release counterpart.
        album_dirs_by_base = {}
        for album in sorted(art.iterdir()):
            if not album.is_dir():
                continue
            b = album_base(album.name)
            if b:
                album_dirs_by_base.setdefault(b, []).append(album)

        groups = {}
        for b, album_dirs in album_dirs_by_base.items():
            if len(album_dirs) < 2:
                continue
            releases = []
            for album in album_dirs:
                files = _audio_files(album)
                if files:
                    releases.append((album, files))
            if len(releases) >= 2:
                groups[b] = releases

        for b, releases in groups.items():
            if len(releases) < 2:
                continue
            n_groups += 1
            releases.sort(key=lambda r: (folder_year(r[0], r[1]), r[0].name))
            canonical = releases[0]
            others = releases[1:]
            progress.clear()
            print(f"\n=== {art.name} / [{b}] ===")
            progress.clear()
            print(f"    CANONICA : {canonical[0].name} "
                  f"({len(canonical[1])} tracce, anno {folder_year(canonical[0], canonical[1])})")
            for al, fl in others:
                progress.clear()
                print(f"    duplicata: {al.name} ({len(fl)} tracce, anno {folder_year(al, fl)})")

            c_strict, c_norm, c_meta = {}, {}, {}
            for f in canonical[1]:
                tags, dur = probe_dur(f)
                c_meta[f] = (tags, dur)
                c_strict.setdefault(norm_bare(best_title(f, tags)), f)
                c_norm.setdefault(norm(best_title(f, tags)), []).append(f)

            canon_files = list(canonical[1])
            next_num = _max_tracknum(canon_files)
            fp_cache = {}
            progress.clear()
            prefetch_probe([f for _, fl in releases for f in fl], 'dedupe')

            for al, fl in others:
                for f in fl:
                    tags, dur = probe_dur(f)
                    title_full = norm_bare(best_title(f, tags))
                    title_norm = norm(best_title(f, tags))
                    match = why = None
                    if title_full in c_strict:
                        match, why = c_strict[title_full], 'titolo esatto'
                    elif title_norm in c_norm:
                        match, why = c_norm[title_norm][0], 'titolo normalizzato'
                    elif _HAS_NP and dur:
                        fp = fingerprint(f)
                        for cf in canon_files:
                            _, cdur = c_meta[cf]
                            if not _dur_compatible(cdur, dur, max_dur):
                                continue
                            if same_recording(fp, _fp_cached(fp_cache, cf), threshold=corr):
                                match, why = cf, 'waveform'
                                break
                    if match:
                        n_dup += 1
                        progress.clear()
                        print(f"    {'[dry] ' if not apply else ''}DUPE  {al.name}/"
                              f"{f.name} == {match.parent.name}/{match.name} ({why})")
                        if apply:
                            try:
                                _move_to_trash(f, stamp, hard_delete, base)
                            except Exception as e:
                                errors += 1
                                progress.clear()
                                print(f"    ERRORE spostamento {f}: {e}", file=sys.stderr)
                    else:
                        n_bonus += 1
                        next_num += 1
                        clean_name = re.sub(r'^\d{1,3}\s*[-._ ]\s*', '', f.name)
                        newname = f"{next_num:02d} - {clean_name}"
                        progress.clear()
                        print(f"    {'[dry] ' if not apply else ''}BONUS {al.name}/"
                              f"{f.name} -> {canonical[0].name}/{newname}")
                        if apply:
                            try:
                                dest = canonical[0] / newname
                                shutil.move(str(f), str(dest))
                                lrc = f.with_suffix('.lrc')
                                if lrc.exists():
                                    shutil.move(str(lrc), str(dest.with_suffix('.lrc')))
                                try:
                                    _set_tracknumber(dest, next_num)
                                except Exception as e:
                                    progress.clear()
                                    print(f"    [warn] tracknumber non scritto "
                                          f"su {dest}: {e}", file=sys.stderr)
                                canon_files.append(dest)
                                c_meta[dest] = probe_dur(dest)
                            except Exception as e:
                                errors += 1
                                progress.clear()
                                print(f"    ERRORE spostamento bonus {f}: {e}",
                                      file=sys.stderr)

    progress.close(complete=True)

    print(f"\ngruppi release: {n_groups} | duplicati: {n_dup} | "
          f"bonus spostate: {n_bonus} | errori: {errors}")
    if apply and not hard_delete:
        print(f"[i] duplicati nel cestino: {DEDUPE_TRASH / stamp}")
    if apply:
        print("[i] dopo verifica: scan rapido su Navidrome, poi svuota il cestino.")


def _album_candidate_pairs(albums):
    """Return unique album-index pairs which share at least one artist identity.

    An inverted index avoids comparing every album in the library against every other album.
    The resulting pairs are sorted so diagnostic reports remain deterministic across runs.
    """
    indices_by_artist = {}
    for idx, album in enumerate(albums):
        for artist_key in album.get('artist_keys', ()):
            if artist_key:
                indices_by_artist.setdefault(artist_key, []).append(idx)
    candidate_pairs = set()
    for indices in indices_by_artist.values():
        if len(indices) < 2:
            continue
        for pos, left in enumerate(indices[:-1]):
            for right in indices[pos + 1:]:
                candidate_pairs.add((left, right) if left < right else (right, left))
    return sorted(candidate_pairs)


def _cleanup_standalone_album_reports():
    """Rimuove i sidecar diagnostici delle vecchie versioni dopo aver consolidato i report in e2m."""
    removed = 0
    for pattern in ('album_db_diagnostics_*.txt', 'album_cross_folder_review_*.txt'):
        for report_path in LOG_DIR.glob(pattern):
            try:
                report_path.unlink(missing_ok=True)
                removed += 1
            except OSError as e:
                print(f'[warn] impossibile eliminare il vecchio report autonomo {report_path}: {e}',
                      file=sys.stderr)
    if removed:
        print(f'[i] rimossi {removed} vecchi report album autonomi; conservarli solo nei log e2m')
    return removed


def run_diagnose_album_splits(album_filter=None, artist_filter=None):
    """Legge soltanto il DB Navidrome e incorpora in e2m un rapporto su album/artisti divisi.

    Il rapporto include ID, titoli, artisti, MBID, conteggi tracce e percorsi di esempio.
    Serve a verificare sul server i casi reali prima di applicare una riparazione dei tag.
    """
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB Navidrome non trovato: {NAVIDROME_DB}. '
              'Esegui questa diagnostica sul server che ospita Navidrome.')
        return False
    lines = [f'Navidrome album/artist diagnostic — {time.strftime("%Y-%m-%d %H:%M:%S")}',
             f'Database: {NAVIDROME_DB}', '']
    with _nd_db(write=False) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        acols = _nd_table_cols(con, 'album')
        mcols = _nd_table_cols(con, 'media_file')
        required_album = {'id', 'name', 'album_artist'}
        required_media = {'album_id'}
        if not required_album <= acols or not required_media <= mcols:
            print(f'[ERRORE] schema DB non riconosciuto: album={sorted(acols)} media_file={sorted(mcols)}')
            return False
        mbid_col = 'mbz_album_id' if 'mbz_album_id' in acols else None
        artist_id_col = next((c for c in ('album_artist_id', 'albumartist_id', 'artist_id') if c in acols), None)
        version_col = next((c for c in ('album_version', 'albumversion', 'version') if c in acols), None)
        release_date_col = next((c for c in ('release_date', 'releasedate', 'releaseDate') if c in acols), None)
        rgid_col = next((c for c in ('mbz_release_group_id', 'mbz_releasegroup_id', 'mbz_release_groupid') if c in acols), None)
        extra_cols = (mbid_col, artist_id_col, version_col, release_date_col, rgid_col)
        extra_exprs = [f'"{col}"' if col else "''" for col in extra_cols]
        missing_filter = ' WHERE (missing IS NULL OR missing=0)' if 'missing' in acols else ''
        album_rows = con.execute(
            f'SELECT id, name, album_artist, {", ".join(extra_exprs)} FROM album{missing_filter}'
        ).fetchall()
        m_missing = ' WHERE (missing IS NULL OR missing=0)' if 'missing' in mcols else ''
        m_fields = ['album_id']
        if 'path' in mcols: m_fields.append('path')
        if 'title' in mcols: m_fields.append('title')
        media_rows = con.execute(f"SELECT {', '.join(m_fields)} FROM media_file{m_missing}").fetchall()
        details = {}
        for row in media_rows:
            aid = row[0]
            item = details.setdefault(aid, {'count': 0, 'paths': [], 'titles': []})
            item['count'] += 1
            if 'path' in m_fields and row[m_fields.index('path')]:
                item['paths'].append(row[m_fields.index('path')])
            if 'title' in m_fields and row[m_fields.index('title')]:
                item['titles'].append(row[m_fields.index('title')])
        albums = []
        for album_row in album_rows:
            aid, name, artist, mbid, artist_db_id, album_version, release_date, release_group_id = album_row
            detail = details.get(aid)
            if not detail or not _album_filter(name, artist, album_filter, artist_filter):
                continue
            keys = _album_title_keys(name)
            albums.append({'id': aid, 'name': name or '', 'artist': artist or '',
                           'mbid': mbid or '', 'artist_db_id': artist_db_id or '',
                           'album_version': album_version or '', 'release_date': release_date or '',
                           'release_group_id': release_group_id or '',
                           'count': detail['count'], 'paths': detail['paths'],
                           'titles': detail['titles'], 'keys': keys,
                           'artist_keys': _artist_identity_keys(artist or '')})

        # Pairwise duplicate candidates. Exact aliases are strongest; fuzzy title matches are
        # reported as REVIEW only and never used to edit files automatically by this command.
        parent = list(range(len(albums)))
        pair_reason = {}
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        def union(i, j):
            x, y = find(i), find(j)
            if x != y: parent[y] = x
        # Only compare albums sharing at least one artist identity. Fuzzy candidates are
        # still review-only, and the helper returns deterministic pair order for stable reports.
        fuzzy = []
        candidate_pairs = _album_candidate_pairs(albums)
        progress = _ProgressBar('diagnosi split album', len(candidate_pairs), 'coppie')
        for pair_index, (i, j) in enumerate(candidate_pairs, 1):
            progress.update(pair_index)
            a, b = albums[i], albums[j]
            sim, label = _album_title_similarity(a['keys'], b['keys'])
            edition_a = _album_explicit_edition_markers([a['name']])
            edition_b = _album_explicit_edition_markers([b['name']])
            edition_conflict = (edition_a != edition_b and bool(edition_a or edition_b))
            version_a = str(a.get('album_version') or '').strip().casefold()
            version_b = str(b.get('album_version') or '').strip().casefold()
            version_conflict = version_a != version_b and bool(version_a or version_b)
            if edition_conflict or version_conflict:
                reason = ('explicit edition qualifier differs' if edition_conflict
                          else f'ALBUMVERSION differs: {version_a!r} vs {version_b!r}')
                fuzzy.append((i, j, sim, reason))
            elif sim >= 0.999:
                union(i, j)
                pair_reason[(i,j)] = ('SAME IDENTITY KEY', sim, label)
            elif sim >= 0.88:
                fuzzy.append((i,j,sim,label))
        progress.close(complete=True)
        groups = {}
        for i,a in enumerate(albums): groups.setdefault(find(i), []).append(i)
        duplicate_groups = [g for g in groups.values() if len(g) > 1]
        lines.append(f'ALBUM DUPLICATE GROUPS (exact/known alias): {len(duplicate_groups)}')
        for ix, group in enumerate(sorted(duplicate_groups, key=lambda g: (albums[g[0]]['artist'].casefold(), albums[g[0]]['name'].casefold())), 1):
            lines.append(f'\n[{ix}] artist family: {albums[group[0]]["artist"]!r}')
            for i in group:
                a = albums[i]
                paths = a['paths'][:3]
                reason = next((pair_reason[k][0] for k in pair_reason if i in k and k[0] in group and k[1] in group), 'shared title alias')
                lines.append(f'  album.id={a["id"]!r} tracks={a["count"]} name={a["name"]!r} '
                             f'album_artist={a["artist"]!r} album_artist_db_id={a["artist_db_id"]!r} '
                             f'mbid={a["mbid"]!r} release_group_id={a["release_group_id"]!r} '
                             f'album_version={a["album_version"]!r} release_date={a["release_date"]!r} [{reason}]')
                lines.extend(f'    path: {x}' for x in paths)
        # An album MBID reused across visibly different DB album names can force a bad merge.
        by_mbid = {}
        for a in albums:
            if a['mbid']:
                by_mbid.setdefault(a['mbid'].strip().lower(), []).append(a)
        reused_mbids = []
        for mbid, rows in by_mbid.items():
            distinct = {(norm_bare(row['name']), norm_bare(row['artist'])) for row in rows}
            if len(rows) > 1 and len(distinct) > 1:
                reused_mbids.append((mbid, rows))
        lines.append(f'\nMBID REUSED ACROSS DIFFERENT ALBUM/ARTIST LABELS: {len(reused_mbids)}')
        for mbid, rows in sorted(reused_mbids, key=lambda item: item[0]):
            lines.append(f'  MBID={mbid!r}')
            for row in rows:
                lines.append(f"    id={row['id']!r} artist={row['artist']!r} album={row['name']!r} tracks={row['count']}")
                lines.extend(f"      path: {path}" for path in row['paths'][:2])

        lines.append(f'\nFUZZY TITLE CANDIDATES (review only): {len(fuzzy)}')
        for i,j,sim,label in sorted(fuzzy, key=lambda x: -x[2]):
            a,b=albums[i],albums[j]
            lines.append(f'  score={sim:.3f} {a["artist"]!r}: {a["name"]!r} '
                         f'(id={a["id"]!r}, {a["count"]} tracks) <-> {b["name"]!r} '
                         f'(id={b["id"]!r}, {b["count"]} tracks) [{label}]')

        # Inspect actual artist entities if this Navidrome version has an artist table.
        artist_groups = []
        if 'artist' in tables:
            cols = _nd_table_cols(con, 'artist')
            name_col = next((c for c in ('name','artist_name','artist') if c in cols), None)
            id_col = 'id' if 'id' in cols else None
            if name_col:
                selected = ([id_col] if id_col else []) + [name_col]
                ar = con.execute(f"SELECT {', '.join(selected)} FROM artist").fetchall()
                by_name = {}
                for row in ar:
                    aid = row[0] if id_col else None
                    name = row[1] if id_col else row[0]
                    if not name or not _has_asian(name):
                        continue
                    stem = _artist_entity_cjk_stem(name)
                    if stem:
                        by_name.setdefault(stem, []).append((aid, name))
                artist_groups = [v for v in by_name.values() if len(v) > 1]
        lines.append(f'\nDUPLICATE CJK ARTIST ENTITY GROUPS (CJK-only vs bilingual): {len(artist_groups)}')
        for i, group in enumerate(sorted(artist_groups, key=lambda g: g[0][1].casefold()), 1):
            def artist_preference(name):
                gloss = re.search(r'[\(（]([^\)）]*[A-Za-z][^\)）]*)[\)）]', name)
                return (int(bool(_has_asian(name) and gloss)), len(gloss.group(1)) if gloss else 0, len(name))
            preferred = max((name for _, name in group), key=artist_preference)
            lines.append(f'  [{i}] CJK identity={_artist_entity_cjk_stem(preferred)!r}; '
                         f'preferred display={preferred!r}')
            for aid, name in group:
                state = 'PREFERRED' if name == preferred else 'old alias (should disappear after tag fix + full scan)'
                lines.append(f'    artist.id={aid!r} name={name!r} [{state}]')
        known_names = _navidrome_artist_name_map(con)
        compound_rows = []
        if known_names and 'artist' in tables:
            cols = _nd_table_cols(con, 'artist')
            name_col = next((c for c in ('name', 'artist_name', 'artist') if c in cols), None)
            if name_col:
                for (raw_name,) in con.execute(f'SELECT "{name_col}" FROM artist'):
                    raw_name = str(raw_name or '').strip()
                    parts = [x.strip() for x in re.split(r'\s*;\s*', raw_name) if x.strip()]
                    if len(parts) < 2:
                        continue
                    matches = [x for x in parts if norm(x) in known_names and norm(x) != norm(raw_name)]
                    if matches:
                        compound_rows.append((raw_name, parts, matches))
        lines.append(f'\nSEMICOLON ARTIST CANDIDATES (must match DB component): {len(compound_rows)}')
        for raw_name, parts, matches in compound_rows:
            lines.append(f'  {raw_name!r} -> {parts!r}; DB matches: {matches!r}')
        lines.append('\nNOTE: this report is read-only. Exact groups are strong candidates; fuzzy pairs are never auto-merged by diagnosis.')

    _embed_report_in_main_log('album_db_diagnostics', lines)
    _cleanup_standalone_album_reports()
    print('[i] diagnostica album incorporata direttamente nel log principale e2m (nessun file separato)')
    return True


def run_repair_albumversion_pids(dry_run=False, base=None, files_only=None):
    """Make ALBUMVERSION consistent per logical album root for Navidrome Album PIDs.

    If all tagged tracks agree, propagate the single value to untagged tracks. If multiple
    versions occur inside the same physical album tree, clear the conflicting field on all
    tracks rather than arbitrarily selecting a value. Different explicit editions in separate
    folders are stopped by the cross-folder review gate above.
    """
    base = Path(base) if base else LIBRARY_ROOT
    wanted_files = {Path(f).resolve() for f in files_only} if files_only is not None else None
    roots = {}
    for rel in _walk_audio(base, AUDIO_EXT):
        if rel[-1].endswith(('.backup', '.meta-backup')) or '.tmp.' in rel[-1]:
            continue
        f = base.joinpath(*rel)
        if wanted_files is not None and f.resolve() not in wanted_files:
            continue
        roots.setdefault(_album_root_for_file(base, f), []).append(f)
    prefetch_probe((f for fs in roots.values() for f in fs), 'albumversion_pid_repair')
    candidates = changed_files = errors = reviewed = 0
    tg = '[dry] ' if dry_run else ''
    progress = _ProgressBar('albumversion_pid_repair', len(roots), 'album')
    for root_index, (root, files) in enumerate(roots.items(), 1):
        progress.update(root_index)
        tags = [probe(f) for f in files]
        values = {str(t.get('albumversion') or t.get('album_version') or '').strip()
                  for t in tags if str(t.get('albumversion') or t.get('album_version') or '').strip()}
        if not values:
            continue
        conflict = len(values) > 1
        target = None if conflict else next(iter(values))
        changes = []
        for f, tag in zip(files, tags):
            current = str(tag.get('albumversion') or tag.get('album_version') or '').strip()
            if conflict and current:
                changes.append((f, {'albumversion': None}))
            elif not conflict and current != target:
                changes.append((f, {'albumversion': target}))
        if not changes:
            continue
        candidates += 1
        if conflict:
            reviewed += 1
            action = f'ALBUMVERSION discordanti {sorted(values)!r}; rimuovo il campo dall’intero album logico'
        else:
            action = f'ALBUMVERSION unico {target!r}; propago ai tag mancanti'
        progress.clear()
        print(f'{tg}ALBUM-PID {root}: {action}; {len(changes)} file')
        if dry_run:
            changed_files += len(changes)
            continue
        for f, diff in changes:
            try:
                if f.suffix.lower() == '.flac':
                    write_flac(f, diff)
                else:
                    _rewrite_nonflac(f, diff)
                changed_files += 1
            except Exception as e:
                errors += 1
                progress.clear()
                print(f'[ERRORE] ALBUM-PID {f}: {type(e).__name__}: {e}', file=sys.stderr)
    progress.close(complete=True)
    print(f'album PID version: {candidates} album logici, {changed_files} file '
          f'{"da correggere" if dry_run else "corretti"}, {reviewed} conflitti risolti, {errors} errori')
    return {'albums': candidates, 'files': changed_files, 'reviewed': reviewed, 'errors': errors}


def _is_unknown_artist(value):
    """Riconosce tag vuoti/generici comunemente mostrati come [Unknown Artist]."""
    raw = unicodedata.normalize('NFKC', str(value or '')).strip().casefold()
    raw = re.sub(r'^[\s\[\(\{【]+|[\s\]\)\}】]+$', '', raw).strip()
    return raw in {'', 'unknown', 'unknown artist', 'unknownartist', '[unknown artist]',
                   'n/a', 'na', 'none', 'null', 'unknown performer'}


def _has_unknown_artist_component(value):
    raw = unicodedata.normalize('NFKC', str(value or '')).strip()
    if _is_unknown_artist(raw):
        return True
    # norm() strips bracketed/parenthesized annotations before keying. Detect placeholder
    # tokens inside a larger label too, or "The Cure [Unknown Artist]" can collide with
    # the real "The Cure" row just like "The Cure, [Unknown Artist]" does.
    if re.search(r'[\[(]\s*unknown\s+artist\s*[\])]', raw, re.I):
        return True
    return any(_is_unknown_artist(part.strip())
               for part in re.split(r'\s*[;,]\s*', raw) if part.strip())


_GENERIC_ARTIST_NAMES = {
    'various artists', 'various', 'va', 'soundtrack', 'unknown', 'unknown artist',
    'unknownartist', 'n a', 'na', 'none', 'null',
}


def _artist_parts_for_inference(value, known_names=None, context_names=None):
    """Split artist components using delimiters, catalog evidence, or folder context."""
    raw = str(value or '').strip()
    if not raw:
        return []
    known_names = known_names or {}
    out = []
    for chunk in re.split(r'\s*;\s*', raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        split = (_split_artist_tag_if_known(chunk, known_names, context_names)
                 if ',' in chunk else None)
        out.extend(split or [chunk])
    return out


def _infer_album_artist_for_unknown_tracks(tags, known_names=None):
    """Infer an artist conservatively, without guessing on compilations.

    A concrete, consistent ALBUMARTIST takes priority. If ALBUMARTIST is present
    but generic or conflicting (for example, "Various Artists"), do not infer a
    substitute from the most common track artist. Without usable ALBUMARTIST tags,
    all known track artists must agree on a single normalized identity.
    """
    aa_counts = Counter()
    aa_total = 0
    aa_alias_conflict = False
    aa_fields = ('albumartist', 'album_artist', 'albumartists')
    for tag in tags:
        values = [str(tag.get(key) or '').strip() for key in aa_fields]
        # Remove placeholder components, not the entire mixed string: e.g. 'The Cure; Unknown Artist'
        # still provides a reliable album-artist identity of The Cure.
        cleaned_values = []
        for value in values:
            if not value:
                continue
            parts = [part for part in _artist_parts_for_inference(value, known_names)
                     if part and not _is_unknown_artist(part)]
            if parts:
                cleaned_values.append('; '.join(parts))
        values = list(dict.fromkeys(cleaned_values))
        if not values:
            continue
        aa_total += 1
        # Multiple aliases on one file should describe the same artist list. If they
        # disagree, don't hide the conflict by accepting whichever field comes first.
        identities = {
            tuple(sorted(norm(part) for part in _artist_parts_for_inference(value, known_names)
                         if norm(part) and not _is_unknown_artist(part)))
            for value in values
        }
        if len(identities) > 1:
            aa_alias_conflict = True
            continue
        parts = [p for p in _artist_parts_for_inference(values[0], known_names)
                 if norm(p) not in _GENERIC_ARTIST_NAMES]
        if parts:
            aa_counts['; '.join(parts)] += 1

    if aa_total:
        if not aa_alias_conflict and aa_counts:
            best, count = aa_counts.most_common(1)[0]
            # Include generic/conflicting albumartist tags in the denominator:
            # they are evidence against inferring a single album identity.
            if count / aa_total >= 0.6:
                return _artist_parts_for_inference(best)
        # A generic or conflicting ALBUMARTIST is a strong reason not to guess
        # from track frequency (especially on compilations/soundtracks).
        return []

    track_artists = {}
    for tag in tags:
        values = [str(tag.get(key) or '').strip() for key in ('artist', 'artists')]
        for raw in values:
            if not raw or _is_unknown_artist(raw):
                continue
            for part in _artist_parts_for_inference(raw, known_names):
                key = norm(part)
                if key and key not in _GENERIC_ARTIST_NAMES:
                    track_artists.setdefault(key, part)
    if len(track_artists) == 1:
        return [next(iter(track_artists.values()))]
    return []


def _infer_track_artist_from_filename(path, known_names=None):
    """Inferenza forte per file nominati 'Titolo - Artista': accetta solo artisti noti al DB."""
    known_names = known_names or {}
    path = Path(path)
    chunks = [chunk.strip() for chunk in path.stem.split(' - ') if chunk.strip()]
    # Il suffisso e' piu' affidabile del prefisso (che e' normalmente il titolo del brano).
    for candidate in reversed(chunks[1:]):
        key = norm(candidate)
        if key in known_names and key not in _GENERIC_ARTIST_NAMES:
            return [known_names[key]]
        parts = _artist_parts_for_inference(candidate, known_names)
        resolved = []
        for part in parts:
            pkey = norm(part)
            if pkey in known_names and pkey not in _GENERIC_ARTIST_NAMES:
                value = known_names[pkey]
                if value not in resolved:
                    resolved.append(value)
        if resolved:
            return resolved
    # Ultimo fallback: artista della cartella SOLO se il filename lo conferma nel suffisso.
    folder_key = norm(path.parent.parent.name)
    if folder_key in known_names and any(norm(chunk) == folder_key for chunk in chunks[1:]):
        return [known_names[folder_key]]
    return []


def run_fix_unknown_artists(dry_run=False, base=None, album_dirs_only=None):
    """Ripara tracce Unknown Artist usando tag album, cartella e artisti noti delle altre tracce."""
    base = Path(base) if base else LIBRARY_ROOT
    dirs = list(unify_album_dirs(base))
    if album_dirs_only is not None:
        wanted_dirs = {Path(d).resolve() for d in album_dirs_only}
        dirs = [(album, files) for album, files in dirs if album.resolve() in wanted_dirs]
    known_names = _navidrome_artist_name_map()
    prefetch_probe((f for _album, files in dirs for f in files), 'fix_unknown_artists')
    seen = fixed_files = errors = ambiguous = 0
    tg = '[dry] ' if dry_run else ''
    progress = _ProgressBar('fix_unknown_artists', len(dirs), 'album')
    for album_index, (album, files) in enumerate(dirs, 1):
        progress.update(album_index)
        tags = [probe(f) for f in files]
        unknown_idxs = [i for i, tag in enumerate(tags) if _has_unknown_artist_component(tag.get('artist', ''))]
        # Navidrome può creare un artista/album separato anche quando ARTIST è valido ma
        # ALBUMARTIST/ALBUM_ARTIST contiene esplicitamente [Unknown Artist]. Ripara entrambi.
        unknown_albumartist_idxs = []
        for i, tag in enumerate(tags):
            albumartist_values = [str(tag.get(k) or '').strip()
                                  for k in ('albumartist', 'album_artist', 'albumartists')]
            if any(v and _has_unknown_artist_component(v)
                   for v in albumartist_values):
                unknown_albumartist_idxs.append(i)
        if not unknown_idxs and not unknown_albumartist_idxs:
            continue
        seen += len(unknown_idxs) + len(unknown_albumartist_idxs)
        target = _infer_album_artist_for_unknown_tracks(tags, known_names)
        # Un campo plural ARTISTS attendibile e' una sorgente specifica della traccia, anche se
        # un'altra traccia dello stesso album appartiene a un compositore diverso.
        per_track_targets = {}
        for idx in unknown_idxs:
            plural = str(tags[idx].get('artists') or '').strip()
            if plural and not _is_unknown_artist(plural):
                parts = _artist_parts_for_inference(plural, known_names)
                known_parts = [known_names.get(norm(part), part) for part in parts
                               if norm(part) not in _GENERIC_ARTIST_NAMES and not _is_unknown_artist(part)]
                if known_parts:
                    per_track_targets[idx] = list(dict.fromkeys(known_parts))

        aa_values = [str(t.get(k) or '').strip() for t in tags
                     for k in ('albumartist', 'album_artist', 'albumartists') if str(t.get(k) or '').strip()]
        aa_parts = [part for value in aa_values for part in _artist_parts_for_inference(value, known_names)]
        # "Unknown Artist" non significa compilation e non deve bloccare il fallback alla
        # cartella; solo i marcatori espliciti di raccolta sono una barriera.
        explicit_compilation = any(norm(part) in {'various artists', 'various', 'va', 'soundtrack'}
                                   for part in aa_parts)
        # Alias field incoerenti sono un segnale per non inferire dalla cartella o da una maggioranza.
        aa_alias_conflict = False
        for tag in tags:
            alias_values = [str(tag.get(k) or '').strip() for k in ('albumartist', 'album_artist', 'albumartists')]
            alias_values = [v for v in alias_values if v]
            identities = set()
            for value in alias_values:
                parts = [part for part in _artist_parts_for_inference(value, known_names)
                         if part and not _is_unknown_artist(part)]
                if parts:
                    identities.add(tuple(sorted(norm(part) for part in parts if norm(part))))
            if len(identities) > 1:
                aa_alias_conflict = True
                break

        if not target and not explicit_compilation and not aa_alias_conflict:
            # La cartella artista e' una fonte forte se il metadato non dichiara una compilation.
            folder_artist = str(album.parent.name or '').strip()
            if (folder_artist and norm(folder_artist) not in _GENERIC_ARTIST_NAMES
                    and not _is_unknown_artist(folder_artist)):
                target = [folder_artist]

        if not target and not explicit_compilation and not aa_alias_conflict:
            # Fallback sulle tracce note dello stesso album. Basta una maggioranza chiara;
            # per esempio una traccia senza ARTIST eredita l'artista che hanno le altre.
            track_counts, track_labels = Counter(), {}
            for tag in tags:
                for key in ('artist', 'artists'):
                    value = str(tag.get(key) or '').strip()
                    if not value or _is_unknown_artist(value):
                        continue
                    for part in _artist_parts_for_inference(value, known_names):
                        k = norm(part)
                        if k and k not in _GENERIC_ARTIST_NAMES:
                            track_counts[k] += 1
                            track_labels.setdefault(k, part)
            total_known = sum(track_counts.values())
            if track_counts and max(track_counts.values()) / max(total_known, 1) >= 0.60:
                winner = sorted(track_counts, key=lambda k: (-track_counts[k], k))[0]
                target = [track_labels[winner]]

        if target:
            display = _canonicalize_artist_value('; '.join(target), known_names=known_names)
            target_parts = [p.strip() for p in display.split(';') if p.strip()]
            for idx in unknown_idxs:
                per_track_targets.setdefault(idx, target_parts)
        else:
            for idx in unknown_idxs:
                if idx not in per_track_targets:
                    per_track_targets[idx] = _infer_track_artist_from_filename(files[idx], known_names)

        repairable = {idx: parts for idx, parts in per_track_targets.items() if parts}
        unresolved = [idx for idx in unknown_idxs if idx not in repairable]
        if unresolved:
            ambiguous += len(unresolved)
            progress.clear()
            print(f'[review] UNKNOWN-ARTIST {album.parent.name}/{album.name}: '
                  f'{len(unresolved)} tracce senza artista e senza sorgente affidabile per traccia; lasciate intatte')
        for i, target_parts in repairable.items():
            f = files[i]
            display = _canonicalize_artist_value('; '.join(target_parts), known_names=known_names)
            target_parts = [p.strip() for p in display.split(';') if p.strip()]
            progress.clear()
            print(f'{tg}UNKNOWN-ARTIST {album.parent.name}/{album.name}/{f.name}: '
                  f'{tags[i].get("artist", "")!r} -> {display!r}')
            if dry_run:
                fixed_files += 1
                continue
            try:
                if f.suffix.lower() == '.flac':
                    _flac_set_multi(f, {'ARTIST': [display], 'ARTISTS': target_parts})
                    invalidate_probe_cache([f])
                else:
                    _rewrite_nonflac(f, {'artist': display})
                fixed_files += 1
            except Exception as e:
                errors += 1
                progress.clear()
                print(f'[ERRORE] UNKNOWN-ARTIST {f}: {type(e).__name__}: {e}', file=sys.stderr)

        if unknown_albumartist_idxs:
            albumartist_target = target
            if not albumartist_target and not explicit_compilation and not aa_alias_conflict:
                folder_name = str(album.parent.name or '').strip()
                if folder_name and norm(folder_name) not in _GENERIC_ARTIST_NAMES and not _is_unknown_artist(folder_name):
                    albumartist_target = [folder_name]
            if albumartist_target:
                display_albumartist = _canonicalize_artist_value(
                    '; '.join(albumartist_target), known_names=known_names)
                albumartist_parts = [p.strip() for p in display_albumartist.split(';') if p.strip()]
                for idx in unknown_albumartist_idxs:
                    f = files[idx]
                    progress.clear()
                    print(f'{tg}UNKNOWN-ALBUMARTIST {album.parent.name}/{album.name}/{f.name}: '
                          f'-> {display_albumartist!r}')
                    if dry_run:
                        fixed_files += 1
                        continue
                    try:
                        if f.suffix.lower() == '.flac':
                            _flac_set_multi(f, {'ALBUMARTIST': [display_albumartist],
                                                'ALBUMARTISTS': albumartist_parts})
                            invalidate_probe_cache([f])
                        else:
                            aa_key = 'albumartist' if f.suffix.lower() in ('.ogg', '.opus') else 'album_artist'
                            _rewrite_nonflac(f, {aa_key: display_albumartist})
                        fixed_files += 1
                    except Exception as e:
                        errors += 1
                        progress.clear()
                        print(f'[ERRORE] UNKNOWN-ALBUMARTIST {f}: {type(e).__name__}: {e}', file=sys.stderr)
            else:
                ambiguous += len(unknown_albumartist_idxs)
                progress.clear()
                print(f'[review] UNKNOWN-ALBUMARTIST {album.parent.name}/{album.name}: '
                      'nessuna sorgente affidabile per ALBUMARTIST; lasciato invariato')
    progress.close(complete=True)
    print(f'unknown artist: {seen} tracce candidate, {fixed_files} '
          f'{"da correggere" if dry_run else "corrette"}, {ambiguous} da rivedere, {errors} errori')
    return {'candidates': seen, 'fixed': fixed_files, 'ambiguous': ambiguous, 'errors': errors}


def _navidrome_artist_name_map(con=None):
    """Mappa norm(nome artista) -> grafia in DB; vuota se la tabella non e' leggibile."""
    if con is None:
        if not NAVIDROME_DB.exists():
            return {}
        try:
            with _nd_db(write=False) as db_con:
                return _navidrome_artist_name_map(db_con)
        except (sqlite3.Error, OSError) as e:
            print(f'[warn] impossibile leggere gli artisti dal DB Navidrome: {e}', file=sys.stderr)
            return {}
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'artist' not in tables:
            return {}
        cols = _nd_table_cols(con, 'artist')
        name_col = next((c for c in ('name', 'artist_name', 'artist') if c in cols), None)
        if not name_col:
            return {}
        found = {}
        for row in con.execute(f'SELECT "{name_col}" FROM artist'):
            name = str(row[0] or '').strip()
            # norm() deliberately strips square-bracketed annotations. Thus a corrupted
            # composite label such as "The Cure, [Unknown Artist]" normalizes to the same
            # key as "The Cure" and, because it is longer, could otherwise replace the real
            # catalog spelling. Never index an artist row containing a placeholder component.
            if _has_unknown_artist_component(name):
                continue
            key = norm(name)
            if key:
                previous = found.get(key)
                if previous is None or _artist_display_score(name) > _artist_display_score(previous):
                    found[key] = name
        return found
    except sqlite3.Error as e:
        print(f'[warn] impossibile leggere gli artisti dal DB Navidrome: {e}', file=sys.stderr)
        return {}


def _artist_display_score(name):
    has_asian = _has_asian(name)
    gloss = re.search(r'[\(（]([^\)）]*[A-Za-z][^\)）]*)[\)）]', str(name or ''))
    titlecase = sum(c.isupper() for c in gloss.group(1)) if gloss else 0
    raw = str(name or '').strip()
    return (int(bool(has_asian and gloss)), int(has_asian), titlecase,
            int('_' not in raw), int('.' in raw and '_' not in raw), len(raw), raw.casefold())


@lru_cache(maxsize=8192)
def _artist_context_from_parent(parent_path, base_path):
    """Cached candidate artist-folder labels for a directory, most-specific first."""
    parent, root = Path(parent_path), Path(base_path)
    names = []
    try:
        relative = parent.relative_to(root)
        names.extend(reversed(relative.parts))
    except (ValueError, OSError):
        pass
    names.append(root.name)
    result, seen = [], set()
    for name in names:
        key = norm(name)
        if key and key not in seen:
            seen.add(key)
            result.append(name)
    return tuple(result)


def _artist_context_from_path(file_path, base):
    """Artist-folder evidence for a file, cached for all tracks in the same directory."""
    return _artist_context_from_parent(str(Path(file_path).parent), str(Path(base)))


def _split_artist_tag_if_known(value, known_names, context_names=None):
    """Separate artist lists without per-name overrides.

    Semicolons are explicit artist delimiters. A comma with no following whitespace is
    treated as a malformed collaboration delimiter even when Navidrome has indexed the
    full joined string as one artist. For spaced commas, catalog components or a matching
    artist-folder label provide evidence; known comma-bearing solo names remain intact.
    """
    raw = str(value or '').strip()
    if not raw:
        return None
    known_names = known_names or {}
    explicit_chunks = [x.strip() for x in raw.split(';') if x.strip()]
    explicit = len(explicit_chunks) > 1
    if not explicit:
        explicit_chunks = [raw]
    out = []
    recognized = 0
    forced_split = explicit

    for chunk in explicit_chunks:
        if not chunk:
            continue
        if _has_tight_comma_separator(chunk):
            # Do not let the exact joined catalog key mask a collaboration delimiter.
            comma_parts = [x.strip() for x in re.split(r',(?=\S)', chunk) if x.strip()]
            if len(comma_parts) >= 2:
                forced_split = True
                for part in comma_parts:
                    key = norm(part)
                    out.append(known_names.get(key, part))
                    recognized += int(key in known_names)
                continue

        comma_parts = [x.strip() for x in re.split(r'\s*,\s*', chunk) if x.strip()]
        if len(comma_parts) == 1:
            key = norm(chunk)
            out.append(known_names.get(key, chunk))
            recognized += int(key in known_names)
            continue

        context_keys = set()
        for context_name in (context_names or ()):
            context_key = norm(context_name)
            if context_key:
                context_keys.add(context_key)
        # A matching artist directory is useful evidence when this component has never
        # been indexed separately. This generalizes to all artist folders and does not
        # require a JSON rule for each joined collaboration.
        if any(norm(part) in context_keys for part in comma_parts):
            forced_split = True
            for part in comma_parts:
                key = norm(part)
                out.append(known_names.get(key, part))
                recognized += int(key in known_names)
            continue

        atom_keys = [norm(part) for part in comma_parts]
        whole_key = norm(chunk)
        component_is_safe = all(
            (key and key in known_names) or _is_unknown_artist(part)
            for key, part in zip(atom_keys, comma_parts))
        has_real_catalog_component = any(key in known_names for key in atom_keys)
        if component_is_safe and has_real_catalog_component:
            out.extend(known_names.get(key, part) for key, part in zip(atom_keys, comma_parts))
            recognized += sum(1 for key, part in zip(atom_keys, comma_parts)
                              if key in known_names or _is_unknown_artist(part))
            forced_split = True
            continue

        # A spaced comma on a catalog-known whole-name is not enough evidence to split.
        if whole_key in known_names:
            out.append(known_names[whole_key])
            recognized += 1
            continue

        # Reconstruct longest known names. This preserves known comma-bearing solo artists
        # while still allowing an additional catalog-recognized collaborator after them.
        i = 0
        while i < len(comma_parts):
            hit = None
            for j in range(len(comma_parts), i, -1):
                candidate = ', '.join(comma_parts[i:j])
                key = norm(candidate)
                if key and key in known_names:
                    hit = (known_names[key], j)
                    break
            if hit:
                out.append(hit[0])
                recognized += 1
                i = hit[1]
            else:
                out.append(comma_parts[i])
                i += 1

    out = [part.strip() for part in out if part and part.strip()]
    reliable = [part for part in out if not _is_unknown_artist(part)]
    if reliable:
        # A generic placeholder must not remain as an extra artist beside real names.
        out = reliable
    result, seen = [], set()
    for part in out:
        key = norm(part)
        canonical = known_names.get(key, part.strip())
        if key and key not in seen:
            seen.add(key)
            result.append(canonical)
    if len(result) >= 2:
        return result
    # When an evidenced multi-artist tag collapses to one reliable artist after dropping
    # placeholders, return that one artist so callers can remove the stale placeholder.
    if forced_split and reliable and result:
        return result
    if not forced_split and recognized < 2:
        return None
    return None


# Compatibilita' interna con il nome precedente.
def _split_semicolon_if_known(value, known_names):
    return _split_artist_tag_if_known(value, known_names)


def run_split_known_artist_tags(dry_run=False, base=None, files_only=None):
    """Normalize multi-artist tags using separators, catalog evidence, and artist folders."""
    base = Path(base) if base else LIBRARY_ROOT
    known = _navidrome_artist_name_map()
    if not known:
        print('[warn] catalogo artisti Navidrome non leggibile: uso separatori espliciti e contesto della cartella-artista',
              file=sys.stderr)
    files = [base.joinpath(*r) for r in _walk_audio(base, AUDIO_EXT)]
    if files_only is not None:
        wanted_files = {Path(f).resolve() for f in files_only}
        files = [f for f in files if f.resolve() in wanted_files]
    # ffprobe is cached and can reject almost every file before we spawn metaflac.
    # In v0.68 the function launched metaflac once for virtually every track; on this
    # library that dominated repair_album_groups (41m45s) despite only 193 files changing.
    prefetch_probe(files, 'split_known_artist_tags')
    candidates = changed = errors = skipped = 0
    candidate_files = []
    scan_progress = _ProgressBar('preselezione split artisti', len(files), 'brani')
    for scan_index, f in enumerate(files, 1):
        scan_progress.update(scan_index)
        tags = probe(f)
        path_context = _artist_context_from_path(f, base)
        values_to_check = (tags.get('artist'), tags.get('artists'), tags.get('albumartist'),
                           tags.get('album_artist'), tags.get('albumartists'))
        if any(_split_artist_tag_if_known(value, known, path_context)
               for value in values_to_check if value):
            candidate_files.append(f)
    scan_progress.close(complete=True)
    print(f'[i] split artisti: {len(candidate_files)}/{len(files)} file hanno tag candidati', flush=True)
    tg = '[dry] ' if dry_run else ''
    progress = _ProgressBar('split_known_artist_tags', len(candidate_files), 'candidati')
    for file_index, f in enumerate(candidate_files, 1):
        progress.update(file_index)
        ext = f.suffix.lower()
        try:
            path_context = _artist_context_from_path(f, base)
            if ext == '.flac':
                try:
                    raw_tags = _flac_raw_tags(f)
                except Exception as e:
                    skipped += 1
                    progress.clear()
                    print(f'[warn] split artisti: tag FLAC non leggibili, file saltato: {f}: {e}',
                          file=sys.stderr)
                    continue
                values = {}
                for key in ('ARTIST', 'ARTISTS', 'ALBUMARTIST', 'ALBUMARTISTS'):
                    values[key] = [v for k, v in raw_tags if k == key]
                updates = {}
                for singular, plural in (('ARTIST', 'ARTISTS'), ('ALBUMARTIST', 'ALBUMARTISTS')):
                    singular_values = values[singular]
                    plural_values = values[plural]
                    expanded_singular = []
                    did_split = False
                    for value in singular_values:
                        parts = _split_artist_tag_if_known(value, known, path_context)
                        if parts:
                            did_split = True
                            expanded_singular.extend(parts)
                        else:
                            expanded_singular.append(value.strip())
                    expanded_plural = []
                    for value in plural_values:
                        parts = _split_artist_tag_if_known(value, known, path_context)
                        if parts:
                            did_split = True
                            expanded_plural.extend(parts)
                        else:
                            expanded_plural.append(value.strip())
                    if not did_split:
                        continue
                    # The singular tag remains one readable string with Navidrome's default '; ' delimiter.
                    singular_display = '; '.join(dict.fromkeys(x for x in expanded_singular if x))
                    desired_plural = []
                    seen_plural = set()
                    for value in expanded_plural + expanded_singular:
                        key = norm(value)
                        if key and key not in seen_plural:
                            seen_plural.add(key)
                            desired_plural.append(known.get(key, value))
                    if singular_display and singular_values != [singular_display]:
                        updates[singular] = [singular_display]
                    if desired_plural and plural_values != desired_plural:
                        updates[plural] = desired_plural
                if not updates:
                    continue
                candidates += 1
                progress.clear()
                print(f'{tg}SPLIT-ARTIST {f}: ' + ', '.join(f'{k}={v}' for k, v in updates.items()))
                if not dry_run:
                    _flac_set_multi(f, updates)
                    invalidate_probe_cache([f])
                changed += 1
            else:
                tag, _dur = probe_dur(f)
                updates = {}
                for dest_key, source_keys in (
                    ('artist', ('artist', 'artists')),
                    ('albumartist', ('albumartist', 'album_artist', 'albumartists')),
                ):
                    merged_parts, seen_parts = [], set()
                    found_split = False
                    for key in source_keys:
                        value = str(tag.get(key) or '').strip()
                        parts = _split_artist_tag_if_known(value, known, path_context)
                        if not parts:
                            continue
                        found_split = True
                        for part in parts:
                            identity = norm(part)
                            if identity and identity not in seen_parts:
                                seen_parts.add(identity)
                                merged_parts.append(known.get(identity, part))
                    if found_split and merged_parts:
                        # Navidrome's default splitter requires '; ' (with a space).
                        updates[dest_key] = '; '.join(merged_parts)
                if not updates:
                    continue
                candidates += 1
                progress.clear()
                print(f'{tg}SPLIT-ARTIST {f}: ' + ', '.join(f'{k}={v}' for k, v in updates.items()))
                if not dry_run:
                    _rewrite_nonflac(f, updates)
                changed += 1
        except Exception as e:
            errors += 1
            progress.clear()
            print(f'[ERRORE] split artisti {f}: {type(e).__name__}: {e}', file=sys.stderr)
    progress.close(complete=True)
    print(f'split artisti da DB: {candidates} file candidati, {changed} '
          f'{"da correggere" if dry_run else "corretti"}, {errors} errori, '
          f'{skipped} saltati per tag non leggibili')
    return {'files': changed, 'errors': errors, 'skipped': skipped}


def run_repair_album_groups(dry_run=True, base=None, include_existing_passes=True,
                            album_dirs_only=None, files_only=None):
    """Ripara album e artisti. --all riusa le fasi tag gia' eseguite, senza duplicarle."""
    base = Path(base) if base else LIBRARY_ROOT
    mbid_errors = artist_errors = unify_errors = 0
    if include_existing_passes:
        try:
            mb_cache = json.loads(MBDATE_CACHE.read_text(encoding='utf-8'))
        except Exception:
            mb_cache = {}
        try:
            title_cache = json.loads(MBTITLE_CACHE.read_text(encoding='utf-8'))
        except Exception:
            title_cache = {}
        mbid_result = _repair_mbid_sanity(base, mb_cache, title_cache, dry_run=dry_run)
        stripped = mbid_result.get('roots', 0)
        mbid_errors = mbid_result.get('errors', 0)
        artist_result = run_unify_artists(dry_run=dry_run, base=base)
        unify_result = run_unify(dry_run=dry_run, base=base)
        artist_errors = artist_result.get('errors', 0) if isinstance(artist_result, dict) else 0
        unify_errors = unify_result.get('errors', 0) if isinstance(unify_result, dict) else 0
        # These are reusable lookup caches, not audio/tag outputs. Persist them even in
        # preview mode so repeated --repair-album-groups dry-runs do not re-query MusicBrainz.
        _write_json_atomic(MBDATE_CACHE, mb_cache)
        _write_json_atomic(MBTITLE_CACHE, title_cache)
    else:
        stripped = 0
    version_result = run_repair_albumversion_pids(dry_run=dry_run, base=base, files_only=files_only)
    unknown_result = run_fix_unknown_artists(dry_run=dry_run, base=base, album_dirs_only=album_dirs_only)
    split_result = run_split_known_artist_tags(dry_run=dry_run, base=base, files_only=files_only)
    if not dry_run:
        # In scoped reruns, never clean backups outside the affected album folders.
        if files_only is None:
            backup_candidates = base.rglob('*.meta-backup')
        else:
            backup_candidates = (b for folder in {Path(f).parent for f in files_only}
                                 for b in folder.glob('*.meta-backup'))
        for backup in backup_candidates:
            original = backup.with_name(backup.name[:-len('.meta-backup')])
            if original.exists():
                try:
                    backup.unlink()
                except OSError:
                    pass
    errors = mbid_errors + artist_errors + unify_errors + \
             (version_result.get('errors', 0) if isinstance(version_result, dict) else 0) + \
             (unknown_result.get('errors', 0) if isinstance(unknown_result, dict) else 0) + \
             (split_result.get('errors', 0) if isinstance(split_result, dict) else 0)
    print(f'album-group repair: {stripped} root con MBID errato identificati; '
          f'{"PREVIEW" if dry_run else "APPLICATO"}; fuzzy sempre solo report; errori={errors}')
    return errors == 0


def rebuild_album(name_frag):
    """Cancella dal DB di Navidrome le righe media_file/album dell'album
    indicato (match parziale): il full scan successivo lo ricostruisce
    da zero dai tag dei file. Il martello generalizzato per album 'incollati'
    che nessuno scan riesce a separare."""
    if not NAVIDROME_DB.exists():
        print('[ERRORE] DB non trovato')
        return
    ps = _docker('ps', '--filter', 'name=navidrome', '--format', '{{.Names}}')
    running = 'navidrome' in ps.stdout
    if running:
        print('fermo navidrome...')
        _docker('stop', 'navidrome')
    try:
        con = sqlite3.connect(str(NAVIDROME_DB))
        cur = con.cursor()
        rows = cur.execute(
            "SELECT id, name FROM album WHERE name LIKE ?", (f'%{name_frag}%',)
        ).fetchall()
        if not rows:
            print(f'[ERRORE] nessun album contiene {name_frag!r}')
            return
        for aid, aname in rows:
            n = cur.execute('DELETE FROM media_file WHERE album_id=?', (aid,)).rowcount
            cur.execute('DELETE FROM album WHERE id=?', (aid,))
            print(f'  rimosso album {aname!r} ({n} tracce)')
        con.commit()
        con.close()
    finally:
        if running:
            print('riavvio navidrome...')
            _docker('start', 'navidrome')


def explain_row(by_full, by_artist, by_strict, path_qual, artist, album, title):
    """Diagnostica: riesegue il matching mostrando TUTTI i candidati con i
    punteggi (album 0-2, qualificato, specificita', artista 1-2)."""
    trace = []
    hit = find_match(by_full, by_artist, by_strict, path_qual, artist, album,
                     title, 0.8, _trace=trace)
    print(f"query: artist={artist!r} album={album!r} title={title!r}")
    print(f"RISULTATO: {hit or '(nessun match)'}")
    print(f"{'stage':24s} {'alb':>3s} {'qual':>4s} {'spec':>4s} {'art':>3s} {'rk':>2s}  file")
    for row in trace:
        stage, path, alb, qual, spec, art, *rest = row   # stage 3/4: 7 campi (rank)
        rk = str(rest[0]) if rest else ''
        if alb == '' and qual == '':
            print(f"{stage:24s} {'':>3s} {'':>4s} {'':>4s} {'':>3s} {'':>2s}  {path}")
        else:
            print(f"{stage:24s} {str(alb):>3s} {str(qual):>4s} {str(spec):>4s} "
                  f"{str(art):>3s} {rk:>2s}  {Path(path).name}")


# ===================== fase: download artwork album mancanti =====================
# Comportamento ispirato a MusicBee: cerca solo album senza cover locale/embedded,
# conserva artwork già presente, verifica album+artista nei risultati e usa fonti multiple.
# Le immagini vengono salvate come cover.jpg/png/webp nella cartella album per Navidrome.
ARTWORK_CACHE = SCRIPT_DIR / '.missing_artwork_cache.json'
ARTWORK_USER_AGENT = f'exportify-to-m3u/{VERSION} (personal music library artwork lookup)'
_ARTWORK_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
_ARTWORK_KNOWN_STEMS = {
    'cover', 'folder', 'front', 'album', 'albumart', 'album art', 'album_art',
    'cover art', 'artwork', 'album artwork', 'front cover', 'cover front',
}


def _artwork_cache_load():
    try:
        value = json.loads(ARTWORK_CACHE.read_text(encoding='utf-8'))
        if isinstance(value, dict) and isinstance(value.get('not_found'), dict):
            return value
    except (OSError, ValueError):
        pass
    return {'version': 1, 'not_found': {}}


def _artwork_cache_save(cache):
    try:
        _write_json_atomic(ARTWORK_CACHE, cache, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f'[warn] cache artwork non salvata: {e}', file=sys.stderr)


def _artwork_cache_key(artist, album):
    return f'{norm(artist)}\t{norm(album)}'


def _album_art_directory(track_path):
    directory = track_path.parent
    if _DISC_DIR.match(directory.name):
        directory = directory.parent
    try:
        rel = directory.relative_to(LIBRARY_ROOT)
    except ValueError:
        return None
    # Evita di depositare una cover nella root o direttamente nella cartella artista,
    # che potrebbe contenere molti singoli/album distinti.
    return directory if len(rel.parts) >= 2 else None


def _has_local_album_art(album_dir, album_title='', artwork_stems_by_dir=None):
    """True se la cartella possiede cover; riusa i nomi raccolti dalla scansione se forniti."""
    known = _ARTWORK_KNOWN_STEMS | ({norm_bare(album_title)} if album_title else set())
    if artwork_stems_by_dir is not None:
        # run_missing_album_artwork ha gia' raccolto i filename in un'unica passeggiata;
        # evita una scandir separata per ciascuno dei ~1.300 album.
        return bool(known.intersection(artwork_stems_by_dir.get(Path(album_dir), ())))
    try:
        for child in album_dir.iterdir():
            if child.is_file() and child.suffix.lower() in _ARTWORK_EXTS:
                if norm_bare(child.stem) in known:
                    return True
    except OSError:
        return True  # non potendo leggere la cartella, non scrivere a tentoni
    return False


def _embedded_art_state(track_path, timeout=10):
    """Stato cover embedded dalla cache ffprobe; migra i record vecchi con una probe dedicata."""
    global _PROBE_DIRTY
    ent = _probe_entry(track_path)
    if ent is None:
        return None
    if len(ent) >= 5 and ent[4] in (True, False):
        return bool(ent[4])
    # Una voce della cache senza stato artwork fa una sola probe dedicata, poi lo conserva.
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v',
             '-show_entries', 'stream=codec_type:stream_disposition=attached_pic',
             '-of', 'json', str(track_path)],
            capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or '{}')
        state = any(int((stream.get('disposition') or {}).get('attached_pic', 0) or 0) == 1
                    for stream in data.get('streams', []))
        if len(ent) < 5:
            ent.append(bool(state))
        else:
            ent[4] = bool(state)
        _PROBE_DIRTY = True
        return bool(state)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None


def _artwork_score(query_artist, query_album, result_artist, result_album):
    """Punteggio prudente, per non scaricare la copertina di un album omonimo."""
    qa, ra = norm(query_album), norm(result_album)
    if not qa or not ra:
        return None
    title_ratio = difflib.SequenceMatcher(None, qa, ra).ratio()
    if qa == ra:
        title_score = 1.0
    elif len(qa) >= 5 and (qa in ra or ra in qa):
        title_score = max(title_ratio, 0.91)
    else:
        title_score = title_ratio
    if title_score < 0.87:
        return None

    qartist = _canon(norm(query_artist))
    rartist = _canon(norm(result_artist))
    if not qartist or not rartist:
        return None
    if qartist == rartist:
        artist_score = 1.0
    else:
        qt, rt = set(qartist.split()), set(rartist.split())
        overlap = len(qt & rt) / max(1, min(len(qt), len(rt)))
        artist_score = max(overlap * 0.92,
                           difflib.SequenceMatcher(None, qartist, rartist).ratio())
    if artist_score < 0.55:
        return None
    return 0.68 * title_score + 0.32 * artist_score


def _safe_artwork_url(url, allowed_suffixes):
    try:
        parsed = urllib.parse.urlsplit(str(url or ''))
        host = (parsed.hostname or '').casefold()
        return parsed.scheme == 'https' and any(host.endswith(suffix) for suffix in allowed_suffixes)
    except ValueError:
        return False


def _artwork_json(url, timeout, max_bytes=3_000_000):
    request = urllib.request.Request(url, headers={
        'User-Agent': ARTWORK_USER_AGENT,
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError('risposta JSON artwork troppo grande')
    return json.loads(data.decode('utf-8', errors='replace'))


def _itunes_artwork_urls(artist, album, timeout):
    """URL iTunes ordinati per corrispondenza; ok=False indica errore rete/API."""
    params = urllib.parse.urlencode({'term': f'{artist} {album}', 'entity': 'album', 'limit': 25})
    try:
        data = _artwork_json('https://itunes.apple.com/search?' + params, timeout)
    except Exception as e:
        print(f'[artwork] iTunes non disponibile per {artist} — {album}: {e}', file=sys.stderr)
        return [], False
    ranked = []
    for item in data.get('results', []):
        score = _artwork_score(artist, album, item.get('artistName', ''), item.get('collectionName', ''))
        url = item.get('artworkUrl100') or item.get('artworkUrl60')
        if score is None or not url:
            continue
        # iTunes espone la dimensione dell'immagine nel segmento NNNxNNNbb.
        url = re.sub(r'\d+x\d+bb', '600x600bb', url)
        if _safe_artwork_url(url, ('.mzstatic.com',)):
            ranked.append((score, url))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))
    return list(dict.fromkeys(url for _, url in ranked[:5])), True


def _deezer_artwork_urls(artist, album, timeout):
    """Fallback pubblico Deezer, con lo stesso controllo album+artista."""
    query = urllib.parse.urlencode({'q': f'{artist} {album}', 'limit': 25})
    try:
        data = _artwork_json('https://api.deezer.com/search/album?' + query, timeout)
    except Exception as e:
        print(f'[artwork] Deezer non disponibile per {artist} — {album}: {e}', file=sys.stderr)
        return [], False
    if data.get('error'):
        print(f"[artwork] Deezer: {data['error']} ({artist} — {album})", file=sys.stderr)
        return [], False
    ranked = []
    for item in data.get('data', []):
        result_artist = (item.get('artist') or {}).get('name', '')
        score = _artwork_score(artist, album, result_artist, item.get('title', ''))
        url = item.get('cover_xl') or item.get('cover_big') or item.get('cover_medium')
        if score is None or not url or not _safe_artwork_url(url, ('.dzcdn.net',)):
            continue
        ranked.append((score, url))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))
    return list(dict.fromkeys(url for _, url in ranked[:5])), True


def _read_artwork_image(url, timeout, min_bytes, max_bytes):
    """Scarica solo JPG/PNG/WEBP validi e limitati; non sovrascrive artwork locale."""
    is_caa = str(url).startswith('https://coverartarchive.org/release/')
    if not (is_caa or _safe_artwork_url(url, ('.mzstatic.com', '.dzcdn.net'))):
        return None
    request = urllib.request.Request(url, headers={
        'User-Agent': ARTWORK_USER_AGENT,
        'Accept': 'image/jpeg,image/png,image/webp,*/*;q=0.5',
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            if is_caa:
                final_host = (urllib.parse.urlsplit(final_url).hostname or '').casefold()
                if not (final_host == 'coverartarchive.org' or final_host.endswith('.archive.org')):
                    return None
            elif not _safe_artwork_url(final_url, ('.mzstatic.com', '.dzcdn.net')):
                return None
            length = response.headers.get('Content-Length')
            if length and int(length) > max_bytes:
                return None
            data = response.read(max_bytes + 1)
    except Exception:
        return None
    if not min_bytes <= len(data) <= max_bytes:
        return None
    if data.startswith(b'\xff\xd8\xff'):
        ext = '.jpg'
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):
        ext = '.png'
    elif len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        ext = '.webp'
    else:
        return None
    return data, ext


def _load_artwork_album_groups():
    """Raccoglie tracce e nomi cover in un'unica scansione delle cartelle."""
    groups = {}
    art_stems_by_dir = {}
    root = Path(LIBRARY_ROOT)
    stack = [root]
    exts = INDEX_EXT
    # Estimate the audio-file total from the current probe cache. This scan used to run
    # before the artwork-query bar started, so a slow NAS walk could look frozen for minutes.
    try:
        estimated_audio_total = sum(
            1 for cached_path in _probe_mem()
            if Path(cached_path).suffix.lower() in exts and
            Path(cached_path).is_relative_to(root)
        )
    except Exception:
        estimated_audio_total = 0
    scan_progress = _ProgressBar('scansione file per artwork', estimated_audio_total, 'brani')
    audio_seen = 0
    while stack:
        base = stack.pop()
        try:
            with os.scandir(base) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if name.lower() in _SKIP_DIRS:
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                    continue
                suffix = os.path.splitext(name)[1].lower()
                if suffix in _ARTWORK_EXTS and entry.is_file():
                    art_stems_by_dir.setdefault(base, set()).add(norm_bare(os.path.splitext(name)[0]))
                if suffix in exts and entry.is_file():
                    audio_seen += 1
                    scan_progress.update(audio_seen)
                    track = Path(entry.path)
                    album_dir = _album_art_directory(track)
                    if album_dir is not None:
                        groups.setdefault(album_dir, []).append(track)
            except OSError:
                continue
    # The probe-cache estimate can be stale by a deleted/moved file. Once the walk ends,
    # retarget the final display to the observed count so a completed scan never remains at
    # 99% or shows a denominator that cannot be reached.
    if audio_seen > 0 and scan_progress.total != audio_seen:
        scan_progress.total = audio_seen
        scan_progress.update(audio_seen, force=True)
    scan_progress.close(complete=True)
    if estimated_audio_total and audio_seen != estimated_audio_total:
        print(f'[artwork] file audio rilevati: {audio_seen}; totale cache stimato: '
              f'{estimated_audio_total}', flush=True)
    return groups, art_stems_by_dir


def run_missing_album_artwork(dry_run=False):
    """Trova album senza cover locale/embedded e scarica fino a max_per_run immagini.

    Prima prova il release ID MusicBrainz già nei tag/NFO (Cover Art Archive), poi cerca
    album+artista su iTunes e Deezer. Non modifica i tag audio. I mancati risultati sono
    messi in cache per retry_days; gli errori di rete non vengono memorizzati come mancanti.
    """
    cfg = MISSING_ARTWORK_CONFIG
    if not cfg.get('enabled', True):
        print('[i] download cover album disabilitato da exportify_names.json')
        return {'downloaded': 0, 'missing': 0, 'attempted': 0}
    if not LIBRARY_ROOT.is_dir():
        print(f'[warn] directory libreria non accessibile per artwork: {LIBRARY_ROOT}', file=sys.stderr)
        return {'downloaded': 0, 'missing': 0, 'attempted': 0}

    groups, artwork_stems_by_dir = _load_artwork_album_groups()
    cache = _artwork_cache_load()
    negative = cache.setdefault('not_found', {})
    now = int(time.time())
    timeout = int(cfg['request_timeout'])
    min_bytes, max_bytes = int(cfg['min_image_bytes']), int(cfg['max_image_bytes'])
    candidates, negative_skipped = [], 0
    embedded_unknown = 0

    ordered_groups = sorted(groups.items(), key=lambda item: str(item[0]).casefold())
    scan_progress = _ProgressBar('scansione album senza artwork', len(ordered_groups), 'album')
    for album_index, (album_dir, tracks) in enumerate(ordered_groups, 1):
        scan_progress.update(album_index)
        if not tracks or _has_local_album_art(album_dir, album_dir.name, artwork_stems_by_dir):
            continue
        tags = probe(tracks[0])
        album_name = (tags.get('album') or '').strip() or album_dir.name
        artist_name = (tags.get('albumartist') or tags.get('album_artist') or
                       tags.get('artist') or '').strip() or album_dir.parent.name
        if not album_name or not artist_name:
            continue

        # Non scrivere una cover comune a piu' album finiti per errore nella stessa cartella.
        album_tags = set()
        for track in tracks[:4]:
            track_album = probe(track).get('album', '').strip()
            if track_album:
                album_tags.add(norm(track_album))
        if len(album_tags) > 1:
            print(f'[artwork] salto cartella con piu album taggati: {album_dir}', file=sys.stderr)
            continue

        key = _artwork_cache_key(artist_name, album_name)
        until = int(negative.get(key, 0) or 0)
        if until > now:
            # Il servizio remoto aveva gia' risposto che non esiste una cover valida.
            # Non serve lanciare fino a tre ffprobe solo per arrivare poi allo stesso skip.
            negative_skipped += 1
            continue
        if until:
            negative.pop(key, None)

        if cfg.get('check_embedded_art', True):
            # Non lanciare tre ffprobe in ogni album: fermarsi appena la prima traccia
            # conferma una cover embedded. Stato cacheato anche per i run successivi.
            states = []
            embedded_found = False
            for track in tracks[:3]:
                state = _embedded_art_state(track, timeout=min(timeout, 10))
                states.append(state)
                if state is True:
                    embedded_found = True
                    break
            if embedded_found:
                continue
            if states and all(state is None for state in states):
                print(f'[artwork] cover non controllabile (ffprobe): {album_dir}', file=sys.stderr)
                embedded_unknown += 1
                continue
        tags_mbid = str(tags.get('musicbrainz_albumid') or '').strip()
        nfo_mbid = (_nfo_field(album_dir, 'musicbrainzalbumid') or
                    _nfo_field(album_dir, 'MusicBrainzAlbumID')).strip()
        mbid = tags_mbid or nfo_mbid
        if not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', mbid):
            mbid = ''
        candidates.append({
            'dir': album_dir, 'tracks': tracks, 'artist': artist_name,
            'album': album_name, 'key': key, 'mbid': mbid,
        })
    scan_progress.close(complete=True)

    limit = int(cfg['max_per_run'])
    selected = candidates if limit == 0 else candidates[:limit]
    print(f'[artwork] album/cartelle audio: {len(groups)} | senza cover da cercare: '
          f'{len(candidates) + negative_skipped} | query da fare questa run: {len(selected)} | '
          f'no-result in cache: {negative_skipped} | verifica embedded non riuscita: {embedded_unknown}',
          flush=True)

    if dry_run:
        for item in selected[:20]:
            print(f"[dry-run][artwork] cercherei: {item['artist']} — {item['album']} -> {item['dir']}")
        if len(selected) > 20:
            print(f'[dry-run][artwork] ... e altre {len(selected) - 20} cartelle')
        return {'downloaded': 0, 'missing': len(candidates) + negative_skipped, 'attempted': 0}

    downloaded = attempted = not_found = network_errors = 0
    retry_seconds = int(cfg['retry_days']) * 86400
    basename = cfg['cover_basename']
    progress = _ProgressBar('download artwork', len(selected), 'album', stream=sys.stdout)
    for index, item in enumerate(selected, 1):
        progress.update(index)
        artist, album, album_dir, mbid = item['artist'], item['album'], item['dir'], item['mbid']
        attempted += 1
        image_result = None
        if mbid:
            image_result = _read_artwork_image(
                f'https://coverartarchive.org/release/{mbid}/front-500', timeout, min_bytes, max_bytes)

        itunes_ok = deezer_ok = False
        had_candidate_url = False
        if image_result is None:
            itunes_urls, itunes_ok = _itunes_artwork_urls(artist, album, timeout)
            had_candidate_url = had_candidate_url or bool(itunes_urls)
            for url in itunes_urls:
                image_result = _read_artwork_image(url, timeout, min_bytes, max_bytes)
                if image_result:
                    break
        if image_result is None:
            deezer_urls, deezer_ok = _deezer_artwork_urls(artist, album, timeout)
            had_candidate_url = had_candidate_url or bool(deezer_urls)
            for url in deezer_urls:
                image_result = _read_artwork_image(url, timeout, min_bytes, max_bytes)
                if image_result:
                    break

        if image_result is None:
            if itunes_ok and deezer_ok and not had_candidate_url and retry_seconds:
                negative[item['key']] = now + retry_seconds
                not_found += 1
            else:
                network_errors += 1
            continue

        data, ext = image_result
        target = album_dir / f'{basename}{ext}'
        # Second check to avoid clobbering a manually added cover during this run.
        if _has_local_album_art(album_dir, album):
            continue
        tmp = target.with_name(target.name + '.download.tmp')
        try:
            with tmp.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if _has_local_album_art(album_dir, album):
                tmp.unlink(missing_ok=True)
                continue
            os.replace(tmp, target)
            downloaded += 1
            negative.pop(item['key'], None)
            progress.clear()
            print(f'[artwork] scaricata: {target} ({len(data) // 1024} KiB)', flush=True)
        except FileExistsError:
            progress.clear()
            print(f'[artwork] file temporaneo già esistente, salto: {tmp}', file=sys.stderr)
        except OSError as e:
            progress.clear()
            print(f'[artwork] impossibile salvare {target}: {e}', file=sys.stderr)
        finally:
            tmp.unlink(missing_ok=True)

    progress.close(complete=True)
    # Limita la crescita della cache ed elimina voci ormai scadute.
    negative = {key: int(until) for key, until in negative.items() if int(until or 0) > now}
    cache['version'] = 1
    cache['not_found'] = negative
    _artwork_cache_save(cache)
    remaining = max(0, len(candidates) - len(selected) + negative_skipped + network_errors + not_found)
    print(f'[artwork] risultato: {downloaded} cover scaricate | query {attempted} | '
          f'non trovate/cached {negative_skipped + not_found} | errori/retry {network_errors} | '
          f'candidati rimasti per run future: {remaining}', flush=True)
    return {'downloaded': downloaded, 'missing': len(candidates) + negative_skipped,
            'attempted': attempted, 'network_errors': network_errors, 'not_found': not_found}

def _embedded_changelog_text():
    """Restituisce il changelog contenuto nel docstring del modulo, senza duplicarlo."""
    lines = (__doc__ or "").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == 'CHANGELOG':
            return "\n".join(lines[index:]).strip()
    return "CHANGELOG non trovato nel docstring dello script."


def _print_changelog():
    """Stampa l'intero changelog senza avviare la pipeline o creare un log di esecuzione."""
    print(_embedded_changelog_text())


def main():
    ap = argparse.ArgumentParser(description='Exportify CSV -> m3u per Jellyfin + manutenzione libreria')
    ap.add_argument('--version', action='version',
                    version=f'%(prog)s {VERSION}')
    ap.add_argument('--changelog', action='store_true',
                    help='stampa il changelog completo incorporato nello script ed esce')
    ap.add_argument('csv', nargs='*', help='CSV specifici (default: tutti in EXPORTIFY_DIR)')
    ap.add_argument('--build-spotify-proxies', action='store_true',
                    help='genera MP3 proxy compatti (64k default) e aggiorna manifest/preferiti Navidrome')
    ap.add_argument('--sync-proxy-favorites', action='store_true',
                    help='ricalcola liked.m3u dai brani preferiti di Navidrome; preview predefinita, --apply scrive')
    ap.add_argument('--sync-spotify-proxy-config', action='store_true',
                    help='confronta gli album della libreria con il catalogo Spotify; dry-run predefinito, '
                         '--apply aggiorna solo SPOTIFY_LOCAL_PROXY.auto_albums')
    ap.add_argument('--proxy-limit', type=int, default=0, metavar='N',
                    help='limita a N album nuovi da interrogare per --sync-spotify-proxy-config; 0 = tutti')
    ap.add_argument('--proxy-force-refresh', action='store_true',
                    help='ignora la cache Spotify e ripete le query catalogo')
    ap.add_argument('--proxy-report', metavar='FILE',
                    help='percorso report per --sync-spotify-proxy-config (default: logs/...)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-artwork-download', action='store_true',
                    help='salta la ricerca e il download automatico delle copertine album mancanti')
    ap.add_argument('--threshold', type=float, default=0.8,
                    help='cutoff fuzzy 0-1 (default 0.8)')
    ap.add_argument('--zip', action='append', metavar='ZIP|DIR',
                    help='zip Exportify (o cartella di zip), ripetibile; il nome deve iniziare '
                         'con l\'utente Navidrome, altrimenti l\'utente si ricava dall\'ID Spotify '
                         '(vedi SPOTIFY_USERS nel JSON). Default: tutti i *.zip di ZIP_DIR')
    ap.add_argument('--fetch', action='store_true',
                    help='prima di elaborare scarica gli zip da exportify.app (browser headless '
                         'Playwright; serve --fetch-login una volta per utente). Saltato con '
                         '--dry-run; se fallisce si usano gli zip gia\' presenti')
    ap.add_argument('--fetch-only', action='store_true',
                    help='scarica gli zip da exportify.app e basta (codice 2 = sessione scaduta)')
    ap.add_argument('--fetch-login', metavar='UTENTE',
                    help='login manuale una tantum per UTENTE Navidrome (browser visibile): '
                         'salva la sessione Spotify in .exportify_sessions/')
    ap.add_argument('--fetch-cookies', metavar='FILE', nargs='?', const='auto',
                    help='con --fetch-login: invece di aprire un browser importa i cookie di '
                         'spotify.com esportati da un browser normale (JSON Cookie-Editor o '
                         'cookies.txt). Il file e\' cercato anche in spotify_cookies/; senza nome '
                         'prende il piu\' recente <utente>*.json/.txt li\' dentro')
    ap.add_argument('--fetch-check', action='store_true',
                    help='verifica (headless) che le sessioni Exportify salvate siano ancora '
                         'valide; codice 2 se una e\' scaduta (utile in cron)')
    ap.add_argument('--fetch-list', action='store_true',
                    help='mostra le sessioni salvate e gli zip in ZIP_DIR')
    ap.add_argument('--fetch-headed', action='store_true',
                    help='--fetch / --fetch-only con il browser visibile (debug)')
    ap.add_argument('--fetch-timeout', type=int, default=30, metavar='MIN',
                    help='minuti massimi per l\'export di un utente (default 30)')
    ap.add_argument('--users', '--user', action='append', metavar='USER[,USER...]',
                    help='limita le fasi per-utente (playlist, fix-owners, dedupe-playlists, '
                         'star-liked) a questi utenti Navidrome; senza, TUTTI. Le fasi sulla '
                         'libreria condivisa non sono filtrate')
    ap.add_argument('--no-unzip', action='store_true', help='salta lo step unzip')
    ap.add_argument('--rebuild-cache', action='store_true', help='riscansione della libreria')
    ap.add_argument('--clean', action='store_true',
                    help='legacy: accettato per compatibilita; la pulizia avviene dopo estrazione riuscita')
    ap.add_argument('--only', help='importa SOLO queste playlist (nomi separati da virgola)')
    ap.add_argument('--skip', help='escludi queste playlist (nomi separati da virgola)')
    ap.add_argument('--pick', action='store_true', help='scegli interattivamente dalla lista')
    ap.add_argument('--force', action='store_true', help='riscrive TUTTE le playlist (ignora lo stato sync)')
    ap.add_argument('--skip-unify', action='store_true', help='salta il passo album_unify')
    ap.add_argument('--unify-only', action='store_true', help='esegui SOLO album_unify (niente playlist)')
    # --- fasi di manutenzione (log separati in logs/); senza flag: playlist+unify ---
    ap.add_argument('--playlists', action='store_true',
                    help='forza anche la fase playlist quando combini altre fasi')
    ap.add_argument('--all', action='store_true',
                    help='esegui TUTTE le fasi: diagnosi album DB (fuzzy solo report), fix-owners, '
                         'dedupe, tag/date, album repair, playlist e star-liked. --apply abilita le '
                         'azioni dedupe; --dry-run mantiene le riparazioni tag in anteprima. Se esistono '
                         'sessioni Exportify salvate scarica anche gli zip, come --fetch')
    ap.add_argument('--sync-only', action='store_true',
                    help='modalità quotidiana leggera: fetch + playlist M3U + fix proprietari + '
                         'star-liked; salta dedupe, mp3-vs-flac, conversione FLAC e manutenzione '
                         'tag/date/album. Non usarla insieme a --all o alle fasi dedupe.')
    ap.add_argument('--dedupe-playlists', action='store_true',
                    help='fase: elimina dal DB Navidrome le playlist con lo stesso nome ESATTO e lo '
                         'stesso proprietario, tenendo la piu\' recente (updated_at). Dry-run '
                         'salvo --apply')
    ap.add_argument('--dedupe-releases', action='store_true',
                    help='fase: unifica release duplicate (originale vs remaster)')
    ap.add_argument('--dedupe-tracks', action='store_true',
                    help='fase: duplicati di tracce nella STESSA cartella album')
    ap.add_argument('--mp3-vs-flac', action='store_true',
                    help='fase: elimina gli mp3 la cui stessa traccia esiste gia\' in FLAC '
                         '(stesso artista+album, titolo uguale, durata compatibile, '
                         'verifica waveform salvo --trust-format). Dry-run salvo --apply; '
                         'senza --hard-delete finiscono nel cestino DEDUPE_TRASH')
    ap.add_argument('--skip-artist-names', action='store_true',
                    help='salta la fase artist_names (un solo nome per artista CJK/coreano)')
    ap.add_argument('--apply', action='store_true',
                    help='dedupe (playlist, release, tracce) / mp3-vs-flac: esegui (default dry-run)')
    ap.add_argument('--corr', type=float, default=0.95,
                    help='dedupe: soglia correlazione waveform 0-1 (default 0.95)')
    ap.add_argument('--trust-format', action='store_true',
                    help='dedupe: stesso titolo + durate compatibili = duplicato '
                         '(senza verifica waveform; tiene il flac). Usare quando i '
                         'mp3 sono master diversi della stessa canzone')
    ap.add_argument('--max-dur-diff', type=float, default=10.0,
                    help='dedupe: max differenza durata in secondi (default 10; '
                         'vale anche il 5%% relativo)')
    ap.add_argument('--compare', nargs=2, metavar=('FILE1', 'FILE2'),
                    help='diagnostica: confronta due file (durate + correlazione '
                         'waveform) e dichiara se sono la stessa incisione')
    ap.add_argument('--hard-delete', action='store_true',
                    help='dedupe: cancella invece di spostare nel cestino')
    ap.add_argument('--artist', help='dedupe: solo questo artista (nome cartella)')
    ap.add_argument('--album', help='fix-collab-artists / check-albums: solo gli album il cui nome '
                                    'contiene questo testo')
    ap.add_argument('--fix-collab-artists', action='store_true',
                    help='fase: album collab mostrati come "A • A & B" in Navidrome: lascia in ALBUMARTIST '
                         'solo i componenti ["A", "B"] (FLAC). Dry-run salvo --apply; --album/--artist '
                         'restringono')
    ap.add_argument('--check-albums', action='store_true',
                    help='confronta gli album del DB con MusicBrainz e integra il report completo in '
                         'logs/mancanti_<data>.txt. Solo lettura; '
                         'la prima run e\' lenta (1 richiesta/s), poi c\'e\' la cache')
    ap.add_argument('--mb-no-search', action='store_true',
                    help='check-albums: controlla solo gli album con MUSICBRAINZ_ALBUMID, senza cercare '
                         'gli altri per artista+album')
    ap.add_argument('--diagnose-album-splits', action='store_true',
                    help='diagnostica read-only del DB: album duplicati/spezzati, fuzzy candidati (review only), artisti CJK e separatori ; / ,')
    ap.add_argument('--repair-album-groups', action='store_true',
                    help='ripara tag album/artisti, Unknown Artist e artisti separati da ; / , se confermati dal DB; preview di default. In --all e integrato')
    ap.add_argument('--clean-empty', action='store_true',
                    help='fase: rimuovi cartelle senza audio vuote da >24h')
    ap.add_argument('--star-liked', action='store_true',
                    help='fase: stella brani di liked/liked songs, album di saved albums e artisti presenti '
                         '(password per utente in ND_PASS_<UTENTE>)')
    ap.add_argument('--fix-owners', nargs='?', const='', default=None, metavar='USER',
                    help='fase: assegna le playlist importate da m3u al proprietario giusto (cartella '
                         'utente in Playlists/); USER = proprietario di quelle fuori dalle cartelle '
                         'utente (default: DEFAULT_USER)')
    ap.add_argument('--fix-all-playlist-owners', nargs='?', const='', default=None, metavar='USER',
                    help='utility: assegna TUTTE le playlist (anche UI) a USER; preview di default, --apply modifica il DB')
    ap.add_argument('--fix-flac-safe', action='store_true',
                    help='utility: ripara i .flac.flac validi e pulisce .backup; preview di default, --apply modifica')
    ap.add_argument('--lidarr-folder-fix', action='store_true',
                    help='utility: riconcilia i path artisti Lidarr con le cartelle; preview di default, --apply aggiorna')
    ap.add_argument('--lidarr-import-slskd', action='store_true',
                    help='utility: invia DownloadedAlbumsScan a Lidarr, corregge i path e conta failed_imports')
    ap.add_argument('--lidarr-url', metavar='URL',
                    help='override per le utility Lidarr (default LIDARR_URL nell’ambiente/.env)')
    ap.add_argument('--library-root', metavar='PATH',
                    help='override root della libreria per --fix-flac-safe, utility Lidarr e proxy Spotify')
    ap.add_argument('--lidarr-container-root', metavar='PATH',
                    help='prefisso path visto da Lidarr (default /music o LIDARR_CONTAINER_ROOT)')
    ap.add_argument('--slskd-import-folder', metavar='PATH',
                    help='cartella dentro Lidarr da importare (default /downloads/slskd)')
    ap.add_argument('--slskd-failed-folder', metavar='PATH',
                    help='cartella host failed_imports da controllare dopo l’import')
    ap.add_argument('--lb-dedup', metavar='UTENTE',
                    help='utility: controlla ascolti duplicati ListenBrainz; token richiesto in LISTENBRAINZ_TOKEN')
    ap.add_argument('--lb-delete', action='store_true',
                    help='ListenBrainz: cancella gli ascolti duplicati trovati da --lb-dedup (irreversibile)')
    ap.add_argument('--lb-window', type=int, default=5, metavar='SEC',
                    help='ListenBrainz: ascolti identici a distanza massima di SEC secondi (default 5)')
    ap.add_argument('--lb-days', type=int, default=365, metavar='GIORNI',
                    help='ListenBrainz: storico da esaminare (default 365 giorni)')
    ap.add_argument('--no-scan', action='store_true',
                    help='non avviare lo scan FULL di Navidrome a fine lavoro')
    ap.add_argument('--rebuild-album', metavar='NOME',
                    help="cancella l'album dal DB Navidrome (match parziale); "
                         "il full scan lo ricostruisce dai tag dei file")
    ap.add_argument('--missing', nargs='?', const='-', metavar='FILE',
                    help="elenca TUTTE le tracce mancanti, ricalcolate ora dai CSV contro la "
                         "libreria (niente .missing.txt vecchi). FILE = dove salvarle "
                         "(senza: a schermo)")
    ap.add_argument('--explain', metavar='ARTIST|||ALBUM|||TITLE',
                    help='diagnostica: mostra candidati e punteggi del matching '
                         'per una riga (album/titolo come nel CSV)')
    ap.add_argument('--skip-fix-dates', action='store_true',
                    help='salta la fase fix_date_tags dopo album_unify')
    ap.add_argument('--skip-romaji', action='store_true',
                    help='salta la fase romaji_tags (bilingue kanji+romaji)')
    ap.add_argument('--skip-date-heal', action='store_true',
                    help='salta la fase date_heal (correzione automatica date '
                         'da MusicBrainz/nfo/cartella) prima di album_unify')
    ap.add_argument('--flac-16bit', action='store_true',
                    help='fase: converti/ricomprimi i FLAC (24->16bit livello 8, '
                         '16bit male compressi)')
    args = ap.parse_args()
    if args.changelog:
        _print_changelog()
        return

    # UN solo log per tutta l'esecuzione: console + file, fasi comprese
    logf = open_run_log(_log_command_tag(sys.argv[1:], tuple(getattr(ap, '_option_string_actions', {}))))
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Tee(old_out, logf), Tee(old_err, logf)
    # Apply the JSON palette before _run prints its startup banner and before the first
    # measured phase heading. load_user_config still loads the remaining settings normally.
    _preload_terminal_colors()
    previous_signal_handlers = _install_progress_signal_handlers()
    global _RUN_STARTED_AT, _PHASE_TIMINGS, _RUN_INTERRUPTED, _RUN_FAILED_PHASES
    _RUN_STARTED_AT = time.perf_counter()
    _PHASE_TIMINGS.clear()
    _RUN_INTERRUPTED = False
    _RUN_FAILED_PHASES.clear()
    try:
        _run(args)
        if _RUN_FAILED_PHASES:
            failed = ', '.join(dict.fromkeys(name for name, _status in _RUN_FAILED_PHASES))
            print(f'[ERRORE] pipeline completata con {len(_RUN_FAILED_PHASES)} fase/i non riuscita/e: {failed}',
                  file=sys.stderr, flush=True)
            raise SystemExit(1)
    except SystemExit as e:
        if isinstance(e.code, str):          # sys.exit("msg") altrimenti uscirebbe dal log
            print(e.code, file=sys.stderr)
            raise SystemExit(1)
        raise
    except KeyboardInterrupt:
        _RUN_INTERRUPTED = True
        _cleanup_active_progress_bars()
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
    finally:
        # First remove the pinned row; then timing/log messages can use the full terminal.
        _cleanup_active_progress_bars()
        _restore_progress_signal_handlers(previous_signal_handlers)
        flush_probe_cache()
        _print_timing_summary()
        print(f"[i] log: {RUN_LOG_PATH}", file=sys.stderr)
        sys.stdout, sys.stderr = old_out, old_err
        logf.close()


def _prune_stale_m3u_after_fetch(groups, args):
    """Rimuove vecchie M3U solo per utenti con fetch+estrazione fresca e conversioni valide.

    Le M3U vengono trattate come output derivati dai CSV selezionati durante questa run. Le
    cartelle che appartengono a un altro utente sono escluse quando l'utente di default usa
    il layout storico Playlists/ senza sottocartella. Se anche un solo CSV selezionato fallisce,
    la pulizia di quell'utente viene sospesa per non eliminare una playlist valida per errore.
    I percorsi eliminati sono salvati per la successiva fase separata di pulizia DB Navidrome.
    """
    global _STALE_M3U_REMOVED_PATHS
    _STALE_M3U_REMOVED_PATHS = []
    if args.dry_run or not _FRESH_EXTRACTED_USERS:
        return
    if args.only or args.skip or args.pick or args.csv or args.no_unzip:
        print("[i] pulizia M3U stale saltata: run limitata da --only/--skip/--pick/CSV/--no-unzip",
              file=sys.stderr)
        return

    users_by_key = {u.casefold(): u for u, _files in groups}
    if not users_by_key:
        return
    protected_user_dirs = {u.casefold() for u in known_users()}
    protected_user_dirs.update(FETCH_IGNORED_USERS)
    protected_user_dirs.update(str(u).casefold() for u in SPOTIFY_USERS.values())
    total_removed = 0
    removed_paths_all = []
    for user_key in sorted(_FRESH_EXTRACTED_USERS & users_by_key.keys()):
        user = users_by_key[user_key]
        if user_key in _M3U_GENERATION_FAILED_USERS:
            print(f"[!] {user}: pulizia M3U sospesa: almeno un CSV selezionato non e' stato convertito "
                  "correttamente", file=sys.stderr)
            continue
        root = _user_playlist_root(user)
        if not root.is_dir():
            continue
        expected = {_normal_path(p) for p in _GENERATED_M3U_PATHS.get(user_key, set())}
        other_users = protected_user_dirs - {user_key}
        removed = []
        try:
            candidates = sorted(p for p in root.rglob('*') if p.suffix.casefold() == '.m3u' and (p.is_file() or p.is_symlink()))
        except OSError as e:
            print(f"[warn] {user}: impossibile elencare M3U per pulizia: {e}", file=sys.stderr)
            continue
        for path in candidates:
            # Il layout storico di DEFAULT_USER condivide Playlists/ con le cartelle utenti:
            # non toccare mai la sottocartella di un altro utente.
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if len(rel.parts) > 1 and rel.parts[0].casefold() in other_users:
                continue
            if _normal_path(path) in expected:
                continue
            try:
                if path.is_symlink() or path.is_file():
                    path.unlink()
                    path.with_suffix('.missing.txt').unlink(missing_ok=True)
                    for artwork in _playlist_sidecar_paths(path):
                        artwork.unlink(missing_ok=True)
                    removed.append(path)
            except OSError as e:
                print(f"[warn] {user}: M3U obsoleta non rimossa ({path}): {e}", file=sys.stderr)
        if removed:
            expected_stems = {p.stem for p in expected}
            for path in removed:
                if path.stem not in expected_stems:
                    SYNC_STATE.pop(_sync_key(user, path.stem), None)
            total_removed += len(removed)
            removed_paths_all.extend(removed)
            sample = ', '.join(p.name for p in removed[:8])
            if len(removed) > 8:
                sample += f" ... (+{len(removed)-8})"
            print(f"[i] {user}: rimosse {len(removed)} M3U non presenti tra i CSV selezionati dal fetch: "
                  f"{sample}", file=sys.stderr)
        else:
            print(f"[i] {user}: nessuna M3U obsoleta da rimuovere", file=sys.stderr)
    _STALE_M3U_REMOVED_PATHS = removed_paths_all
    if total_removed:
        print(f"[i] pulizia M3U completata: {total_removed} file obsoleti rimossi", file=sys.stderr)


def _generate_m3u_playlists(groups, by_full, by_artist, by_strict, path_qual, args, selected_users):
    """Genera le M3U di brani; saved albums e' una raccolta album, non una playlist di tracce."""
    _GENERATED_M3U_PATHS.clear()
    _M3U_GENERATION_FAILED_USERS.clear()
    ok = total = album_collections = 0
    for user, files in groups:
        if len(groups) > 1 or user != DEFAULT_USER:
            print(f"=== playlist di {user} ({len(files)} CSV) ===", file=sys.stderr)
        for f in files:
            if _norm_playlist_name(Path(f).stem.replace('_', ' ')) in {'saved albums', 'saved album'}:
                album_collections += 1
                print(f"[i] {f.name}: raccolta album riconosciuta; non genera una M3U di brani")
                continue
            total += 1
            try:
                if process_csv(f, by_full, by_artist, by_strict, path_qual, args, user=user):
                    ok += 1
                else:
                    _M3U_GENERATION_FAILED_USERS.add(user.casefold())
            except Exception as e:
                _M3U_GENERATION_FAILED_USERS.add(user.casefold())
                print(f"[ERRORE] {f.name}: {type(e).__name__}: {e}", file=sys.stderr)
    print(f"[i] fatto: {ok}/{total} playlist M3U generate" +
          (f"; {album_collections} raccolte album riconosciute" if album_collections else ""),
          file=sys.stderr)
    write_missing_report(partial=bool(args.only or args.skip or args.csv or selected_users is not None))
    return ok, total


def _reconcile_navidrome_album_changes(before, library_root=None, planned_target_phases=True):
    """Dopo uno scan riuscito: report album, riparazione mirata e scan incrementale finale."""
    global _PHASE_PROGRESS_TOTAL
    after = _snapshot_navidrome_albums()
    if before is None or after is None:
        print('[warn] snapshot Navidrome pre/post scan non disponibile; evito di trattare l’intera libreria '
              'come nuova e salto la riparazione mirata', file=sys.stderr, flush=True)
        if planned_target_phases:
            remaining = _PHASE_PROGRESS_TOTAL - _PHASE_PROGRESS_INDEX
            reducible = min(7, max(0, remaining - 1))
            _PHASE_PROGRESS_TOTAL = max(_PHASE_PROGRESS_INDEX, _PHASE_PROGRESS_TOTAL - reducible)
        return True
    changes = _diff_navidrome_albums(before, after)
    _print_navidrome_album_diff(changes)
    base = Path(library_root) if library_root else LIBRARY_ROOT
    base = base.expanduser().resolve()
    album_dirs, files_only = _affected_album_paths(changes, base)
    if not changes.get('affected') or not album_dirs or not files_only:
        if changes.get('affected'):
            print('[warn] nuovi/aggiornati album rilevati ma non sono stati risolti file host; '
                  'riparazione mirata non eseguita', file=sys.stderr, flush=True)
        # Il piano --all prevede sei fasi mirate + scan rapido. Se non ci sono album
        # toccati, rimuovi queste sette fasi dal totale previsto prima della fase successiva.
        if planned_target_phases:
            remaining = _PHASE_PROGRESS_TOTAL - _PHASE_PROGRESS_INDEX
            # lascia in piano la diagnostica post-scan se e' quella che segue il helper
            reducible = min(7, max(0, remaining - 1))
            _PHASE_PROGRESS_TOTAL = max(_PHASE_PROGRESS_INDEX, _PHASE_PROGRESS_TOTAL - reducible)
        return True

    print(f'[i] riparazione mirata: {len(album_dirs)} album/cartelle, '
          f'{len(files_only)} file audio', flush=True)
    # Tutte le fasi ricevono esclusivamente le cartelle/file coinvolti nel diff post-scan.
    run_phase('targeted_date_heal', run_date_heal, dry_run=False, base=base,
              album_dirs_only=album_dirs)
    run_phase('targeted_romaji_tags', run_romaji_tags, dry_run=False, base=base,
              files_only=files_only)
    run_phase('targeted_artist_names', run_unify_artists, dry_run=False, base=base,
              files_only=files_only)
    run_phase('targeted_album_unify', run_unify, dry_run=False, base=base,
              album_dirs_only=album_dirs)
    run_phase('targeted_repair_album_groups', run_repair_album_groups, dry_run=False,
              base=base, include_existing_passes=False,
              album_dirs_only=album_dirs, files_only=files_only)
    run_phase('targeted_fix_date_tags', run_fix_dates, dry_run=False, base=base,
              files_only=files_only)
    quick_ok = bool(run_phase('navidrome_scan_after_album_repair', run_navidrome_scan,
                              full_scan=False, prune_refs=False))
    if not quick_ok:
        print('[ERRORE] scan incrementale dopo la riparazione album non riuscito',
              file=sys.stderr, flush=True)
    return quick_ok


def _scan_before_favorites(users, full_scan=True, reconcile_changes=False, library_root=None):
    """Esegue la scan; in --all confronta gli album e riapplica solo i tag degli album toccati."""
    candidates = [SUBSONIC_USER]
    candidates.extend(users if users is not None else (_db_users() or []))
    seen = set()
    for username in candidates:
        if not username or username.casefold() in seen:
            continue
        seen.add(username.casefold())
        password, _ = _user_password(username)
        if not password:
            continue
        old_user, old_password = SUBSONIC_USER, SUBSONIC_PASS
        globals()['SUBSONIC_USER'], globals()['SUBSONIC_PASS'] = username, password
        try:
            before = _snapshot_navidrome_albums() if reconcile_changes and full_scan else {}
            scan_ok = bool(run_phase('navidrome_scan_before_stars', run_navidrome_scan,
                                     full_scan=full_scan, prune_refs=full_scan))
            if not scan_ok:
                return False
            if reconcile_changes and full_scan:
                if not _reconcile_navidrome_album_changes(before, library_root=library_root,
                                                           planned_target_phases=True):
                    return False
            return True
        finally:
            globals()['SUBSONIC_USER'], globals()['SUBSONIC_PASS'] = old_user, old_password
    print('[warn] scan pre-favorites saltata: nessuna password ND_PASS/ND_PASS_<utente> disponibile; '
          'le playlist appena generate potrebbero non essere ancora visibili all’API', file=sys.stderr)
    return None


def _spotify_proxy_norm(value):
    """Normalizzazione stretta per nome artista/album ignorando maiuscole e punteggiatura."""
    return norm_bare(str(value or ''))


def _spotify_proxy_artist_keys(value):
    """Nome artista e varianti note (alias, gruppi, lettura romaji)."""
    raw = str(value or '').strip()
    if not raw:
        return set()
    n = norm(raw)
    out = {_spotify_proxy_norm(raw), _spotify_proxy_norm(n)}
    if n:
        out.add(_spotify_proxy_norm(_canon(n)))
        preferred = _preferred_name(n)
        if preferred:
            out.add(_spotify_proxy_norm(preferred))
        if n in ALIASES:
            out.add(_spotify_proxy_norm(ALIASES[n]))
        for table in (NAME_TRANSLATIONS, NAME_FIXES):
            for alias, target in table.items():
                if norm(target) == n:
                    out.add(_spotify_proxy_norm(alias))
        for alias, target in ALIASES.items():
            if target == n:
                out.add(_spotify_proxy_norm(alias))
        for group in ARTIST_GROUPS:
            if n in group:
                out.update(_spotify_proxy_norm(x) for x in group)
        romanized = to_romaji(n)
        if romanized:
            out.add(_spotify_proxy_norm(romanized))
    return {x for x in out if x}


def _spotify_proxy_rel_album(rel):
    """Nome cartella album per Artist/Album/CD1/track.ext o Artist/Album/track.ext."""
    if len(rel) >= 4 and _DISC_DIR.match(rel[-2]):
        return rel[-3]
    return rel[-2] if len(rel) >= 2 else ''


def _spotify_proxy_title(path, tags):
    title = str(tags.get('title') or '').strip()
    if not title:
        title = re.sub(r'^\s*\d{1,3}\s*[-._: ]+\s*', '', Path(path).stem).strip()
    return title or Path(path).stem


_SPOTIFY_CATALOG_TOKEN = None
_SPOTIFY_CATALOG_TOKEN_UNTIL = 0


def _spotify_proxy_items():
    """Unisce i criteri manuali e automatici, mantenendo prioritari quelli manuali."""
    out, seen = [], set()
    for field in ('albums', 'auto_albums'):
        for item in SPOTIFY_LOCAL_PROXY_CONFIG.get(field, []) or []:
            artist, album = str(item.get('artist') or '').strip(), str(item.get('album') or '').strip()
            key = (_spotify_proxy_norm(artist), _spotify_proxy_norm(album))
            if artist and album and key not in seen:
                seen.add(key)
                out.append({'artist': artist, 'album': album, '_source': field})
    return out


def _spotify_catalog_cache_path():
    return CACHE_DIR / 'spotify_album_catalog_cache.json'


def _spotify_catalog_cache_load():
    try:
        data = json.loads(_spotify_catalog_cache_path().read_text(encoding='utf-8'))
        if data.get('version') == 1 and isinstance(data.get('items'), dict):
            return data['items']
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _spotify_catalog_cache_save(cache):
    path = _spotify_catalog_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f'.tmp-{os.getpid()}')
        tmp.write_text(json.dumps({'version': 1, 'items': cache}, ensure_ascii=False,
                                  separators=(',', ':')), encoding='utf-8')
        os.replace(tmp, path)
    except OSError as e:
        print(f'[warn] cache catalogo Spotify non salvata: {e}', file=sys.stderr)


def _spotify_catalog_token():
    """OAuth client-credentials token per Search API; credenziali solo da ambiente/.env."""
    global _SPOTIFY_CATALOG_TOKEN, _SPOTIFY_CATALOG_TOKEN_UNTIL
    if _SPOTIFY_CATALOG_TOKEN and time.time() < _SPOTIFY_CATALOG_TOKEN_UNTIL - 30:
        return _SPOTIFY_CATALOG_TOKEN
    client_id = os.environ.get('SPOTIFY_CLIENT_ID', '').strip()
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET', '').strip()
    if not client_id or not client_secret:
        raise RuntimeError('mancano SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET nel .env o nell ambiente')
    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode('ascii')
    req = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode('ascii'),
        headers={'Authorization': 'Basic ' + basic,
                 'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')[:240]
        if 'premium' in detail.casefold() and ('required' in detail.casefold() or 'active' in detail.casefold()):
            raise RuntimeError('Spotify richiede un abbonamento Premium attivo al proprietario dell’app '
                               'per le app in Development Mode (regole 2026); nessun JSON aggiornato. '
                               'Un catalogo interamente in cache può essere esaminato offline.') from e
        raise RuntimeError(f'Spotify OAuth HTTP {e.code}: {detail}') from e
    if not data.get('access_token'):
        raise RuntimeError(f'Spotify OAuth senza access_token: {str(data)[:200]}')
    _SPOTIFY_CATALOG_TOKEN = data['access_token']
    _SPOTIFY_CATALOG_TOKEN_UNTIL = time.time() + int(data.get('expires_in') or 3600)
    return _SPOTIFY_CATALOG_TOKEN


def _spotify_catalog_search(query, market, token):
    url = 'https://api.spotify.com/v1/search?' + urllib.parse.urlencode({
        'q': query, 'type': 'album', 'market': market, 'limit': 10, 'offset': 0,
    })
    last_error = None
    for attempt in range(5):
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
                                                   'User-Agent': f'exportify-to-m3u/{VERSION}'})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode('utf-8'))
            items = payload.get('albums', {}).get('items', []) or []
            time.sleep(0.2)  # evitare burst di richieste al catalogo nei primi scan
            return items
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                global _SPOTIFY_CATALOG_TOKEN, _SPOTIFY_CATALOG_TOKEN_UNTIL
                _SPOTIFY_CATALOG_TOKEN = None
                _SPOTIFY_CATALOG_TOKEN_UNTIL = 0
                token = _spotify_catalog_token()
                last_error = 'token scaduto, rinnovato'
            elif e.code == 429:
                try:
                    wait = int(e.headers.get('Retry-After') or 2)
                except (TypeError, ValueError):
                    wait = 2
                if wait > 120:
                    raise RuntimeError(f'Spotify rate limit: Retry-After={wait}s, fermo per prudenza') from e
                time.sleep(max(1, wait))
                last_error = f'HTTP 429, atteso {wait}s'
            elif e.code in (500, 502, 503, 504):
                last_error = f'HTTP {e.code}'
                if attempt < 4:
                    time.sleep(2 ** attempt)
            else:
                detail = e.read().decode('utf-8', 'replace')[:240]
                if 'premium' in detail.casefold() and ('required' in detail.casefold() or 'active' in detail.casefold()):
                    raise RuntimeError('Spotify richiede un abbonamento Premium attivo al proprietario dell’app '
                                       'per le app in Development Mode (regole 2026); nessun JSON aggiornato. '
                                       'Un catalogo interamente in cache può essere esaminato offline.') from e
                raise RuntimeError(f'Spotify Search API HTTP {e.code}: {detail}') from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = f'{type(e).__name__}: {e}'
            if attempt < 4:
                time.sleep(2 ** attempt)
    raise RuntimeError(f'Spotify Search API non disponibile dopo i retry: {last_error}')


def _proxy_similarity(left, right):
    left, right = _spotify_proxy_norm(left), _spotify_proxy_norm(right)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    seq = difflib.SequenceMatcher(None, left, right).ratio()
    lt, rt = set(left.split()), set(right.split())
    token = len(lt & rt) / max(len(lt), len(rt)) if lt and rt else 0.0
    return max(seq, token)


def _proxy_query_variants(artist, album):
    """Query originali e al massimo una query con alias/romanizzazione/traduzione nota."""
    raw = (artist, album)
    variants = [raw]
    alts = []
    for value in raw:
        preferred = _preferred_name(value)
        if not preferred:
            preferred = _auto_translation_phonetic(value)
        alts.append(preferred or value)
    if tuple(alts) != raw:
        variants.append(tuple(alts))
    # Search is tolerant but the third, unquoted query catches localized / mixed-script cases.
    if len(variants) == 1:
        roman = tuple(_auto_translation_phonetic(x) or x for x in raw)
        if roman != raw:
            variants.append(roman)
    queries, seen = [], set()
    for a, b in variants:
        q = f'artist:"{a}" album:"{b}"'
        if q not in seen:
            seen.add(q)
            queries.append(q)
    loose = f'{artist} {album}'.strip()
    if loose and loose not in seen:
        queries.append(loose)
    return queries[:3]


def _score_spotify_album_candidate(artist, album, item):
    target_artist_keys = _spotify_proxy_artist_keys(artist)
    # Prefer English/official/local aliases and the phonetic fallback for album names.
    target_album_keys = {_spotify_proxy_norm(album)}
    preferred = _preferred_name(album)
    if preferred:
        target_album_keys.add(_spotify_proxy_norm(preferred))
    roman = _auto_translation_phonetic(album)
    if roman:
        target_album_keys.add(_spotify_proxy_norm(roman))
    candidate_artists = [str(a.get('name') or '') for a in item.get('artists', [])]
    artist_score = max((_proxy_similarity(a, k) for a in candidate_artists
                        for k in target_artist_keys), default=0.0)
    album_score = max((_proxy_similarity(item.get('name', ''), k) for k in target_album_keys), default=0.0)
    combined = 0.58 * album_score + 0.42 * artist_score
    external_url = (item.get('external_urls') or {}).get('spotify', '')
    return {
        'name': str(item.get('name') or ''), 'artists': candidate_artists,
        'album_score': round(album_score, 3), 'artist_score': round(artist_score, 3),
        'score': round(combined, 3), 'release_date': str(item.get('release_date') or ''),
        'url': external_url,
    }


def _classify_spotify_candidates(candidates):
    """Solo match forti = presente; vicini incerti = review, mai auto-proxy."""
    candidates.sort(key=lambda x: (x['score'], x['album_score'], x['artist_score']), reverse=True)
    if not candidates:
        return 'not_found', []
    if any((c['album_score'] >= 0.92 and c['artist_score'] >= 0.82) or
           (c['album_score'] >= 0.97 and c['artist_score'] >= 0.72) for c in candidates):
        return 'found', candidates[:3]
    if any(c['album_score'] >= 0.72 and c['artist_score'] >= 0.48 for c in candidates):
        return 'review', candidates[:5]
    # Un album dal titolo quasi identico ma con artista molto diverso merita verifica manuale.
    if any(c['album_score'] >= 0.88 for c in candidates):
        return 'review', candidates[:5]
    return 'not_found', candidates[:3]


def _scan_library_album_folders(root):
    """Un record per cartella artista/album, contando i file audio senza leggere ogni tag."""
    rels = _walk_audio(root, INDEX_EXT)
    albums = {}
    for rel in rels:
        if len(rel) < 2:
            continue
        artist = str(rel[0]).strip()
        album = str(_spotify_proxy_rel_album(rel) or '').strip()
        if not artist or not album or artist.startswith('.'):
            continue
        key = (_spotify_proxy_norm(artist), _spotify_proxy_norm(album))
        if not key[0] or not key[1]:
            continue
        row = albums.setdefault(key, {'artist': artist, 'album': album, 'tracks': 0})
        row['tracks'] += 1
    return [albums[k] for k in sorted(albums)]


def _atomic_write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.tmp-{os.getpid()}')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def run_sync_spotify_proxy_config(dry_run=True, apply=False, library_root=None,
                                  limit=0, force_refresh=False, report_path=None):
    """Confronta gli album disco con Spotify Search e propone/aggiorna auto_albums.

    Nessuna modifica al JSON live senza apply=True. Se anche un solo controllo fallisce, non
    sostituisce l'elenco automatico: un timeout non deve sembrare una prova di assenza dal catalogo.
    """
    if not SPOTIFY_LOCAL_PROXY_CONFIG.get('enabled', True):
        print('[ERRORE] SPOTIFY_LOCAL_PROXY.enabled=false: scansione annullata')
        return {'errors': 1}
    root = Path(library_root or LIBRARY_ROOT).expanduser().resolve()
    if not root.is_dir():
        print(f'[ERRORE] root della libreria non accessibile: {root}', file=sys.stderr)
        return {'errors': 1}
    albums = _scan_library_album_folders(root)
    if not albums:
        print(f'[ERRORE] nessun album audio trovato sotto {root}', file=sys.stderr)
        return {'errors': 1}

    cfg_path = _USER_CFG
    try:
        config_existed = cfg_path.exists()
        original_bytes = cfg_path.read_bytes() if config_existed else None
        original_config = json.loads(original_bytes.decode('utf-8')) if original_bytes is not None else {}
        original_config_digest = (hashlib.sha256(original_bytes).hexdigest()
                                  if original_bytes is not None else None)
    except Exception as e:
        print(f'[ERRORE] impossibile leggere {cfg_path}: {e}', file=sys.stderr)
        return {'errors': 1}

    def config_unchanged_since_scan_start():
        """Evita di sovrascrivere modifiche manuali fatte mentre lo scan era in corso."""
        try:
            exists_now = cfg_path.exists()
            if exists_now != config_existed:
                return False
            if not exists_now:
                return True
            return hashlib.sha256(cfg_path.read_bytes()).hexdigest() == original_config_digest
        except OSError:
            return False

    proxy_json = original_config.setdefault('SPOTIFY_LOCAL_PROXY', {})
    if not isinstance(proxy_json, dict):
        print('[ERRORE] SPOTIFY_LOCAL_PROXY nel JSON non e\' un oggetto', file=sys.stderr)
        return {'errors': 1}

    market = str(os.environ.get('SPOTIFY_MARKET') or proxy_json.get('market') or 'IT').upper()
    if not re.fullmatch(r'[A-Z]{2}', market):
        print(f'[ERRORE] market Spotify non valido: {market!r}', file=sys.stderr)
        return {'errors': 1}
    try:
        cache_days = int(proxy_json.get('catalog_cache_days', 90))
    except (TypeError, ValueError):
        print('[ERRORE] SPOTIFY_LOCAL_PROXY.catalog_cache_days deve essere un intero', file=sys.stderr)
        return {'errors': 1}
    if not 0 <= cache_days <= 3650:
        print('[ERRORE] SPOTIFY_LOCAL_PROXY.catalog_cache_days deve essere tra 0 e 3650', file=sys.stderr)
        return {'errors': 1}
    ttl = cache_days * 86400
    cache = _spotify_catalog_cache_load()
    now = int(time.time())

    def cache_is_fresh(entry):
        if ttl <= 0 or not isinstance(entry, dict):
            return False
        try:
            checked_at = int(entry.get('checked_at') or 0)
        except (TypeError, ValueError):
            return False
        return checked_at > 0 and now - checked_at <= ttl
    manual = list(proxy_json.get('albums') or [])
    previous_auto = list(proxy_json.get('auto_albums') or [])
    manual_keys = {(_spotify_proxy_norm(x.get('artist')), _spotify_proxy_norm(x.get('album')))
                   for x in manual if isinstance(x, dict)}
    manual_keys.discard(('', ''))
    # Fail early, rather than printing one error per album, if this scan needs uncached API data
    # but OAuth credentials are missing. A complete cache can still be reviewed offline.
    needs_query = []
    for row in albums:
        key = (_spotify_proxy_norm(row['artist']), _spotify_proxy_norm(row['album']))
        if key in manual_keys:
            continue
        ident = hashlib.sha256((market + '\0' + key[0] + '\0' + key[1]).encode()).hexdigest()
        entry = None if force_refresh else cache.get(ident)
        if (not cache_is_fresh(entry) or
                entry.get('status') not in {'found', 'review', 'not_found'}):
            needs_query.append(row)
    if limit:
        needs_query = needs_query[:limit]
    if needs_query and (not os.environ.get('SPOTIFY_CLIENT_ID') or not os.environ.get('SPOTIFY_CLIENT_SECRET')):
        print('[ERRORE] la scansione richiede nuove query Spotify ma mancano SPOTIFY_CLIENT_ID e/o '
              'SPOTIFY_CLIENT_SECRET nel .env. Nessun JSON modificato.', file=sys.stderr)
        print(f'[i] {len(needs_query)} album richiedono una query non presente in cache.', file=sys.stderr)
        return {'errors': 1}

    print(f'[i] confronto {len(albums)} album della libreria con Spotify, mercato {market}')
    # Avoid acquiring credentials for a fully cached offline review; acquire on first cache miss.
    token = None
    records, errors, checked = [], 0, 0
    uncached_checked = 0
    progress = _ProgressBar('confronto catalogo Spotify', len(albums), 'album', stream=sys.stdout)
    for idx, album_row in enumerate(albums, 1):
        progress.update(idx)
        artist, album = album_row['artist'], album_row['album']
        key = (_spotify_proxy_norm(artist), _spotify_proxy_norm(album))
        identity = hashlib.sha256((market + '\0' + key[0] + '\0' + key[1]).encode()).hexdigest()
        if key in manual_keys:
            records.append({**album_row, 'status': 'manual_keep', 'candidates': []})
            continue
        entry = None if force_refresh else cache.get(identity)
        if not cache_is_fresh(entry):
            entry = None
        if isinstance(entry, dict) and entry.get('status') in {'found', 'review', 'not_found'}:
            status = entry['status']
            candidates = entry.get('candidates', [])
        else:
            if limit and uncached_checked >= limit:
                records.append({**album_row, 'status': 'not_checked_limit', 'candidates': []})
                continue
            uncached_checked += 1
            try:
                if token is None:
                    token = _spotify_catalog_token()
                results = []
                seen_results = set()
                for query in _proxy_query_variants(artist, album):
                    for item in _spotify_catalog_search(query, market, token):
                        sid = (item.get('id') or '')
                        dedupe_key = sid or (_spotify_proxy_norm(item.get('name')), tuple(
                            _spotify_proxy_norm(a.get('name')) for a in item.get('artists', [])))
                        if dedupe_key in seen_results:
                            continue
                        seen_results.add(dedupe_key)
                        results.append(_score_spotify_album_candidate(artist, album, item))
                    status_now, top_now = _classify_spotify_candidates(list(results))
                    if status_now == 'found':
                        break
                status, candidates = _classify_spotify_candidates(results)
                cache[identity] = {'artist': artist, 'album': album, 'market': market,
                                   'status': status, 'candidates': candidates, 'checked_at': now}
                checked += 1
                # Persist regularly, so interruption or rate limiting loses little progress.
                if checked % 10 == 0:
                    _spotify_catalog_cache_save(cache)
            except Exception as e:
                errors += 1
                records.append({**album_row, 'status': 'error', 'error': f'{type(e).__name__}: {e}',
                                'candidates': []})
                print(f'[ERRORE] {artist} — {album}: {type(e).__name__}: {e}', file=sys.stderr)
                # Errori API sono di norma globali (credenziali, quota, rete); fermarsi riduce
                # richieste inutili e garantisce che l'elenco automatico non venga rimpiazzato.
                for remaining in albums[idx:]:
                    rkey = (_spotify_proxy_norm(remaining['artist']), _spotify_proxy_norm(remaining['album']))
                    if rkey == key:
                        continue
                    if rkey in manual_keys:
                        records.append({**remaining, 'status': 'manual_keep', 'candidates': []})
                    else:
                        records.append({**remaining, 'status': 'error',
                                        'error': 'scan interrotta dopo errore API; stato sconosciuto',
                                        'candidates': []})
                errors += sum(1 for r in records if r.get('status') == 'error') - errors
                break
        records.append({**album_row, 'status': status, 'candidates': candidates})

    progress.close(complete=True)
    _spotify_catalog_cache_save(cache)
    not_found = [r for r in records if r['status'] == 'not_found']
    review = [r for r in records if r['status'] == 'review']
    found = [r for r in records if r['status'] == 'found']
    unknown = [r for r in records if r['status'] in {'error', 'not_checked_limit'}]
    if limit:
        # Limited/batch scan is additive only; don't remove previous automatic entries based
        # on albums that haven't been checked in this run.
        auto_new_by_key = {(_spotify_proxy_norm(x.get('artist')), _spotify_proxy_norm(x.get('album'))): x
                           for x in previous_auto if isinstance(x, dict)}
        for r in not_found:
            auto_new_by_key[(_spotify_proxy_norm(r['artist']), _spotify_proxy_norm(r['album']))] = {
                'artist': r['artist'], 'album': r['album']}
        proposed_auto = [auto_new_by_key[k] for k in sorted(auto_new_by_key)]
    else:
        proposed_auto = [{'artist': r['artist'], 'album': r['album']} for r in not_found]
    # Avoid automatic entries duplicating manual overrides.
    proposed_auto = [x for x in proposed_auto
                     if (_spotify_proxy_norm(x.get('artist')), _spotify_proxy_norm(x.get('album'))) not in manual_keys]
    proposed_auto.sort(key=lambda x: (_spotify_proxy_norm(x['artist']), _spotify_proxy_norm(x['album'])))
    proposed_config = json.loads(json.dumps(original_config))
    proposed_config.setdefault('SPOTIFY_LOCAL_PROXY', {})['auto_albums'] = proposed_auto

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = Path(report_path).expanduser() if report_path else LOG_DIR / f'spotify_proxy_sync_{stamp}.txt'
    preview_json = LOG_DIR / f'exportify_names_proxy_preview_{stamp}.json'
    lines = [
        f'Spotify Local Files proxy catalog scan — {datetime.now():%Y-%m-%d %H:%M:%S}',
        f'Library root: {root}', f'Spotify market: {market}',
        f'Album folders found: {len(albums)}', f'New catalog queries: {checked}',
        f'Found on Spotify: {len(found)}',
        f'Not found / likely unavailable in market {market}: {len(not_found)}',
        f'Ambiguous candidates (manual review; not auto-added): {len(review)}',
        f'Manually configured albums: {sum(r["status"] == "manual_keep" for r in records)}',
        f'Unverified because of errors/limit: {len(unknown)}',
        f'Existing auto_albums: {len(previous_auto)}', f'Proposed auto_albums: {len(proposed_auto)}',
        '', ('Only confirmed not_found albums are proposed automatically. Spotify search is not a full '
             'catalog export; “not found” means no sufficiently similar result was returned in the configured market.'),
        'Ambiguous candidates are intentionally excluded until reviewed.', '',
    ]
    labels = {'not_found': 'ADD PROXY (not found)', 'review': 'REVIEW (possible catalog match)',
              'found': 'SPOTIFY MATCH', 'manual_keep': 'MANUAL OVERRIDE',
              'error': 'ERROR / UNKNOWN', 'not_checked_limit': 'NOT CHECKED (limit)'}
    for status in ('not_found', 'review', 'found', 'manual_keep', 'error', 'not_checked_limit'):
        subset = [r for r in records if r['status'] == status]
        if not subset:
            continue
        lines.extend([f'--- {labels[status]} ({len(subset)}) ---'])
        for r in subset:
            lines.append(f'{r["artist"]} — {r["album"]} [{r["tracks"]} files]')
            if r.get('error'):
                lines.append(f'    error: {r["error"]}')
            for c in r.get('candidates', [])[:3]:
                artists_text = ', '.join(c.get('artists') or [])
                lines.append(f'    candidate: {artists_text} — {c.get("name")} '
                             f'(album={c.get("album_score"):.3f}, artist={c.get("artist_score"):.3f}) '
                             f'{c.get("url", "")}')
    if errors:
        lines.extend(['', 'SCAN INCOMPLETE: no replacement auto_albums list is safe to apply.',
                      'The existing auto_albums list will be preserved. Candidate additions from successful queries only:'])
        lines.extend(f'  - {r["artist"]} — {r["album"]}' for r in not_found)
    else:
        lines.extend(['', 'Proposed automatic proxy albums (auto_albums):'])
        lines.extend(f'  - {x["artist"]} — {x["album"]}' for x in proposed_auto)
    lines.append('')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[:13]))
    print(f'[i] report: {report_path}')

    if errors:
        print('[ERRORE] almeno una richiesta catalogo è fallita: JSON non aggiornato; correggi il problema e ripeti.',
              file=sys.stderr)
        return {'errors': errors, 'report': str(report_path), 'added': len(not_found)}
    if limit:
        # Qualunque --proxy-limit e' esplicitamente una scansione a batch: non rimuove
        # automaticamente voci esistenti neppure se la cache fa rientrare tutto nel limite.
        _atomic_write_json(preview_json, proposed_config)
        print(f'[i] scansione a batch additiva: ho preservato tutti gli auto_albums precedenti; JSON proposta: {preview_json}')
        if apply and not dry_run:
            if not config_unchanged_since_scan_start():
                print(f"[ERRORE] {cfg_path} e' cambiato durante la scansione: nessuna modifica applicata; ripeti il dry-run.", file=sys.stderr)
                return {'errors': 1, 'report': str(report_path), 'added': len(not_found)}
            _atomic_write_json(cfg_path, proposed_config)
            print(f'[OK] config aggiornata (batch additivo): {cfg_path}')
        return {'errors': 0, 'report': str(report_path), 'added': len(not_found),
                'preview_json': str(preview_json), 'partial': True}
    if dry_run or not apply:
        _atomic_write_json(preview_json, proposed_config)
        print(f'[dry-run] JSON attivo invariato; proposta scritta in {preview_json}')
    else:
        if not config_unchanged_since_scan_start():
            print(f"[ERRORE] {cfg_path} e' cambiato durante la scansione: nessuna modifica applicata; ripeti il dry-run.", file=sys.stderr)
            return {'errors': 1, 'report': str(report_path), 'added': len(not_found)}
        _atomic_write_json(cfg_path, proposed_config)
        print(f'[OK] aggiornato solo SPOTIFY_LOCAL_PROXY.auto_albums in {cfg_path}')
    if review:
        print(f'[i] {len(review)} album ambigui esclusi automaticamente: controlla il report prima di applicare.')
    return {'errors': 0, 'report': str(report_path), 'added': len(not_found),
            'review': len(review), 'found': len(found), 'preview_json': str(preview_json)}


def _proxy_manifest_path(output_root):
    return Path(output_root) / '.spotify_proxy_manifest.json'


def _proxy_favorites_playlist_path(output_root):
    return Path(output_root) / 'liked.m3u'


def _proxy_favorites_json_path(output_root):
    return Path(output_root) / 'spotify_proxy_favorites.json'


def _proxy_manifest_load(output_root):
    try:
        data = json.loads(_proxy_manifest_path(output_root).read_text(encoding='utf-8'))
        if data.get('version') == 1 and isinstance(data.get('entries'), list):
            return data
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {'version': 1, 'entries': []}


def _proxy_manifest_save(output_root, root, entries):
    _atomic_write_json(_proxy_manifest_path(output_root), {
        'version': 1, 'library_root': str(Path(root).resolve()),
        'output_dir': str(Path(output_root).resolve()), 'entries': entries,
    })


def _resolve_navidrome_path(raw_path, root):
    """Converte il path Subsonic (host, container o relativo) in un file del root host."""
    raw = str(raw_path or '').strip()
    if not raw:
        return None
    root = Path(root).expanduser().resolve()
    p = Path(raw)
    candidates = []

    def add(candidate):
        try:
            candidate = Path(candidate).expanduser()
            if candidate.is_file():
                resolved = candidate.resolve()
                resolved.relative_to(root)
                candidates.append(resolved)
        except (OSError, ValueError, RuntimeError):
            return

    if p.is_absolute():
        add(p)
        prefixes = [os.environ.get('ND_MUSIC_ROOT', ''), '/music', str(LIBRARY_ROOT), str(MUSIC_ROOT)]
        for prefix in prefixes:
            prefix = str(prefix or '').rstrip('/')
            if prefix and (raw == prefix or raw.startswith(prefix + '/')):
                tail = raw[len(prefix):].lstrip('/')
                if tail:
                    add(root / tail)
        # Alcune API restituiscono /music/Artista/... senza che ND_MUSIC_ROOT sia impostato.
        parts = p.parts[1:]
        for i in range(len(parts)):
            if parts[i].casefold() in {'music', 'media', 'audio'} and i + 1 < len(parts):
                add(root.joinpath(*parts[i + 1:]))
    else:
        add(root / p)
        parts = p.parts
        for i in range(1, len(parts)):
            add(root.joinpath(*parts[i:]))
    return candidates[0] if candidates else None


def _navidrome_proxy_favorite_snapshot(root):
    """Legge i brani col cuore attivo tramite Subsonic getStarred2; fallisce senza alterare output."""
    user = (str(SPOTIFY_LOCAL_PROXY_CONFIG.get('favorites_user') or '').strip()
            or os.environ.get('ND_FAVORITES_USER', '').strip() or SUBSONIC_USER)
    password, env_key = _user_password(user)
    if not password:
        raise RuntimeError(f'manca la password Navidrome per {user!r}; imposta {env_key} o '
                           'SPOTIFY_LOCAL_PROXY.favorites_user')
    data = _subsonic_req('/getStarred2', user=user, password=password).get('starred2', {})
    raw_songs = data.get('song') or []
    if isinstance(raw_songs, dict):
        raw_songs = [raw_songs]
    path_keys, signatures = set(), set()
    count = 0
    for song in raw_songs:
        if not isinstance(song, dict):
            continue
        count += 1
        resolved = _resolve_navidrome_path(song.get('path'), root)
        if resolved is not None:
            path_keys.add(os.path.normcase(str(resolved)))
        title = str(song.get('title') or '').strip()
        album = str(song.get('album') or '').strip()
        artist_names = [song.get('artist'), song.get('albumArtist'), song.get('album_artist')]
        for artist in artist_names:
            artist = str(artist or '').strip()
            if artist and title and album:
                signatures.add((_spotify_proxy_norm(artist), _spotify_proxy_norm(title),
                                _spotify_proxy_norm(album)))
    return {'user': user, 'count': count, 'path_keys': path_keys, 'signatures': signatures}


def _proxy_entry_is_favorite(entry, root, snapshot):
    source = str(entry.get('source') or '').strip()
    if source:
        source_path = (Path(root).resolve() / Path(source)).resolve()
        if os.path.normcase(str(source_path)) in snapshot['path_keys']:
            return True
    title = str(entry.get('title') or '').strip()
    album = str(entry.get('album') or '').strip()
    for artist_field in ('artist', 'album_artist'):
        artist = str(entry.get(artist_field) or '').strip()
        key = (_spotify_proxy_norm(artist), _spotify_proxy_norm(title), _spotify_proxy_norm(album))
        if artist and title and album and key in snapshot['signatures']:
            return True
    return False


def _atomic_write_text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.tmp-{os.getpid()}')
    tmp.write_text(value, encoding='utf-8')
    os.replace(tmp, path)


def _sync_proxy_favorites_entries(entries, root, output_root, dry_run=True, save_manifest=True):
    """Genera liked.m3u dai preferiti Navidrome; errori API preservano l'output precedente."""
    root = Path(root).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    try:
        snapshot = _navidrome_proxy_favorite_snapshot(root)
    except Exception as exc:
        print(f'[warn] preferiti proxy non sincronizzati: {type(exc).__name__}: {exc}', file=sys.stderr)
        return {'errors': 1, 'updated': False}

    normalized = []
    liked = []
    for original in entries:
        if not isinstance(original, dict):
            continue
        entry = dict(original)
        proxy_rel = str(entry.get('proxy') or '').strip()
        if not proxy_rel:
            continue
        proxy_path = (output_root / proxy_rel).resolve()
        try:
            proxy_path.relative_to(output_root)
        except ValueError:
            print(f'[warn] proxy path fuori dalla cartella output ignorato: {proxy_rel}', file=sys.stderr)
            continue
        exists = proxy_path.is_file()
        if not exists and not dry_run:
            continue
        favorite = _proxy_entry_is_favorite(entry, root, snapshot)
        entry['favorite'] = favorite
        normalized.append(entry)
        if favorite and (exists or dry_run):
            liked.append(entry)

    print(f"[i] preferiti Navidrome utente {snapshot['user']}: {snapshot['count']} brani totali; "
          f'{len(liked)} proxy favoriti da elencare in liked.m3u')
    for entry in liked[:30]:
        print(f"  {'[dry-run] ' if dry_run else ''}{entry.get('artist', '?')} — "
              f"{entry.get('title', '?')} ({entry.get('album', '?')})")
    if len(liked) > 30:
        print(f'  ... altri {len(liked) - 30} brani')
    if dry_run:
        print(f'[dry-run] nessun file scritto: anteprima di {_proxy_favorites_playlist_path(output_root)}')
        return {'errors': 0, 'updated': False, 'favorites': len(liked), 'user': snapshot['user']}

    # Nel M3U restano solo proxy che esistono davvero e hanno contenuto non vuoto.
    actual_liked = []
    for entry in liked:
        path = (output_root / str(entry['proxy'])).resolve()
        try:
            path.relative_to(output_root)
            if path.is_file() and path.stat().st_size > 0:
                actual_liked.append(entry)
        except (OSError, ValueError):
            continue
    lines = ['#EXTM3U']
    for entry in actual_liked:
        artist = str(entry.get('artist') or '').replace('\r', ' ').replace('\n', ' ').strip()
        title = str(entry.get('title') or Path(str(entry.get('proxy') or '')).stem)
        title = title.replace('\r', ' ').replace('\n', ' ').strip()
        lines.append(f'#EXTINF:-1,{artist} - {title}')
        lines.append(str(entry['proxy']).replace('\\', '/'))
    _atomic_write_text(_proxy_favorites_playlist_path(output_root), '\n'.join(lines) + '\n')
    _atomic_write_json(_proxy_favorites_json_path(output_root), {
        'version': 1, 'source': 'Navidrome Subsonic getStarred2', 'user': snapshot['user'],
        'updated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
        'count': len(actual_liked), 'tracks': actual_liked,
    })
    if save_manifest:
        _proxy_manifest_save(output_root, root, normalized)
    print(f"[OK] aggiornati liked.m3u e spotify_proxy_favorites.json: {len(actual_liked)} proxy favoriti")
    print('[i] Spotify Web API non consente di aggiungere file locali a playlist/Liked Songs: '
          'questi file tengono traccia dei preferiti, ma la playlist Spotify nativa richiede un passaggio nel client Desktop.')
    return {'errors': 0, 'updated': True, 'favorites': len(actual_liked), 'user': snapshot['user']}


def _discover_proxy_manifest_entries(root, output_root):
    """Ricostruisce una mappa di base per proxy creati prima dell'introduzione del manifest."""
    root, output_root = Path(root).resolve(), Path(output_root).resolve()
    if not root.is_dir() or not output_root.is_dir():
        return []
    audio_rels = _walk_audio(root, INDEX_EXT)
    by_parent_stem = {}
    for rel in audio_rels:
        key = (tuple(part.casefold() for part in rel[:-1]), Path(rel[-1]).stem.casefold())
        by_parent_stem.setdefault(key, []).append(rel)
    entries = []
    for proxy in sorted(output_root.rglob('*.mp3'), key=lambda p: str(p).casefold()):
        try:
            proxy_rel = proxy.relative_to(output_root).as_posix()
            parent = proxy.relative_to(output_root).parts[:-1]
        except ValueError:
            continue
        key = (tuple(part.casefold() for part in parent), proxy.stem.casefold())
        source_rels = by_parent_stem.get(key, [])
        source_rel = source_rels[0] if len(source_rels) == 1 else ''
        tags = probe(proxy)
        artist = str(tags.get('artist') or (parent[0] if parent else '')).strip()
        album = str(tags.get('album') or _spotify_proxy_rel_album(tuple(parent) + (proxy.name,))).strip()
        title = _spotify_proxy_title(proxy, tags)
        album_artist = str(tags.get('albumartist') or tags.get('album_artist') or artist).strip()
        entries.append({'source': Path(*source_rel).as_posix() if source_rel else '',
                        'proxy': proxy_rel, 'artist': artist, 'album_artist': album_artist,
                        'album': album, 'title': title, 'favorite': None})
    return entries


def run_sync_proxy_favorites(dry_run=True, library_root=None, output_dir=None):
    """Aggiorna il manifest dei proxy e liked.m3u dai cuori correnti di Navidrome."""
    root = Path(library_root or LIBRARY_ROOT).expanduser().resolve()
    output_root = Path(output_dir or SPOTIFY_LOCAL_PROXY_CONFIG.get('output_dir') or
                       '~/Music/Spotify Local Files').expanduser().resolve()
    if not output_root.is_dir():
        print(f'[ERRORE] cartella proxy non trovata: {output_root}', file=sys.stderr)
        return {'errors': 1}
    manifest = _proxy_manifest_load(output_root)
    entries = manifest.get('entries', [])
    # Accetta soltanto path relativi e non esce mai dalla root di libreria/output.
    safe_entries = []
    for e in entries:
        if not isinstance(e, dict) or not e.get('proxy'):
            continue
        try:
            proxy = (output_root / str(e['proxy'])).resolve()
            proxy.relative_to(output_root)
        except (OSError, ValueError):
            continue
        if proxy.is_file():
            safe_entries.append(dict(e))
    if not safe_entries:
        safe_entries = _discover_proxy_manifest_entries(root, output_root)
    if not safe_entries:
        print(f'[ERRORE] nessun proxy MP3 trovato sotto {output_root}; crea prima i proxy', file=sys.stderr)
        return {'errors': 1}
    result = _sync_proxy_favorites_entries(safe_entries, root, output_root,
                                           dry_run=dry_run, save_manifest=True)
    return result


def run_build_spotify_proxies(dry_run=False, library_root=None):
    """Crea proxy MP3 selettivi per Spotify Local Files, preservando gli originali lossless."""
    cfg = SPOTIFY_LOCAL_PROXY_CONFIG
    if not cfg.get('enabled', True):
        print('[i] SPOTIFY_LOCAL_PROXY.enabled=false: generazione proxy disabilitata')
        return {'created': 0, 'skipped': 0, 'errors': 0}
    requested = _spotify_proxy_items()
    if not requested:
        print('[i] nessun album in SPOTIFY_LOCAL_PROXY.albums; nessuna conversione avviata')
        print('[i] aggiungi oggetti {"artist": "Artista", "album": "Album"} per gli album assenti dal catalogo Spotify')
        return {'created': 0, 'skipped': 0, 'errors': 0}
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        print('[ERRORE] ffmpeg non trovato; impossibile generare i proxy MP3', file=sys.stderr)
        return {'created': 0, 'skipped': 0, 'errors': 1}

    root = Path(library_root or LIBRARY_ROOT).expanduser().resolve()
    output_root = Path(str(cfg.get('output_dir') or '~/Music/Spotify Local Files')).expanduser().resolve()
    try:
        output_root.relative_to(root)
    except ValueError:
        pass
    else:
        print(f'[ERRORE] output proxy dentro la libreria Navidrome: {output_root}; scegli una cartella esterna a {root}',
              file=sys.stderr)
        return {'created': 0, 'skipped': 0, 'errors': 1}
    bitrate = str(cfg.get('bitrate', '64k')).lower()
    m_bitrate = re.fullmatch(r'(\d{2,3})k', bitrate)
    if not m_bitrate or not 64 <= int(m_bitrate.group(1)) <= 320:
        print(f'[ERRORE] bitrate proxy non valido: {bitrate!r}', file=sys.stderr)
        return {'created': 0, 'skipped': 0, 'errors': 1}

    criteria, seen_criteria = [], set()
    for item in requested:
        if not isinstance(item, dict):
            print(f'[warn] criterio ignorato (richiede artist e album): {item!r}', file=sys.stderr)
            continue
        artist = str(item.get('artist') or '').strip()
        album = str(item.get('album') or '').strip()
        if not artist or not album:
            print(f'[warn] criterio incompleto ignorato: {item!r}', file=sys.stderr)
            continue
        key = (_spotify_proxy_norm(artist), _spotify_proxy_norm(album))
        if key in seen_criteria:
            continue
        seen_criteria.add(key)
        criteria.append({'artist': artist, 'album': album,
                         'artist_keys': _spotify_proxy_artist_keys(artist),
                         'album_key': _spotify_proxy_norm(album), 'matches': 0})
    if not criteria:
        print('[ERRORE] SPOTIFY_LOCAL_PROXY.albums non contiene criteri validi', file=sys.stderr)
        return {'created': 0, 'skipped': 0, 'errors': 1}

    print(f'[i] ricerca {len(criteria)} album selezionati in {root}; output: {output_root}')
    rels = _walk_audio(root, INDEX_EXT)
    # Fast path: the library is normally Artist/Album/Track. Probe only tracks in
    # matching folders. Fall back to tag matching across the library only if a
    # configured album cannot be located by its directory names.
    for crit in criteria:
        crit['folder_rels'] = []
        for rel in rels:
            folder_artist = _spotify_proxy_artist_keys(rel[0]) if rel else set()
            folder_album = _spotify_proxy_norm(_spotify_proxy_rel_album(rel))
            if crit['album_key'] == folder_album and crit['artist_keys'] & folder_artist:
                crit['folder_rels'].append(rel)
        crit['fallback_tags'] = not bool(crit['folder_rels'])
        if crit['fallback_tags']:
            print(f"[warn] {crit['artist']} — {crit['album']}: cartella non trovata esattamente, ripiego sui tag della libreria",
                  file=sys.stderr)

    if any(crit['fallback_tags'] for crit in criteria):
        candidate_rels = rels
    else:
        wanted = {rel for crit in criteria for rel in crit['folder_rels']}
        candidate_rels = sorted(wanted)
    selected = {}
    for rel in candidate_rels:
        path = root.joinpath(*rel)
        tags = probe(path)
        folder_album = _spotify_proxy_norm(_spotify_proxy_rel_album(rel))
        tagged_album = _spotify_proxy_norm(tags.get('album') or '')
        artist_values = [tags.get('albumartist'), tags.get('album_artist'), tags.get('artist')]
        if rel:
            artist_values.append(rel[0])
        artist_keys = set()
        for value in artist_values:
            artist_keys.update(_spotify_proxy_artist_keys(value))
        for crit in criteria:
            path_match = rel in crit['folder_rels']
            if path_match or (crit['fallback_tags'] and crit['album_key'] in {folder_album, tagged_album}
                              and bool(crit['artist_keys'] & artist_keys)):
                if path not in selected:
                    selected[path] = (rel, tags, crit)
                    crit['matches'] += 1
                break

    for crit in criteria:
        print(f"[i] album proxy {crit['artist']} — {crit['album']}: {crit['matches']} tracce")
    if not selected:
        print('[warn] nessun file corrisponde; controlla i nomi artista/album nei tag o nelle cartelle', file=sys.stderr)
        return {'created': 0, 'skipped': 0, 'errors': 0}

    destinations, used_targets = [], {}
    for source, (rel, tags, crit) in sorted(selected.items(), key=lambda item: str(item[0]).casefold()):
        dest = output_root / Path(*rel).with_suffix('.mp3')
        owner = used_targets.get(str(dest).casefold())
        if owner is not None and owner != source:
            dest = dest.with_name(f'{dest.stem} [from {source.suffix[1:].upper()}].mp3')
        used_targets[str(dest).casefold()] = source
        destinations.append((source, dest, rel, tags, crit))

    if not dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
    created = skipped = errors = 0
    for source, dest, rel, tags, crit in destinations:
        title = _spotify_proxy_title(source, tags)
        album = str(tags.get('album') or _spotify_proxy_rel_album(rel) or crit['album']).strip()
        track_artist = str(tags.get('artist') or tags.get('albumartist') or tags.get('album_artist') or rel[0]).strip()
        album_artist = str(tags.get('albumartist') or tags.get('album_artist') or rel[0]).strip()
        try:
            src_mtime = source.stat().st_mtime
            if dest.exists() and dest.stat().st_size > 4096 and dest.stat().st_mtime >= src_mtime:
                skipped += 1
                continue
        except OSError:
            pass
        if dry_run:
            print(f'[dry-run] {source} -> {dest}')
            created += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f'.{dest.stem}.tmp-{os.getpid()}.mp3')
        cmd = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
               '-map', '0:a:0', '-map', '0:v:disp:attached_pic?', '-map_metadata', '0',
               '-c:a', 'libmp3lame', '-b:a', bitrate, '-c:v', 'copy',
               '-id3v2_version', '3', '-write_id3v1', '1',
               '-metadata', f'title={title}', '-metadata', f'artist={track_artist}',
               '-metadata', f'album={album}', '-metadata', f'album_artist={album_artist}',
               '-f', 'mp3', str(tmp)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 4096:
                raise RuntimeError((result.stderr or f'ffmpeg exit {result.returncode}').strip()[:400])
            if not _ffprobe_raw(str(tmp)):
                raise RuntimeError('ffprobe non riesce a leggere il proxy generato')
            os.replace(tmp, dest)
            # Timestamp del proxy uguale al sorgente: una modifica successiva al FLAC lo invalida.
            try:
                shutil.copystat(source, dest, follow_symlinks=True)
            except OSError:
                pass
            created += 1
        except Exception as exc:
            errors += 1
            print(f'[ERRORE] proxy {source}: {exc}', file=sys.stderr)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    flush_probe_cache()
    # Un manifest persistente permette di collegare i proxy ai sorgenti anche quando la
    # prossima run deve aggiornare soltanto i preferiti, senza ricodificare gli audio.
    manifest_entries = []
    old_manifest = _proxy_manifest_load(output_root)
    old_by_proxy = {str(e.get('proxy') or ''): e for e in old_manifest.get('entries', [])
                    if isinstance(e, dict)}
    for source, dest, rel, tags, crit in destinations:
        try:
            source_rel = source.resolve().relative_to(root.resolve()).as_posix()
            proxy_rel = dest.resolve().relative_to(output_root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        exists_ok = False
        try:
            exists_ok = dest.is_file() and dest.stat().st_size > 4096
        except OSError:
            pass
        if not exists_ok and not dry_run:
            continue
        if not exists_ok and dry_run:
            # Mostra anche proxy che verrebbero creati, ma non scrive nessun file.
            pass
        prior = old_by_proxy.get(proxy_rel, {})
        title = _spotify_proxy_title(source, tags)
        album = str(tags.get('album') or _spotify_proxy_rel_album(rel) or crit['album']).strip()
        track_artist = str(tags.get('artist') or tags.get('albumartist') or tags.get('album_artist') or rel[0]).strip()
        album_artist = str(tags.get('albumartist') or tags.get('album_artist') or rel[0]).strip()
        manifest_entries.append({
            'source': source_rel, 'proxy': proxy_rel, 'title': title,
            'artist': track_artist, 'album_artist': album_artist, 'album': album,
            'favorite': prior.get('favorite') if isinstance(prior, dict) else None,
        })
    if not dry_run:
        try:
            _proxy_manifest_save(output_root, root, manifest_entries)
        except OSError as exc:
            print(f'[warn] impossibile salvare manifest proxy: {exc}', file=sys.stderr)
    favorite_result = _sync_proxy_favorites_entries(
        manifest_entries, root, output_root, dry_run=dry_run,
        save_manifest=not dry_run,
    ) if manifest_entries else {'errors': 0, 'skipped': True}
    if favorite_result.get('errors'):
        print('[warn] proxy creati, ma la sincronizzazione dei preferiti Navidrome non e\' riuscita; '
              'la precedente liked.m3u e\' stata preservata', file=sys.stderr)
    print(f'[i] proxy Spotify conclusi: {created} creati, {skipped} gia aggiornati, {errors} errori')
    print('[i] aggiungi la cartella proxy in Spotify Desktop > Settings > Local Files; liked.m3u e\' un elenco locale di supporto')
    print('[i] al prossimo --sync-only, Exportify puo\' esportare i metadati locali e il matcher li abbina ai file originali')
    return {'created': created, 'skipped': skipped, 'errors': errors}



# ===================== utilita' integrate: FLAC safe / Lidarr / ListenBrainz =====================
# I valori di default derivano dagli helper precedenti, ma le credenziali NON sono nel sorgente.

class _LBRetryFailed(Exception):
    """Richiesta ListenBrainz non riuscita dopo i tentativi consentiti."""


def _safe_flac_valid(path):
    """Valida un FLAC tramite metaflac o ffprobe; un controllo fallito non autorizza la sostituzione."""
    if shutil.which('metaflac'):
        try:
            subprocess.run([*METAFLAC, '--list', str(path)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, check=True, timeout=45)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
    if shutil.which('ffprobe'):
        try:
            r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=format_name',
                                '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                               capture_output=True, text=True, check=True, timeout=45)
            return 'flac' in (r.stdout or '').casefold()
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False
    print('[ERRORE] servono metaflac o ffprobe per validare i FLAC.', file=sys.stderr)
    return False


def run_fix_flac_safe(base=None, apply=False):
    """Ripara <file>.flac.flac solo quando il duplicato e' un FLAC valido; poi elimina .backup
    soltanto quando il relativo file originale esiste. Per sicurezza il chiamante usa dry-run di
    default e passa apply=True esclusivamente con --apply (e senza --dry-run)."""
    base = Path(base or LIBRARY_ROOT).expanduser()
    if not base.is_dir():
        print(f'[ERRORE] cartella libreria non trovata: {base}', file=sys.stderr)
        return False
    mode = 'APPLICA' if apply else 'DRY-RUN'
    print(f'[i] fix-flac-safe: root={base} | modalita={mode}')
    originals = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in {'.git', '@eaDir', '.stfolder'}]
        for name in files:
            lower = name.casefold()
            if lower.endswith('.flac') and not lower.endswith('.flac.flac'):
                originals.append(Path(root) / name)
    originals.sort(key=lambda p: str(p).casefold())
    print(f'Trovati {len(originals)} file FLAC originali.')
    fixed = skipped_no_dup = skipped_invalid = errors = 0
    progress = _ProgressBar('fix_flac_safe', len(originals), 'file')
    for file_index, original in enumerate(originals, 1):
        progress.update(file_index)
        duplicate = Path(str(original) + '.flac')
        if not duplicate.exists():
            skipped_no_dup += 1
            continue
        if not _safe_flac_valid(duplicate):
            progress.clear()
            print(f'  WARN: duplicato non valido, salto: {duplicate.name}')
            skipped_invalid += 1
            continue
        if not apply:
            progress.clear()
            print(f'  FIX previsto: {original} <- {duplicate.name}')
            fixed += 1
            continue
        try:
            # os.replace sovrascrive in modo atomico sullo stesso filesystem; se fallisce,
            # non eliminiamo prima il vecchio originale (il vecchio helper poteva perdere dati).
            os.replace(duplicate, original)
            fixed += 1
        except OSError as e:
            progress.clear()
            print(f'  ERRORE: {original}: {e}', file=sys.stderr)
            errors += 1
    progress.close(complete=True)
    print(f'Fase FLAC: {fixed} sistemati/previsti, {skipped_no_dup} senza duplicato, '
          f'{skipped_invalid} duplicati non validi, {errors} errori.')

    backups = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in {'.git', '@eaDir', '.stfolder'}]
        for name in files:
            if name.endswith('.backup'):
                backups.append(Path(root) / name)
    removed = 0
    sorted_backups = sorted(backups, key=lambda p: str(p).casefold())
    backup_progress = _ProgressBar('fix_flac_safe backup', len(sorted_backups), 'file')
    for backup_index, backup in enumerate(sorted_backups, 1):
        backup_progress.update(backup_index)
        original = Path(str(backup)[:-7])
        if not original.exists():
            continue
        if not apply:
            backup_progress.clear()
            print(f'  BACKUP da rimuovere: {backup}')
            removed += 1
            continue
        try:
            backup.unlink()
            removed += 1
        except OSError as e:
            backup_progress.clear()
            print(f'  WARN: non riesco a rimuovere il backup {backup}: {e}', file=sys.stderr)
    backup_progress.close(complete=True)
    print(f'Backup con originale presente rimossi/previsti: {removed}.')
    if not apply:
        print('[i] anteprima soltanto: usare --fix-flac-safe --apply per applicare le modifiche.')
    return errors == 0


def _lidarr_norm(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(c for c in value if not unicodedata.combining(c)).casefold().strip()
    value = re.sub(r'[^\w ]+', ' ', value, flags=re.UNICODE)
    value = value.replace('_', ' ')
    return re.sub(r'\s+', ' ', value).strip()


def _lidarr_config(url=None, api_key=None, music_root=None, container_root=None):
    url = (url or os.environ.get('LIDARR_URL') or 'http://192.168.1.7:8686').rstrip('/')
    api_key = api_key or os.environ.get('LIDARR_API_KEY')
    host_root = Path(music_root or os.environ.get('LIDARR_MUSIC_ROOT') or LIBRARY_ROOT).expanduser()
    container_root = (container_root or os.environ.get('LIDARR_CONTAINER_ROOT') or '/music').rstrip('/')
    return url, api_key, host_root, container_root


def _lidarr_request(method, path, data=None, url=None, api_key=None, _tries=0):
    """Richiesta API Lidarr con redirect limitati e senza inviare la chiave a un host diverso."""
    if not url or not api_key:
        print('[ERRORE] configurare LIDARR_URL e LIDARR_API_KEY nel .env/ambiente.', file=sys.stderr)
        return None
    full_url = path if path.startswith('http://') or path.startswith('https://') else url.rstrip('/') + '/' + path.lstrip('/')
    body = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(full_url, data=body, method=method)
    req.add_header('X-Api-Key', api_key)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            if not raw:
                return {}
            try:
                return json.loads(raw.decode('utf-8'))
            except json.JSONDecodeError:
                return {'_raw': raw.decode('utf-8', errors='replace')}
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308) and _tries < 3:
            location = e.headers.get('Location')
            if location:
                target = urllib.parse.urljoin(full_url, location)
                if urllib.parse.urlsplit(target).netloc.casefold() == urllib.parse.urlsplit(url).netloc.casefold():
                    return _lidarr_request(method, target, data, url, api_key, _tries + 1)
                print(f'[ERRORE API Lidarr] redirect verso host diverso rifiutato: {target}', file=sys.stderr)
                return None
        print(f'[ERRORE API Lidarr {method}]: HTTP {e.code}: {e.read().decode(errors="replace")[:300]}',
              file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f'[ERRORE API Lidarr {method} {full_url}: {e}]', file=sys.stderr)
        return None


def _lidarr_path_to_host(path, host_root, container_root):
    path = str(path or '')
    if path.startswith(container_root + '/'):
        return str(host_root) + path[len(container_root):]
    return path


def _lidarr_alias_data():
    """Usa le tabelle gia' caricate da exportify_names.json, inclusa la priorita' inglese."""
    mapping = {}
    for table in (NAME_TRANSLATIONS, NAME_FIXES, ALIASES):
        for key, value in table.items():
            k, v = _lidarr_norm(key), _lidarr_norm(value)
            if k and v:
                mapping[k] = v
                mapping.setdefault(v, k)  # consenti anche il match inverso dell'alias
    groups = []
    for group in ARTIST_GROUPS:
        vals = {_lidarr_norm(x) for x in group if _lidarr_norm(x)}
        if vals:
            groups.append(vals)
    return mapping, groups


def run_lidarr_folder_fix(apply=False, url=None, api_key=None, music_root=None, container_root=None):
    """Ripara i path artisti Lidarr che puntano a cartelle mancanti; --apply aggiorna l'API."""
    url, api_key, host_root, container_root = _lidarr_config(url, api_key, music_root, container_root)
    if not api_key:
        print('[ERRORE] LIDARR_API_KEY mancante: inserirla nel .env locale (non nel sorgente).', file=sys.stderr)
        return False
    if not host_root.is_dir():
        print(f'[ERRORE] cartella libreria non trovata: {host_root}', file=sys.stderr)
        return False
    artists = _lidarr_request('GET', '/api/v1/artist', url=url, api_key=api_key)
    if not isinstance(artists, list) or not artists:
        print('[ERRORE] Lidarr non ha restituito un elenco artisti valido.', file=sys.stderr)
        return False

    actual = sorted((d.name for d in os.scandir(host_root)
                     if d.is_dir() and not d.name.startswith('.')
                     and _lidarr_norm(d.name) not in {'playlists', 'strawberry playlists'}),
                    key=str.casefold)
    by_norm = {}
    for name in actual:
        by_norm.setdefault(_lidarr_norm(name), name)
    alias_map, groups = _lidarr_alias_data()
    fixed = failed = ok = noop = 0
    reserved = set()
    # Non assegnare una cartella gia' usata da un artista con un path valido.
    for artist in artists:
        path = str(artist.get('path') or '')
        host_path = _lidarr_path_to_host(path, host_root, container_root)
        if path and os.path.isdir(host_path):
            ok += 1
            reserved.add(_lidarr_norm(os.path.basename(path.rstrip('/'))))

    matched_folders = set()
    for artist in artists:
        path = str(artist.get('path') or '')
        if path and os.path.isdir(_lidarr_path_to_host(path, host_root, container_root)):
            continue
        base = os.path.basename(path.rstrip('/'))
        nb = _lidarr_norm(base)
        artist_name = str(artist.get('artistName') or artist.get('name') or artist.get('id'))
        if not nb:
            print(f'NO-MATCH: {artist_name} (path vuoto/non confrontabile: {path})')
            failed += 1
            continue
        candidates = [nb]
        if nb in alias_map:
            candidates.append(alias_map[nb])
        for group in groups:
            if nb in group:
                candidates.extend(sorted(group - {nb}))
        hit = None
        for cand in dict.fromkeys(candidates):
            candidate = by_norm.get(cand)
            if candidate and _lidarr_norm(candidate) not in reserved:
                hit = candidate
                break
        if not hit:
            available = [k for k, v in by_norm.items() if k not in reserved]
            close = difflib.get_close_matches(nb, available, n=1, cutoff=0.8)
            if close:
                hit = by_norm[close[0]]
        if not hit:
            print(f'NO-MATCH: {artist_name} (atteso: {base})')
            failed += 1
            continue
        hit_norm = _lidarr_norm(hit)
        if hit_norm in reserved:
            print(f'NO-MATCH: {artist_name} (cartella {hit!r} gia assegnata)')
            failed += 1
            continue
        matched_folders.add(hit)
        reserved.add(hit_norm)
        parent = path.rstrip('/').rsplit('/', 1)[0] if '/' in path.rstrip('/') else ''
        newpath = f'{parent}/{hit}' if parent else hit
        print(f'{"FIX" if apply else "PREVIEW"}: {artist_name}: {base!r} -> {hit!r}')
        if apply:
            payload = dict(artist)
            payload['path'] = newpath
            result = _lidarr_request('PUT', f"/api/v1/artist/{artist.get('id')}", payload,
                                     url=url, api_key=api_key)
            if result is None:
                failed += 1
                reserved.discard(hit_norm)
                matched_folders.discard(hit)
                print(f'  [ATTENZIONE] aggiornamento fallito per {artist_name}', file=sys.stderr)
            else:
                fixed += 1
        else:
            fixed += 1

    known = {_lidarr_norm(os.path.basename(str(a.get('path') or '').rstrip('/'))) for a in artists}
    known |= {_lidarr_norm(f) for f in matched_folders}
    orphans = [n for n in actual if _lidarr_norm(n) not in known]
    if orphans:
        print('\nCartelle su disco senza artista in Lidarr (da aggiungere a mano):')
        for name in orphans:
            print(f'  - {name}')
    print(f'\nGia a posto: {ok} | correzioni {"applicate" if apply else "previste"}: {fixed} | senza corrispondenza/errori: {failed}')
    if apply and fixed:
        if _lidarr_request('POST', '/api/v1/command/', {'name': 'RescanFolders'}, url=url, api_key=api_key) is not None:
            print('RescanFolders avviato.')
        else:
            print('RescanFolders NON avviato (errore API).', file=sys.stderr)
    elif not apply:
        print('[i] anteprima soltanto: usare --lidarr-folder-fix --apply per aggiornare Lidarr.')
    return failed == 0


def run_lidarr_import_slskd(dry_run=False, apply=False, url=None, api_key=None, music_root=None,
                            container_root=None, import_folder=None, failed_folder=None):
    """Esegue DownloadedAlbumsScan di Lidarr, riallinea i path e segnala failed_imports."""
    url, api_key, host_root, container_root = _lidarr_config(url, api_key, music_root, container_root)
    import_folder = import_folder or os.environ.get('SLKSD_IMPORT_FOLDER') or '/downloads/slskd'
    failed_folder = Path(failed_folder or os.environ.get('SLKSD_FAILED_FOLDER') or
                         '/downloads/slskd/failed_imports').expanduser()
    if not api_key:
        print('[ERRORE] LIDARR_API_KEY mancante: inserirla nel .env locale (non nel sorgente).', file=sys.stderr)
        return False
    folder_ok = True
    if dry_run:
        print(f'[dry-run] non invio DownloadedAlbumsScan per {import_folder}')
        folder_ok = run_lidarr_folder_fix(False, url=url, api_key=api_key, music_root=host_root,
                                          container_root=container_root)
    else:
        print(f'>>> Lidarr DownloadedAlbumsScan: {import_folder}')
        response = _lidarr_request('POST', '/api/v1/command/',
                                   {'name': 'DownloadedAlbumsScan', 'path': import_folder},
                                   url=url, api_key=api_key)
        if response is None:
            print('[ERRORE] Lidarr non ha accettato DownloadedAlbumsScan.', file=sys.stderr)
            return False
        print('>>> OK: comando di import inviato a Lidarr.')
        # Comportamento dell'helper precedente: correzione path subito dopo l'accodamento.
        folder_ok = run_lidarr_folder_fix(apply=apply, url=url, api_key=api_key, music_root=host_root,
                                          container_root=container_root)
    if failed_folder.is_dir():
        count = sum(1 for p in failed_folder.iterdir() if p.is_dir())
        if count:
            print(f'[ATTENZIONE] {count} album/cartelle in {failed_folder} richiedono gestione manuale.')
        else:
            print(f'[i] nessuna sottocartella fallita in {failed_folder}.')
    else:
        print(f'[i] cartella failed_imports non trovata: {failed_folder}')
    return folder_ok is not False


def _lb_request(url, token, data=None, timeout=90):
    headers = {'Authorization': f'Token {token}', 'Content-Type': 'application/json'}
    body = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            try:
                wait = max(1, int(e.headers.get('Retry-After') or 10))
            except (ValueError, TypeError):
                wait = 10
            print(f'  [ListenBrainz 429] attendo {wait}s...', file=sys.stderr, flush=True)
            time.sleep(wait)
        raise _LBRetryFailed(f'HTTP {e.code}') from e
    except (urllib.error.URLError, http.client.RemoteDisconnected,
            ConnectionResetError, TimeoutError, OSError) as e:
        raise _LBRetryFailed(str(e)) from e


def _lb_api_get(path, token):
    url = 'https://api.listenbrainz.org/1' + path
    last_error = None
    for attempt in range(1, 7):
        try:
            raw = _lb_request(url, token, timeout=90)
            return json.loads(raw)
        except (_LBRetryFailed, json.JSONDecodeError) as e:
            last_error = e
            print(f'  [ListenBrainz tentativo {attempt}/6 fallito: {str(e)[:90]}] '
                  f'riprovo tra {3 * attempt}s...', file=sys.stderr, flush=True)
            if attempt < 6:
                time.sleep(3 * attempt)
    raise _LBRetryFailed(f'pagina irraggiungibile dopo 6 tentativi: {url} ({last_error})')


def _lb_fetch_page(user, token, max_ts, count):
    path = f'/user/{urllib.parse.quote(user, safe="")}/listens?count={count}'
    if max_ts is not None:
        path += f'&max_ts={int(max_ts)}'
    data = _lb_api_get(path, token)
    if not isinstance(data, dict) or not isinstance(data.get('payload'), dict):
        raise _LBRetryFailed('risposta ListenBrainz senza payload valido')
    listens = data['payload'].get('listens')
    if not isinstance(listens, list):
        raise _LBRetryFailed('risposta ListenBrainz senza elenco listens valido')
    return listens


def _lb_fetch_all(user, token, days=365):
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', user)[:80] or 'user'
    cache = CACHE_DIR / f'lb_dedup_{slug}_cache.json'
    listens, max_ts = [], None
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding='utf-8'))
            listens, max_ts = cached['listens'], cached['max_ts']
            print(f'  [ripreso dalla cache: {len(listens)} ascolti, max_ts={max_ts}]',
                  file=sys.stderr, flush=True)
        except (OSError, KeyError, ValueError, TypeError):
            listens, max_ts = [], None
    skipped = []
    consecutive_skips = 0
    cutoff = int(time.time()) - int(days * 86400)
    while max_ts is None or max_ts > cutoff:
        batch = None
        for count, attempts in ((100, 4), (25, 2), (5, 1)):
            try:
                batch = _lb_fetch_page(user, token, max_ts, count)
                break
            except _LBRetryFailed as e:
                print(f'  [pagina ListenBrainz bloccata count={count}: {str(e)[:100]}]',
                      file=sys.stderr, flush=True)
        if batch is None:
            frm = max_ts if max_ts is not None else int(time.time())
            skipped.append((frm, frm - 3 * 86400))
            max_ts = frm - 3 * 86400
            consecutive_skips += 1
            print(f'  [SALTO finestra ListenBrainz {time.strftime("%Y-%m-%d", time.gmtime(frm))} - 3 giorni]',
                  file=sys.stderr, flush=True)
            cache.write_text(json.dumps({'listens': listens, 'max_ts': max_ts}), encoding='utf-8')
            if consecutive_skips >= 5:
                print('[!] 5 finestre consecutive non raggiungibili; la cache resta per il prossimo tentativo.',
                      file=sys.stderr)
                raise _LBRetryFailed('5 finestre consecutive saltate; rilanciare per riprendere dalla cache')
            continue
        consecutive_skips = 0
        if not batch:
            break
        listens.extend(batch)
        listens.sort(key=lambda item: int(item.get('listened_at') or 0), reverse=True)
        try:
            oldest = min(int(item['listened_at']) for item in batch)
        except (KeyError, TypeError, ValueError):
            raise _LBRetryFailed('ListenBrainz ha restituito un ascolto senza listened_at')
        max_ts = oldest - 1
        # Scrive checkpoint a ogni pagina per poter riprendere dopo un crash/interruzione.
        cache.write_text(json.dumps({'listens': listens, 'max_ts': max_ts}), encoding='utf-8')
        print(f'  ...{len(listens)} ascolti scaricati', file=sys.stderr, flush=True)
        time.sleep(1.2)
    cache.unlink(missing_ok=True)
    return listens, skipped


def _lb_find_dupes(listens, window=5):
    by_song = {}
    for item in listens:
        meta = item.get('track_metadata') or {}
        artist = re.sub(r'\s+', ' ', str(meta.get('artist_name') or '')).strip().casefold()
        title = re.sub(r'\s+', ' ', str(meta.get('track_name') or '')).strip().casefold()
        if artist and title:
            by_song.setdefault((artist, title), []).append(item)
    dupes = []
    for group in by_song.values():
        group.sort(key=lambda item: int(item.get('listened_at') or 0))
        cluster = []
        for item in group:
            ts = int(item.get('listened_at') or 0)
            if cluster and ts - int(cluster[-1].get('listened_at') or 0) > window:
                if len(cluster) > 1:
                    dupes.append(cluster)
                cluster = []
            cluster.append(item)
        if len(cluster) > 1:
            dupes.append(cluster)
    return dupes


def _lb_delete_listen(token, item):
    msid = item.get('recording_msid')
    listened_at = item.get('listened_at')
    if not msid or listened_at is None:
        print('    [ERRORE] ascolto senza recording_msid/listened_at: non cancellato', file=sys.stderr)
        return False
    payload = {'listened_at': int(listened_at), 'recording_msid': msid}
    for attempt in range(1, 5):
        try:
            _lb_request('https://api.listenbrainz.org/1/delete-listen', token,
                        data=payload, timeout=30)
            return True
        except Exception as e:
            print(f'    [retry cancellazione {attempt}/4: {str(e)[:70]}]', file=sys.stderr)
            if attempt < 4:
                time.sleep(3 * attempt)
    return False


def run_lb_dedup(user, token, delete=False, window=5, days=365):
    """Trova listen duplicati. Default sola lettura; cancellazione solo con --lb-delete."""
    if not token:
        print('[ERRORE] LISTENBRAINZ_TOKEN mancante nel .env/ambiente.', file=sys.stderr)
        return False
    if not user or window < 0 or days < 1:
        print('[ERRORE] utente ListenBrainz, finestra e giorni non validi.', file=sys.stderr)
        return False
    print(f"[i] scarico lo storico ListenBrainz di '{user}' (ultimi {days} giorni)...", file=sys.stderr)
    try:
        listens, skipped = _lb_fetch_all(user, token, days=days)
    except _LBRetryFailed as e:
        print(f'[ERRORE] download ListenBrainz incompleto: {e}', file=sys.stderr)
        return False
    print(f'[i] {len(listens)} ascolti scaricati', file=sys.stderr)
    if skipped:
        print(f'[!] ATTENZIONE: {len(skipped)} finestre non scaricate:')
        for start, end in skipped:
            print(f'    {time.strftime("%Y-%m-%d", time.gmtime(end))} - '
                  f'{time.strftime("%Y-%m-%d", time.gmtime(start))} UTC')
        if delete:
            print('[ERRORE] cancellazione bloccata: lo storico e incompleto, quindi i duplicati non sono affidabili.',
                  file=sys.stderr)
            return False
    dupes = _lb_find_dupes(listens, window=window)
    extra_count = sum(len(cluster) - 1 for cluster in dupes)
    if not dupes:
        print('Nessun doppione trovato. Nulla da fare.')
        return True
    print(f'\nTrovati {len(dupes)} gruppi con doppioni ({extra_count} listen in eccesso):\n')
    for cluster in sorted(dupes, key=lambda group: int(group[0].get('listened_at') or 0)):
        meta = cluster[0].get('track_metadata') or {}
        stamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(cluster[0].get('listened_at') or 0)))
        print(f"  {stamp} UTC | {meta.get('artist_name', '?')} - {meta.get('track_name', '?')} | x{len(cluster)}")
    if not delete:
        print('\nDRY-RUN: nessuna cancellazione. Per confermare usa --lb-delete (senza --dry-run).')
        return True
    print(f'\n[*] cancello {extra_count} listen in eccesso (mantengo il primo di ogni gruppo)...')
    ok = fail = 0
    for cluster in dupes:
        # La prima occorrenza cronologica del cluster resta conservata.
        for extra in cluster[1:]:
            if _lb_delete_listen(token, extra):
                ok += 1
            else:
                fail += 1
            time.sleep(1.5)
    print(f'Fatto: {ok} cancellate, {fail} errori.')
    return fail == 0


def _run(args):
    if args.sync_only:
        conflicts = (args.all or args.dedupe_playlists or args.dedupe_releases or
                     args.dedupe_tracks or args.mp3_vs_flac or args.flac_16bit or
                     args.clean_empty or args.fix_collab_artists)
        if conflicts:
            sys.exit("[ERRORE] --sync-only non va combinato con --all o con fasi di manutenzione file.")
        args.fetch = True
        args.playlists = True
        args.star_liked = True
        if args.fix_owners is None:
            args.fix_owners = ''
        # Le correzioni di tag/date/album sono manutenzione massiva, non necessaria
        # per importare le playlist. Manteniamo separata la fase romaji dal matching:
        # in sync-only è disattivata insieme alle altre scritture sui tag.
        args.skip_date_heal = True
        args.skip_romaji = True
        args.skip_artist_names = True
        args.skip_unify = True
        args.skip_fix_dates = True
        print("[i] --sync-only: fetch + M3U + proprietari + star-liked; "
              "saltate dedupe/FLAC16/tag/date/album", file=sys.stderr, flush=True)
    print(f"[i] exportify_to_m3u.py v{VERSION} @ "
          f"{datetime.now():%Y-%m-%d %H:%M}", file=sys.stderr)
    _load_navidrome_env_file()
    # --all seleziona le fasi prima di calcolare il totale, cosi' il contatore include la pipeline intera.
    if args.all:
        _expand_all(args)
    has_scan_creds_for_plan = bool(SUBSONIC_PASS or any(
        k.startswith('ND_PASS_') and v for k, v in os.environ.items()))
    planned_scan_before_stars = bool(args.star_liked and not args.dry_run and not args.no_scan
                                     and has_scan_creds_for_plan)
    global _PHASE_PROGRESS_INDEX, _PHASE_PROGRESS_TOTAL
    _PHASE_PROGRESS_INDEX = 0
    _PHASE_PROGRESS_TOTAL = _estimate_phase_total(args)
    run_phase('load_user_config', load_user_config)
    # A questo punto la config JSON e' caricata: ricalcola le fasi opzionali prima della fase 2.
    _PHASE_PROGRESS_TOTAL = max(_PHASE_PROGRESS_INDEX, _estimate_phase_total(args))
    global SYNC_STATE, ROMAJI_TAGS_ACTIVE
    ROMAJI_TAGS_ACTIVE = not args.skip_romaji
    try:
        SYNC_STATE = json.loads(SYNC_FILE.read_text())
    except Exception:
        SYNC_STATE = {}

    # Le utility indipendenti non si combinano con la pipeline. La diagnosi/riparazione album
    # sono invece integrate in --all; da sole restano disponibili come comandi standalone.
    utility_modes = [args.fix_all_playlist_owners is not None, args.fix_flac_safe,
                     args.lidarr_folder_fix, args.lidarr_import_slskd, args.lb_dedup is not None,
                     args.sync_spotify_proxy_config, args.build_spotify_proxies,
                     args.sync_proxy_favorites]
    if sum(utility_modes) > 1:
        sys.exit('[ERRORE] esegui una sola utility standalone per volta')
    if any(utility_modes) and (args.all or args.sync_only or args.playlists or args.fetch or args.fetch_only
                               or args.diagnose_album_splits or args.repair_album_groups):
        sys.exit('[ERRORE] le utility standalone non si combinano con la pipeline playlist o album repair')
    if args.lb_delete and args.lb_dedup is None:
        sys.exit('[ERRORE] --lb-delete richiede --lb-dedup UTENTE')
    if (args.diagnose_album_splits or args.repair_album_groups) and not args.all:
        if args.sync_only or args.playlists or args.fetch or args.fetch_only:
            sys.exit('[ERRORE] diagnosi/riparazione album standalone non si combina con fetch/playlist; usa --all')
        if args.diagnose_album_splits:
            ok = run_phase('diagnose_album_splits', run_diagnose_album_splits,
                           album_filter=args.album, artist_filter=args.artist)
            if ok is False:
                raise SystemExit(1)
            if not args.repair_album_groups:
                return
        if args.repair_album_groups:
            dry = not (args.apply and not args.dry_run)
            ok = run_phase('repair_album_groups', run_repair_album_groups,
                           dry_run=dry, base=args.library_root or LIBRARY_ROOT,
                           include_existing_passes=True)
            if ok is not True:
                raise SystemExit(1)
            if not dry and not args.no_scan:
                run_phase('navidrome_scan', run_navidrome_scan, full_scan=True, prune_refs=True)
            return
    if args.fix_all_playlist_owners is not None:
        result = run_phase('fix_all_playlist_owners', run_fix_all_playlist_owners,
                           args.fix_all_playlist_owners, dry_run=not (args.apply and not args.dry_run))
        if result is not True:
            raise SystemExit(1)
        return
    if args.fix_flac_safe:
        result = run_phase('fix_flac_safe', run_fix_flac_safe,
                           base=args.library_root or LIBRARY_ROOT,
                           apply=args.apply and not args.dry_run)
        if result is not True:
            raise SystemExit(1)
        return
    if args.lidarr_folder_fix:
        result = run_phase('lidarr_folder_fix', run_lidarr_folder_fix,
                           apply=args.apply and not args.dry_run, url=args.lidarr_url,
                           music_root=args.library_root, container_root=args.lidarr_container_root)
        if result is not True:
            raise SystemExit(1)
        return
    if args.lidarr_import_slskd:
        result = run_phase('lidarr_import_slskd', run_lidarr_import_slskd,
                           dry_run=args.dry_run, apply=args.apply and not args.dry_run,
                           url=args.lidarr_url, music_root=args.library_root,
                           container_root=args.lidarr_container_root,
                           import_folder=args.slskd_import_folder, failed_folder=args.slskd_failed_folder)
        if result is not True:
            raise SystemExit(1)
        return
    if args.lb_dedup is not None:
        result = run_phase('listenbrainz_dedup', run_lb_dedup, args.lb_dedup,
                           os.environ.get('LISTENBRAINZ_TOKEN'),
                           delete=args.lb_delete and not args.dry_run,
                           window=args.lb_window, days=args.lb_days)
        if result is not True:
            raise SystemExit(1)
        return

    if args.proxy_limit < 0:
        sys.exit('[ERRORE] --proxy-limit deve essere >= 0')
    if args.sync_proxy_favorites:
        result = run_sync_proxy_favorites(
            dry_run=not args.apply or args.dry_run,
            library_root=args.library_root,
        )
        if not isinstance(result, dict) or result.get('errors'):
            raise SystemExit(1)
        return
    if args.sync_spotify_proxy_config:
        result = run_phase('sync_spotify_proxy_config', run_sync_spotify_proxy_config,
                           dry_run=not args.apply or args.dry_run,
                           apply=args.apply and not args.dry_run,
                           library_root=args.library_root, limit=args.proxy_limit,
                           force_refresh=args.proxy_force_refresh, report_path=args.proxy_report)
        if not isinstance(result, dict) or result.get('errors'):
            raise SystemExit(1)
        return

    if args.build_spotify_proxies:
        result = run_phase('build_spotify_local_proxies', run_build_spotify_proxies,
                           dry_run=args.dry_run, library_root=args.library_root)
        if not isinstance(result, dict) or result.get('errors'):
            raise SystemExit(1)
        return

    if args.rebuild_album:
        run_phase('rebuild_album', rebuild_album, args.rebuild_album)
        return

    sel = resolve_selected_users(args.users)      # None = tutti gli utenti

    if args.fetch_cookies and not args.fetch_login:
        sys.exit("[ERRORE] --fetch-cookies si usa insieme a --fetch-login UTENTE")
    if args.fetch_login:
        rc = run_phase('fetch_login', run_fetch_login, args.fetch_login,
                       cookies=args.fetch_cookies)
        raise SystemExit(1 if rc is None else rc)
    if args.fetch_list:
        run_phase('list_exportify_sessions', run_fetch_list)
        return
    if args.fetch_check:
        rc = run_phase('check_exportify_sessions', run_fetch_check, sel)
        raise SystemExit(1 if rc is None else rc)
    if args.check_albums and not args.all:
        run_phase('check_albums', run_check_albums, album=args.album, artist=args.artist,
                  search=not args.mb_no_search, append_missing_report=True)
        return
    if args.fetch_only:
        rc = run_phase('fetch_exportify', run_fetch, sel,
                       headed=args.fetch_headed, timeout_min=args.fetch_timeout)
        raise SystemExit(1 if rc is None else rc)

    if args.missing is not None:
        by_full, by_artist, by_strict, path_qual = run_phase('index_library', load_library, rebuild=args.rebuild_cache)
        groups = [(u, select_playlists(fs, args, user=u)) for u, fs in collect_user_csvs(args, sel)]
        files = [f for _, fs in groups for f in fs]
        if not files:
            sys.exit(f"[ERRORE] nessun CSV da elaborare in {EXPORTIFY_DIR}")
        run_phase('report_missing_tracks', report_missing, files, by_full, by_artist,
                  by_strict, path_qual, args.threshold, args.missing)
        return

    if args.explain:
        parts = (args.explain.split('|||') + ['', '', ''])[:3]
        by_full, by_artist, by_strict, path_qual = run_phase('index_library', load_library, rebuild=args.rebuild_cache)
        run_phase('explain_track_match', explain_row, by_full, by_artist, by_strict,
                  path_qual, *parts)
        return

    if args.compare:
        f1, f2 = Path(args.compare[0]), Path(args.compare[1])
        if not f1.exists() or not f2.exists():
            sys.exit(f"[ERRORE] file non trovato: {args.compare}")
        t1, d1 = probe_dur(f1)
        t2, d2 = probe_dur(f2)
        print(f"  {f1.name}: {f1.suffix}  durata {round(d1, 1) if d1 else '?'}s"
              f"  (title tag: {t1.get('title', '-')!r})")
        print(f"  {f2.name}: {f2.suffix}  durata {round(d2, 1) if d2 else '?'}s"
              f"  (title tag: {t2.get('title', '-')!r})")
        print(f"  durate compatibili: {_dur_compatible(d1, d2, args.max_dur_diff)}")
        if not _HAS_NP:
            print("  numpy assente: correlazione non calcolabile")
            return
        c = correlate(fingerprint(f1), fingerprint(f2))
        if c is None:
            print("  correlazione: non calcolabile (audio <5s dopo il trim del silenzio)")
            return
        print(f"  correlazione waveform: {c:.4f}")
        if c >= 0.95:
            print("  VERDETTO: Stessa incisione -> dedupe li cestina tenendo il migliore (FLAC)")
        elif c >= 0.70:
            print("  VERDETTO: parzialmente in comune ma audio diverso (mix/extended/master diversi)")
        else:
            print("  VERDETTO: audio diverso -> registrazioni/mix DIFFERENTI, non copie")
        return

    if args.all:
        # Snapshot the pre-repair DB so duplicate albums and fuzzy REVIEW-only pairs remain
        # visible even if later tag repair makes Navidrome rebuild these rows.
        diag_ok = run_phase('diagnose_album_splits', run_diagnose_album_splits,
                            album_filter=args.album, artist_filter=args.artist)
        if diag_ok is False:
            print('[warn] diagnostica album saltata/non riuscita; la pipeline continua con le riparazioni',
                  file=sys.stderr)

    maintenance = any([args.fix_owners is not None, args.dedupe_playlists, args.dedupe_releases,
                       args.dedupe_tracks, args.mp3_vs_flac, args.clean_empty,
                       args.fix_collab_artists, args.star_liked])

    if args.unify_only:
        run_phase('album_unify', run_unify, args.dry_run)
        if not args.dry_run and not args.no_scan:
            run_phase('navidrome_scan', run_navidrome_scan)
        return

    # ordine deliberato: manutenzione file PRIMA delle playlist (i dedupe
    # spostano file: le m3u devono vedere i path definitivi)
    if args.fix_owners is not None:
        run_phase('fix_playlist_owners', run_fix_owners, args.fix_owners,
                  dry_run=args.dry_run, users=sel)
    if args.dedupe_playlists:
        run_phase('dedupe_playlists', run_dedupe_playlists,
                  args.apply and not args.dry_run, users=sel)
    if args.dedupe_releases:
        run_phase('dedupe_releases', run_dedupe_releases,
                  args.apply, args.hard_delete, args.artist,
                  corr=args.corr, max_dur=args.max_dur_diff)
    if args.dedupe_tracks:
        run_phase('dedupe_tracks', run_dedupe_tracks,
                  args.apply, args.hard_delete, args.artist,
                  corr=args.corr, max_dur=args.max_dur_diff,
                  trust_format=args.trust_format)
    if args.mp3_vs_flac:
        run_phase('mp3_vs_flac', run_mp3_vs_flac,
                  args.apply, args.hard_delete, args.artist,
                  corr=args.corr, max_dur=args.max_dur_diff,
                  trust_format=args.trust_format)
    if args.fix_collab_artists:
        run_phase('fix_collab_artists', run_fix_collab_artists,
                  args.apply and not args.dry_run, args.album, args.artist)
    if args.flac_16bit:
        run_phase('flac_16bit', run_flac_16bit, args.dry_run)
    if args.clean_empty:
        run_phase('clean_empty', run_clean_empty, args.dry_run)

    if args.playlists or not maintenance:
        groups = collect_user_csvs(args, sel)
        by_full, by_artist, by_strict, path_qual = run_phase('index_library', load_library, rebuild=args.rebuild_cache)
        groups = [(u, select_playlists(fs, args, user=u)) for u, fs in groups]
        report_skips(args, users=[u for u, _files in groups])
        groups = [(u, fs) for u, fs in groups if fs]
        if not groups:
            sys.exit(f"[ERRORE] nessun CSV da elaborare (nessuno zip riconosciuto, vuoto o tutto "
                     f"filtrato) in {EXPORTIFY_DIR}")

        run_phase('generate_m3u_playlists', _generate_m3u_playlists, groups,
                  by_full, by_artist, by_strict, path_qual, args, sel)

        if not args.dry_run and _FRESH_EXTRACTED_USERS:
            run_phase('prune_stale_m3u', _prune_stale_m3u_after_fetch, groups, args)
            fresh_user_keys = {u.casefold() for u, _files in groups} & _FRESH_EXTRACTED_USERS
            canonical_m3u_paths = [path for user_key, paths in _GENERATED_M3U_PATHS.items()
                                   if user_key in fresh_user_keys for path in paths]
            if _STALE_M3U_REMOVED_PATHS or canonical_m3u_paths:
                run_phase('prune_stale_m3u_db', _remove_nav_playlists_for_deleted_m3u,
                          list(_STALE_M3U_REMOVED_PATHS), expected_paths=canonical_m3u_paths)
        if not args.dry_run:
            SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(SYNC_FILE, SYNC_STATE, ensure_ascii=False)

        if not args.skip_date_heal:
            run_phase('date_heal', run_date_heal, args.dry_run)

        if not args.skip_romaji:
            run_phase('romaji_tags', run_romaji_tags, args.dry_run)

        if not args.skip_artist_names:
            run_phase('artist_names', run_unify_artists, args.dry_run)

        if not args.skip_unify:
            run_phase('album_unify', run_unify, args.dry_run)

        if args.all:
            # date_heal, artist_names e album_unify hanno gia' eseguito i passaggi principali
            # della repair utility: qui aggiungiamo solo Unknown Artist e split verificato dal DB.
            run_phase('repair_album_groups', run_repair_album_groups,
                      dry_run=args.dry_run, base=args.library_root or LIBRARY_ROOT,
                      include_existing_passes=False)
            # dedupe_tracks runs before album_unify. A second, metadata-conservative pass is
            # needed here because exact album groups can be joined from separate folders only
            # after tag normalization (e.g. Animals / Dogs in two source directories).
            run_phase('dedupe_cross_album_tracks', run_dedupe_cross_album_tracks,
                      args.apply and not args.dry_run, args.hard_delete,
                      base=args.library_root or LIBRARY_ROOT)

        if not args.skip_fix_dates:
            run_phase('fix_date_tags', run_fix_dates, args.dry_run)

        if args.dry_run:
            print("[i] dry-run: report libreria saltato (si basa sui .missing.txt reali)",
                  file=sys.stderr)
        elif args.sync_only:
            print("[i] sync-only: report_library_gaps saltato (diagnostica, non necessaria alla sync)",
                  file=sys.stderr, flush=True)
        else:
            run_phase('report_library_gaps', print_gap_report, LIBRARY_ROOT)

    # Le playlist M3U appena scritte non sono visibili all'API finche' Navidrome non le
    # indicizza. Esegui quindi la scan prima di leggere 'liked'/'saved albums' e stellare
    # tracce/album/artisti; non serve una seconda scan dopo le sole stelle.
    scanned_before_stars = False
    scan_attempted_before_stars = False
    scan_before_stars_ok = None
    if args.star_liked and not args.dry_run and not args.no_scan:
        scan_attempted_before_stars = True
        # In --sync-only basta l'indicizzazione incrementale: evita il full scan di tutta
        # la libreria e, soprattutto, non ferma Navidrome subito prima delle stelle.
        scan_before_stars_ok = _scan_before_favorites(
            sel, full_scan=not args.sync_only,
            reconcile_changes=bool(args.all and not args.sync_only),
            library_root=args.library_root or LIBRARY_ROOT)
        # None significa che non e' stato trovato un account con credenziali per la scansione.
        scanned_before_stars = bool(scan_before_stars_ok)
        if args.all and scan_before_stars_ok is True:
            # Secondo report: mostra cosa e' rimasto dopo riparazione tag + full scan Navidrome.
            run_phase('diagnose_album_splits_after_scan', run_diagnose_album_splits,
                      album_filter=args.album, artist_filter=args.artist)

    if args.star_liked:
        if args.dry_run:
            print("[i] dry-run: star_liked saltato (applica preferiti tramite API Navidrome)",
                  file=sys.stderr, flush=True)
        elif scan_attempted_before_stars and scan_before_stars_ok is False:
            print("[ERRORE] star_liked saltato: scan Navidrome non riuscito; verificare il servizio e rilanciare.",
                  file=sys.stderr, flush=True)
        else:
            run_phase('star_liked', run_star_liked, sel)

    if not args.dry_run and not args.no_scan and not scanned_before_stars:
        before_final_scan = _snapshot_navidrome_albums() if args.all else {}
        final_scan_ok = bool(run_phase('navidrome_scan_final', run_navidrome_scan))
        if args.all:
            if planned_scan_before_stars:
                # Il pre-scan era previsto ma ha saltato/fallito: questo retry e' una fase extra.
                _PHASE_PROGRESS_TOTAL += 1
            if final_scan_ok:
                if _reconcile_navidrome_album_changes(
                        before_final_scan, library_root=args.library_root or LIBRARY_ROOT,
                        planned_target_phases=True):
                    run_phase('diagnose_album_splits_after_scan', run_diagnose_album_splits,
                              album_filter=args.album, artist_filter=args.artist)
            elif not planned_scan_before_stars:
                # Il piano includeva target/diagnostica come follow-up del fallback scan,
                # ma lo scan e' fallito e tali fasi non verranno eseguite.
                _PHASE_PROGRESS_TOTAL = max(_PHASE_PROGRESS_INDEX,
                                            _PHASE_PROGRESS_TOTAL - 8)
            else:
                # Anche con retry fallito, non lasciare nel totale le sette fasi mirate e la diagnosi.
                _PHASE_PROGRESS_TOTAL = max(_PHASE_PROGRESS_INDEX,
                                            _PHASE_PROGRESS_TOTAL - 8)

    # In --all controlla ogni album con MBID contro la sua release esatta e aggiunge le tracce
    # mancanti in fondo a mancanti_<data>.txt oltre al report dettagliato.
    if args.all:
        run_phase('check_album_completeness', run_check_albums,
                  search=False, mbid_only=True, append_missing_report=True)

    # Come MusicBee 'Update Missing Artwork': fase distinta alla fine della pipeline.
    # Non sovrascrive artwork locale/embedded; dopo download riusciti richiede una scan incrementale.
    if args.no_artwork_download:
        print('[i] ricerca copertine album saltata da --no-artwork-download', flush=True)
    elif MISSING_ARTWORK_CONFIG.get('enabled', True):
        art_result = run_phase('download_missing_album_artwork', run_missing_album_artwork,
                               dry_run=args.dry_run)
        if (not args.dry_run and not args.no_scan and
                MISSING_ARTWORK_CONFIG.get('scan_after_download', True) and
                isinstance(art_result, dict) and art_result.get('downloaded', 0) > 0):
            # La scansione e' condizionale: aggiungila al totale solo quando serve davvero.
            _PHASE_PROGRESS_TOTAL += 1
            run_phase('navidrome_scan_after_artwork', run_navidrome_scan,
                      full_scan=False, prune_refs=False)


if __name__ == '__main__':
    main()
