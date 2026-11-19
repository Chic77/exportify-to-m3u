# Exportify to M3U

`exportify_to_m3u.py` importa gli export CSV di Spotify/Exportify, genera playlist M3U per Navidrome e svolge manutenzione della libreria musicale. Gestisce anche metadati bilingui, copertine, diagnosi dei brani mancanti e sincronizzazione degli album con Lidarr.

**Versione documentata: v0.151.** Per tutte le opzioni aggiornate e per lo storico completo delle modifiche, lo script resta la fonte autorevole:

```bash
python3 exportify_to_m3u.py --help
python3 exportify_to_m3u.py --version
python3 exportify_to_m3u.py --changelog
```

## v0.151 — fallback originale Radiohead e iniziali dei gloss bilingui

- Il log v0.150 ha dimostrato che, dopo il circuit breaker MusicBrainz, 1.084 album restavano irrisolti. Per i Radiohead, album_unify conservava così `RELEASEDATE=2009` (e `Amnesiac=2021`) perché mancava un consenso `ORIGINALDATE`. Aggiunti fallback esatti e verificati, usati prima della rete in `date_heal` e anche in `album_unify`: *Pablo Honey* 1993, *The Bends* 1995, *OK Computer* 1997, *Hail to the Thief* 2003, *Amnesiac* 2001, *In Rainbows* e *In Rainbows (Disk 2)* 2007. Funzionano anche quando MusicBrainz è offline.
- I fallback sono limitati agli esatti titoli Radiohead; per gli altri album non viene indovinato l'anno originale da cartella, `DATE` o `RELEASEDATE`, che potrebbero indicare una ristampa. Gli altri album continuano a richiedere MusicBrainz o un consenso `ORIGINALDATE` affidabile.
- `date_heal` aggiorna `DATE`, `ORIGINALDATE` e `RELEASEDATE`; se esiste già anche `YEAR` ed è discordante, lo corregge. La cache passa a v6 e riconosce il fallback curato come fonte attendibile.
- I gloss latini delle forme bilingui ricevono ora l'iniziale maiuscola per ogni token tutto minuscolo, anche quando la forma proviene già da Navidrome/Lidarr o da `NAME_TRANSLATIONS`/`NAME_FIXES`. Le grafie mixed-case e gli acronimi già maiuscoli restano invariati.
- Rimossa la vecchia eccezione che preservava il casing minuscolo del catalogo bilingue: era la ragione per cui la precedente correzione riguardava solo alcuni nomi generati.

## v0.150 — correzione generale date originali e Navidrome RELEASEDATE

- `date_heal` include anche gli album che hanno soltanto `RELEASEDATE`, non solo quelli con `DATE` o `ORIGINALDATE`. Ora verifica e corregge `DATE`, `ORIGINALDATE` e `RELEASEDATE`: quest'ultimo campo e' importante per l'identita' Album PID usata da Navidrome.
- MusicBrainz viene interrogato con il browse endpoint delle release `Official`, paginato correttamente usando il numero effettivo di righe restituite (le pagine possono contenere meno di 100 release a causa del limite di 500 tracce). Il vecchio `inc=releases` su release-group restituiva al massimo 25 elementi e non era una fonte completa.
- Le release sono verificate contro artista e titolo; gli anni di registrazioni non ufficiali non vengono usati. Quando esiste una release commerciale etichettata/catalogata, un CD-R senza label/catalogo non puo' anticiparla (caso documentato di *The Bends*: CD-R no-label 1994 contro release retail 1995). Se il CD-R e' l'unica release disponibile, rimane una possibile fonte per album autopubblicati.
- Per edizioni bonus/companion vengono lette anche le annotazioni di release e release-group, compresi formati come `Original release date: 2007-10-10` e `Originally released in 2007` (utile per *In Rainbows Disk 2*).
- Non vengono piu' promossi a data originale valori NFO, `DATE` da solo o anno della cartella quando MusicBrainz non conferma una release attendibile: `DATE` puo' riferirsi alla ristampa/remaster. L'album resta segnalato come irrisolto/ritentabile; il riepilogo non lo nasconde piu' come zero errori.
- La cache di date heal passa a v5 e salva solo date MusicBrainz autorevoli. Prima di saltare un album verifica firma file (mtime e dimensione), identita' MBID e che tutti i tag data richiesti siano allineati.
- `album_unify`, `fix_date_tags` e la riparazione dei duplicati preferiscono un consenso `ORIGINALDATE` affidabile a un `RELEASEDATE` residuo/discordante, evitando che Navidrome continui a vedere l'anno della ristampa.
- Ottimizzazione: la data-heal riusa i tag gia' letti da ffprobe, cerca gli MBID in tutti i tag gia' in memoria (non solo nelle prime 12 tracce) e il passaggio `fix_date_tags` non ripete il probe ne' il calcolo della root album per ogni FLAC.

