# Exportify to M3U

`exportify_to_m3u.py` converts playlists exported by Spotify's Exportify into M3U playlists that reference files in a local music library. It is designed for a multi-user Navidrome setup and also includes library maintenance utilities.

## Quick start

**Current release: v0.65.** The Spotify Local Files proxy can now discover candidate albums automatically from the Navidrome library and compare them with Spotify's catalog. The default proxy bitrate remains `64k` to use less disk space. v0.65 adds profiled artwork/translation/waveform improvements on top of v0.64; v0.63 also tracks Navidrome-heart status for these files in a generated `liked.m3u`/JSON manifest (Spotify does not expose a Web API for adding local tracks to native playlists).


Use the script's built-in help as the authoritative, up-to-date command reference:

```text
python3 exportify_to_m3u.py --help
```

The help text is maintained inside the script so it can be updated alongside its options. `--changelog` prints the complete changelog embedded in the script.

The main operating modes serve different purposes:

- **`--sync-only` — routine playlist sync.** Fetches current Exportify exports where a saved session is available, processes the selected local exports, generates/synchronizes M3U playlists, fixes playlist ownership and applies Navidrome favorites. It skips the heavier library-maintenance work, including duplicate detection, MP3-versus-FLAC cleanup, FLAC conversion and bulk tag/date/album maintenance. Users in `FETCH_IGNORED_USERS` are not fetched, but their existing local exports can still be processed.
- **`--all` — full pipeline, with destructive phases in preview mode.** Selects the complete maintenance and playlist pipeline and automatically fetches exports when saved Exportify sessions are available. Destructive duplicate-removal phases do not actually apply their deletions unless `--apply` is also specified. This is not a global no-change dry run: other selected processing, such as playlist generation or metadata work, can still make changes.
- **`--apply` — execution modifier, not a full-pipeline selector.** It allows the destructive operations selected by other options to execute. By itself it does not enable every maintenance phase; combine it with the phase options you intend to run.
- **`--all --apply` — full maintenance and sync with destructive phases enabled.** Runs the complete pipeline, including actual duplicate cleanup and MP3-versus-FLAC cleanup. Review the log carefully first: files selected by file-cleanup phases are normally moved to the configured dedupe trash instead of being permanently deleted, unless `--hard-delete` is selected. Playlist/database cleanup may remove records as part of the requested operation.

For the full set of options, combinations, defaults and warnings, consult `--help` rather than relying on a copied list in this README.

## Features

- Fetches Exportify playlist exports for configured accounts and processes per-user ZIP/CSV collections.
- Matches Spotify tracks against the local library using title, artist and album metadata, including Unicode, Japanese/Kanji and romaji aliases.
- Scores likely recording variants so an unqualified original track is preferred over alternatives such as live, demo, instrumental, rehearsal, extended and expanded editions, unless the CSV explicitly requests a variant.
- Generates M3U playlists while preserving Spotify playlist names and associated artwork metadata, and reports tracks that could not be matched. The `ALBUM DA SCARICARE` section of `mancanti_*.txt` now lists the active source playlists for each album recommendation, distinguishing an album suggestion from a playlist name.
- Synchronizes fetched exports safely, removes stale generated playlists for users whose export was successfully refreshed, and cleans corresponding imported Navidrome playlist records.
- Can apply Navidrome favorites for liked tracks, saved albums and artists represented by the available exports.
- Includes optional maintenance for duplicate playlists/tracks/releases, format cleanup, tags, album metadata and missing album artwork.
- Integrates the former FLAC filename repair, Lidarr folder alignment/import workflow, ListenBrainz listen deduplication, and playlist-owner repair utilities as opt-in commands.
- Can create selected MP3 proxy copies of local albums absent from Spotify, while playlist matching still targets the original lossless files; tracks favorited in Navidrome are tracked in `liked.m3u` and a JSON manifest.
- Produces execution logs, per-phase durations and summaries of missing tracks.
- Reduces repeated ffprobe-cache writes in duplicate-track checks, caches already-efficient FLAC files, and uses cumulative waveform norms to speed repeated offset comparisons without changing the duplicate threshold.

