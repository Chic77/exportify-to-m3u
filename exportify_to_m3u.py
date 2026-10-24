#!/usr/bin/env python3
"""
exportify2m3u.py - Exportify CSV -> playlist .m3u con path reali della libreria.

Sostituisce il vecchio script crontab. Migliorie:
  - intestazioni CSV italiane E inglesi, BOM-safe (utf-8-sig)
  - fallisce LOUD se un CSV non produce nemmeno un brano (niente piu' m3u vuoti)
  - normalizzazione seria (accenti, (Remastered), feat., punteggiatura)
  - indice da FILESYSTEM (Artista/Album/Brano.ext), non piu' dal DB beets
  - nomi file 'Artista - Album - 01 - Titolo' gestiti; kanji/unicode conservati;
    album multi-disco (Artista/Album/CD1/Traccia) indicizzati sotto l'artista vero
  - ARTIST_GROUPS: piu' nomi per lo stesso artista (aka), in entrambe le direzioni
  - virgole nel nome gestite via libreria ('Tyler, The Creator' resta intero)
  - conversione automatica kanji<->romaji (pykakasi) per artista e titolo,
    con e senza spazi (es. 'natsu mado' == 'natsumado'), in entrambe le direzioni
    alias manuali per artisti con nome diverso; duplicati rimossi
  - matching: esatto (artista,album,titolo) -> esatto (artista,titolo) ->
    primo artista -> contenimento -> fuzzy difflib entro l'artista
  - report .missing.txt accanto a ogni playlist

Requisiti (Debian 12+/13: 'pip install --user' e' bloccato da PEP 668 -> venv):
    cd ~/homelab/scripts && python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt     # pykakasi, hangul-romanize, numpy
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
    logs/              log di ogni run (e2m_<opzioni>_<data>.log), mancanti_<data>.txt,
                       album_incompleti_<data>.txt
    .exportify_sessions/  sessioni Spotify salvate da --fetch-login (riservate, permessi 600)
                       (consigliato nel .gitignore: .exportify_sessions/ spotify_cookies/
                       spotify_csv/)
    spotify_cookies/   (facoltativa) dove mettere i cookie esportati per --fetch-cookies
    exportify_names.json  la TUA configurazione (vedi 6)

------------------------------------------------------------------------------
2. PRIMA INSTALLAZIONE (una volta sola)
------------------------------------------------------------------------------
    cd ~/homelab/scripts && python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt        # pykakasi, hangul-romanize, numpy
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
  --unify-only          esegue SOLO album_unify (niente playlist). --skip-unify lo salta.
  --skip-date-heal, --skip-romaji, --skip-artist-names, --skip-fix-dates
                        saltano la rispettiva fase tag della pipeline playlist.

  --- Report e diagnostica (a sola lettura) ------------------------------------------
  --check-albums        confronta ogni album del DB con la tracklist di MusicBrainz e
                        scrive logs/album_incompleti_<data>.txt (tracce mancanti X/Y,
                        quali, e l'elenco da riscaricare). Usa MUSICBRAINZ_ALBUMID se c'e',
                        altrimenti cerca per artista+album (--mb-no-search lo evita).
                        1 richiesta/secondo: la prima run e' lunga, poi c'e' la cache.
  --missing [FILE]      elenca TUTTE le tracce mancanti, ricalcolate ora dai CSV contro la
                        libreria. Con FILE le salva li', senza le stampa.
  --explain "ARTISTA|||ALBUM|||TITOLO"
                        mostra candidati e punteggi dell'abbinamento per UNA riga (album
                        e titolo come nel CSV): serve a capire perche' un brano non
                        viene trovato.
  --compare FILE1 FILE2 confronta due file audio (durate + forma d'onda) e dice se sono
                        la stessa incisione.
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
    SKIP_PLAYLISTS   nomi di playlist da non importare mai (confronto tollerante; '*'
                     finale = tutte quelle che iniziano cosi': "daylist*")
    SPOTIFY_USERS    {"<id spotify>": "<utente navidrome>"}: lega gli zip senza il nome
                     utente (lo script puo' aggiungere voci da solo, vedi passo 3)
    FETCH_IGNORED_USERS ["octochic", ...]: utenti da NON aggiornare con Exportify;
                     i loro CSV/ZIP locali possono comunque essere usati
    PLAYLIST_FOLDERS {"nome playlist": "sottocartella"}: dove mettere certe m3u
    PLAYLIST_PREFIXES ["color", ...]: "color yellow" diventa "color - yellow" (si
                     raggruppano in tutti i client)
    NAME_FIXES       letture sbagliate di kanji/hangul: {"original": "lettura giusta"}
    ALIASES          artista scritto diversamente su Spotify e in libreria
    ARTIST_GROUPS    gruppi di nomi dello STESSO artista (aka): [["a", "b"], ...]
    FORCE_ARTIST     "artista - titolo" -> artista da cercare al posto di quello del CSV
    CSV_FIX          correzioni per riga CSV (album/artista) che sopravvivono ai nuovi
                     export: {"playlist": {"artista - titolo": {"album": "..."}}}
    UNIFY_FORCE      valori da forzare per album in album_unify ("cartella artista /
                     cartella album": {campo: valore})
    EMOJI_WORDS      parole usate al posto di un'emoji nei titoli Spotify

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
    MB_BASE                      indirizzo dell'API MusicBrainz (per prove/mirror)

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
Novita' 5.2 (matching piu' semplice e scoring configurabile):
  - riutilizzata la mappa TITLE_MATCH_PENALTIES gia' presente nel JSON anche per la penalita' parentesi;
    il vecchio TITLE_MATCH_PARENTHESES_PENALTY viene ancora letto solo per compatibilita' con JSON v5.1
  - lista dei qualificatori normalizzata/ordinata una sola volta e memorizzata in cache, invece di
    ricostruire e ordinare gli stessi set per ogni candidato; cache invalidata dopo il caricamento config
  - mantenuto il punteggio piu' alto per le versioni esplicitamente richieste (Live/Demo ecc.); i suffissi
    alternativi non richiesti perdono contro il titolo pulito

Novita' 4.9 (fetch fresco e pulizia M3U per utente):
  - FETCH_IGNORED_USERS in exportify_names.json esclude gli account dal fetch Exportify;
  - quando il fetch riesce, l'estrazione usa solo lo ZIP appena scaricato per quell'utente,
    ignorando gli altri ZIP della cartella spotify_csv;
  - dopo una conversione riuscita vengono rimosse le M3U obsolete dell'utente non piu' coperte
    dai CSV selezionati; CSV in errore sospendono la pulizia per sicurezza;
  - pulisce anche dal DB Navidrome le playlist importate col path dei file rimossi (e righe collegate);
  - fetch, pulizia M3U e pulizia DB sono fasi distinte e temporizzate;
  - le cartelle M3U degli altri utenti sono protette anche col layout storico dell'utente default.

Novita' 4.5 (revisione bug + pulizia):
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

Novita' 4.4:
  - --star-liked: accetta la playlist 'liked' (e 'liked songs'), stella le tracce; usa 'saved albums'
    per stellare gli album e stella gli artisti presenti nelle due playlist; la scan Navidrome avviene
    prima di questa fase, cosi' vengono lette le playlist appena aggiornate
  - unzip: se ci sono piu' ZIP dello stesso utente, usa solo il piu' recente; i CSV rimasti fuori
    dal nuovo export di quello stesso utente vengono rimossi

Novita' 4.3:
  - import playlist: recupera durante --fetch nome Spotify originale (case, emoji, Unicode) e cover;
    conserva i metadati per CSV e usa il nome esatto come basename M3U (slash -> ／, non puo' stare in un filename)
  - importa la cover Spotify come sidecar accanto alla M3U, riconosciuto da Navidrome; aggiorna la cover
    anche quando la playlist non deve essere riscritta; recupero artwork non riuscito non blocca l'import

Novita' 4.2:
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

Novita' 4.1:
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

Novita' 4.0 - versione maggiore: pipeline multi-utente completa e guida integrata.
  Riassume le novita' 3.22-3.30 qui sotto: zip e playlist per utente (--users), download
  automatico degli zip da Exportify (--fetch*), dedupe delle playlist, report mancanti
  con statistiche, controllo album incompleti su MusicBrainz, correzione dei collab.
  - aggiunta questa guida in testa al file (uso, nuovo utente, comandi, configurazione)
  - corretto --help: la descrizione di --max-dur-diff (contiene un '%') non veniva
    mostrata e stampava un dizionario Python

Novita' 3.30:
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
  - --check-albums: confronta ogni album del DB con la tracklist di MusicBrainz e scrive
    logs/album_incompleti_<data>.txt: album con tracce mancanti (X/Y, %), quali tracce, e
    l'elenco "Artista - Album - Titolo" da riscaricare. Usa MUSICBRAINZ_ALBUMID del DB
    (release esatta); senza, cerca per artista+album (--mb-no-search = solo gli album
    taggati). 1 richiesta/secondo come chiede MusicBrainz, cache in .mb_albums_cache.json:
    la prima run su una libreria grande e' lunga (si puo' interrompere e riprendere),
    le successive sono quasi istantanee. Solo lettura: non tocca file ne' DB

Novita' 3.29:
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

Novita' 3.28 - controllo della sessione Exportify e cartella dei cookie:
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

Novita' 3.27 - logs/mancanti_<data>.txt piu' ricco (l'elenco completo resta IN FONDO):
  - totale: X/Y tracce uniche mancanti e percentuale (Y = brani unici letti dai CSV)
  - per utente: mancanti/totale e %, e quante canzoni mancano a quali utenti ("3 canzoni
    mancanti a elena", "1 canzone mancante a chic, stello"); solo con piu' utenti nella run
  - le playlist con piu' canzoni mancanti (X/Y, %)
  - i 10 album da scaricare, per numero di canzoni mancanti (X/Y = mancanti / brani di
    quell'album presenti nelle playlist; non si conosce la tracklist completa dell'album)
  - nell'elenco completo le playlist portano il prefisso "utente:" se gli utenti sono piu' di uno

Novita' 3.26 - login Exportify piu' robusto:
  - il browser del login nasconde i segnali di automazione (flag --enable-automation,
    navigator.webdriver) e usa Google Chrome se installato, altrimenti Chromium
  - chiudere il browser a meta' login non produce piu' un traceback
  - se Spotify scambia comunque il browser per un bot (captcha impossibili, "something
    went wrong"): fare il login nel PROPRIO browser, esportare i cookie di spotify.com
    (estensione "Cookie-Editor" -> Export -> JSON, oppure cookies.txt Netscape) e importarli:
        --fetch-login UTENTE --fetch-cookies FILE
    Servono almeno i cookie di login (sp_dc); lo script verifica la sessione subito.
    Consiglio: login in una finestra PRIVATA, esporta, chiudi la finestra SENZA fare logout.

Novita' 3.25 - download automatico degli zip da Exportify (tutto in questo script):
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

Novita' 3.23 (multi-utenteNovita' 3.23 (multi-utente Navidrome - prima tappa):
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

Novita' 3.22:
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

Novita' 3.21 (dai log reali del 13/10):
  - album_unify: la riparazione dei tag mancanti (spotyFLAC) dava KeyError 'title' su
    OGNI FLAC (funzionava solo per mp3/m4a); titolo ricostruito meglio
  - stop alle riscritture notturne che non convergono: .m4a (ffmpeg non salva
    albumartist/originaldate/MBID), FLAC con ORIGINALDATE (unify rimetteva DATE e
    fix_date_tags lo toglieva), .opus/.ogg (tag illeggibili)
  - ALBUMARTIST riscritto col nome 'sanificato' della cartella solo per cartelle asiatiche
  - .missing.txt delle playlist 'invariate' ora aggiornato; nuovo --missing [FILE]

Novita' 3.20 (ottimizzazioni + bugfix):
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
import contextlib
import csv
import difflib
import fnmatch
import random
import shutil
import sqlite3
import string
import subprocess
import time
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
from concurrent.futures import ThreadPoolExecutor


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

VERSION = "5.3"   # bump a ogni modifica: loggata all'avvio e via --version

# intestazioni Exportify: italiano (prima) e inglese
COLS = {
    'title':  ['Nome della traccia', 'Track Name'],
    'artist': ["Nome dell'artista", 'Artist Name(s)', 'Artist Name', 'Artista'],
    'album':  ["Nome dell'album", 'Album Name', 'Album'],
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

# Playlist da NON importare mai (nomi come i file .csv). Dal JSON: "SKIP_PLAYLISTS".
SKIP_PLAYLISTS = []

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

# Prefissi tipo "color yellow": il nome diventa "color - yellow" (piatto, raggruppa
# in tutti i client). Dal JSON: "PLAYLIST_PREFIXES".
PLAYLIST_PREFIXES = []

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

NAME_FIXES = {
    # letture che pykakasi sbaglia — valgono per artisti E titoli (chiave = stringa normalizzata)
    '高中正義': 'masayoshi takanaka',
}

# --- configurazione utente esterna: exportify_names.json accanto allo script ---
# Contiene le TUE tabelle (NAME_FIXES, ALIASES, ARTIST_GROUPS): modifica quello,
# non questo file — sopravvive agli aggiornamenti dello script.
_USER_CFG = Path(__file__).with_name('exportify_names.json')


def load_user_config():
    if not _USER_CFG.exists():
        return
    try:
        _cfg = json.loads(_USER_CFG.read_text(encoding='utf-8'))
        # EMOJI_WORDS PRIMA di tutto: norm() lo usa per normalizzare le chiavi
        # delle tabelle qui sotto (prima veniva applicato dopo)
        EMOJI_WORDS.update(_cfg.get('EMOJI_WORDS', {}))
        NAME_FIXES.update({norm(k): norm(v) for k, v in _cfg.get('NAME_FIXES', {}).items()})
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
        PLAYLIST_FOLDERS.update(_cfg.get('PLAYLIST_FOLDERS', {}))
        SKIP_PLAYLISTS.extend(_cfg.get('SKIP_PLAYLISTS', []))
        PLAYLIST_PREFIXES.extend(_cfg.get('PLAYLIST_PREFIXES', []))
        for g in _cfg.get('ARTIST_GROUPS', []):
            sg = {norm(x) for x in g}
            if sg and sg not in ARTIST_GROUPS:
                ARTIST_GROUPS.append(sg)
        to_romaji.cache_clear()
        _title_qualifier_phrases.cache_clear()
        _title_variant_penalty_cached.cache_clear()
        print(f"[i] configurazione utente caricata: {_USER_CFG}", file=sys.stderr)
    except Exception as e:
        # prima: stampava l'errore e andava avanti con la config a meta' (skip-list
        # ignorata => playlist indesiderate importate in Navidrome). Ora: stop.
        sys.exit(f"[ERRORE] configurazione non valida ({_USER_CFG}): {e}")

_CJK = re.compile(r'[぀-ヿ㐀-鿿豈-﫿]')


@lru_cache(maxsize=None)
def to_romaji(s):
    """Kanji/kana -> romaji (Hepburn). Ritorna '' se non applicabile."""
    if not s:
        return ''
    if s in NAME_FIXES:
        return norm(NAME_FIXES[s])
    if not _HAS_KAKASI:
        return ''
    if not _CJK.search(s):
        return ''
    return norm(' '.join(w['hepburn'] for w in _kks.convert(s)))


AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wav', '.wma'}


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


def split_artists(s, by_artist):
    """Spezza 'Artista1, Artista2' in componenti, RICOMPOSTI usando la libreria
    come riferimento: 'Tyler, The Creator' e' UN artista (la virgola e' nel nome),
    'Tyler, The Creator, Kali Uchis' sono DUE. Se nessuna ricomposizione
    corrisponde a un artista noto, fallback allo split semplice."""
    ns = norm(s)
    if ns in by_artist:
        return [ns]
    parts = [norm(x) for x in re.split(r'[,;/]', s) if norm(x)]
    out, i = [], 0
    while i < len(parts):
        hit = None
        for j in range(len(parts), i, -1):          # prova il gruppo piu' lungo prima
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
    for rel in rels:
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
        if n % 5000 == 0:
            print(f"[i]   ...{n} brani scansionati", file=sys.stderr, flush=True)
    cjk = sorted({k for k in by_artist if _CJK.search(k)})
    if cjk:
        print(f"[i] {len(cjk)} nomi in kanji rilevati nella libreria (gruppati automaticamente col romaji):",
              file=sys.stderr)
        for k in cjk:
            print(f"      {k} -> {to_romaji(k) or '(nessuna conversione)'}", file=sys.stderr)
    return by_full, by_artist, by_strict, path_qual, n


CACHE_VERSION = 5


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
    print(f"[i] scansione di {LIBRARY_ROOT} in corso ({len(rels)} file)...", file=sys.stderr)
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
    return norm_bare(name)


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
    corr = correlate(fp1, fp2) if fp1 is not None and fp2 is not None else None
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

    nalb = norm_bare(album)
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


def _skip_patterns(extra=''):
    """[(voce originale, pattern)] da SKIP_PLAYLISTS (JSON) e --skip. '*' = jolly."""
    raws = [x.strip() for x in extra.split(',') if x.strip()] + [x for x in SKIP_PLAYLISTS if x.strip()]
    return [(r, '*'.join(_name_key(part) for part in r.split('*'))) for r in raws]


_SKIP_HITS = set()       # voci di SKIP_PLAYLISTS che hanno ignorato almeno un CSV
_SKIPPED_NAMES = []      # playlist ignorate in questa run
_SKIP_FILES_SEEN = [0]    # CSV esaminati da select_playlists in questa run


def report_skips(args):
    """Riepilogo: quante playlist ignorate e quali voci di SKIP_PLAYLISTS non combaciano con nulla."""
    if _SKIPPED_NAMES:
        shown = ', '.join(_SKIPPED_NAMES[:8]) + (' ...' if len(_SKIPPED_NAMES) > 8 else '')
        print(f"[i] playlist ignorate (SKIP_PLAYLISTS/--skip): {len(_SKIPPED_NAMES)}: {shown}",
              file=sys.stderr)
    unmatched = [r for r, _ in _skip_patterns(args.skip or '') if r not in _SKIP_HITS]
    if unmatched and not args.only and _SKIP_FILES_SEEN[0]:
        print(f"[i] voci di SKIP_PLAYLISTS/--skip senza nessun CSV corrispondente in questa run: "
              f"{', '.join(unmatched)} (se il nome e' giusto, puo' riguardare un altro utente)",
              file=sys.stderr)


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


def select_playlists(files, args):
    if args.only:
        keep = {_name_key(x) for x in args.only.split(',') if x.strip()}
        files = [f for f in files if _name_key(f.stem) in keep]
    pats = _skip_patterns(args.skip or '')
    _SKIP_FILES_SEEN[0] += len(files)
    if pats:
        kept = []
        for f in files:
            key = _name_key(f.stem)
            hits = [raw for raw, pat in pats if fnmatch.fnmatchcase(key, pat)]
            if not hits:
                kept.append(f)
            else:
                _SKIP_HITS.update(hits)          # tutte, non solo la prima: "entra?" e "entra" combaciano insieme
                _SKIPPED_NAMES.append(f.stem.replace('_', ' ').strip())
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
            if not ct or not ca:
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
        if not ct or not ca:
            print(f"[ERRORE] {csv_path.name}: intestazioni non riconosciute: {fieldnames[:8]}",
                  file=sys.stderr)
            return False

        matched, missing, seen, skipped = [], [], 0, 0
        seen_paths = set()
        for row in reader:
            title = (row.get(ct) or '').strip().strip('"')
            artist = clean_artist(row.get(ca))
            album = (row.get(cal) or '').strip().strip('"') if cal else ''
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

    # Prefissi configurati restano una trasformazione esplicita dell'utente.
    if auto_folder is None:
        prefix_source = original_title if original_title else base
        for pf in PLAYLIST_PREFIXES:
            if prefix_source.casefold().startswith(pf.casefold() + ' '):
                base = _playlist_filename(f'{pf} - {prefix_source[len(pf):].strip()}')
                break
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
        print(f"{tag}{out_path.name}: invariata (modifiche lato client preservate)")
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
          f"{f', {skipped} righe vuote saltate' if skipped else ''}")
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
    """Scrivi su piu' stream insieme (console + file di log)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
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
        seen_a, miss_a, who_a, name_a = Counter(), Counter(), {}, {}
        for (a, al, t) in SEEN_ALL:
            if al:
                ak = (a.lower(), al.lower())
                seen_a[ak] += 1
                name_a.setdefault(ak, (a, al))
        for (a, al, t), v in MISSING_ALL.items():
            if al:
                ak = (a.lower(), al.lower())
                miss_a[ak] += 1
                who_a.setdefault(ak, set()).update(u for u, _ in v)
        top_a = sorted(miss_a, key=lambda ak: (-miss_a[ak], -miss_a[ak] / seen_a[ak], ak))[:MISSING_TOP_ALBUMS]
        L.append(f"=== {len(top_a)} ALBUM DA SCARICARE (per canzoni mancanti) ===")
        L.append("# X/Y = canzoni trovate / canzoni di quell'album presenti nelle playlist")
        for i, ak in enumerate(top_a, 1):
            a, al = name_a[ak]
            who = f"  [{', '.join(sorted(who_a[ak], key=str.lower))}]" if multi else ''
            L.append(f"  {i:>2}. {a} - {al}  {_found_ratio(miss_a[ak], seen_a[ak])}{who}")
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
    out.write_text('\n'.join(L) + '\n', encoding='utf-8')
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
    # la TUA tabella (NAME_FIXES) vince su kakasi/hangul, anche nei tag. Prima la
    # lookup usava il valore GREZZO ('スペース・ロード') mentre le chiavi sono
    # normalizzate ('スペース ロード'): le voci del JSON non scattavano mai.
    r = NAME_FIXES.get(norm(s), '')
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
    # aggiungi la lettura a NAME_FIXES: kakasi leggerebbe con
    # pronuncia giapponese, sbagliata per il cinese.
    return to_romaji(s)


