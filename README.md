# Exportify to M3U

`exportify_to_m3u.py` converts playlists exported by Spotify's Exportify into M3U playlists that reference files in a local music library. It is designed for a multi-user Navidrome setup and also includes library-maintenance, metadata-repair and diagnosis utilities.

## Quick start

**Current release: v0.68.** This update makes album-split diagnosis faster on large libraries, makes non-FLAC tag rewrites safer if an I/O error occurs, and makes semicolon-separated artist repair deterministic. v0.67 integrated album diagnosis and repair into `--all`; v0.66 improved album-fragment and CJK artist handling; v0.65 added measured artwork, translation and waveform optimizations.

Use the script's built-in help as the authoritative, current command reference:

```bash
python3 exportify_to_m3u.py --help
```

The help text is maintained inside the script so it can be updated alongside its options. `--changelog` prints the complete changelog embedded in the script.

The main operating modes serve different purposes:

- **`--sync-only` — routine playlist sync.** Fetches current Exportify exports where a saved session is available, processes local exports, generates/synchronizes M3U playlists, fixes playlist ownership and applies Navidrome favorites. It skips heavier library maintenance such as duplicate detection, MP3-versus-FLAC cleanup, FLAC conversion and bulk tag/date/album maintenance. Users in `FETCH_IGNORED_USERS` are not fetched, but their existing local exports can still be processed.
- **`--all` — full pipeline.** Selects all maintenance and playlist phases, and fetches exports when saved Exportify sessions are available. File-cleanup phases such as duplicate removal remain in preview unless `--apply` is supplied. This is **not** a global no-change dry run: tag/date/album repairs and playlist/database operations may still write changes unless `--dry-run` is supplied where supported.
- **`--apply` — execution modifier.** Enables destructive duplicate-cleanup operations selected by the other options. By itself it does not select every maintenance phase.
- **`--all --apply` — full maintenance and sync.** Enables the selected duplicate cleanup as well as the rest of the pipeline. Review the log first: files selected by cleanup phases are normally moved to the configured dedupe trash unless `--hard-delete` is selected; playlist/database cleanup may remove records.

For all options, combinations, defaults and warnings, consult `--help` rather than relying on a copied list in this README.

## Features

- Fetches Exportify playlist exports for configured accounts and processes per-user ZIP/CSV collections.
- Matches Spotify tracks against the local library using title, artist and album metadata, including Unicode, Japanese/Kanji and romaji aliases.
- Scores recording variants so an unqualified original is preferred over alternatives such as live, demo, instrumental, rehearsal, extended and expanded editions unless the requested Spotify title explicitly asks for a variant.
- Generates M3U playlists while preserving Spotify playlist names and artwork metadata, and reports tracks that could not be matched. The `ALBUM DA SCARICARE` section in `mancanti_*.txt` identifies the active source playlists for album recommendations.
- Synchronizes fetched exports safely, removes stale generated playlists only for users whose exports were freshly fetched and successfully processed, and removes corresponding imported Navidrome playlist records.
- Can apply Navidrome favorites for liked tracks, saved albums and artists represented by the available exports.
- Includes optional maintenance for duplicate playlists/tracks/releases, format cleanup, tags, album metadata, album-split repair and missing artwork.
- Integrates FLAC filename repair, Lidarr folder alignment/import, ListenBrainz listen deduplication and playlist-owner repair as opt-in utilities.
- Can create selected MP3 proxy copies for local albums absent from Spotify's catalog, while playlist matching continues to target original lossless files. Navidrome favorites for proxy tracks are tracked in `liked.m3u` and a JSON manifest.
- Produces execution logs, per-phase durations and summaries of missing tracks.
- Includes caching and profiling-based optimizations for repeated metadata probes, normalization, waveform comparisons, automatic translations and artwork checks.

### Album diagnosis and repair (v0.66–v0.68)

The album diagnosis and repair features are intended to address albums that Navidrome splits into several database entries, reused MusicBrainz IDs, repeated CJK artist names and ambiguous artist tags.