## v0.149 — fallback date_heal sicuro

- Se MusicBrainz individua il release-group corretto ma il dettaglio originale/Official fallisce temporaneamente, l'album resta irrisolto e riprovabile alla run successiva. Lo script non ripete la query nello stesso run e non usa un anno ID/cache potenzialmente vecchio.
- L'eccezione ufficiale `Fred again..` e' esplicita; la regola per `JPEGMAFIA .` continua a eliminare soltanto il punto isolato dopo uno spazio.

## v0.148 — Fred again.. e cache anni originali

- Ripristina il display ufficiale `Fred again..` anche se il catalogo Lidarr conserva soltanto la forma gia' degradata `Fred again`. La correzione `JPEGMAFIA .` resta mirata al singolo punto preceduto da spazio; non viene rimossa la punteggiatura terminale intenzionale.
- `_mb_year()` non riusa piu' gli anni grezzi salvati da vecchie query (per esempio il 2009 di una ristampa). Per un release MBID risale al release-group e usa la stessa regola di `date_heal`: annotazione esplicita della data originale, poi prima release con stato `Official`.
- La cache date_heal e' ora v4 e la cache MusicBrainz usa chiavi nuove: gli anni 2009 eventualmente memorizzati dalla vecchia logica vengono rivalutati.

## v0.147 — matching univoco, date originali e nomi artista punteggiati

- Ogni file locale puo' essere assegnato a una sola riga della stessa playlist. I match esatti e piu' specifici vengono risolti prima; in caso di conflitto il secondo brano cerca un altro file esatto e, se non esiste, finisce nel `.missing.txt` invece di essere ignorato. L'ordine finale della playlist resta quello Spotify.
- `Pt.`, `Pts.` e `Parts` sono equivalenti nel matching, quindi `Shine On You Crazy Diamond (Pts. 1-5)` e `(Pts. 6-9)` non collidono con le rispettive tracce locali `Parts 1-5` e `Parts 6-9`.
- `date_heal` cerca MusicBrainz usando artista album + titolo esatti; controlla `DATE` e `ORIGINALDATE` per ogni traccia e corregge entrambi i campi. Preferisce annotazioni di data originale e prime release ufficiali, non promo/CD-R o ristampe. L'anno corretto viene scritto anche nei formati audio non-FLAC supportati.
- La cache precedente di `date_heal` viene invalidata. Esempi verificati nei test: Pablo Honey 1993, The Bends 1995, OK Computer 1997, Hail to the Thief 2003 e In Rainbows Disk 2 2007.

## v0.145 — correzione spaziatura descrizioni playlist

- La descrizione generata mantiene una riga vuota tra la descrizione Spotify e il contatore, ma l'URL GitHub segue subito il contatore nella riga successiva (nessuna riga vuota aggiuntiva).
- Esempio: `descrizione Spotify`, riga vuota, `playlist.m3u: 46/59 match, 12 mancanti`, newline, `https://github.com/Chic77/exportify-to-m3u`.

## v0.144 — report album salvati, descrizioni pulite e artwork multi-catalogo