def _romanize_tag_value(v, _check=True):
    # niente caratteri asiatici = niente da romanizzare NE' da "riparare". Prima la
    # regola 'X (English) (romaji)' -> 'X (English)' girava su OGNI tag e troncava
    # titoli latini legittimi: 'Swimming Pools (Drank) (Extended Version)' diventava
    # 'Swimming Pools (Drank)', 'A Military Alphabet (five eyes all blind) (4 of 4)'
    # perdeva '(4 of 4)'.
    if not v or not (_CJK.search(v) or _HANGUL.search(v)):
        return v
    # gia' bilingue: c'e' una parentesi latina (traduzione/alias presente)
    # -> non toccare. E ripara le doppie traduzioni scritte dalle versioni
    # precedenti ('X (English) (romaji)' -> 'X (English)').
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


def run_romaji_tags(dry_run=False, base=None):
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
    prefetch_probe(files, 'romaji')      # ffprobe in parallelo / dalla cache
    for f in files:
        scanned += 1
        if scanned % 500 == 0:
            print(f'  ...{scanned} file scansiti, {changed} da romanizzare',
                  flush=True)
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
            print(f'{"[dry] " if dry_run else ""}ROMAJI '
                  f'{f.parent.parent.name} / {f.parent.name}: {desc}')
            if dry_run:
                changed += 1
                continue
            if f.suffix.lower() == '.flac':
                for k, v in newvals.items():
                    subprocess.run([*METAFLAC, f'--remove-tag={VORBIS[k]}',
                                    f'--set-tag={VORBIS[k]}={v}', str(f)],
                                   capture_output=True, timeout=60, check=True)
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
            print(f'ERRORE: {f}: {e}', file=sys.stderr)
    for b in base.rglob('*.meta-backup'):
        if b.with_name(b.name[:-len('.meta-backup')]).exists():
            b.unlink(missing_ok=True)
    print(f'romaji_tags: {scanned} file scansiti, {changed} modificati, {errors} errori')