- **`--diagnose-album-splits`** reads the Navidrome database without writing to it and creates `logs/album_db_diagnostics_<timestamp>.txt`. It reports candidate album groups with database IDs, track counts, MusicBrainz IDs, album version/release-date fields and example paths. Fuzzy title pairs and conflicting editions are marked for review; the diagnostic does not merge albums or change audio tags.
- **`--repair-album-groups`** runs the repair workflow. It previews by default; use `--apply` to write changes when running it by itself. It checks MusicBrainz album IDs, harmonizes album tags, aligns `ALBUMVERSION` within logical album roots, repairs `[Unknown Artist]` only when an album provides a reliable artist, and normalizes semicolon-separated artist tags only when at least one component matches an artist already present in Navidrome.
- **`--all`** automatically creates a diagnosis report before the main modifications and includes album-group repair in the pipeline. After a successful full Navidrome scan, it can create a second report to compare the rebuilt database. The post-scan report is skipped if the scan cannot be confirmed successful or scanning is disabled.
- **Fuzzy candidates remain review-only.** Similar titles are not automatically merged just because a fragment has few tracks. Explicit edition or `ALBUMVERSION` conflicts are also held for review rather than being blindly unified.
- **Tag-write safety:** `--dry-run` previews the tag repairs. In standalone mode, `--repair-album-groups` also requires `--apply` to write. In `--all`, tag/date/album phases are controlled by `--dry-run`; `--apply` primarily enables the destructive duplicate-cleanup phases. Read the operation log before running a live repair.
- **Artist fixes:** `[Unknown Artist]` is replaced only when `ALBUMARTIST` is reliable, or (when album-artist tags are absent) all known track-artist values agree on one artist. A generic or conflicting `ALBUMARTIST` such as `Various Artists` blocks the track-artist fallback; ambiguous compilations are left untouched and reported for review. Semicolon-separated tags are split only when the Navidrome artist catalog confirms at least one component; FLAC receives multi-valued `ARTISTS`/`ALBUMARTISTS` tags and other formats use the scanner-compatible `; ` separator.
- **v0.68 performance/safety changes:** diagnosis compares albums sharing an artist identity instead of needlessly comparing every album pair; non-FLAC tag writes restore the original file if committing the rewritten file fails; the semicolon repair combines duplicate alias fields deterministically. MusicBrainz lookup caches populated during a preview are kept as auxiliary caches so repeat previews can reuse them. No new end-to-end timing profile was collected for v0.68, so the pair-index change is a structural optimization rather than a measured whole-run speed claim. Repair summaries now also account for failed MusicBrainz-ID, artist-normalization and album-unification writes instead of reporting success when one of those sub-phases had errors. Artist inference checks all available metadata aliases and refuses to choose a field when aliases conflict.

### Performance notes (v0.65 — second Tachyon profile)

A second Python 3.15.2 wall-clock profile was collected on the homelab on October 27, 2026, using `--sync-only --dry-run --no-scan`. The log total was 6 min 10 sec; the profiler observed 372.7 seconds. Compared with the previous 7 min 24 sec run, the total was shorter, but the comparison was not perfectly controlled: the library index changed from 15,074 cached files to 15,079 files, triggering a full index rebuild, and external translation availability differed.

The profile showed that the v0.64 probe-cache flush was no longer a leading hotspot. Remaining sampled areas included:

- **Embedded artwork probes — about 92 seconds inclusive.** The code now stops after the first track with embedded artwork rather than always probing all first three tracks; picture status is persisted in the shared ffprobe cache.
- **Automatic translation HTTPS — about 85 seconds inclusive.** If the public translation provider fails, a persistent six-hour circuit breaker avoids repeatedly waiting on additional requests. Cached translations remain available and uncached names fall back to phonetic romanization until the cooldown expires.
- **Waveform tie-breaks — about 69 seconds inclusive.** Threshold-only comparisons check zero offset and nearby coarse offsets first, allowing already-aligned copies to return early. Full-score `--compare` diagnostics keep the broader search grid.

These are sampling estimates, not exact function timers. The total was around 74 seconds shorter than the previous run, but that difference cannot be attributed entirely to the changes. Re-profile with the same library and options to confirm results.

`--dry-run` can still refresh local caches and extract Exportify CSV staging files. It avoids applying supported playlist/tag repairs and skips scan/starring actions for the documented dry-run use.

## Configuration

`exportify_names.json` contains deployment-specific naming rules, playlist filters, user mappings and matching preferences. It is intended to survive script updates; prefer changing these settings over editing Python source when behavior is configurable. The file must be valid JSON: comments and trailing commas are not allowed.

### Artist and name normalization

