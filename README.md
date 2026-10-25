# Exportify to M3U

`exportify_to_m3u.py` converts playlists exported by Spotify's Exportify into M3U playlists that reference files in a local music library. It is designed for a multi-user Navidrome setup and also includes library maintenance utilities.

## Quick start

**Current release: v0.60.** The Spotify Local Files MP3 proxy now defaults to `64k` to use less disk space.


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
- Can create selected MP3 proxy copies of local albums absent from Spotify, while playlist matching still targets the original lossless files.
- Produces execution logs, per-phase durations and summaries of missing tracks.

## Configuration

`exportify_names.json` contains deployment-specific naming rules, playlist filters, user mappings and matching preferences. It is intended to survive script updates; prefer changing these settings over editing the Python source when a behavior is configurable. The file must be valid JSON: comments and trailing commas are not valid JSON syntax.

### Artist and name normalization

- **`NAME_TRANSLATIONS`** is the highest-priority dictionary for a real English translation or official English/Latin title/name. Use it for known bilingual releases and established English titles, for example `"ワールドイズユアーズ": "World Is Yours"`. It is curated rather than guessed automatically, so it won't silently mistranslate proper nouns.
- **`NAME_FIXES`** is the backward-compatible second layer for manual aliases, canonical spellings and preferred romanizations (for example, an artist's known Latin spelling). If neither table contains the source, the script falls back to phonetic romanization through `pykakasi` for Japanese/Kanji or the available Hangul romanizer for Korean. That fallback is a reading, not a semantic translation.

  Matching, album-name comparison, tag glossing and Spotify proxy matching all follow the same order: **`NAME_TRANSLATIONS` → `NAME_FIXES` → phonetic fallback**. A curated mapping can preserve mixed case for readable tags; matching normalizes it internally. Existing `NAME_FIXES` entries continue to work without being moved.
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
  "albums": [
    {"artist": "Example Artist", "album": "Album Not on Spotify"}
  ]
}
```

Only listed albums are converted; an empty list deliberately creates no proxies to avoid converting an entire collection by accident. Keep `output_dir` outside `MUSIC_ROOT`, so proxy files do not appear as duplicates in Navidrome. After generating them, add that folder as a Local Files source in Spotify Desktop and add the local tracks to whichever Spotify playlists should include them. On the next successful Exportify fetch, their metadata should be included in the exported CSV and matched against the original FLACs. `--dry-run` with `--build-spotify-proxies` previews selected files without writing them. The feature requires `ffmpeg` with the `libmp3lame` encoder.

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

## Performance changes in v0.59

- Repeated `norm()` and `norm_bare()` calls use bounded LRU caches; the caches are invalidated when custom emoji normalization rules are loaded.
- `romaji_tags` now batches all changed FLAC fields into one `metaflac` process per file rather than one process per tag.
- `fix_date_tags` uses the shared ffprobe metadata cache and parallel prefetch, then writes/removes date tags in one `metaflac` process per changed file.
- `clean_empty` checks whether a directory contains audio using one bottom-up walk instead of recursively re-scanning every directory's entire subtree.

These changes reduce repeated CPU work, subprocess launches and redundant filesystem traversal. Actual end-to-end savings depend on cache warmth, library layout, disk performance and which phases are enabled.

## Performance profiling (Python 3.15+)

Python 3.15 includes the low-overhead statistical profiler `profiling.sampling` (Tachyon), which can print a summary or create an interactive flame graph. See the [official profiler documentation](https://docs.python.org/3.15/library/profiling.sampling.html). The build environment for this release only has Python 3.13.5, and the attempt to install 3.15 was blocked by network/DNS failure, so this release has not yet been sampled with Tachyon itself. The optimization changes above were validated with code review and isolated smoke/benchmark tests; the profiling commands below let you collect a real profile on your homelab.

Do not replace the existing `.venv` used by cron just to test Python 3.15. Create a separate venv so the scheduled interpreter and dependencies remain unchanged. The safe dry-run example below only needs Python's standard library; install dependencies compatible with Python 3.15 before profiling a live run:

```bash
python3.15 -m venv .venv315
source .venv315/bin/activate
mkdir -p logs
```

A safe first profile focuses on playlist matching without fetching new Exportify exports, writing playlists/tags, or scanning Navidrome:

```bash
python -m profiling.sampling run --flamegraph -o logs/e2m_sync_dry_profile.html ./exportify_to_m3u.py --sync-only --dry-run --no-scan
```

The commands above use the activated `.venv315`; activating it sets `VIRTUAL_ENV` so the script does not re-exec into the older `.venv` used by cron. The dry-run example does not need the optional transliteration/browser packages. For a live run, install dependencies compatible with Python 3.15 in `.venv315` before profiling.

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