- La fase `star_liked` conserva ora le righe di `saved albums.csv` che non trovano un album nel catalogo locale Navidrome. Artista, album, data e URI vengono scritti album per album nella sezione `ALBUM SPOTIFY SENZA MATCH NAVIDROME` di `e2m_mancanti_<data>.txt`. Le righe vengono raccolte soltanto quando il catalogo Navidrome è stato letto correttamente; un errore API non viene trasformato in un elenco vuoto. La sezione è distinta dal report Lidarr, che continua a elencare gli album Spotify senza match Lidarr e le voci coperte da MBID condiviso.
- Le descrizioni playlist usano testo semplice: descrizione Spotify, riga `<playlist>.m3u: M/T match, N mancanti` e URL GitHub non formattato come hyperlink. In v0.144 rimaneva una riga vuota in più prima dell’URL; v0.145 la rimuove. I vecchi paragrafi `Imported from ...` e i link duplicati vengono rimossi; il testo della descrizione Spotify resta intatto. I contatori vengono salvati nella coda persistente, anche quando la M3U non è cambiata.
- Aggiunti **TheAudioDB** e **Wikimedia Commons** ai cataloghi artwork, oltre a MusicBrainz/Cover Art Archive, Apple/iTunes e Deezer. Le nuove fonti usano matching artista+album prudente; Wikimedia richiede nome file coerente con entrambi. Una cover proveniente dai cataloghi è accettata solo quando almeno due provider indipendenti restituiscono immagini con hash percettivo entro la soglia; Google Images da solo resta una proposta di revisione e non viene salvata automaticamente. Il provider TheAudioDB è limitato a una richiesta ogni 2,1 secondi per rispettare la quota del key pubblico.
- `SPOTIFY_LOCAL_PROXY.auto_sync` (predefinito `true`) rende automatica, dentro `--all --apply`, la scansione degli album già presenti nella libreria ma non trovati nel mercato Spotify e l'aggiornamento di `auto_albums` nel JSON. Senza credenziali OAuth vengono utilizzate le cache valide; se servono nuove richieste, la scansione segnala l'errore e conserva `auto_albums` esistenti. Gli album Spotify che non esistono nella libreria locale non possono diventare proxy MP3: restano invece nel report dei mancanti.

## v0.143 — unificazione dei nomi artista con punteggiatura accidentale

- I nomi artista che differiscono soltanto per punteggiatura terminale o spazi prima della punteggiatura condividono una sola identità: `JPEGMAFIA` e `JPEGMAFIA .` vengono trattati come lo stesso artista.
- La riparazione tag Lidarr aggrega le prove dei record con identità equivalente e sceglie la grafia pulita, aggiornando `ALBUMARTIST` e i campi `ARTIST` che rappresentano lo stesso artista. Il successivo scan Navidrome riunisce così gli album sotto `JPEGMAFIA`.
- La regola è conservativa: rimuove soltanto la punteggiatura finale accidentale. Mantiene punteggiatura interna (`AC/DC`, `Tyler, The Creator`) e nomi composti soltanto da punteggiatura (`!!!`). Non elimina né fonde record o album nel database Lidarr.
- La lista dei nomi Lidarr attendibili viene deduplicata prima della riparazione bilingue, evitando che una variante con punto finale venga reintrodotta dopo la correzione.

## v0.142 — resilienza MusicBrainz, Lidarr e fasi parziali

- Tutte le richieste al Web Service MusicBrainz (date, completezza album, resolver Lidarr e ricerca artwork) usano lo stesso limiter. L'intervallo minimo e' 1,2 secondi; lock e stato persistente coordinano anche due processi dello script sullo stesso host. User-Agent identifica nome, versione e progetto. Le risposte 429/503 applicano backoff comune e rispettano `Retry-After`.
- Se MusicBrainz restituisce 503 durante `lidarr_sync`, il resolver esterno viene sospeso per il resto della run, ma il catalogo Lidarr gia' letto da SQLite resta attivo. Gli album esatti gia' presenti possono ancora essere riconosciuti; gli altri diventano **rinviati**, non falsi album definitivamente senza match. Il report separa i rinviati dai veri mancati.
- Il controllo `DownloadedAlbumsScan` non considera piu' un `NO-MATCH` artisti che sono nel DB Lidarr ma non hanno una cartella direttamente nella root musicale. Prova il nome canonico/alias per correggere i path esistenti; le cartelle assenti vengono riepilogate come informazione, non come errore di import.
- `star_liked` tratta password assenti, password rifiutate ed errori API per account come problemi locali a quell'utente. Gli altri account continuano; la fase non fallisce e ogni problema resta visibile nel riepilogo.
- Dopo il 429 dei due endpoint Google, la traduzione prova MyMemory. Il contatore anonimo e' persistente e limitato prudenzialmente a 4.500 caratteri/giorno (il limite pubblicato e' 5.000); non viene inventata o aggiunta un'e-mail di contatto per aumentare la quota. Se anche il fallback non e' disponibile o la quota e' esaurita, resta la fonetica e la fase prosegue.
- Le intestazioni diventano `=== fase nome === #N`: fase verde, contatore giallo, senza la dicitura `(totale dinamico)`. Il filtro del Metadata Profile che accetta soltanto status Official e' informativo: lo script non modifica il profilo, per evitare di abilitare automaticamente Promotion/Bootleg o altri tipi di release indesiderati. Per includere altri status o tipi primari/secondari, modificare consapevolmente il profilo in Lidarr (Settings → Profiles); lo script non lo amplia da solo.