- **`NAME_TRANSLATIONS`** is the highest-priority dictionary for a real English translation or official English/Latin title/name. Use it for known bilingual releases and established English titles, for example `"ワールドイズユアーズ": "World Is Yours"`. It is curated rather than guessed automatically.
- **`NAME_FIXES`** is the backward-compatible second layer for manual aliases, canonical spellings and preferred romanizations.
- **`AUTO_NAME_TRANSLATION`** is the automatic English layer for Japanese/Kanji and Korean/Hangul names without a manual rule. It translates the original script, caches the result, estimates reliability with conservative heuristics and accepts a result only when it reaches `min_confidence`. If confidence is too low or the provider is unavailable, it falls back to phonetic romanization.
- The public Google Translate endpoint does not provide a calibrated confidence probability. The stored score is an estimate, not a guarantee. Unknown CJK/Hangul text may be sent to the public translation service; set `enabled` to `false` if you do not want metadata sent externally.
- Name resolution order is `NAME_TRANSLATIONS` → `NAME_FIXES` → accepted automatic English translation → phonetic fallback. The automatic cache is stored separately in `auto_name_translations.json`, so guessed translations are not silently promoted into the curated JSON.
- `max_new_per_run` limits new translation requests; `cache_days` controls cache lifetime; `timeout` controls the request timeout; and `failure_cooldown_hours` controls how long provider failures pause further requests.
- **`ARTIST_GROUPS`** groups names that represent the same artist; names within each entry match one another in both directions. Use it for aliases, name-order variants and established alternate romanizations, not merely for different artists who collaborate. Example: `[["eiichi ohtaki", "eiichi otaki", "ohtaki eiichi"]]`.
- **`ALIASES`** provides additional alternate artist spellings. Prefer the most specific rule that fixes a match and avoid conflicting aliases for different artists.

### Playlist selection and naming

- **`SKIP_PLAYLISTS`** lists playlists that should not be imported. Comparison tolerates capitalization, punctuation and emoji differences. A final `*` acts as a prefix wildcard, for example `"daylist*"`.
- **`PLAYLIST_PREFIXES`** standardizes names beginning with a configured prefix. For example, `color yellow` can become `color - yellow` so related playlists group consistently in clients.
- **`PLAYLIST_FOLDERS`** routes named playlists into subfolders under the playlist directory; it affects the output path, not whether a playlist is selected.

### Spotify-to-Navidrome user mapping

- **`SPOTIFY_USERS`** maps a Spotify identity/ID found in Exportify data (for example, the `Added By` field) to the corresponding Navidrome username. It is useful when the ZIP filename does not identify the owner.
- **`FETCH_IGNORED_USERS`** lists Navidrome users whose live Exportify fetch must be skipped. This does not disable processing of their existing ZIP/CSV exports: locally available exports can still be used by later phases.

### Track matching and alternate-version scoring

- **`TITLE_MATCH_PENALTIES`** maps version/edition phrases to numeric penalties used when ranking local audio candidates. Current examples include `live`, `demo`, `instrumental`, `rehearsal`, `extended`, `expanded`, `remix`, `remastered` and `parentheses`.
- A higher penalty makes an unrequested qualifier less desirable. This helps an unqualified title such as `Pictures of You` beat `Pictures of You (Live)` when Spotify did not request a live recording. A requested variant remains eligible to win when the CSV includes that qualifier.
- The `parentheses` entry penalizes extra parentheses in a candidate filename when the requested title has none. Keep values non-negative and use the same key spelling as the matcher.

### Adding local albums that are absent from Spotify

Spotify's official Local Files support does not include FLAC. The script can generate compatibility MP3s for selected albums while keeping original FLAC files in Navidrome. Exportify can export the text metadata for local tracks in playlists; the script uses that metadata to find the original lossless tracks.

Configure `SPOTIFY_LOCAL_PROXY` in `exportify_names.json`:

```json
"SPOTIFY_LOCAL_PROXY": {
  "enabled": true,
  "output_dir": "~/Music/Spotify Local Files",
  "bitrate": "64k",
  "market": "IT",
  "catalog_cache_days": 90,
  "albums": [
    {"artist": "Example Artist", "album": "Always keep this manual proxy"}
  ],
  "auto_albums": []
}
```

`albums` is the manual list and is not overwritten by catalog discovery. `auto_albums` is maintained by `--sync-spotify-proxy-config`; the proxy builder uses the union of both lists. Keep `output_dir` outside `MUSIC_ROOT` so proxy files do not appear as duplicates in Navidrome.