# ===================== cache di ffprobe =====================
# Ogni notte date_heal / romaji_tags / album_unify rileggevano con ffprobe TUTTA
# la libreria (~50 ms a file: ~18 min ogni 20.000 brani, PER OGNI fase) anche
# se non era cambiato nulla. Ora i tag letti stanno in una cache persistente
# (path + mtime + dimensione): un file modificato (anche dallo script stesso)
# viene riletto, gli altri no. Le letture a freddo sono parallele.

PROBE_CACHE = CACHE_DIR / 'probe_cache_v3.json'   # v3: tag dei flussi (opus/ogg) + 'track'
for _old in ('probe_cache.json', 'probe_cache_v2.json'):      # formati precedenti
    try:
        (CACHE_DIR / _old).unlink()
    except OSError:
        pass
# thread di ffprobe in parallelo (EXPORTIFY_PROBE_WORKERS=2 se la musica sta su un NAS lento)
PROBE_WORKERS = max(1, int(os.environ.get('EXPORTIFY_PROBE_WORKERS') or min(8, (os.cpu_count() or 2) * 2)))
# solo i tag che lo script usa davvero (niente testi/commenti da KB per file)
_PROBE_KEEP = {'title', 'artist', 'album', 'albumartist', 'album_artist', 'date',
               'originaldate', 'musicbrainz_albumid', 'musicbrainz_releasegroupid',
               'track', 'tracknumber'}
_PROBE_MEM = None        # {path: [mtime_ns, size, tags, durata]}
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
                            'format_tags:format=duration:stream=codec_type:stream_tags', key],
                           capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or '{}')
        fmt = d.get('format')
        if not isinstance(fmt, dict):
            return None
        tags = {k.lower(): str(v) for k, v in (fmt.get('tags') or {}).items()}
        # .opus/.ogg: i Vorbis comment stanno nei tag del FLUSSO audio, non del formato
        # (prima probe() non leggeva NESSUN tag di questi file e unify li riscriveva ogni
        # notte). Solo il flusso audio: la copertina incorporata ha tag suoi (title...).
        for st in (d.get('streams') or []):
            if st.get('codec_type') == 'audio':
                for k, v in (st.get('tags') or {}).items():
                    tags.setdefault(k.lower(), str(v))
                break
        dur = fmt.get('duration')
        return tags, (float(dur) if dur else None)
    except Exception:
        return None


def _probe_entry(path):
    global _PROBE_DIRTY
    key = str(path)
    try:
        st = os.stat(key)
    except OSError:
        return None
    mem = _probe_mem()
    ent = mem.get(key)
    if ent and ent[0] == st.st_mtime_ns and ent[1] == st.st_size:
        return ent
    res = _ffprobe_raw(key)
    if res is None:
        return None
    tags, dur = res
    ent = [st.st_mtime_ns, st.st_size, {k: v for k, v in tags.items() if k in _PROBE_KEEP}, dur]
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
    return tags


def probe_dur(path: Path):
    """(tags, durata_sec) via ffprobe (con cache)."""
    ent = _probe_entry(path)
    if ent is None:
        return {}, None
    return dict(ent[2]), ent[3]


def flush_probe_cache():
    """Salva la cache (atomico). Sicuro mentre i thread di prefetch scrivono:
    lavora su uno snapshot (list(items) non cede il GIL) e riabbassa il flag
    PRIMA dello snapshot, cosi' le voci aggiunte durante il salvataggio
    restano 'sporche' per il flush successivo."""
    global _PROBE_DIRTY
    if _PROBE_MEM is None or not _PROBE_DIRTY:
        return
    _PROBE_DIRTY = False
    mem = _PROBE_MEM
    snap = list(mem.items())
    dead = {k for k, _ in snap if not os.path.exists(k)}
    # se "spariscono" piu' della meta' dei file la libreria e' probabilmente
    # smontata: non buttare la cache
    if dead and (len(snap) < 100 or len(dead) <= len(snap) // 2):
        for k in dead:
            mem.pop(k, None)
        snap = [(k, v) for k, v in snap if k not in dead]
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
        with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as ex:
            for _ in ex.map(_probe_entry, todo):
                done += 1
                if done % 2000 == 0:
                    print(f'  [{label}] ...{done}/{len(todo)}', file=sys.stderr, flush=True)
                if done % 10000 == 0:
                    flush_probe_cache()
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
              'musicbrainz_albumid': 'MUSICBRAINZ_ALBUMID',
              # title/artist: servono alla riparazione da nome file e alla regola 'artist'
              # di unify. Mancavano: KeyError su OGNI FLAC (la regola 'artist' ripiegava
              # su ffmpeg, la riparazione falliva e riprovava ogni notte)
              'title': 'TITLE', 'artist': 'ARTIST'}
    for k, v in targets.items():
        args += [f'--remove-tag={vorbis[k]}', f'--set-tag={vorbis[k]}={v}']
    args.append(str(path))
    subprocess.run(args, capture_output=True, timeout=120, check=True)


CODEC_FOR = {'.flac': 'flac', '.mp3': 'libmp3lame', '.m4a': 'aac',
             '.ogg': 'libvorbis', '.opus': 'libopus'}