### Performance notes (v0.65 — second Tachyon profile)

A second Python 3.15.2 wall-clock profile was collected on the homelab on October 27, 2026, using `--sync-only --dry-run --no-scan`. The log total was **6 min 10 sec**; the profiler observed 372.7 seconds. Compared with the previous 7 min 24 sec run, the total is shorter, but the comparison is not perfectly controlled: the library index changed from 15,074 cached files to 15,079 files, triggering a full index rebuild, and external translation availability differed.

The new profile shows that the v0.64 probe-cache flush is no longer a leading hotspot. The biggest remaining areas were:

- **Embedded artwork probes — about 92 sec inclusive.** The code always evaluated all of the first three tracks in an album, even when the first already had embedded artwork. v0.65 stops after the first positive result and persists the attached-picture status in the shared ffprobe cache. Existing cache rows are migrated the first time they are checked.
- **Automatic translation HTTPS — about 85 sec inclusive.** The log reported the Google translation service was unavailable. Previously, the script continued to try other names after that failure, potentially repeating network waits. v0.65 opens a persistent six-hour circuit breaker after a provider error, keeps using valid cached translations and falls back to phonetic names until the cooldown expires. Set `AUTO_NAME_TRANSLATION.failure_cooldown_hours` to change the cooldown.
- **Waveform tie-breaks — about 69 sec inclusive, with roughly 50 sec sampled in `_shift_corr`.** Threshold-only comparisons now check offset zero first, then coarse offsets in order of distance. Already-aligned copies can return before scanning the entire offset grid. The full-score `--compare` diagnostic keeps the previous search grid; offset- or speed-variant candidates can still take longer.

These are sampling estimates rather than exact per-function timers. The total observed time was around 74 seconds less than the previous run, but that difference cannot be attributed entirely to the v0.65 changes. Verify the speedup with another profile on the same library and options.

`--dry-run` still refreshes local caches and extracts Exportify CSV staging files. It avoids applying playlist/tag changes and skips the Navidrome scan/starring actions in the documented command.

## Configuration

`exportify_names.json` contains deployment-specific naming rules, playlist filters, user mappings and matching preferences. It is intended to survive script updates; prefer changing these settings over editing the Python source when a behavior is configurable. The file must be valid JSON: comments and trailing commas are not valid JSON syntax.

### Artist and name normalization