#### Compare the library with Spotify first (dry-run by default)

The script uses Spotify's authenticated Search API for each unique artist/album folder in the library, filtered by `market` (`IT` by default). Search is not an exhaustive catalog dump: uncertain candidates are marked **REVIEW** and are not automatically added.

Put `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` and optionally `SPOTIFY_MARKET` in a private `.env` beside the script. Development Mode access and its requirements are controlled by Spotify and may change; consult the [official Search API docs](https://developer.spotify.com/documentation/web-api/reference/search), [authorization guide](https://developer.spotify.com/documentation/web-api/concepts/authorization) and [Developer Access update](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security) for current account and application requirements.

Preview the catalog comparison:

```bash
python3 exportify_to_m3u.py --sync-spotify-proxy-config --dry-run
```

This writes a report in `logs/spotify_proxy_sync_*.txt` and a proposed JSON copy without changing the active configuration. Review **ADD PROXY** and **REVIEW**. If the first scan would query too many albums, use `--proxy-limit 100` to preview a batch; limited runs are additive and preserve existing `auto_albums` entries.

After reviewing, apply the configuration update:

```bash
python3 exportify_to_m3u.py --sync-spotify-proxy-config --apply
```

Only `SPOTIFY_LOCAL_PROXY.auto_albums` is updated. If an API request fails, or the JSON is edited while the scan is running, the update is blocked instead of applying partial results or overwriting newer edits. Use `--build-spotify-proxies --dry-run` to preview proxy creation and `--build-spotify-proxies` to write MP3 files. This feature requires `ffmpeg` with the `libmp3lame` encoder.

#### Track Navidrome favorites for proxy files

When `--build-spotify-proxies` finishes, the script can query Navidrome's Subsonic `getStarred2` endpoint and match favorited source tracks to generated proxy files. It writes or updates:

- `liked.m3u` — a companion M3U containing proxy tracks whose original source is currently favorited in Navidrome.
- `spotify_proxy_favorites.json` — a readable snapshot of favorite proxy tracks, selected Navidrome user and update time.
- `.spotify_proxy_manifest.json` — the source-to-proxy mapping used for later refreshes without re-encoding audio.

Set `SPOTIFY_LOCAL_PROXY.favorites_user` to select the Navidrome account. Otherwise the script uses `ND_FAVORITES_USER`, then the configured `ND_USER` account. The matching account needs `ND_PASS_<USER>` or the default `ND_PASS` environment value.

To refresh favorite state without rebuilding the MP3s, preview and then apply:

```bash
python3 exportify_to_m3u.py --sync-proxy-favorites --dry-run
python3 exportify_to_m3u.py --sync-proxy-favorites --apply
```

**Spotify limitation:** Spotify's official Web API cannot add `spotify:local:` tracks to a native playlist or Liked Songs. This feature can track Navidrome favorites and export a companion `liked.m3u`, but does not create or update a native Spotify playlist. The default proxy bitrate is `64k` to save space; it is intentionally low quality for direct listening and can be raised to `96k`, `128k` or another supported value if preferred.

### Missing album artwork

- **`MISSING_ARTWORK`** controls the final missing-cover search/download stage. `enabled` toggles it; `max_per_run` caps the number examined (`0` means no limit); timeout and size settings constrain remote requests; `retry_days` controls negative-cache retries; `check_embedded_art` checks for embedded covers; `scan_after_download` requests a Navidrome scan after successful downloads; and `cover_basename` selects the standard filename.
- Artwork lookup is intended to fill gaps, not replace an existing local or embedded cover. It can make remote requests and write image files, so disable it in the JSON if you do not want that behavior.

The configuration may also contain `FORCE_ARTIST` and `CSV_FIX` for persistent per-track overrides, `UNIFY_FORCE` for album metadata normalization and `EMOJI_WORDS` for handling emoji-related words. See `--help` and the configuration comments for the exact structure.

Environment variables and a private `.env` file can provide Navidrome credentials and optional integration settings. Keep `.env`, Spotify session files, exported cookies and API tokens private; do not commit them to a repository. Library, playlist, ZIP-storage and Navidrome database paths are set for the deployment environment in the script.

## Integrated maintenance utilities

These commands are opt-in unless documented as part of `--all`. Use `--help` for the full current option list.

### Safe FLAC filename repair

`--fix-flac-safe` looks for pairs such as `track.flac` and `track.flac.flac`. It replaces the original only when the appended file passes validation with `metaflac` or `ffprobe`. Preview is the default:

```bash
python3 exportify_to_m3u.py --fix-flac-safe --dry-run
python3 exportify_to_m3u.py --fix-flac-safe --apply
```

### Lidarr folder alignment and slskd import

`--lidarr-folder-fix` compares Lidarr artist paths to the actual folders on disk using normalized names, configured aliases and a fuzzy fallback. It previews by default; `--apply` updates Lidarr and triggers a rescan after successful path changes. `--lidarr-import-slskd` submits a `DownloadedAlbumsScan` request for the configured import folder, then checks `failed_imports` and runs the folder-alignment step. It does not wait for Lidarr to finish processing every queued download.

The private `.env` may contain `LIDARR_URL`, `LIDARR_API_KEY`, `LIDARR_MUSIC_ROOT`, `LIDARR_CONTAINER_ROOT`, `SLKSD_IMPORT_FOLDER`, `SLKSD_FAILED_FOLDER` and `LISTENBRAINZ_TOKEN`. Never put real credentials in the README or source. If a real API key was ever committed, rotate it.

### ListenBrainz duplicate listens

`--lb-dedup USER` scans the recent listen history, identifies repeated listens with the same normalized artist/title within the configured time window and keeps the first listen in each cluster. It is preview-only by default:

```bash
python3 exportify_to_m3u.py --lb-dedup YOUR_LISTENBRAINZ_USERNAME
python3 exportify_to_m3u.py --lb-dedup YOUR_LISTENBRAINZ_USERNAME --lb-delete
```

Add `LISTENBRAINZ_TOKEN` to a private `.env` or the process environment; never pass it on the command line. `--lb-delete` performs irreversible API deletions and is blocked when listen-history windows could not be fetched.

### Navidrome playlist ownership: per-folder vs force-all

`--fix-owners [USER]` assigns M3U-imported playlists based on their folder and leaves UI-created playlists (with no M3U path) alone. `--fix-all-playlist-owners [USER]` is broader: it assigns every playlist, including UI-created playlists, to one account. The force-all command previews by default:

```bash
python3 exportify_to_m3u.py --fix-all-playlist-owners --dry-run
python3 exportify_to_m3u.py --fix-all-playlist-owners chic --apply
```

Use force-all only when one owner for every playlist is intentional.

## Usage reference

The built-in `--help` is the authoritative list of current flags, argument forms, defaults and safety notes. `--changelog` prints the entire release history embedded in the script.

## Dependencies and optional capabilities

The core script uses Python's standard library. `pykakasi` and `hangul-romanize` add phonetic transliteration; `numpy` enables waveform comparisons; automatic Exportify fetching needs Playwright and a browser runtime. Audio metadata inspection and FLAC maintenance use `ffprobe`, `ffmpeg` and/or `metaflac` depending on the selected phase. Install the applicable dependencies in the `.venv` beside the script so cron can use the same environment.

## Performance profiling (Python 3.15+)

Python 3.15 includes the low-overhead statistical profiler `profiling.sampling` (Tachyon), which can print summaries or create flame graphs. v0.64–v0.65 optimizations are based on a real homelab profile. Keep the `.venv` used by cron unchanged while testing a newer interpreter in a separate environment. On a host with internet access, `uv` can install Python alongside the system interpreter:

```bash
uv self update
uv python install 3.15.2
uv venv --python 3.15.2 .venv315
uv pip install --python .venv315/bin/python pykakasi hangul-romanize numpy
# Only needed for automatic Exportify fetching:
uv pip install --python .venv315/bin/python playwright
.venv315/bin/playwright install chromium
source .venv315/bin/activate
python --version
mkdir -p logs
```

A safe profile exercises playlist matching without fetching, writing playlists/tags or scanning Navidrome:

```bash
python -m profiling.sampling run --flamegraph -o logs/e2m_sync_dry_profile.html ./exportify_to_m3u.py --sync-only --dry-run --no-scan
python -m profiling.sampling run --mode=cpu --flamegraph -o logs/e2m_sync_cpu_profile.html ./exportify_to_m3u.py --sync-only --dry-run --no-scan
```

Run profiles with the same interpreter and options when comparing results. Wall-clock profiles include time spent waiting on disk/network/subprocesses; CPU profiles help distinguish those waits from Python computation. Do not replace the active `.venv` until the new interpreter and optional packages have been validated.

## Safety notes

Some maintenance phases can modify audio tags, media files, playlists or the Navidrome database. Read the built-in help and execution log before enabling destructive operations. `--all` is a complete pipeline selector, not a universal dry-run switch. Use `--dry-run` to preview supported tag/file operations and use `--apply` only when you intend to enable the selected duplicate-cleanup operations. Stale-playlist cleanup is restricted to users whose exports were freshly fetched and extracted; if any selected CSV conversion fails, cleanup for that user is suspended. Artwork downloads are intended to fill missing covers rather than overwrite existing artwork.

## Changelog

### v0.68 — diagnosis performance and safer tag writes

- Album diagnosis builds candidate pairs from shared artist-identity keys rather than comparing unrelated albums. Candidate ranking remains deterministic; fuzzy pairs stay review-only.
- Non-FLAC tag rewrites restore the original file if committing the rewritten file fails.
- Semicolon-separated artist repair combines duplicate metadata aliases deterministically instead of allowing the last alias field to overwrite an earlier result.
- Standalone album-repair previews retain MusicBrainz lookup caches, avoiding repeated network requests during later previews.
- Repair status includes errors from MusicBrainz-ID sanity, artist normalization and album unification; conflicting metadata aliases block unknown-artist inference rather than silently preferring the first field.

### beta-0.67 — album repair integrated into `--all`

- `--all` writes a pre-modification album diagnosis report and includes album-group repairs; a successful scan can be followed by a second report.
- Repairs `[Unknown Artist]` only when a reliable album artist exists or, if album-artist tags are absent, all known track artists agree. Generic/conflicting album-artist tags such as `Various Artists` block inference from track-majority counts; ambiguous compilations remain unchanged and are reported for review.
- Splits semicolon-delimited artist values only when at least one component exists in the Navidrome artist catalog; supports multi-value FLAC `ARTISTS` tags and the scanner-compatible delimiter for other formats.
- Reports `ALBUMVERSION`, release date and release-group IDs when available; conflicting editions remain review-only.

### beta-0.66 — fragmented albums and duplicate CJK artists

- Album identity removes edition suffixes conservatively and preserves meaningful titles such as `Blackbox Live Recorder`.
- Cross-folder album unification uses matching titles/aliases and track evidence while avoiding automatic merges for uncertain candidates.
- `date_heal` checks album IDs across the logical album tree, including multi-disc layouts and all supported audio formats.
- Artist-name normalization also covers CJK/Hangul values in Latin-named folders and compilation albums.
- Added `--diagnose-album-splits` and `--repair-album-groups`, with preview by default for standalone repair.

### beta-0.65 — second Tachyon profile

- Embedded-artwork status is stored in the shared ffprobe cache; checks stop after finding a cover on one of the first tracks.
- Automatic translation adds a persistent provider-failure cooldown, while cached translations continue to work and uncached values fall back to phonetic romanization.
- Threshold-only waveform checks can return once the required score is reached; full `--compare` diagnostics retain their broader search.

### beta-0.64 — profile-based cache and artwork optimizations

- Removes repeated full-cache path-existence sweeps at phase boundaries; cache entries are checked with `stat` before use and stale missing paths are cleaned lazily.
- Collects cover filenames during the library walk and checks negative artwork results before probing embedded art.
- Saves automatic-translation cache updates in batches with atomic writes.

### beta-0.63 — Navidrome favorites for Spotify proxies

- Tracks Navidrome-starred source songs for generated local-file proxies with a manifest, `liked.m3u` and `spotify_proxy_favorites.json`.
- Adds `--sync-proxy-favorites` to refresh favorite state without re-encoding proxies; API failures preserve the previous list.
- Documents that Spotify's Web API cannot add `spotify:local:` tracks to native playlists or Liked Songs.

### beta-0.62 — targeted performance and dry-run safety

- Caches FLAC files already at the desired encoding, uses a `scandir` walker for FLAC16 enumeration and keeps the FLAC16 dry-run read-only.
- Batches duplicate-track metadata prefetch and uses cumulative squared-sample sums to avoid repeatedly calculating waveform norms.
- Improves diagnostics for Spotify Development Mode authorization failures.

### Earlier releases

Older release details, including v0.61 and earlier beta releases, remain available via `python3 exportify_to_m3u.py --changelog`.