UNIFY_FIELDS = ['album', 'albumartist', 'date', 'originaldate', 'musicbrainz_albumid']


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
        args += ['-metadata:s:a:0' if ogg else '-metadata', f'{k}={v}']
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
      - FLAC con ORIGINALDATE: fix_date_tags toglie comunque DATE, quindi unify
        non deve rimetterlo (si annullavano a vicenda nella stessa notte)."""
    ext = f.suffix.lower()
    if ext in ('.m4a', '.mp4') and k in ('originaldate', 'musicbrainz_albumid'):
        return False
    if k == 'date' and ext == '.flac' and (t.get('originaldate') or targets.get('originaldate')):
        return False
    return True


def run_unify(dry_run=False, base=None):
    base = Path(base) if base else LIBRARY_ROOT
    dirs = list(unify_album_dirs(base))   # materializzato: serve il totale per %/rimanenti
    total = len(dirs)
    prefetch_probe((f for _, fl in dirs for f in fl), 'unify')
    changed_albums = changed_files = errors = scanned = 0
    for album, files in dirs:
        scanned += 1
        if scanned % 50 == 0 or scanned == total:
            pct = scanned * 100 // total
            print(f'  ...{scanned}/{total} album esaminati '
                  f'({pct}% - ancora {total - scanned} da scansionare)',
                  file=sys.stderr, flush=True)
        tags = [probe(f) for f in files]
        # repair spotyFLAC: artist/title dai nomi file quando il tag e' rotto
        for f, t in zip(files, tags):
            rep = _filename_repair(f, t, (t.get('album'), album.name))
            if not rep:
                continue
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
                    t.update(rep)
                except Exception as e:
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
            if k == 'albumartist':
                pref = _folder_artist_preference(tags, album.parent.name)
                if pref:
                    top = pref
            if top is None:
                continue
            targets[k] = top
        # UNIFY_FORCE: pin per-album dalla configurazione (vincono sul voto)
        forced = UNIFY_FORCE.get(norm(f"{album.parent.name} / {album.name}"))
        if forced:
            for k, v in forced.items():
                if k in UNIFY_FIELDS:
                    print(f'    [force] {k}="{str(v)[:40]}" (pin dalla config)')
                    targets[k] = str(v)
        for k in list(targets):
            if all(t.get(k, '') == targets[k] for f, t in zip(files, tags)
                   if _unify_applies(f, t, k, targets)):
                del targets[k]
        if not targets:
            continue
        changed_albums += 1
        desc = ', '.join(f'{k}="{v[:40]}"' for k, v in targets.items())
        print(f'{"[dry] " if dry_run else ""}UNIFY {album.parent.name} / {album.name}: {desc}')
        if dry_run:
            continue
        for f, t in zip(files, tags):
            diff = {k: v for k, v in targets.items()
                    if t.get(k, '') != v and _unify_applies(f, t, k, targets)}
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
                changed_files += 1
            except Exception as e:
                errors += 1
                err = getattr(e, 'stderr', '') or ''
                print(f'ERRORE: {f}: {e} {str(err).strip()[:300]}', file=sys.stderr)
                if backup.exists() and not f.exists():
                    os.replace(backup, f)
                f.with_name(f.stem + '.tmp' + f.suffix).unlink(missing_ok=True)

    removed = 0
    for b in base.rglob('*.meta-backup'):
        if b.with_name(b.name[:-len('.meta-backup')]).exists():
            try:
                b.unlink()
                removed += 1
            except Exception:
                pass
    print(f'album esaminati: {scanned} | modificati: {changed_albums} '
          f'({changed_files} file) | errori: {errors} | backup rimossi: {removed}')



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
            c = correlate(fps[a], fps[b])
            if c is not None and c >= corr:        # None = non confrontabili
                parent[find(a)] = find(b)

    clusters = {}
    for f in files:
        clusters.setdefault(find(f), []).append(f)
    return list(clusters.values()), fps


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

    for art in artists:
        for album in sorted(art.iterdir()):
            if not album.is_dir():
                continue
            files = _audio_files(album)
            if len(files) < 2:
                continue
            prefetch_probe(files, 'dedupe')

            def handle_group(label, group):
                """Verifica waveform + eventuale cestinamento di un gruppo
                di file che condividono il titolo (strict o fuzzy)."""
                nonlocal n_groups, n_dup, n_distinct, unverifiable, errors
                n_groups += 1
                if not _HAS_NP:
                    unverifiable += 1
                    print(f"    [info] {album.name}: titolo '{label}' x{len(group)} "
                          f"— numpy assente, niente verifica: lascio tutto")
                    return
                clusters, fps = _cluster_by_waveform(group, meta, corr, max_dur,
                                                     trust_format=trust_format)
                multi = [c for c in clusters if len(c) > 1]
                if not multi:
                    n_distinct += 1
                    if all(fps[f] is None for f in group):
                        unverifiable += 1
                        print(f"    [info] {album.name}: titolo '{label}' x{len(group)} "
                              f"non verificabile (file <5s o non decodificabili)")
                    else:
                        print(f"    [info] {album.name}: titolo '{label}' con "
                              f"{len(group)} file ma versioni distinte (nessuna copia)")
                    return
                for cluster in multi:
                    cluster = sorted(cluster, key=lambda f: _keeper_score(f, meta[f][0]))
                    keeper, rest = cluster[0], cluster[1:]
                    for f in rest:
                        n_dup += 1
                        print(f"    {'[dry] ' if not apply else ''}DUPE  {album.name}/"
                              f"{f.name} (tengo {keeper.name})")
                        if apply:
                            try:
                                _move_to_trash(f, stamp, hard_delete, base)
                            except Exception as e:
                                errors += 1
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
                    print(f"    [review] {album.name}: titolo '{label}' con {len(group)} "
                          f"file e versioni qualificate (mix/live/karaoke/...): "
                          f"lascio tutto, verifica a orecchio")
                    continue
                handle_group(label, group)

    print(f"\ngruppi titolo esaminati: {n_groups} | duplicati nel cestino: {n_dup} "
          f"| versioni distinte: {n_distinct} | da verificare a orecchio: {n_review} "
          f"| non verificabili: {unverifiable} | errori: {errors}")
    if apply and not hard_delete:
        print(f"[i] duplicati nel cestino: {DEDUPE_TRASH / stamp}")
    if apply:
        print("[i] dopo verifica: scan rapido su Navidrome, poi svuota il cestino.")


# ===================== infrastruttura fasi (log UNICO + timer) =====================

_PHASE_TIMINGS = []       # [(nome fase, secondi), ...] nell'ordine di esecuzione
_RUN_STARTED_AT = None
_RUN_INTERRUPTED = False

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

def run_phase(logname, fn, *args, **kwargs):
    """Esegue e misura una fase; distingue completamento, errore e interruzione."""
    global _RUN_INTERRUPTED
    print(f'=== fase {logname} ===', flush=True)
    started = time.perf_counter()
    result = None
    status = 'completata'
    try:
        result = fn(*args, **kwargs)
        if result is False:
            status = 'fallita (ritorno False)'
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
        flush_probe_cache()
        elapsed = time.perf_counter() - started
        _PHASE_TIMINGS.append((logname, elapsed))
        if status == 'completata':
            label = f'fine fase {logname}'
        else:
            label = f'{status}: {logname}'
        print(f'=== {label} | durata {_elapsed_text(elapsed)} ===', flush=True)
    return result


# ===================== fase: artist_names (UN nome per artista) =====================
# Su Navidrome lo stesso artista giapponese/coreano compariva con 3 nomi:
#   'masayoshi takanaka'                (latino: spotyFLAC / tagger)
#   '高中正義'                           (kanji: tag originale)
#   '高中正義 (masayoshi takanaka)'      (gloss bilingue scritto da romaji_tags)
# Cause: romaji_tags aggiunge il gloss SOLO ai tag che contengono CJK, e album_unify
# riscriveva ALBUMARTIST ma ARTIST solo se i token del tag erano un sottoinsieme di
# quelli della cartella (mai vero per 'masayoshi takanaka' vs '高中正義').
# Questa fase porta TUTTE le scritture note dello stesso artista (NAME_FIXES,
# ARTIST_GROUPS, kakasi) alla forma canonica della cartella, nei tag ARTIST /
# ALBUMARTIST (e ARTISTS / ALBUMARTISTS dei FLAC, che Navidrome legge per i
# multi-artista). Cartelle in kanji/hangul: sempre. Cartelle latine: solo se nei tag
# della cartella compare davvero la scrittura CJK (evita falsi positivi tipo il
# 'Prism' canadese scambiato per 'プリズム').

_NF_REV = None
_FLAC_ARTIST_TAGS = ('ARTIST', 'ALBUMARTIST', 'ARTISTS', 'ALBUMARTISTS')


def _name_fixes_rev():
    """latino(norm) -> {chiavi CJK(norm)} da NAME_FIXES."""
    global _NF_REV
    if _NF_REV is None:
        _NF_REV = {}
        for k, v in NAME_FIXES.items():
            if k and v:
                _NF_REV.setdefault(v, set()).add(k)
    return _NF_REV


def _has_asian(s):
    return bool(s and (_CJK.search(s) or _HANGUL.search(s)))


def _artist_variants(name):
    """Tutte le scritture (norm) che la configurazione conosce per lo STESSO artista:
    il nome, il romaji (NAME_FIXES o kakasi), la direzione inversa latino->CJK e i
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
    """Riscrive i tag di un mp3/m4a/ogg/opus con ffmpeg (copia dello stream)."""
    tmp = f.with_name(f.stem + '.tmp' + f.suffix)
    try:
        write_ffmpeg(f, targets, tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(f, f.with_name(f.name + '.meta-backup'))
    os.replace(tmp, f)


def run_unify_artists(dry_run=False, base=None):
    global _NF_REV
    _NF_REV = None                      # NAME_FIXES puo' essere cambiato dopo la config
    base = Path(base) if base else LIBRARY_ROOT
    have_mf = shutil.which('metaflac') is not None
    tg = '[dry] ' if dry_run else ''
    n_art = n_files = n_stray = errors = 0

    # --- A. mp3 con DUE album artist: TPE2 (vecchio) + TXXX:albumartist (scritto da
    # write_ffmpeg <= 3.21). Lo script vedeva solo il TXXX e li credeva a posto, ma
    # Navidrome legge entrambi e mostra un artista in piu'. Teniamo il valore che lo
    # script voleva (TXXX), lo mettiamo in TPE2 e togliamo il TXXX.
    mp3s = [base.joinpath(*r) for r in _walk_audio(base, {'.mp3'})]
    prefetch_probe(mp3s, 'artist_names/mp3')
    for f in mp3s:
        t = probe(f)
        if t.get('album_artist') and t.get('albumartist') \
                and t['album_artist'] != t['albumartist']:
            new = t['albumartist']
            print(f'{tg}MP3-ALBUMARTIST {f.parent.parent.name} / {f.parent.name}: '
                  f'TPE2="{t["album_artist"][:30]}" + TXXX="{new[:30]}" -> "{new[:40]}"')
            if dry_run:
                n_stray += 1
                continue
            try:
                _rewrite_nonflac(f, {'album_artist': new, 'albumartist': ''})
                n_stray += 1
            except Exception as e:
                errors += 1
                print(f'ERRORE: {f}: {e}', file=sys.stderr)

    # --- B. un solo nome per artista, cartella per cartella
    artists = sorted(d for d in base.iterdir()
                     if d.is_dir() and d.name.lower() not in SKIP_TOP
                     and not d.name.startswith('.'))
    for art in artists:
        variants = _artist_variants(art.name)
        if not (_has_asian(art.name) or any(_has_asian(x) for x in variants)):
            continue                    # nessuna scrittura CJK possibile: non leggo i tag
        files = _audio_files(art)
        flacs = [f for f in files if f.suffix.lower() == '.flac']
        others = [f for f in files if f.suffix.lower() in
                  ('.mp3', '.m4a', '.mp4', '.ogg', '.opus')]
        if flacs and not have_mf:
            print(f'[ERRORE] metaflac non trovato: salto i FLAC di {art.name}',
                  file=sys.stderr)
            flacs = []
        prefetch_probe(others, 'artist_names')
        raw, probes, vals = {}, {}, []
        for f in flacs:
            try:
                raw[f] = _flac_raw_tags(f)
            except Exception as e:
                errors += 1
                print(f'ERRORE: {f}: {e}', file=sys.stderr)
                continue
            for k, v in raw[f]:
                if k in _FLAC_ARTIST_TAGS:
                    vals += [p.strip() for p in v.split(';') if p.strip()]
        for f in others:
            probes[f] = probe(f)
            for k in ('artist', 'albumartist'):
                vals += [p.strip() for p in probes[f].get(k, '').split(';') if p.strip()]
        canon = _folder_canon(art.name, vals)
        if not canon:
            continue
        variants = variants | {norm(canon)}
        changed = 0

        for f in raw:
            changes = {}
            for tag in _FLAC_ARTIST_TAGS:
                olds = [v for k, v in raw[f] if k == tag]
                if not olds:
                    continue
                news = []
                for v in olds:
                    nv = _remap_artist_value(v, variants, canon)
                    if nv not in news:
                        news.append(nv)
                if news != olds:
                    changes[tag] = news
            if not changes:
                continue
            changed += 1
            if dry_run:
                continue
            args = [*METAFLAC]
            for tag, vs in changes.items():
                args.append(f'--remove-tag={tag}')
                args += [f'--set-tag={tag}={v}' for v in vs]
            args.append(str(f))
            try:
                r = subprocess.run(args, capture_output=True, timeout=120)
                if r.returncode != 0:
                    raise RuntimeError(f'metaflac exit {r.returncode}: '
                                       f'{r.stderr.decode("utf-8", "replace").strip()[:160]}')
            except Exception as e:
                errors += 1
                changed -= 1
                print(f'ERRORE: {f}: {e}', file=sys.stderr)

        for f in others:
            t = probes[f]
            aa_key = 'albumartist' if f.suffix.lower() in ('.ogg', '.opus') else 'album_artist'
            changes = {}
            for src_key, out_key in (('artist', 'artist'), ('albumartist', aa_key)):
                old = t.get(src_key, '')
                if not old:
                    continue
                new = _remap_artist_value(old, variants, canon)
                if new != old:
                    changes[out_key] = new
            if not changes:
                continue
            changed += 1
            if dry_run:
                continue
            try:
                _rewrite_nonflac(f, changes)
            except Exception as e:
                errors += 1
                changed -= 1
                print(f'ERRORE: {f}: {e}', file=sys.stderr)

        if changed:
            n_art += 1
            n_files += changed
            print(f'{tg}ARTIST-NAMES {art.name}: {changed} file -> "{canon}"')

    removed = 0
    for b in base.rglob('*.meta-backup'):
        if b.with_name(b.name[:-len('.meta-backup')]).exists():
            try:
                b.unlink()
                removed += 1
            except OSError:
                pass
    print(f'artist_names: {n_art} artisti unificati ({n_files} file) | '
          f'mp3 con doppio album artist riparati: {n_stray} | errori: {errors} | '
          f'backup rimossi: {removed}')
    if n_art or n_stray:
        print("[i] su Navidrome le voci artista vecchie spariscono col full scan "
              "(parte da solo a fine lavoro, salvo --no-scan)")


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

    for art in artists:
        files = _audio_files(art)
        mp3s = [f for f in files if f.suffix.lower() == '.mp3']
        flacs = [f for f in files if f.suffix.lower() == '.flac']
        if not mp3s or not flacs:
            continue
        prefetch_probe(mp3s + flacs, 'mp3_vs_flac')
        meta = {f: probe_dur(f) for f in mp3s + flacs}
        skey = {f: norm_bare(best_title(f, meta[f][0])) for f in mp3s + flacs}
        fkey = {f: norm(best_title(f, meta[f][0])) for f in mp3s + flacs}
        by_s, by_f = {}, {}
        for fl in flacs:
            by_s.setdefault(skey[fl], []).append(fl)
            by_f.setdefault(fkey[fl], []).append(fl)

        for m in mp3s:
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
                print(f"    [review] {art.name}/{rel}: titolo uguale a un FLAC ma durata "
                      f"ignota o troppo diversa: lascio l'mp3")
                continue
            same = sorted((c for c in ok if _same_album(art, m, c)),
                          key=lambda c: _keeper_score(c, meta[c][0]))
            if not same:
                n_review += 1
                print(f"    [review] {art.name}/{rel}: il FLAC sta in un altro album "
                      f"({ok[0].relative_to(art)}): lascio l'mp3")
                continue
            keeper = None
            if trust_format:
                keeper = same[0]
            elif not _HAS_NP:
                n_review += 1
                print(f"    [info] {art.name}/{rel}: numpy assente, niente verifica waveform: "
                      f"lascio l'mp3 (usa --trust-format per fidarti di titolo+durata)")
                continue
            else:
                fp_m = fingerprint(m)
                for c in same:
                    cc = correlate(fp_m, fingerprint(c))
                    if cc is not None and cc >= corr:
                        keeper = c
                        break
                if keeper is None:
                    n_review += 1
                    print(f"    [review] {art.name}/{rel}: waveform diversa dal FLAC "
                          f"(o non confrontabile): lascio l'mp3")
                    continue
            n_del += 1
            print(f"    {'[dry] ' if not apply else ''}MP3-DUPE  {art.name}/{rel} "
                  f"(tengo {keeper.relative_to(art)})")
            if apply:
                try:
                    _move_to_trash(m, stamp, hard_delete, base)
                except Exception as e:
                    errors += 1
                    n_del -= 1
                    print(f"    ERRORE spostamento {m}: {e}", file=sys.stderr)

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


def run_date_heal(dry_run=False, base=None):
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

    # --- FASE MBID SANITY: uno stesso MUSICBRAINZ_ALBUMID in piu' cartelle
    # con nomi diversi = PID condiviso = album fusi per sempre (Navidrome
    # PID.Album: musicbrainz_albumid vince su tutto). Strippo l'ID dalle
    # cartelle il cui nome NON corrisponde al titolo della release MB.
    mbid_map = {}
    for album, files in folders.items():
        for f in files[:6]:
            t = probe_dur(f)[0]
            mb = t.get('musicbrainz_albumid', '')
            if mb:
                mbid_map.setdefault(mb, {}).setdefault(album, []).append(f)
                break
    for mb, places in mbid_map.items():
        if len(places) < 2:
            continue
        _, title = _mb_release_info(None, mb, cache, tcache)
        nt = norm(album_base(title)) if title else ''
        if not nt:
            continue
        for album, files in places.items():
            # confronto col TAG ALBUM dei file (non col nome cartella: le
            # convenzioni di naming variano, il tag e' la verita' di grouping)
            alb_tags = [probe_dur(f)[0].get('album', '') for f in files[:8]]
            alb_tags = [a for a in alb_tags if a]
            maj = Counter(alb_tags).most_common(1)[0][0] if alb_tags else album.name
            # nome cartella e nome GENITORE (i sottodischi 'Vinyl 01' hanno
            # il titolo un livello sopra)
            name_bases = [norm(album_base(album.name)),
                          norm(album_base(album.parent.name))]
            # tiene l'ID se: tag album corrisponde, OPPURE nome cartella
            # corrisponde, OPPURE il titolo release e' contenuto nel nome
            # cartella (prefissi tipo '虹伝説 The Rainbow Goblins'). Il
            # contenimento vale SOLO title->folder, mai il contrario:
            # 'ok computer oknotok' in 'ok computer' e' falso, cosi' la
            # cartella 'OK Computer' pura perde l'ID del box OKNOTOK.
            if (norm(album_base(maj)) == nt or nt in name_bases
                    or any(len(nt) >= 4 and nt in nb for nb in name_bases)):
                continue   # questa cartella e' la release corretta: tiene l'ID
            print(f"{'[dry] ' if dry_run else ''}MBID-SANITY: '{album.parent.name} / {album.name}' "
                  f"ha MUSICBRAINZ_ALBUMID di '{title}': rimuovo l'ID (merge forzato)")
            if not dry_run:
                ok = True
                # `files` contiene UN solo file (quello su cui e' stato letto l'ID: il
                # ciclo di raccolta fa break). Prima l'ID veniva tolto da quel file e
                # album_unify lo ricopiava dagli altri la stessa notte (OK Computer,
                # FINGER DANCIN'...): il 'merge forzato' non funzionava mai.
                album_files = folders.get(album, files)
                non_flac = [f for f in album_files if f.suffix.lower() != '.flac']
                if non_flac:
                    print(f"    [ATTENZIONE] {len(non_flac)} file non-FLAC in '{album.name}' "
                          f"conservano l'ID (metaflac non li gestisce)", file=sys.stderr)
                for f in album_files:
                    if f.suffix.lower() != '.flac':
                        continue
                    r = subprocess.run([*METAFLAC, '--remove-tag=MUSICBRAINZ_ALBUMID',
                                        '--remove-tag=MUSICBRAINZ_RELEASEGROUPID', str(f)],
                                       capture_output=True, timeout=60)
                    if r.returncode != 0:
                        ok = False
                        print(f'    [ERRORE] metaflac su {f.name}: '
                              f'{r.stderr.decode()[:200]}', file=sys.stderr)
                if not ok:
                    print(f'    [ATTENZIONE] strip parziale in {album}: '
                          f'alcuni file hanno ancora l\'ID', file=sys.stderr)
                stripped += 1

    for album, files in sorted(folders.items()):
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
            print(f'ERRORE: {album}: {e}', file=sys.stderr)
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


def run_fix_dates(dry_run=False, base=None):
    import shutil as _sh
    if not _sh.which('metaflac'):
        print('[ERRORE] metaflac non trovato: salto fix_date_tags')
        return
    base = Path(base) if base else LIBRARY_ROOT
    fixed = errors = 0
    for f in sorted(base.rglob('*.flac')):
        try:
            _tv = _flac_tags(f, 'DATE', 'ORIGINALDATE')
            date_v, orig_v = _tv['DATE'], _tv['ORIGINALDATE']
            if orig_v:
                if date_v and date_v != orig_v:
                    print(f"{'[dry] ' if dry_run else ''}FIX(rem): {f.name}  "
                          f"DATE={date_v} ORIGINALDATE={orig_v}")
                    if not dry_run:
                        _metaflac_run('--remove-tag=DATE', path=f)
                        fixed += 1
            elif date_v:
                year = ''
                for d in (f.parent, f.parent.parent):
                    m = DATE_YEAR_RE.search(d.name)
                    if m:
                        year = m.group(0).strip('()')
                        break
                if year and date_v != year:
                    print(f"{'[dry] ' if dry_run else ''}FIX(set): {f.name}  "
                          f"DATE={date_v} -> ORIGINALDATE={year}")
                    if not dry_run:
                        _metaflac_run(f'--set-tag=ORIGINALDATE={year}', path=f)
                        _metaflac_run('--remove-tag=DATE', path=f)
                        fixed += 1
        except Exception as e:
            errors += 1
            print(f'ERRORE: {f}: {e}', file=sys.stderr)
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


def _probe_flac(path):
    try:
        r = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json',
                            '-show_entries',
                            'format=duration:stream=channels,sample_rate,'
                            'bits_per_raw_sample', str(path)],
                           capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or '{}')
        st = (d.get('streams') or [{}])[0]
        return (int(st.get('bits_per_raw_sample') or 0),
                int(st.get('channels') or 0),
                int(st.get('sample_rate') or 0),
                float(d.get('format', {}).get('duration') or 0))
    except Exception:
        return 0, 0, 0, 0.0


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
    except Exception:
        cache = {}
    converted = skipped = errors = nogain = 0
    saved = 0
    stopped = ''
    attempts = 0
    for p in sorted(base.rglob('*.flac')):
        if p.name.endswith('.flac.flac') or p.name.endswith('.backup'):
            continue
        try:
            st = p.stat()
        except Exception:
            continue
        key = str(p)
        if cache.get(key) == [st.st_mtime, st.st_size]:
            skipped += 1
            continue
        bps, ch, sr, dur = _probe_flac(p)
        if not bps or not ch or not sr or not dur:
            skipped += 1
            continue
        raw = dur * sr * ch * bps / 8
        ratio = st.st_size / raw if raw else 1.0
        if bps <= 16 and ratio <= FLAC16_MAX_RATIO:
            skipped += 1
            continue          # gia' ben compresso: non toccare
        tag = f'24->16bit ({bps}bit)' if bps > 16 else f'16bit ricomprimo (ratio {ratio:.2f})'
        if dry_run:
            print(f'[dry] {tag}: {p.name}')
            converted += 1
            continue
        # spazio: serve ~ la dimensione del file nuovo (<= originale) + margine. Ieri il
        # disco si e' riempito a meta' fase ('No space left on device') e le ultime
        # decine di file sono fallite una dopo l'altra.
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
                # nessun guadagno: NON e' un errore. Lo ricordiamo (path+mtime+size) cosi'
                # non si rifa' ogni notte (prima: ~230 ricompressioni inutili a notte)
                cache[key] = [st.st_mtime, st.st_size]
                nogain += 1
                continue                       # il finally cancella il tmp
            backup = p.with_name(p.name + '.backup')
            os.replace(p, backup)
            os.replace(tmp, p)
            # verifica del file finale e SUBITO via il backup (prima restavano tutti
            # fino a fine fase: lo spazio occupato cresceva a ogni conversione)
            fb, fch, fsr, _fd = _probe_flac(p)
            if not fb or fch != ch or fsr != sr:
                os.replace(backup, p)
                raise RuntimeError("verifica finale fallita: ripristinato l'originale")
            backup.unlink(missing_ok=True)
            cache[key] = [p.stat().st_mtime, p.stat().st_size]
            saved += st.st_size - newsize
            print(f'{tag}: {p.name} ({st.st_size // 1024}K -> {newsize // 1024}K)')
            converted += 1
        except Exception as e:
            errors += 1
            msg = str(e)
            print(f'ERRORE: {p}: {msg[:300]}', file=sys.stderr)
            if 'No space left' in msg:
                stopped = 'disco pieno (No space left on device)'
                break
        finally:
            tmp.unlink(missing_ok=True)
            if attempts and attempts % 100 == 0:
                _write_json_atomic(cache_path, cache)

    removed = 0
    for b in base.rglob('*.backup'):          # residui di esecuzioni interrotte
        if b.with_name(b.name[:-len('.backup')]).exists():
            try:
                b.unlink()
                removed += 1
            except Exception:
                pass
    _write_json_atomic(cache_path, cache)
    if stopped:
        print(f'[STOP] fase interrotta: {stopped}. Libera spazio e rilancia.', file=sys.stderr)
    print(f'convertiti: {converted} | saltati (cache o gia ok): {skipped} | '
          f'scartati (nessun guadagno): {nogain} | errori: {errors} | '
          f'spazio recuperato: {saved // 1024}K | backup residui rimossi: {removed}')


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
        last_print = time.monotonic()
        while st.get('scanning') and time.monotonic() < wait_deadline:
            time.sleep(3)
            try:
                st = _get_scan_status()
            except Exception as e:
                print(f'  [warn] getScanStatus durante attesa: {e}', flush=True)
                continue
            if st.get('scanning') and time.monotonic() - last_print >= 300:
                print(f"  ...scan preesistente ancora in corso: {st.get('count', '?')} brani indicizzati",
                      flush=True)
                last_print = time.monotonic()
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
    last_print = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            st = _get_scan_status()
        except Exception as e:
            print(f'  [warn] getScanStatus: {e}', flush=True)
            continue
        if not st.get('scanning'):
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
        total = globals().get('_LIB_TRACK_COUNT')
        if cnt // 1000 != (last or {}).get('count', 0) // 1000 or \
                time.monotonic() - last_print > 300:
            if total:
                pct = cnt * 100 // total
                print(f"  ...scan in corso: {cnt}/{total} brani "
                      f"({pct}% - ancora {total - cnt} da scansionare)", flush=True)
            else:
                print(f"  ...scan in corso: {cnt} brani", flush=True)
            last_print = time.monotonic()
        last = st
    print(f'[ERRORE] scan Navidrome: timeout dopo {timeout // 60} minuti',
          file=sys.stderr, flush=True)
    return False