## v0.141 — risoluzione diretta degli URI Spotify per Lidarr

- La sincronizzazione usa anche `Album Artist URI(s)` dell'export: risolve il link Spotify dell'artista nelle relazioni URL MusicBrainz e riutilizza il relativo MBID per cercare la discografia. Questo recupera artisti non trovati dal solo nome per differenze di grafia, alias o traslitterazione.
- Prima cerca il titolo esatto nel catalogo dell'artista identificato dall'URI; se il catalogo non mostra il titolo, prova una ricerca mirata per MBID artista + titolo. Solo dopo usa il collegamento dell'album Spotify come ulteriore fallback.
- Titolo dell'album e credito artista MusicBrainz restano obbligatori: l'URI non autorizza a scegliere un album dal titolo soltanto o un artista omonimo.
- La cache MusicBrainz passa a v6 senza eliminare le ricerche e le discografie già salvate; gli URI artista vengono memorizzati, i risultati negativi ritentati dopo un giorno e i cataloghi positivi aggiornati ogni sette giorni.

## v0.140 — descrizioni playlist e copertura completa album Lidarr

- La descrizione playlist acquisita da Spotify/Exportify viene trasferita nel commento/descrizione della playlist Navidrome. In fondo viene aggiunto un paragrafo separato: `Imported from nome_playlist.m3u using exportify_to_m3u on GitHub [https://github.com/Chic77/exportify-to-m3u](https://github.com/Chic77/exportify-to-m3u)`.
- L'attribuzione usa il nome effettivo del file M3U, viene aggiornata se il file viene rinominato e non viene duplicata. Se Spotify non espone la descrizione (valore `null`), il commento già presente in Navidrome viene preservato e viene aggiunta soltanto l'attribuzione.
- Le descrizioni in attesa vengono conservate in una coda JSON persistente e riprovate dopo una scan Navidrome riuscita; i path assoluti/relativi e i nomi vengono abbinati soltanto quando la corrispondenza è univoca.
- Lidarr riceve tutti gli album distinti rappresentati dai brani delle playlist attive, anche quando tutte le tracce sono già presenti localmente. Se una traccia viene trovata sotto un album locale diverso, il match continua a essere usato per la M3U ma l'album Spotify originale resta candidato per Lidarr.
- Il report riconosce anche le Spotify Local Files URI e conserva Album Artist, Album Artist URI, Album URI e data. Il log distingue album playlist, brani mancanti e mismatch con la release locale.
- Viene mostrato il Metadata Profile effettivo di Lidarr e vengono segnalati i tipi/status filtrati; lo script non modifica automaticamente il profilo. Le compilation `Various Artists` restano escluse perché Lidarr non gestisce il meta-artista come un normale artista.

## v0.139 — refresh playlist persistente e cover MusicBrainz esatte

- Quando Spotify/Exportify restituisce più risposte per la stessa playlist, viene conservata l'ultima cover URL non vuota. Questo evita che una prima risposta con l'immagine vecchia impedisca l'aggiornamento arrivato in una risposta successiva.
- I sidecar da rinfrescare in Navidrome sono registrati in `.playlist_artwork_pending.json`. Se il DB non abbina il path, il container è fermo o il comando CLI fallisce, la voce resta in coda e viene ritentata alla prossima scansione.
- Il matching delle playlist prova prima il path assoluto/relativo; usa nome o basename soltanto quando il risultato è univoco. Gli ID dichiarati non validi non vengono considerati aggiornati.
- Al primo avvio v0.139 viene riconciliato una volta anche lo stato artwork già presente in `.sync_state.json`, così i sidecar aggiornati dalle versioni precedenti ma non rinfrescati in Navidrome vengono riprocessati.
- Le cover Cover Art Archive raggiunte tramite un `MUSICBRAINZ_RELEASEGROUPID` presente nei tag vengono usate direttamente. Anche un risultato di ricerca MusicBrainz è utilizzabile senza consenso Apple+Deezer quando artista e titolo corrispondono quasi esattamente (score almeno 0,96); i risultati fuzzy continuano a richiedere conferma indipendente.
- La cache negativa artwork passa a v10 e ritenta i precedenti album senza risultato una volta con la nuova regola MusicBrainz/CAA.
- Le immagini playlist caricate manualmente da Navidrome hanno precedenza sui sidecar: lo script non le elimina, per non cancellare cover personalizzate. Se una playlist continua a mostrare la vecchia immagine nonostante il refresh, controlla se ha una cover caricata dalla WebUI.