- **`NAME_TRANSLATIONS`** is the highest-priority dictionary for a real English translation or official English/Latin title/name. Use it for known bilingual releases and established English titles, for example `"ワールドイズユアーズ": "World Is Yours"`. It is curated rather than guessed automatically, so it won't silently mistranslate proper nouns.
- **`NAME_FIXES`** is the backward-compatible second layer for manual aliases, canonical spellings and preferred romanizations (for example, an artist's known Latin spelling).
- **`AUTO_NAME_TRANSLATION`** is the new automatic English layer for Japanese/Kanji and Korean/Hangul names that have no manual rule. It translates the original script (rather than attempting to translate the phonetic spelling), caches the result, estimates output reliability with conservative heuristics, and accepts the result only when it reaches `min_confidence`. If it falls below the threshold or the service is unavailable, the script falls back to phonetic romanization. The public Google Translate web endpoint does not supply a calibrated confidence probability, so the stored score is an estimate—not a guarantee of semantic correctness. Unknown CJK/Hangul text may be sent to that public translation service; turn `enabled` off if you prefer not to send metadata externally.

  The resolution order is **`NAME_TRANSLATIONS` → `NAME_FIXES` → automatic English translation above the threshold → phonetic fallback**. The translation cache lives under the script's cache directory in `auto_name_translations.json`, separate from the curated JSON so automatic guesses are never silently promoted to official translations. `max_new_per_run` limits new translation requests; `cache_days` sets the cache lifetime; `timeout` sets the request timeout; `failure_cooldown_hours` (default 6) pauses further provider requests after a network/provider failure and then lets a later run retry. A curated mapping can preserve mixed case for readable tags; matching normalizes it internally.
- **`ARTIST_GROUPS`** groups multiple spellings or aliases that represent the same artist. Each entry is a list of equivalent names; names in one group can match one another in either direction. Use this for aliases, name-order differences and established alternate romanizations rather than for two different artists who merely collaborate. For example: `[["eiichi ohtaki", "eiichi otaki", "ohtaki eiichi"]]`.
- **`ALIASES`**, where used by the configuration, provides additional alternate artist spellings. Prefer the most specific rule that solves the matching problem and avoid adding conflicting aliases for different artists.

### Playlist selection and naming

- **`SKIP_PLAYLISTS`** lists playlists that should not be imported. Comparison is tolerant of capitalization and much punctuation/emoji variation, so a single entry can exclude a name even if its filename spelling differs slightly. An entry ending in `*` acts as a prefix wildcard: for example, `"daylist*"` excludes playlist names starting with `daylist`. These are playlist filters, not user exclusions.
- **`PLAYLIST_PREFIXES`** standardizes the presentation of playlist names beginning with the configured prefix, so clients can group related playlists consistently. For example, the configured prefix `"color"` transforms a name such as `color yellow` into `color - yellow`; other configured prefixes can be used for similar families.
- **`PLAYLIST_FOLDERS`** can route named playlists to configured subfolders under the playlist directory. This affects where generated M3U files are written, rather than whether the playlist is selected.

### Spotify-to-Navidrome user mapping

- **`SPOTIFY_USERS`** maps a Spotify identity/ID found in Exportify data (such as the `Added By` field) to the corresponding Navidrome username. This is useful when an archive's filename does not identify its owner. The value must be the Navidrome account name used by the deployment.
- **`FETCH_IGNORED_USERS`** lists Navidrome users for whom the script must skip the live Exportify fetch. This setting does **not** globally disable those users from processing: their existing local ZIPs/CSVs remain available to later stages, including playlist generation, unless other filters exclude them. Use it when an account should not be refreshed from Exportify but its already-downloaded exports should remain useful.

### Track matching and alternate-version scoring

- **`TITLE_MATCH_PENALTIES`** maps version/edition phrases to numeric penalties used when ranking local audio-file candidates for a requested Spotify title. Examples in the current configuration include `live`, `demo`, `instrumental`, `rehearsal`, `extended`, `expanded`, `remix`, `remastered` and `parentheses`.
- A **higher penalty makes an unrequested qualifier less desirable**. This helps a clean title such as `Pictures of You` beat a candidate named `Pictures of You (Live)` when the Spotify title does not request a live recording. A requested version remains eligible to win when the CSV explicitly includes that qualifier.
- The special `parentheses` entry penalizes extra parentheses in a candidate filename when the requested title itself does not contain them. Tune these values when the library consistently prefers an unwanted version; a larger value is a stronger preference against that qualifier. Keep the numbers non-negative and use the same key spelling as the phrase detected by the matcher.

### Adding local albums that are absent from Spotify

Spotify's official Local Files documentation lists MP3, MP4 and M4P formats; FLAC is not officially supported. The script can generate compatibility MP3s for explicitly selected albums, keeping the original FLACs in the Navidrome library. Spotify's playlist API can return local playlist items with their text metadata and a `spotify:local:` URI; Exportify can export the track, artist and album fields. The script then matches those fields to the original lossless files, so the proxy audio is not used by Navidrome.

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

`albums` is the manual list and is never overwritten by catalog discovery. `auto_albums` is maintained by `--sync-spotify-proxy-config`; the builder creates proxies for the union of both lists. `output_dir` must be outside `MUSIC_ROOT`, so proxies do not appear as duplicates in Navidrome.

#### Compare the library with Spotify first (dry-run by default)

The script does not have a local copy of Spotify's full catalog. It uses Spotify's authenticated Search API for each unique artist/album folder in the Navidrome library, filtered by `market` (`IT` by default). A release unavailable in that market may be a reasonable Local Files proxy even if it is listed in another country. Spotify Search is not an exhaustive database dump: albums with plausible but uncertain results are marked **REVIEW** and are deliberately not added automatically.

Create a Spotify Developer app (if your account/app is eligible for Web API access), then put these credentials in the private `.env` next to the script:

```text
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_MARKET=IT
```

The Search API requires authorization. As of Spotify's current 2026 guidance, every Development Mode app requires an active Premium subscription for the app owner (not necessarily for every end user); without it, uncached catalog requests fail. A scan can still produce a cached/offline report if every needed album result is already fresh in the local catalog cache, but it cannot discover new albums until API access works again. Extended Quota Mode has separate requirements. Development Mode currently allows up to five authorized users. Search returns at most 10 results per request, which is the current API maximum. See the [official Search API docs](https://developer.spotify.com/documentation/web-api/reference/search), [authorization guide](https://developer.spotify.com/documentation/web-api/concepts/authorization), and [Developer Access update](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security).

Run a preview on the homelab:

```bash
python3 exportify_to_m3u.py --sync-spotify-proxy-config --dry-run
```

This scans the whole library and writes a detailed `logs/spotify_proxy_sync_*.txt` report plus a proposed `logs/exportify_names_proxy_preview_*.json` file. It does **not** change `exportify_names.json`. Review the **ADD PROXY** and **REVIEW** sections before applying. If the first run would query too many albums, preview a batch first with `--proxy-limit 100`; limited runs are additive and preserve existing `auto_albums` entries. The script caches catalog outcomes for 90 days by default; set `SPOTIFY_LOCAL_PROXY.catalog_cache_days` to `0` to force every scan to query Spotify again, or use `--proxy-force-refresh` for a one-run refresh. Any run with `--proxy-limit` is additive: it preserves existing `auto_albums` entries, even if the current batch happens to cover every uncached album.

After reviewing the report, apply the full scan:

```bash
python3 exportify_to_m3u.py --sync-spotify-proxy-config --apply
```

Only the `SPOTIFY_LOCAL_PROXY.auto_albums` list is updated. If an API request fails, or if `exportify_names.json` was edited while the scan was running, the config update is blocked rather than risking a partial result or overwriting your latest manual changes. To then create a proxy preview, use `--build-spotify-proxies --dry-run`; to write MP3 files after reviewing the list, use `--build-spotify-proxies`. The feature requires `ffmpeg` with the `libmp3lame` encoder.

#### Track Navidrome favorites for proxy files

When `--build-spotify-proxies` finishes, the script queries Navidrome's Subsonic `getStarred2` endpoint and matches the currently favorited songs to the generated proxy files, preferring the exact source path and using artist/title/album metadata as a fallback. It writes/updates:

- `liked.m3u` — a local M3U containing proxy tracks whose source is currently favorited in Navidrome;
- `spotify_proxy_favorites.json` — a readable snapshot listing the favorite proxy tracks, selected Navidrome user and update time;
- `.spotify_proxy_manifest.json` — the source-to-proxy mapping used for later refreshes without re-encoding audio.

Set `SPOTIFY_LOCAL_PROXY.favorites_user` in `exportify_names.json` if the favorites should come from a different Navidrome user. Leave it empty to use `ND_FAVORITES_USER`, then `ND_USER`/the configured Subsonic user. The matching account needs its `ND_PASS_<USER>` or default `ND_PASS` environment setting in the private `.env`.

To refresh favorite state later without rebuilding the MP3s, preview first and then apply:

```bash
python3 exportify_to_m3u.py --sync-proxy-favorites --dry-run
python3 exportify_to_m3u.py --sync-proxy-favorites --apply
```

**Important Spotify limitation:** Spotify's official Web API can read local-file tracks already present in playlists, but it cannot add local files to playlists; its save-to-library endpoint accepts Spotify catalog URIs, not `spotify:local:` URIs. Therefore this feature reliably tracks Navidrome favorites and exports `liked.m3u`, but it cannot automatically put those unavailable catalog tracks into Spotify's native **Liked Songs** playlist. To do that, open Spotify Desktop, add the proxy folder under Settings → Local Files, and manually add the local tracks to a Spotify playlist if your client supports it. The generated M3U itself is not a Spotify playlist. See the [Spotify playlist API's Local Files limitation](https://developer.spotify.com/documentation/web-api/concepts/playlists).

The default proxy bitrate is now **64 kbps**. For the same duration, the encoded audio uses roughly **one-third of the space** of a 192 kbps MP3 (before tags and embedded cover art). This is intentionally low quality: it is fine as a compact compatibility copy, but it will sound noticeably worse if you listen to the proxy directly in Spotify. Set `SPOTIFY_LOCAL_PROXY.bitrate` to `96k` or `128k` if you prefer better sound at the cost of more space. The value is configurable from `64k` to `320k`. If your existing `exportify_names.json` still says `192k`, change that value to `64k`; an explicit existing setting overrides the script default.

### Missing album artwork

- **`MISSING_ARTWORK`** controls the final missing-cover search/download stage. `enabled` turns the feature on or off; `max_per_run` limits the number of albums examined in a run (a value of `0` removes the limit); timeout and image-size limits constrain remote requests; `retry_days` controls how long failed searches are cached; `check_embedded_art` controls whether existing embedded artwork is considered; `scan_after_download` requests a Navidrome scan after successful downloads; and `cover_basename` selects the standard cover filename.
- Artwork lookup is meant to fill gaps, not replace a cover that already exists. A missing-art run can make remote requests and write image files, so keep it enabled only if that behavior is wanted for the deployment.

The configuration may also include `FORCE_ARTIST` and `CSV_FIX` for persistent per-track overrides, `UNIFY_FORCE` for album metadata normalization, and `EMOJI_WORDS` for handling emoji-related words. These are specialist overrides; see the in-script help and configuration comments for the exact structure expected by the current version.

Environment variables and the local `.env` file can provide Navidrome credentials. Keep credentials, browser session files and exported cookies private; they should not be committed to a repository. Paths for the library, playlist directories, ZIP storage and Navidrome database are configured in the script for the deployment environment.

## Integrated maintenance utilities

The following older helper scripts have been integrated into `exportify_to_m3u.py`; they do not run automatically as part of `--all` or `--sync-only`. Use the built-in `--help` for every current option.

### Safe FLAC filename repair

`--fix-flac-safe` looks for pairs such as `track.flac` and `track.flac.flac`. It replaces the original only when the appended file passes validation with `metaflac` or `ffprobe`. It also removes a `.backup` file only when its corresponding original file exists. Preview is the default:

```bash
python3 exportify_to_m3u.py --fix-flac-safe --dry-run
python3 exportify_to_m3u.py --fix-flac-safe --apply
```

The actual replacement uses an atomic overwrite rather than deleting the original first. The library defaults to the path configured in the script; `--library-root /path/to/music` can override it.

### Lidarr folder alignment and slskd import

`--lidarr-folder-fix` compares Lidarr artist paths to folders on disk, using normalized names, `NAME_TRANSLATIONS`, `NAME_FIXES`, `ALIASES` and `ARTIST_GROUPS`, followed by a fuzzy fallback. It previews by default; `--apply` updates Lidarr and triggers `RescanFolders` after successful path changes.

```bash
python3 exportify_to_m3u.py --lidarr-folder-fix --dry-run
python3 exportify_to_m3u.py --lidarr-folder-fix --apply
```

`--lidarr-import-slskd` submits a `DownloadedAlbumsScan` command for `/downloads/slskd`, checks the `failed_imports` directory and runs the folder-alignment step. With `--dry-run`, the import is not submitted. Without `--apply`, folder changes are only previewed; add `--apply` to apply path fixes as part of the import workflow. The failed-folder count is an immediate snapshot after the import command is queued; the script does not wait for Lidarr to finish processing every download. Paths can be overridden with `--slskd-import-folder`, `--slskd-failed-folder`, `--library-root` and `--lidarr-container-root`.

Set these variables in the private `.env` next to the script (or in the process environment):

```text
LIDARR_URL=http://192.168.1.7:8686
LIDARR_API_KEY=replace_with_a_new_lidarr_api_key
LIDARR_MUSIC_ROOT=/homelab/MUSICA
LIDARR_CONTAINER_ROOT=/music
SLKSD_IMPORT_FOLDER=/downloads/slskd
SLKSD_FAILED_FOLDER=/downloads/slskd/failed_imports
LISTENBRAINZ_TOKEN=replace_with_your_listenbrainz_token
```

The API key embedded in the uploaded legacy helper should be treated as exposed if it was real: rotate it in Lidarr and use the new value only in the local `.env`. The distributable bundle deliberately excludes `.env` and credentials.

### ListenBrainz duplicate listens

`--lb-dedup USER` downloads listens for the most recent year by default, identifies repeated listens with the same normalized artist and track title within five seconds, and keeps the first listen in each cluster. The fetch includes retries, resumable page checkpoints and reports unreachable three-day windows. It is a preview by default.

```bash
python3 exportify_to_m3u.py --lb-dedup YOUR_LISTENBRAINZ_USERNAME
python3 exportify_to_m3u.py --lb-dedup YOUR_LISTENBRAINZ_USERNAME --lb-delete
```

Add `LISTENBRAINZ_TOKEN=your_listenbrainz_token` to the private `.env` or environment. Never pass the token as a command-line argument. `--lb-delete` performs irreversible API deletions; when any date windows could not be fetched, deletion is blocked because the history is incomplete. `--lb-window SEC` changes the duplicate time threshold and `--lb-days DAYS` changes the lookback period.

### Navidrome playlist ownership: per-folder vs force-all

`--fix-owners [USER]` remains the normal per-user repair: playlist files under `Playlists/<user>/` are assigned to that user, playlists in the root layout go to the default owner, and playlists created in the Navidrome UI (with no M3U path) are left alone.

The legacy `fix_playlist_owners.py` did something broader: it assigned **every** playlist, including UI-created playlists, to one account. That behavior is now available separately as `--fix-all-playlist-owners [USER]`, with a preview by default:

```bash
python3 exportify_to_m3u.py --fix-all-playlist-owners --dry-run
python3 exportify_to_m3u.py --fix-all-playlist-owners chic --apply
```

Use the force-all option only when a single owner for all playlists is intentional; it overrides per-user ownership.

## Usage reference

The script's built-in `--help` provides the detailed, current list of options and their descriptions. That help text is maintained inside the script so it remains the authoritative reference as options change. The built-in `--changelog` prints the full changelog embedded in the script.

## Dependencies and optional capabilities

The script uses Python's standard library plus optional libraries for transliteration and waveform analysis. Fetching exports requires Playwright and a browser runtime. Audio metadata inspection and FLAC maintenance use `ffprobe`, `ffmpeg`, and/or `metaflac`, depending on the selected phases. Features requiring an optional dependency report when that capability is unavailable.

## v0.65 changes: second Tachyon profile

- Embedded-artwork detection now reuses a fifth optional field in the shared ffprobe cache. Existing four-field entries are still valid; when needed, the embedded-picture status is probed once and appended to that entry. Checks stop as soon as one of the first three album tracks has attached artwork, rather than launching all three probes unconditionally.
- Automatic translation now uses a persistent provider circuit breaker. When the public Google translation endpoint fails, the script records a cooldown timestamp (six hours by default) and avoids waiting through repeated requests for other CJK/Hangul names in the same or subsequent run. Cached successful translations remain available, and new names fall back to phonetic transliteration during cooldown.
- Waveform code paths used only for threshold decisions can return as soon as the requested correlation threshold is actually reached. The explicit `--compare` command keeps its full-score behavior.
- Re-profiled `--sync-only --dry-run --no-scan` after v0.64. The old probe-cache flush hotspot no longer appears among the dominant sampled functions; embedded-art checks, translation HTTP waits and waveform tie-breaks are now the main opportunities.

## v0.64 changes: optimizations based on a real Tachyon profile

- Avoid a full `os.path.exists()` sweep across every ffprobe cache entry whenever a pipeline phase ends. A profile showed about 109 seconds in one flush plus another 23 seconds in a later flush. Cache records are still validated with `stat` before their metadata is used; a stale entry is removed lazily when its path is requested and missing.
- Collect cover-art filenames while walking the library for artwork groups, avoiding a second `Path.iterdir()` scan of each album folder. Check the artwork negative-result cache before running up to three `ffprobe` calls to inspect embedded artwork, skipping albums whose remote search result is already cached as unavailable until the retry date.
- Batch automatic translation-cache saves at the end of timed phases, retaining atomic writes and saves on handled phase errors/interrupts instead of rewriting the entire cache after every translated name.
- Profiling data came from the user's Python 3.15.2 run. The profile is included in this analysis, not distributed as an artifact in the bundle.

## beta-0.63 changes: Navidrome favorites for Spotify proxies

- Proxy builds now fetch Navidrome's starred-song list, match favorited source tracks to generated MP3 proxies, and keep a `.spotify_proxy_manifest.json` source mapping for future refreshes.
- `liked.m3u` and `spotify_proxy_favorites.json` list proxy tracks whose source is currently favorited in Navidrome. API/authentication errors preserve the previous favorite playlist rather than accidentally replacing it with an empty one.
- Added `--sync-proxy-favorites` to refresh favorite status without re-encoding audio. It previews by default; `--apply` writes the manifest and list.
- Documented that Spotify's Web API cannot add `spotify:local:` tracks to playlists or Liked Songs. The generated M3U is a companion list, not a native Spotify playlist.
- Updated the Python 3.15 profiling instructions to use the current Python 3.15.2 release in a separate `uv` environment; the build environment itself could not download Python 3.15 because outbound DNS was unavailable.

## beta-0.61 changes: catalog matching and automatic translations

- `--sync-spotify-proxy-config` checks unique album folders against the Spotify Search API for the configured market. It generates a detailed dry-run report and a proposed JSON copy; the active JSON changes only with `--apply`.
- `SPOTIFY_LOCAL_PROXY.albums` remains the manual list. `SPOTIFY_LOCAL_PROXY.auto_albums` stores only catalog-confirmed missing/unavailable albums, and the proxy builder reads both lists. Suspected matches require review instead of being auto-added.
- Spotify searches are cached with a configurable TTL and retry handling. Full config updates are blocked if any query fails; limited runs only add items and never prune the old automatic list.
- Name resolution now places an automatic English translation layer after the curated `NAME_TRANSLATIONS` and manual `NAME_FIXES` tables, before phonetic romanization. Because the public translation endpoint has no calibrated confidence score, the threshold uses a documented heuristic; the result is cached separately and low-scoring strings fall back to phonetics.
- The library index cache version is incremented because name resolution can change matching results.
- `catalog_cache_days: 0` now reliably disables cache reuse; runs explicitly limited with `--proxy-limit` always preserve prior automatic proxy entries. Unexpected errors in proxy utility modes return a non-zero exit status, and a scan will not overwrite JSON edited while the scan was running.

## Performance changes in beta-0.59

- Repeated `norm()` and `norm_bare()` calls use bounded LRU caches; the caches are invalidated when custom emoji normalization rules are loaded.
- `romaji_tags` now batches all changed FLAC fields into one `metaflac` process per file rather than one process per tag.
- `fix_date_tags` uses the shared ffprobe metadata cache and parallel prefetch, then writes/removes date tags in one `metaflac` process per changed file.
- `clean_empty` checks whether a directory contains audio using one bottom-up walk instead of recursively re-scanning every directory's entire subtree.

These changes reduce repeated CPU work, subprocess launches and redundant filesystem traversal. Actual end-to-end savings depend on cache warmth, library layout, disk performance and which phases are enabled.

## Performance profiling (Python 3.15+)

Python 3.15 includes the low-overhead statistical profiler `profiling.sampling` (Tachyon), which can print a summary or create an interactive flame graph. See the [official profiler documentation](https://docs.python.org/3.15/library/profiling.sampling.html). v0.64's changes are based on the real flame graph and run log collected on the homelab with Python 3.15.2. Sampling estimates elapsed time, so confirm improvements with a fresh log/profile on the same library and options.

Do not replace the existing `.venv` used by cron just to test Python 3.15. Install the current Python 3.15 maintenance release side-by-side and create a separate environment so the scheduled interpreter stays unchanged. On a host with internet access, `uv` can install the Python build without replacing Debian's system Python:

```bash
uv self update
uv python install 3.15.2
uv venv --python 3.15.2 .venv315
uv pip install --python .venv315/bin/python pykakasi hangul-romanize numpy
# Only needed for automatic Exportify fetching:
uv pip install --python .venv315/bin/python playwright
.venv315/bin/playwright install chromium
source .venv315/bin/activate
python --version   # should report Python 3.15.2
mkdir -p logs
```

If you do not use `uv`, first install Python 3.15.2 from the official Python release instructions, then create `.venv315` with that interpreter. Keep your existing `.venv` intact until you have validated the new environment. This release keeps the existing `.venv` and cron setup unchanged; run profiling only after activating `.venv315`.

A safe first profile focuses on playlist matching without fetching new Exportify exports, writing playlists/tags, or scanning Navidrome:

```bash
python -m profiling.sampling run --flamegraph -o logs/e2m_sync_dry_profile.html ./exportify_to_m3u.py --sync-only --dry-run --no-scan
```

The commands above use the activated `.venv315`; activating it sets `VIRTUAL_ENV` so the script does not re-exec into the older `.venv` used by cron. The core script uses the Python standard library. `pykakasi`, `hangul-romanize`, and `numpy` add transliteration and waveform features; `playwright` is only needed for automatic Exportify fetching. If any package is not yet compatible with Python 3.15 on your system, leave your existing `.venv` unchanged and wait to enable that optional feature until a compatible package is available.

The default profile is wall-clock oriented: it helps reveal where the run spends time overall, including waits. Compare it with a CPU-only profile to distinguish Python computation from I/O waits:

```bash
python -m profiling.sampling run --mode=cpu --flamegraph -o logs/e2m_sync_cpu_profile.html ./exportify_to_m3u.py --sync-only --dry-run --no-scan
```

To profile a real run, use the same interpreter and options as the run you want to study, but remember that the script will perform those operations. For example, omit `--dry-run` only when you intentionally want a live run. The profiler can also attach to a running process (replace `PID` with the script's process ID):

```bash
python -m profiling.sampling attach --flamegraph -d 300 -o logs/e2m_running_profile.html PID
```

Flame graphs are estimates from sampled stacks, not exact function-call counts. `--mode=cpu` excludes time spent sleeping or blocked on I/O; if a phase is slow in wall-clock mode but small in CPU mode, investigate subprocesses, filesystem latency, network requests or service response time before optimizing Python code. The script's automatic venv re-exec is avoided when launching it from an activated `.venv315`, so Python 3.15 remains the interpreter being profiled. Keep `.venv` and `.venv315` separate until the new environment is validated.

## Safety notes

Some maintenance phases can modify files, tags, or the Navidrome database. Review the built-in help and the execution log before enabling destructive operations. Playlist cleanup is restricted to users with a successfully fetched and extracted export, and is suspended when selected CSV conversion fails. Artwork downloads are intended to fill missing covers rather than overwrite existing artwork.

## Changelog

### beta-0.62 — targeted performance and dry-run safety

- Cache FLAC files that were probed and found already-efficient, avoiding repeated `ffprobe` runs while path, mtime and size remain unchanged.
- Use the `os.scandir` library walker for FLAC16 enumeration.
- Make FLAC16 dry-run read-only, including backup cleanup and cache writes.
- Batch `dedupe_tracks` metadata prefetch into one operation instead of repeatedly flushing the whole cache per album.
- Use cumulative squared-sample sums in waveform correlation to avoid repeatedly calculating vector norms for every offset.
- Improve diagnostics when Spotify rejects a Development Mode API request because the app owner lacks Premium; remove an unused proxy-scan set.