# ===================== fase: star Spotify-liked music =====================
# Le stelle Navidrome sono per utente. Le tracce provengono da "liked" (o il vecchio
# nome "liked songs"), gli album da "saved albums", e gli artisti sono quelli presenti
# nelle due raccolte. Spotify non esporta i followed artists in un CSV Exportify standard.
SUBSONIC_BASE = os.environ.get('ND_URL', 'http://192.168.1.7:4533').rstrip('/')
SUBSONIC_USER = os.environ.get('ND_USER', 'chic')
SUBSONIC_PASS = os.environ.get('ND_PASS')

def _load_navidrome_env_file():
    """Carica ND_* da un env file per il cron. L'ambiente gia' impostato ha precedenza."""
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
                if not (key in {'ND_URL', 'ND_USER', 'ND_DEFAULT_USER', 'ND_PASS'} or
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
    for u in (users if users is not None else (_db_users() or [SUBSONIC_USER])):
        pw, key = _user_password(u)
        if pw is None:
            print(f"[{u}] star_liked: nessuna password (imposta {key}), saltato")
            continue
        try:
            _star_liked_for(u, pw)
        except Exception as e:
            print(f"[{u}] [ERRORE] star_liked: {type(e).__name__}: {e}", file=sys.stderr)


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
        for pid, oid, path in rows:
            tgt = _owner_for_playlist_path(path, users_lower, default_name)
            if tgt is None or (wanted is not None and tgt.lower() not in wanted):
                continue
            tid = ids[tgt.lower()][0]
            if oid != tid:
                changes.append((tid, pid, tgt))
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
        for (_, name), grp in sorted(groups.items(),
                                     key=lambda kv: (str(kv[1][0][3]).lower(), kv[0][1].lower())):
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
            print(f"  [{uname}] {name!r}: {len(grp)} copie -> tengo {desc(keep)}")
            for r in drop:
                print(f"      elimino {desc(r)}")
            diff = [r for r in drop if r[6] and r[6] != keep[6]]
            if diff:
                print(f"      nota: percorsi m3u diversi (tenuto: {keep[6] or '-'}; eliminato: "
                      f"{diff[0][6]}) - se quell'm3u e' ancora su disco, Navidrome lo reimportera'")
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
    for aid, name, aa, paths in cand:
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
                print(f"  [ERRORE] {f.name}: {type(e).__name__}: {e}", file=sys.stderr)
        values = _collab_values([v for t in per_file.values() for v in t['ALBUMARTIST']])
        target = _collab_target(values)
        print(f"  '{name}'  (Navidrome: {aa})")
        if missing_on_disk:
            print(f"      [!] {len(missing_on_disk)} file del DB non trovati sul disco "
                  f"(imposta ND_MUSIC_ROOT se il prefisso del container non viene riconosciuto), "
                  f"es. {missing_on_disk[0]}")
        if others:
            print(f"      [!] {len(others)} file non FLAC (non modificati): "
                  f"{', '.join(sorted({h.suffix.lower() for h in others}))}")
        if not per_file:
            print("      nessun FLAC leggibile: niente da fare")
            continue
        if target is None:
            print(f"      i tag dei FLAC sono gia' a posto (ALBUMARTIST: {values}): il DB e' "
                  f"indietro, basta uno scan di Navidrome")
            continue
        todo = []
        for f, t in per_file.items():
            if t['ALBUMARTIST'] != target or (t['ALBUMARTISTS'] and t['ALBUMARTISTS'] != target):
                todo.append(f)
        now = Counter(tuple(t['ALBUMARTIST']) for t in per_file.values())
        for combo, n in now.most_common():
            print(f"      ALBUMARTIST ora ({n} file): {list(combo)}")
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
                print(f"      [ERRORE] {f.name}: {type(e).__name__}: {e}", file=sys.stderr)
        fixed_files += ok
        fixed_albums += 1 if ok else 0
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


def run_check_albums(album=None, artist=None, search=True):
    """Confronta ogni album del DB con MusicBrainz e scrive logs/album_incompleti_<data>.txt."""
    if not NAVIDROME_DB.exists():
        print(f'[ERRORE] DB non trovato: {NAVIDROME_DB}')
        return
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
    albums = [a for a in albums if _album_filter(a[1], a[2], album, artist) and local.get(a[0])]
    cache = _mb_load_cache()
    res = []                      # (artista, album, locali, mb_totale, [mancanti], come)
    notfound, errors = [], 0
    calls0 = _MB_CALLS[0]
    n_mbid = n_name = 0
    consec_err = 0
    last_save = _MB_CALLS[0]
    print(f"[i] check-albums: {len(albums)} album da controllare (1 richiesta/s a MusicBrainz, cache: "
          f"{len(cache['release'])} release)", file=sys.stderr)
    try:
        for i, (aid, name, aa, mbid) in enumerate(albums, 1):
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
                print(f"[i] check-albums {i}/{len(albums)} (richieste MusicBrainz: {_MB_CALLS[0] - calls0})",
                      file=sys.stderr)
    finally:
        _mb_save_cache(cache)
    inc = sorted([r for r in res if r[4]], key=lambda r: (-len(r[4]), -len(r[4]) / max(r[3], 1), r[0].lower(), r[1].lower()))
    tot_missing = sum(len(r[4]) for r in inc)
    tot_mb = sum(r[3] for r in res)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    out = LOG_DIR / f'album_incompleti_{now:%Y-%m-%d}.txt'
    L = [f'# album incompleti secondo MusicBrainz - esecuzione {now:%Y-%m-%d %H:%M}',
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
    out.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f"[i] album incompleti: {_ratio(len(inc), len(res))} | tracce mancanti "
          f"{_ratio(tot_missing, tot_mb)} | non trovati: {len(notfound)} -> {out}")
    for aa, name, nloc, ntot, miss, how in inc[:10]:
        print(f"    {aa} - {name}: mancano {_ratio(len(miss), ntot)} [{how}]")


# ===================== fase: clean empty albums =====================
# (da clean_empty_albums.py — rimuove cartelle senza audio vuote da >24h)

CLEAN_MARKER = '.ndempty'
CLEAN_MAX_AGE = 24 * 3600


def _has_audio_tree(d: Path) -> bool:
    # INDEX_EXT (non AUDIO_EXT): una cartella di soli .aiff/.ape/.wv/.dsf/...
    # NON e' vuota. Prima veniva cancellata dopo 24h (rmtree) con tutta la musica.
    for p in d.rglob('*'):
        if p.is_file() and p.suffix.lower() in INDEX_EXT:
            return True
    return False


def run_clean_empty(dry_run=False, base=None):
    base = Path(base) if base else LIBRARY_ROOT
    now = time.time()
    removed = marked = waiting = unmarked = 0
    for root, dirs, files in os.walk(base, topdown=False):
        d = Path(root)
        if d == base or d.name.startswith('.'):
            continue
        rel = d.relative_to(base)
        if rel.parts and rel.parts[0].lower() == 'playlists':
            continue
        if _has_audio_tree(d):
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
            print(f"{'[dry] ' if dry_run else ''}RIMUOVO {rel} (vuota da {int(age // 3600)}h)")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            removed += 1
        else:
            waiting += 1
    conflicts = 0
    for cf in base.rglob('*.sync-conflict-*'):
        if cf.is_file():
            print(f"{'[dry] ' if dry_run else ''}RIMUOVO conflitto syncthing: {cf.name}")
            if not dry_run:
                try:
                    cf.unlink()
                    conflicts += 1
                except Exception:
                    pass
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

QUALIFIERS = re.compile(r'\(.*?\)|\[.*?\]')


def album_base(name: str) -> str:
    """Nome album 'fisso': senza parentesi, anni, remaster/deluxe/..."""
    s = norm(name)
    s = QUALIFIERS.sub(' ', s)
    s = re.sub(r'\b(19|20)\d{2}\b', ' ', s)
    s = re.sub(r'\b(remaster\w*|deluxe|anniversary|edition|version|reissue|'
               r'expanded|bonus|single|ep|demos?|live)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _audio_files(folder: Path):
    return [f for f in sorted(folder.rglob('*'))
            if f.is_file() and f.suffix.lower() in AUDIO_EXT]


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


def _shift_corr(x, y, n, s, min_len):
    """Correlazione con y slittata di s campioni rispetto a x."""
    if s >= 0:
        u, v = x[:n - s], y[s:]
    else:
        u, v = x[-s:], y[:n + s]
    if len(u) < min_len:
        return None
    # abs: una copia a polarita' invertita (capita in alcune masterizzazioni)
    # e' identica al 100% ma correlerebbe a -1 senza il modulo
    return abs(float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9)))