## v0.138 — soglie artwork, path M3U e Docker Compose

- La soglia `MISSING_ARTWORK_MIN_IMAGE_BYTES` si applica alle immagini scaricate; `MISSING_ARTWORK_MIN_EXISTING_COVER_BYTES` resta riservata alla valutazione delle cover locali già presenti. Le immagini valide e compatte non vengono più rifiutate per errore.
- Il refresh delle cover playlist confronta anche il percorso relativo a `PLAYLIST_DIR`, quindi continua a trovare la playlist nel DB Navidrome quando il path host e quello del container hanno prefissi diversi.
- Il rilevamento del container usa il nome effettivo restituito da Docker e supporta i nomi generati da Compose. Le fasi che modificano SQLite non procedono se lo stop del container non è riuscito.
- I redirect del download cover Spotify sono ammessi soltanto verso HTTPS sui CDN Spotify autorizzati.

## v0.137 — cover playlist Spotify e refresh mirato Navidrome

- L'acquisizione delle immagini playlist riconosce più forme JSON Spotify/Exportify (`images`, `image`, `imageUrl`, `coverUrl`, `artworkUrl` e oggetti annidati), senza accettare URL fuori dai CDN Spotify.
- Un sidecar già registrato viene riutilizzato soltanto se esiste, non è vuoto e i magic bytes confermano che è un'immagine valida.
- Quando una cover playlist cambia o viene rimossa, dopo lo scan lo script individua la playlist tramite il path M3U nel DB e lancia `navidrome artwork refresh pl <id>` soltanto per quelle playlist. Questo forza Navidrome a ricalcolare l'artwork memorizzato, invece di lasciare visibile la vecchia immagine.
- Google Images prova più varianti del titolo e della punteggiatura, inclusi numeri di volume (`Vol.1`, `Vol 1`, `Volume 1`).
- La cache artwork passa a v9: i precedenti risultati negativi album vengono riprovati una volta con le query ampliate; cursore e verifiche delle cover esistenti vengono preservati.

## v0.136 — fix crash artwork e percorsi audio obsoleti

- Corretto il riferimento alla barra di avanzamento nella fase artwork: un `NameError` non interrompe più il recupero album prima dell'embedding e della ricerca dei ritratti artista.
- La riparazione `Unknown Artist` scarta i percorsi audio già rimossi e gestisce anche il caso in cui un file sparisca fra `ffprobe` e la scrittura dei tag. Questi casi sono riportati separatamente e non vengono conteggiati come errori di metadati; gli errori effettivi di lettura/scrittura restano visibili.

## v0.135 — diagnosi artwork completa e coda bilingue equa

- Gli artisti bilingui vengono processati prima delle cartelle con soli nomi latini. La query segue l'ordine **tutti i nomi inglesi → nome originale**, riconoscendo sia `Я сошла с ума (I Went Crazy)` sia `I Went Crazy (Я сошла с ума)`.
- Il cursore round-robin avanza dopo ogni query effettiva. Se i provider diventano indisponibili prima della fine del batch, il cursore ruota oltre gli elementi rinviati selezionati: la run successiva può raggiungere la coda successiva, mentre gli elementi differiti restano nella coda circolare e vengono ritentati al giro seguente.
- Ogni album candidato riceve un esito nominativo nel log: scaricato, nessun risultato valido, candidato in revisione, errore temporaneo/provider, errore di salvataggio oppure rinvio per limite batch. Gli errori e i rinvii dello stesso album non vengono presentati come due album distinti.
- Il riepilogo separa i candidati album senza risultato dai retry di rete e dalle verifiche su cover già sane; le verifiche di cover esistenti non vengono confuse con le nuove cover mancanti.
- Rimossi helper e rami ridondanti non utilizzati, mantenendo un solo punto per appiattire/ordinare i nomi di ricerca.
- La disponibilità degli artwork artista considera soltanto Deezer e Google Images; un errore MusicBrainz non influenza più la classificazione dei ritratti.
- Il log elenca l'esito di ogni album candidato e ogni artista rinviato, compresi i candidati fuori dal batch e quelli in cache negativa. Il contatore degli album rimasti è calcolato per elemento unico, senza sommare due volte errori e rinvii.
- Le cover `artist.*` da una cartella alias vengono riutilizzate soltanto quando la corrispondenza tra cartelle è univoca.