def _aligned_corr(x, y, n, rate):
    """Due passaggi di ricerca offset (±1s a 0.1s, poi ±0.1s a 5ms intorno al
    migliore). Il passaggio fine include SEMPRE esplicitamente s0 e 0: le
    griglie a passo fisso non garantiscono di campionare lo zero esatto
    (rate//10 non divide rate), e per segnali tonali perdere lo zero e'
    catastrofico."""
    step_c = rate // 10
    step_f = max(1, rate // 200)
    best, s0 = 0.0, 0
    for s in range(-rate, rate + 1, step_c):
        c = _shift_corr(x, y, n, s, rate * 5)
        if c is not None and c > best:
            best, s0 = c, s
    cand = set(range(s0 - step_c, s0 + step_c + 1, step_f))
    cand |= {s0, 0}
    for s in cand:
        c = _shift_corr(x, y, n, s, rate * 5)
        if c is not None and c > best:
            best = c
    return best


def correlate(x, y, rate=11025):
    """Massima correlazione di Pearson. Gestisce:
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
    best = _aligned_corr(x, y, n, rate)
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
        c = _aligned_corr(x[:m], yy, m, rate)
        if c > best:
            best, best_r = c, r
    if best < 0.95 and best_r is not None:
        for r in np.arange(best_r - 0.005, best_r + 0.0051, 0.001):
            m = min(n, int(len(y) / r) - 1)
            if m < rate * 5:
                continue
            yy = np.interp(np.arange(m) * r, np.arange(len(y)), y)
            c = _aligned_corr(x[:m], yy, m, rate)
            if c > best:
                best = c
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
    c = correlate(x, y, rate)
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

    for art in artists:
        groups = {}
        for album in sorted(art.iterdir()):
            if not album.is_dir():
                continue
            files = _audio_files(album)
            if not files:
                continue
            b = album_base(album.name)
            if b:
                groups.setdefault(b, []).append((album, files))

        for b, releases in groups.items():
            if len(releases) < 2:
                continue
            n_groups += 1
            releases.sort(key=lambda r: (folder_year(r[0], r[1]), r[0].name))
            canonical = releases[0]
            others = releases[1:]
            print(f"\n=== {art.name} / [{b}] ===")
            print(f"    CANONICA : {canonical[0].name} "
                  f"({len(canonical[1])} tracce, anno {folder_year(canonical[0], canonical[1])})")
            for al, fl in others:
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
                        print(f"    {'[dry] ' if not apply else ''}DUPE  {al.name}/"
                              f"{f.name} == {match.parent.name}/{match.name} ({why})")
                        if apply:
                            try:
                                _move_to_trash(f, stamp, hard_delete, base)
                            except Exception as e:
                                errors += 1
                                print(f"    ERRORE spostamento {f}: {e}", file=sys.stderr)
                    else:
                        n_bonus += 1
                        next_num += 1
                        clean_name = re.sub(r'^\d{1,3}\s*[-._ ]\s*', '', f.name)
                        newname = f"{next_num:02d} - {clean_name}"
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
                                    print(f"    [warn] tracknumber non scritto "
                                          f"su {dest}: {e}", file=sys.stderr)
                                canon_files.append(dest)
                                c_meta[dest] = probe_dur(dest)
                            except Exception as e:
                                errors += 1
                                print(f"    ERRORE spostamento bonus {f}: {e}",
                                      file=sys.stderr)

    print(f"\ngruppi release: {n_groups} | duplicati: {n_dup} | "
          f"bonus spostate: {n_bonus} | errori: {errors}")
    if apply and not hard_delete:
        print(f"[i] duplicati nel cestino: {DEDUPE_TRASH / stamp}")
    if apply:
        print("[i] dopo verifica: scan rapido su Navidrome, poi svuota il cestino.")


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


def _has_local_album_art(album_dir, album_title=''):
    """True se la cartella possiede già una cover con nome convenzionale/di album."""
    known = _ARTWORK_KNOWN_STEMS | ({norm_bare(album_title)} if album_title else set())
    try:
        for child in album_dir.iterdir():
            if child.is_file() and child.suffix.lower() in _ARTWORK_EXTS:
                if norm_bare(child.stem) in known:
                    return True
    except OSError:
        return True  # non potendo leggere la cartella, non scrivere a tentoni
    return False


def _embedded_art_state(track_path, timeout=10):
    """True/False se ffprobe rileva una cover embedded; None se non è possibile verificarla."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v',
             '-show_entries', 'stream=codec_type:stream_disposition=attached_pic',
             '-of', 'json', str(track_path)],
            capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or '{}')
        return any(int((stream.get('disposition') or {}).get('attached_pic', 0) or 0) == 1
                   for stream in data.get('streams', []))
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
    """Gruppi filesystem album->tracce, senza interrogare ffprobe su tutti i file audio."""
    groups = {}
    for rel in _walk_audio(LIBRARY_ROOT, INDEX_EXT):
        track = LIBRARY_ROOT.joinpath(*rel)
        album_dir = _album_art_directory(track)
        if album_dir is not None:
            groups.setdefault(album_dir, []).append(track)
    return groups


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

    groups = _load_artwork_album_groups()
    cache = _artwork_cache_load()
    negative = cache.setdefault('not_found', {})
    now = int(time.time())
    timeout = int(cfg['request_timeout'])
    min_bytes, max_bytes = int(cfg['min_image_bytes']), int(cfg['max_image_bytes'])
    candidates, negative_skipped = [], 0
    embedded_unknown = 0

    for album_dir, tracks in sorted(groups.items(), key=lambda item: str(item[0]).casefold()):
        if not tracks or _has_local_album_art(album_dir, album_dir.name):
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

        if cfg.get('check_embedded_art', True):
            states = [_embedded_art_state(track, timeout=min(timeout, 10)) for track in tracks[:3]]
            if any(state is True for state in states):
                continue
            if states and all(state is None for state in states):
                print(f'[artwork] cover non controllabile (ffprobe): {album_dir}', file=sys.stderr)
                embedded_unknown += 1
                continue

        key = _artwork_cache_key(artist_name, album_name)
        until = int(negative.get(key, 0) or 0)
        if until > now:
            negative_skipped += 1
            continue
        if until:
            negative.pop(key, None)
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
    for index, item in enumerate(selected, 1):
        artist, album, album_dir, mbid = item['artist'], item['album'], item['dir'], item['mbid']
        attempted += 1
        print(f'[artwork] {index}/{len(selected)} {artist} — {album}', flush=True)
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
            print(f'[artwork] scaricata: {target} ({len(data) // 1024} KiB)', flush=True)
        except FileExistsError:
            print(f'[artwork] file temporaneo già esistente, salto: {tmp}', file=sys.stderr)
        except OSError as e:
            print(f'[artwork] impossibile salvare {target}: {e}', file=sys.stderr)
        finally:
            tmp.unlink(missing_ok=True)

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

def main():
    ap = argparse.ArgumentParser(description='Exportify CSV -> m3u per Jellyfin + manutenzione libreria')
    ap.add_argument('--version', action='version',
                    version=f'%(prog)s {VERSION}')
    ap.add_argument('csv', nargs='*', help='CSV specifici (default: tutti in EXPORTIFY_DIR)')
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
                    help='esegui TUTTE le fasi in sequenza: fix-owners -> dedupe-playlists -> '
                         'dedupe release/tracce -> '
                         'mp3-vs-flac -> clean-empty -> playlist+unify -> star-liked '
                         '(dedupe e mp3-vs-flac in dry-run salvo --apply). Se esistono sessioni '
                         'Exportify salvate scarica anche gli zip, come --fetch')
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
                    help='confronta ogni album del DB con la tracklist di MusicBrainz e scrive '
                         'logs/album_incompleti_<data>.txt (tracce mancanti). Solo lettura; la prima run '
                         'e\' lenta (1 richiesta/s), poi c\'e\' la cache')
    ap.add_argument('--mb-no-search', action='store_true',
                    help='check-albums: controlla solo gli album con MUSICBRAINZ_ALBUMID, senza cercare '
                         'gli altri per artista+album')
    ap.add_argument('--clean-empty', action='store_true',
                    help='fase: rimuovi cartelle senza audio vuote da >24h')
    ap.add_argument('--star-liked', action='store_true',
                    help='fase: stella brani di liked/liked songs, album di saved albums e artisti presenti '
                         '(password per utente in ND_PASS_<UTENTE>)')
    ap.add_argument('--fix-owners', nargs='?', const='', default=None, metavar='USER',
                    help='fase: assegna le playlist importate da m3u al proprietario giusto (cartella '
                         'utente in Playlists/); USER = proprietario di quelle fuori dalle cartelle '
                         'utente (default: DEFAULT_USER)')
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

    # UN solo log per tutta l'esecuzione: console + file, fasi comprese
    logf = open_run_log(_log_command_tag(sys.argv[1:], tuple(getattr(ap, '_option_string_actions', {}))))
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Tee(old_out, logf), Tee(old_err, logf)
    global _RUN_STARTED_AT, _PHASE_TIMINGS, _RUN_INTERRUPTED
    _RUN_STARTED_AT = time.perf_counter()
    _PHASE_TIMINGS.clear()
    _RUN_INTERRUPTED = False
    try:
        _run(args)
    except SystemExit as e:
        if isinstance(e.code, str):          # sys.exit("msg") altrimenti uscirebbe dal log
            print(e.code, file=sys.stderr)
            raise SystemExit(1)
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
    finally:
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