## v0.134 — priorità bilingue e coda round-robin

- I ritratti bilingui vengono cercati usando prima tutti i nomi inglesi/gloss e soltanto dopo la grafia originale; vengono riconosciuti entrambi gli ordini del gloss.
- La coda artista/album ruota dopo gli elementi effettivamente interrogati. Quando i provider si fermano, il batch differito non blocca per sempre le voci successive.
- Un'immagine `artist.*` già presente in una cartella alias viene copiata soltanto quando l'identità è univoca.
- Il log distingue gli esiti dei candidati album e le immagini artista rinviate.

## v0.132 — immagini originali ospitate da Google

- Google Images può restituire anche URL originali ad alta risoluzione su `googleusercontent.com` o `gstatic.com`. Questi host non vengono più bloccati in blocco: il file deve comunque essere HTTPS, pubblico, nei formati consentiti e superare soglie di byte, dimensioni e proporzioni. Le thumbnail `encrypted-tbn` restano escluse.

## v0.131 — aggiornamento cache artwork Navidrome

- Dopo aver salvato nuove cover album o `artist.*`, lo script esegue uno scan incrementale e poi richiama la CLI Navidrome dentro il container: `navidrome artwork reprocess --kind ar --kind al --source absent --yes`. In questo modo gli artisti e gli album già memorizzati senza immagine vengono rimessi in coda, senza rifare i lookup esterni per gli elementi che hanno già artwork. Se la CLI non è disponibile, viene mostrato un avviso ma i file scaricati restano salvati.

## v0.130 — configurazione artwork artista

- Corretto il nome della variabile `MISSING_ARTWORK_ARTIST_ENABLED`: ora abilita/disabilita realmente la ricerca dei ritratti artista. Per compatibilità viene ancora accettato anche il precedente nome interno `MISSING_ARTWORK_ARTIST_ART_ENABLED`. Se entrambi sono impostati, prevale il nome pubblico corretto.
- I suffissi come `(band)` e `(UK)` non vengono scambiati per gloss bilingui; la parentesi viene trattata da traduzione soltanto quando il nome sorgente contiene caratteri CJK, Hangul o cirillici. Le pagine Google di consenso/CAPTCHA vengono riconosciute come ricerca incompleta, non come assenza definitiva di artwork.

## v0.129 — fallback Google Images e artwork artisti

- Per le copertine album ancora mancanti (o sotto la soglia configurata), dopo Cover Art Archive/MusicBrainz vengono confrontati Apple/iTunes, Deezer, TheAudioDB e Wikimedia Commons; Google Images può fornire un suggerimento ma non autorizza da sola il salvataggio. La prima query è `album_name album cover`; solo se non produce un'immagine valida viene aggiunta la query con l'artista.
- I risultati Google vengono scaricati solo da URL HTTPS pubblici, con redirect controllati, formati JPG/PNG/WEBP verificati e dimensioni reali lette da `ffprobe`. Sono scartate le thumbnail Google, le immagini troppo piccole e le proporzioni poco compatibili con una copertina. Le cover sane locali non vengono sostituite.
- La fase recupera anche le immagini artista mancanti. Per i nomi bilingui cerca prima il gloss/alias o la traduzione inglese automatica/curata e, soltanto se non trova un’immagine valida, il nome originale; per ciascuna identità prova Deezer e Google Images. Salva `artist.jpg`, `artist.png` o `artist.webp` nella cartella artista, senza incorporare il ritratto nei file audio.
- La coda artisti usa cache negativa e cursore round-robin separati dalla coda album. Gli alias bilingui possono riutilizzare un `artist.*` locale solo se la corrispondenza tra cartelle è univoca. Errori temporanei o provider bloccati non diventano risultati definitivi; gli elementi mai interrogati non vengono marcati come tentati e il log ne mostra i motivi di rinvio.
- La traduzione automatica inglese comprende il cirillico russo. Una traduzione semantica accettata ha precedenza sulla traslitterazione fonetica; le regole `NAME_TRANSLATIONS` e `NAME_FIXES` restano prioritarie.

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