def _scan_before_favorites(users, full_scan=True):
    """Avvia la scan con l'utente API principale, senza riavvii inutili del container."""
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
            return bool(run_phase('navidrome_scan_before_stars', run_navidrome_scan,
                                  full_scan=full_scan, prune_refs=full_scan))
        finally:
            globals()['SUBSONIC_USER'], globals()['SUBSONIC_PASS'] = old_user, old_password
    print('[warn] scan pre-favorites saltata: nessuna password ND_PASS/ND_PASS_<utente> disponibile; '
          'le playlist appena generate potrebbero non essere ancora visibili all’API', file=sys.stderr)
    return None


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
    run_phase('load_user_config', load_user_config)
    global SYNC_STATE, ROMAJI_TAGS_ACTIVE
    ROMAJI_TAGS_ACTIVE = not args.skip_romaji
    try:
        SYNC_STATE = json.loads(SYNC_FILE.read_text())
    except Exception:
        SYNC_STATE = {}

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
    if args.check_albums:
        run_phase('check_albums', run_check_albums, album=args.album, artist=args.artist,
                  search=not args.mb_no_search)
        return
    if args.fetch_only:
        rc = run_phase('fetch_exportify', run_fetch, sel,
                       headed=args.fetch_headed, timeout_min=args.fetch_timeout)
        raise SystemExit(1 if rc is None else rc)

    if args.missing is not None:
        by_full, by_artist, by_strict, path_qual = run_phase('index_library', load_library, rebuild=args.rebuild_cache)
        groups = [(u, select_playlists(fs, args)) for u, fs in collect_user_csvs(args, sel)]
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
        _expand_all(args)

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
        groups = [(u, select_playlists(fs, args)) for u, fs in groups]
        report_skips(args)
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
        scan_before_stars_ok = _scan_before_favorites(sel, full_scan=not args.sync_only)
        # None significa che non e' stato trovato un account con credenziali per la scansione.
        scanned_before_stars = True if scan_before_stars_ok is None else bool(scan_before_stars_ok)

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
        run_phase('navidrome_scan_final', run_navidrome_scan)

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
            run_phase('navidrome_scan_after_artwork', run_navidrome_scan,
                      full_scan=False, prune_refs=False)


if __name__ == '__main__':
    main()
