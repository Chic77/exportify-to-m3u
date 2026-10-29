# Exportify to M3U

`exportify_to_m3u.py` converts playlists exported by Spotify's Exportify into M3U playlists that reference files in a local music library. It is designed for a multi-user Navidrome setup and also includes library-maintenance, metadata-repair and diagnosis utilities.

## Quick start

**Current release: v0.83.** Terminal colors are now customizable through the `TERMINAL_COLORS` object in `exportify_names.json`; the shipped JSON uses your customized green/blue/amber palette as the default, with a separate amber `review` accent. You can independently change phase headings, phase outcomes, counters, information/warning/error/dry-run/success prefixes, duration, progress label/count/unit, spinner, bar border/fill/empty cells, and ordinary/completed percentages. Each color can be a named ANSI color, a `#RRGGBB` hex value, a 256-color index such as `256:81`, or an advanced SGR value such as `sgr:1;38;5;81`. Optional `bold`, `dim`, `italic`, `underline`, `reverse`, and `background` settings are supported. Set one role to `"none"` (or `{"color": "none"}`) to disable its accent, or set `TERMINAL_COLORS.enabled` to `false` to disable all colors. Colors are used only on an interactive TTY and never enter the `e2m` log; `NO_COLOR`, `CLICOLOR=0`, or `TERM=dumb` still disable terminal colors. Phase openings and successful endings share the same `phase` color, while the phase count and elapsed duration have independent `counter` and `duration` colors; headers are shown as `=== fase name === 2/22` and `=== fine fase name === 01:02.771`. `[i]`, `[info]` and `[INFO]` use the configurable `info` role, while `[review]` has its own `review` role. The startup palette is preloaded before the first banner. The pinned 50-character progress bar is removed and terminal scrolling restored at normal exit, exceptions, Ctrl+C, SIGTERM and SIGHUP; SIGKILL cannot be intercepted. It stays pinned during execution and refreshes every 100 ms with a compact single-cell Braille spinner (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`), avoiding the visually long horizontal frame. Terminal message lines are buffered and emitted atomically against the progress renderer so new output cannot be joined to or drawn over the bar. Artwork scanning corrects a stale cached file total to the actual count before completion. Repeated album file walks now use a shared `os.scandir` walker; release dedupe skips file scans for titles that have no possible counterpart. Waveform fingerprints and FLAC bit-depth probes use bounded concurrency with configurable worker/timeout settings. v0.78 provides generic artist splitting without `ARTIST_SPLIT_OVERRIDES` and reserves the pinned progress row. v0.77 preserves exact capitalization of bilingual CJK names, standardizes `M_O_O_N`/`M.O.O.N`, reconciles album dates, and reports proposed dry-run changes accurately. v0.76 adds safer album consolidation and cross-folder duplicate previews, with duplicate files moved to trash only when `--apply` is supplied and diagnostic reports embedded directly in `e2m`. v0.74/v0.73 improve progress logging and failure reporting. v0.72 filters artist-split candidates before calling `metaflac`, improves handling of unreadable FLAC tags, and preserves the full MusicBrainz report in `mancanti` across same-day rewrites. v0.71 introduced per-user `SKIP_PLAYLISTS`, removed active `PLAYLIST_PREFIXES` rewriting, and consolidated the diagnostic and MusicBrainz reports. v0.70 added live single-line progress bars; v0.69 improved artist normalization and missing-track reporting; v0.68 added album diagnosis and safer metadata writes; v0.67 integrated album diagnosis and repair into `--all`; v0.66 improved album-fragment and CJK artist handling.

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
- Produces execution logs, a live `=== fase name === (X/Y)` phase counter, one-line in-place progress bars for countable phases, per-phase durations and summaries of missing tracks. A progress bar displays checked/total, a 50-character visual bar and percentage; interactive terminals pin it to the bottom row, while redirected logs retain periodic snapshots. Under `--all`, the MusicBrainz completeness phase checks albums carrying `MUSICBRAINZ_ALBUMID` and appends the complete album report—including missing tracks and releases not found—to the bottom of `logs/mancanti_YYYY-MM-DD.txt`. It no longer creates a separate `album_incompleti_YYYY-MM-DD.txt` file.
- Includes caching and profiling-based optimizations for repeated metadata probes, normalization, waveform comparisons, automatic translations and artwork checks.


### Live progress bars (v0.70)

Countable phases now show a single updating status line, for example:

```text
dedupe_playlists: 91/121 gruppi                        ⠋ [#####################################-------------] 75%
```

On a TTY, the script reserves the physical bottom row for progress and restricts normal terminal scrolling to the rows above it. Rendering saves and restores the log-output cursor, and console writes are serialized against progress redraws, so warnings and repair messages scroll above the bar instead of overwriting or briefly hiding it. The bar is exactly 50 characters inside `[]`; the spinner uses a compact single-cell Braille cycle (`⠋`, `⠙`, `⠹`, `⠸`, `⠼`, `⠴`, `⠦`, `⠧`, `⠇`, `⠏`) refreshed every 100 ms. Complete terminal message lines are buffered and written under the same lock as progress redraws, preventing a message from splitting the status line. When stdout/stderr is redirected by cron or into a log file, the script emits occasional text checkpoints rather than carriage-return or ANSI animation. The unit shown depends on the phase (tracks, files, albums, artist folders, playlist groups or candidate pairs); phases without a reliable total do not fabricate a percentage.


### Terminal colors (v0.83)

All terminal color accents can be changed in the top-level `TERMINAL_COLORS` object in `exportify_names.json`. No Python edit is needed. Every role shown below is independently configurable, including the five new summary/status roles:

| JSON role | Used for |
|---|---|
| `phase`, `counter` | Phase headings and `X/Y` phase counter |
| `phase_failure`, `phase_warning` | Failed/early-exit headings; successful end headings use the same `phase` role as phase starts (`phase_success` is retained for old configs) |
| `info`, `review`, `warn`, `error`, `dry`, `success` | Message prefixes such as `[i]`, `[info]`, `[review]`, `[warn]`, `[ERRORE]`, `[dry]`, `[ok]` |
| `duration` | Phase elapsed time and fallback progress unit color |
| `progress_label`, `progress_counter`, `progress_unit` | Left-hand progress text; each falls back to its base role if omitted |
| `spinner`, `bar_border`, `bar_fill`, `bar_empty` | Spinner glyph, bar brackets, completed cells and remaining cells |
| `percent`, `percent_complete` | Normal percentage and the 100% percentage |
| `waveform_compare`, `run_mode`, `release_summary` | The complete `waveform compare: ...`, `modo: ...`, and `gruppi release: ...` lines |
| `total_label`, `total_duration` | The `TOTALE` label and its elapsed time, independently |

The timing summary title lines (`=== riepilogo tempi ===` and `=== fine riepilogo tempi ===`)
use `phase`. Each timing row uses `phase` for its name and `duration` for its value. The interrupted
phase heading and `[!] RUN INTERROTTA: ...` notification both use `phase_failure`. The shipped
JSON preserves the current user palette exactly, including the green `progress_unit`, and adds
`waveform_compare`, `run_mode`, `release_summary`, `total_label`, and `total_duration`.

A value can be a simple string such as `"bright_blue"`, a hex value such as `"#89B4FA"`, a 256-color value such as `"256:81"`, or an advanced SGR sequence prefixed by `sgr:`. To combine a color with style attributes, use an object, for example:

```json
{
  "TERMINAL_COLORS": {
    "enabled": true,
    "phase": {"color": "#89B4FA", "bold": true},
    "spinner": {"color": "#CBA6F7", "bold": true},
    "bar_empty": {"color": "#45475A"},
    "error": {"color": "#F38BA8", "bold": true, "background": "none"}
  }
}
```

The example above illustrates the format only; preserve the rest of the existing JSON when editing it. In the shipped palette, `[i]` and `[info]` share `info`; `[review]` is independent and defaults to amber. The opening and successful closing phase headings both use `phase`, not `phase_success`. Supported attributes are `bold`, `dim`, `italic`, `underline`, `reverse`, and `background`. Named colors include the eight standard ANSI colors, their bright variants, and gray/grey. `none` turns off the accent for one role; `TERMINAL_COLORS.enabled: false` disables all colors. Unknown roles, invalid colors, and wrong value types stop configuration loading with a message identifying the faulty field, rather than silently applying an unintended palette. Old JSON files without `TERMINAL_COLORS` continue to use the script's built-in fallback palette. `NO_COLOR`, `CLICOLOR=0`, and `TERM=dumb` take precedence.

Colors are applied only to the interactive terminal and are stripped from the `e2m` log. Artist names, titles, paths and arbitrary message bodies are not colorized. The pinned 50-character bar, its 100 ms spinner cadence and the no-ANSI log behavior are unchanged. `EXPORTIFY_FLAC_PROBE_TIMEOUT` controls the individual FLAC metadata probe timeout (default 30 seconds; clamped to 5–120 seconds), and `EXPORTIFY_PROBE_WORKERS` controls the shared metadata-probe worker pool (capped at 8 for the FLAC preflight), while `EXPORTIFY_WAVEFORM_WORKERS` independently controls duplicate-track waveform decoding (default 2; range 1–4).

The cross-folder duplicate pass added to `--all` is preview-only unless `--apply` is supplied. It moves the selected duplicate to the existing trash location; `--hard-delete` is required for permanent deletion.

### Album diagnosis and repair (v0.66–v0.69)

The album diagnosis and repair features are intended to address albums that Navidrome splits into several database entries, reused MusicBrainz IDs, repeated CJK artist names and ambiguous artist tags.

- **`--diagnose-album-splits`** reads the Navidrome database without writing to it and embeds its complete contents in the main `logs/e2m_*.log`. It reports candidate album groups with database IDs, track counts, MusicBrainz IDs, album version/release-date fields and example paths. Fuzzy title pairs and conflicting editions are marked for review; the diagnostic does not merge albums or change audio tags.
- **`--repair-album-groups`** runs the repair workflow. It previews by default; use `--apply` to write changes when running it by itself. It checks MusicBrainz album IDs, harmonizes album tags, aligns `ALBUMVERSION` within logical album roots, repairs `[Unknown Artist]` when album-artist metadata, a non-generic artist folder or a clear consensus from other tracks provides reliable context, and normalizes artist tags only when the Navidrome artist catalog confirms a split.
- **`--all`** automatically creates a diagnosis report before the main modifications and includes album-group repair in the pipeline. After a successful full Navidrome scan, it reports new albums, changed albums and merges using the track paths before/after the scan. It then reruns date, CJK/artist, album-group and tag repair only for the affected album folders, followed by a quick incremental scan. The post-scan report and targeted repair are skipped if scanning is disabled or the database snapshot cannot be trusted.
- **Fuzzy candidates remain review-only.** Similar titles are not automatically merged just because a fragment has few tracks. Explicit edition markers in album titles remain a barrier. When artist and normalized album title match exactly, conflicting `ALBUMVERSION` and MusicBrainz IDs are cleared instead of leaving the exact album split.
- **Tag-write safety:** `--dry-run` previews the tag repairs. In standalone mode, `--repair-album-groups` also requires `--apply` to write. In `--all`, tag/date/album phases are controlled by `--dry-run`; `--apply` primarily enables the destructive duplicate-cleanup phases. Read the operation log before running a live repair.
- **Artist fixes:** `[Unknown Artist]` can inherit a consistent `ALBUMARTIST`, a non-generic artist-folder name, or a clear consensus from known tracks. Explicit compilations such as `Various Artists`, conflicting aliases and ambiguous cases remain review-only instead of receiving a random performer. Semicolons are explicit separators. Commas are split only when the Navidrome artist catalog confirms at least two component names, protecting names such as `Tyler, The Creator`. CJK-only and `CJK (gloss)` variants are normalized using the preferred existing Navidrome spelling when available, preventing the same kanji artist from remaining as two display entries. FLAC receives multi-valued `ARTISTS`/`ALBUMARTISTS` tags and other formats use the scanner-compatible `; ` separator.
- **v0.69 additions:** comma parsing is catalog-aware across normalization and inference paths; duplicate CJK/gloss spellings converge on the preferred Navidrome display name; unknown-artist repair uses trusted album/folder/track context but blocks unsafe compilation guesses; phase progress shows the current phase and planned total. `--all` checks only albums with a MusicBrainz album ID and appends missing tracks to `mancanti_*.txt`. The post-scan comparison uses indexes on album keys and track paths, reports new/changed/merged albums and reruns repair only for those album folders before an incremental scan.
- **v0.68 performance/safety changes:** diagnosis compares albums sharing an artist identity instead of needlessly comparing every album pair; non-FLAC tag writes restore the original file if committing the rewritten file fails; the artist repair combines duplicate alias fields deterministically. MusicBrainz lookup caches populated during a preview are kept as auxiliary caches so repeat previews can reuse them. No new end-to-end timing profile was collected for v0.68, so the pair-index change is a structural optimization rather than a measured whole-run speed claim. Repair summaries also account for failed MusicBrainz-ID, artist-normalization and album-unification writes. Artist inference checks available metadata aliases and refuses to choose a field when aliases conflict.

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
- Collaboration tags do not need per-artist override entries. A tight comma (`Artist A,Artist B`) is treated as a delimiter; a spaced comma is split when the artist catalog confirms its components or the track's containing artist folder confirms one component. An exact known comma-bearing solo name such as `Tyler, The Creator` is kept whole when the catalog does not confirm both components. The legacy `ARTIST_SPLIT_OVERRIDES` field is ignored in v0.78 and can be removed from old configuration files.

### Playlist selection and naming

- **`SKIP_PLAYLISTS`** is an object keyed by Navidrome username. Each user has a separate list of playlist names/patterns to skip; the current exclusions are under `chic` only. Comparison tolerates capitalization, punctuation and emoji differences. A final `*` acts as a prefix wildcard, for example `"daylist*"`.

  Example: to add exclusions for another user, add a sibling array; do not copy `chic`'s rules unless you want them for that user too:
  ```json
  "SKIP_PLAYLISTS": {
    "chic": ["daylist*", "discover weekly"],
    "stello": ["another playlist*"]
  }
  ```
  Playlist names are now preserved exactly as exported by Spotify. Rename playlists in Spotify itself; the script no longer applies prefix-based name rewrites.
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

### v0.83 — dedicated colors for run status and timing summaries

- Adds five independent JSON color roles: `waveform_compare`, `run_mode`, `release_summary`,
  `total_label`, and `total_duration`. These style the waveform status, run mode, release-dedupe
  summary, and the `TOTALE` label/time independently.
- The timing-summary headings use `phase`; each phase name uses `phase` and its elapsed value
  uses `duration`. The `[!] RUN INTERROTTA` line and interrupted-phase heading use `phase_failure`.
- The shipped JSON keeps the user's latest palette exactly, including `progress_unit` in `#77FF94`.

### v0.82 — clean progress shutdown and independently colored phase headings

- The active pinned progress row is removed and the terminal scrolling region is restored on normal shutdown, unhandled exceptions, Ctrl+C, SIGTERM and SIGHUP. An `atexit` cleanup is also installed. SIGKILL and power loss cannot be handled by a process and are not claimed to be recoverable.
- Phase starts use `=== fase name === 2/22`: `phase` colors the title and `counter` independently colors the count. Successful phase endings use `=== fine fase name === 01:02.771`; the heading uses the exact same `phase` setting as the opening heading, while `duration` controls elapsed time.
- Adds independently configurable `review` and `info` prefix styles. `[i]`, `[info]` and `[INFO]` all use `TERMINAL_COLORS.info`; `[review]` uses `TERMINAL_COLORS.review`.
- Preloads only the palette before the initial banner and the first `load_user_config` phase heading, so the first two `[i]` messages and the first phase/counter honor JSON overrides. The full configuration still loads in the measured first phase.
- The shipped JSON preserves the user's supplied colors exactly and adds `review` in amber (`#FFB20F`).

### beta-0.81 — JSON-configurable terminal palette

- Adds `TERMINAL_COLORS` to `exportify_names.json`, exposing every existing terminal accent and finer-grained optional roles for phase outcomes, progress label/count/unit, and the 100% percentage.
- Supports named ANSI colors, truecolor `#RRGGBB`, 256-color indices (`256:N`), advanced numeric SGR (`sgr:...`), optional background color, and bold/dim/italic/underline/reverse attributes.
- Setting a role to `none` disables that accent; `TERMINAL_COLORS.enabled: false` disables all colors. Environment controls `NO_COLOR`, `CLICOLOR=0` and `TERM=dumb` still override the JSON.
- Validates role names, color values and style types before the pipeline runs; old configuration JSON without `TERMINAL_COLORS` stays compatible. The shipped palette uses softer blue/teal/mauve/green tones by default.

### v0.80 — compact spinner, atomic terminal output and pipeline optimization

- Replaces the wide dash animation with a compact, one-cell Braille spinner (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`), cycling every 100 ms without changing the 50-character bar.
- Buffers console message fragments until a newline/flush and emits complete lines under the progress-renderer lock. This fixes the race where `print()` writes its text and newline separately and the spinner could redraw between them. The `e2m` log remains plain text.
- If the cached artwork total differs from the filesystem walk, updates the denominator to the actual count before closing the bar, so a completed scan cannot stop at 99%.
- Reuses the deterministic `os.scandir` audio walker for release/track dedupe instead of repeatedly calling `Path.rglob()` plus `is_file()`. `dedupe_releases` now groups normalized album-folder names first and scans audio only when at least two folders are possible matches; in the supplied log the old phase spent 2m40 finding zero groups.
- `dedupe_tracks` fingerprints files in a duplicate-title group concurrently, capped at four workers and defaulting to two. Set `EXPORTIFY_WAVEFORM_WORKERS=1` for strictly serial fingerprinting or a value from 1–4 to tune it. Correlation decisions and delete thresholds are unchanged.
- `flac_16bit` probes use bounded parallel `ffprobe` workers and a 30-second default timeout configurable with `EXPORTIFY_FLAC_PROBE_TIMEOUT` (5–120 seconds). Probes select the first audio stream explicitly (so embedded cover art cannot masquerade as audio), and exit codes, timeouts, missing streams and incomplete metadata are counted and reported explicitly; conversions themselves remain sequential.
- Makes `fix_date_tags` dry-run output explicit about removing redundant `DATE` fields and changing `ORIGINALDATE`; this avoids log lines that appear unchanged when only `DATE` is being removed.

### v0.79 — colorful terminal output

- Adds restrained 256-color ANSI accents to interactive terminal output: phase headings in bright cyan, counters and spinner in magenta, progress borders in cyan, completed cells in green, unfilled cells in muted gray, and 100% in green.
- Colors `[i]`, `[warn]`, `[ERRORE]`, `[dry]` and phase outcomes while leaving message bodies, paths, artist names and track titles untouched.
- Uses colors only when stdout/stderr is an interactive TTY. `NO_COLOR=1`, `CLICOLOR=0` and `TERM=dumb` disable them. The `Tee` strips ANSI sequences before writing the `e2m` log, so grep/diff and log analysis remain plain-text safe.
- The 50-character bar layout calculates alignment and terminal wrapping from uncolored display width; color codes do not affect the pinned row. Spinner cadence and bottom-row terminal scrolling remain unchanged at 100 ms.

### beta-0.78 — catalog-independent collaboration split and pinned progress row

- Removed `ARTIST_SPLIT_OVERRIDES` from the shipped JSON and source defaults. The root bug was precedence: the parser accepted an already-indexed combined artist before testing its components, while tag repair required the components to already exist as separate Navidrome artists. Tight commas now split before the combined-key lookup; spaced commas use component catalog evidence or a matching directory name as independent evidence. The same path context is passed through artist canonicalization/inference, not only the final repair phase.
- Folder-aware splitting now covers future collaboration tags under artist directories, not just the two examples in the previous config. A real comma-bearing artist name remains intact when its components are not independently confirmed. The artist catalog also skips composite labels containing bracketed or parenthesized `Unknown Artist` placeholders: `norm()` strips bracketed annotations, which previously made `The Cure, [Unknown Artist]` collide with and sometimes replace the real `The Cure` spelling.
- The TTY progress display reserves the last physical row and limits scrolling to the area above it. Rendering uses cursor save/restore and serialized console I/O, so new messages scroll above the bar without hiding it for a frame. `clear()` no longer erases the pinned row, and height reductions reposition the log cursor inside the updated scroll region. ANSI controls stay out of the `e2m` file log; redirected runs continue to emit readable checkpoints only.
- Removed a duplicate legacy implementation of `_split_artist_tag_if_known`; old JSON fields named `ARTIST_SPLIT_OVERRIDES` are ignored with a warning, not used for split decisions.
- Regression tests cover the two previous examples without any override dictionary, tight and spaced comma parsing, folder-context matching, protection for `Tyler, The Creator`, mixed `[Unknown Artist]`/`(Unknown Artist)` collision filtering, fixed 50-character bars, 100 ms spinner frames, pinned bottom-row controls, and clean log output.

### beta-0.77 — smoother spinner, canonical artist alias and album-date convergence

- The spinner cycles deterministically through `/`, `──`, `\`, `|` at 100 ms per frame. A TTY regression test checks the frame order and timing as well as the exact 50-character bar; the thicker horizontal glyph was replaced with a lighter two-character dash to make the rotation visually consistent.
- The explicit `M.O.O.N` canonical alias now overrides a stale Navidrome display spelling such as `M.O.O.N.`. That prevents the trailing dot from recreating a separate artist entity after a tag repair. When a bilingual CJK display already exists, the script also preserves its exact catalog gloss casing (for example, `高中正義 (masayoshi takanaka)`) rather than creating a title-cased second artist name.
- `fix_date_tags` now considers tags across each logical album root (including `CD1`/`CD2`) and, only when a dated-track consensus is supported by at least two tracks and 60% of date-bearing tracks, proposes a shared `ORIGINALDATE` and removal of conflicting `DATE` values. Ambiguous albums remain unchanged rather than being guessed.
- Fixed the dry-run summary in `fix_date_tags`: it now reports how many files have proposed changes instead of incorrectly saying `0 file sistemati` despite printing many `[dry] FIX(...)` lines. Dry-run still does not write any audio tags.
- The supplied v0.76 dry-run completed all 22 phases without a Python traceback or phase error; it took 1h40m38s. It proposes a duplicate `Animals/Dogs` removal and artist-tag fixes, while the new v0.77 date normalizer needs a fresh dry-run to show its newly proposed changes. Navidrome scan and post-scan reconciliation are skipped by the supplied dry-run, so it cannot prove that the live database has merged `SAUDADE` or removed the displayed `[Unknown Artist]` label for The Cure.

### beta-0.76 — targeted artist split and album consolidation

- Progress bar remains exactly 50 characters between `[` and `]`; the spinner uses a fixed two-column footprint and includes a longer horizontal dash. Both redraw and spinner advance every 100 ms in an interactive terminal.
- v0.76 temporarily added editable `ARTIST_SPLIT_OVERRIDES` for two observed collaborations. This approach was removed in v0.78 after identifying the generic delimiter/catalog-precedence bug; the legacy JSON field is now ignored.
- Standardizes `M_O_O_N`/`M.O.O.N` to `M.O.O.N` and reuses the existing bilingual CJK catalog spelling where available. Collaboration splitting was generalized in v0.78 and no longer requires per-artist override entries.
- `album_unify` now chooses a shared original date only when one year appears on at least two tracks and covers at least 60% of date-bearing tags. It clears conflicting MusicBrainz album/release-group IDs (including stale IDs that can be removed from M4A/MP4) and clears conflicting `ALBUMVERSION` tags when exact-title album folders are consolidated; explicit edition markers remain protected.
- Duplicate fallback still requires exact matching title, close duration (within 1.5% or one second), and no version qualifier. It additionally accepts a two-file lossless/lossy pair when at least one track number is missing and the other is absent or agrees; conflicting explicit numbers stay protected.
- Added `dedupe_cross_album_tracks` after album normalization in `--all`: it detects conservative duplicates across different folders now sharing the same album/artist identity. The preview never moves files; `--apply` moves selected duplicates to the existing trash folder, and explicit edition-marker conflicts are skipped. `--hard-delete` is required for permanent deletion. This addresses duplicate `Dogs`-type tracks left after merging `Animals`-like album fragments.
- Fixed a missing initialization of the artist-name map in cross-folder album unification, which could raise `NameError` as soon as a cross-folder group needed canonical `ALBUMARTIST` handling.
- `[Unknown Artist]` is removed as a placeholder component in mixed `ALBUMARTIST` fields such as `The Cure; Unknown Artist`, but repair still requires a reliable remaining artist identity.

### beta-0.75 — artist canonicalization, album repair and 100 ms progress

- The terminal progress bar is exactly 50 characters wide inside `[]`, includes a spinner and redraws every 100 ms on one row; carriage returns and terminal-wrap control sequences do not enter `e2m` logs.
- Catalog-aware artist normalization now canonicalizes punctuation variants such as `M_O_O_N` / `M.O.O.N`, prefers an existing bilingual CJK artist display name, and splits collaborations when every comma-separated component is known, even if the joined value is already in Navidrome.
- `[Unknown Artist]` repair also checks explicit `ALBUMARTIST` / `ALBUM_ARTIST` values and uses the folder/track artist only when compilation markers do not block that inference.
- Fixes the `DATE` gate so an `ORIGINALDATE` target on one track no longer suppresses `DATE` updates on all FLAC tracks that lack `ORIGINALDATE`.
- A conservative duplicate-track fallback catches exact-title groups with the same track number and nearly identical duration when audio correlation differs because of mastering. Live/demo/mix/version-qualified titles are excluded.
- `album_db_diagnostics` and `album_cross_folder_review` are appended directly to the main `e2m` log, without writing sidecar report files. The MusicBrainz completeness report remains consolidated at the bottom of `mancanti`.

### beta-0.74 — terminal progress redraw and single-copy reports

- Previous progress bars redrew the same terminal row every 500 ms and used a 24-character bar. v0.75 extends the bar to 50 characters and refreshes at 100 ms.
- The Tee keeps carriage-return redraws out of the `e2m` log. Diagnostic report content remains embedded in the main log.

### beta-0.73 — convergent MP3 ID3 repair and trustworthy exit status

- Removes legacy `TXXX:albumartist` frames directly through Mutagen while writing one canonical `TPE2` frame; audio is not re-encoded and unrelated ID3 frames are preserved. This fixes the repeated 168-file MP3 repair visible in the supplied v0.68 runs.
- A full pipeline still runs its remaining phases and writes reports after a phase failure, but now exits with status 1 if a phase returns `False`, raises, or returns an error-count result. This makes failures visible to cron/monitoring.
- MusicBrainz report refresh replaces even a truncated old marker block, and `--check-albums` returns a failed status when MusicBrainz requests fail.
- Adds `mutagen` to the virtual-environment install command. The complete MusicBrainz completeness report remains merged into `mancanti`; diagnostic reports remain embedded in the main `e2m` log.

### beta-0.72 — faster artist split and persistent MusicBrainz report

- Filters artist-tag split candidates using cached `ffprobe` metadata before invoking `metaflac`, avoiding one subprocess per track when no supported split is present.
- Adds plural `artists`/`albumartists` fields to the probe cache and bumps its version so older cache entries cannot hide them.
- Reports unreadable FLAC tag exports as skipped warnings, without letting one unreadable file fail the entire artist-split phase. Real tag-write failures still count as errors.
- Preserves the complete MusicBrainz block at the bottom of `mancanti_YYYY-MM-DD.txt` when playlist-missing statistics are regenerated; the next MusicBrainz check replaces the prior block instead of duplicating it.

### beta-0.71 — per-user playlist skip lists and consolidated reports

- `SKIP_PLAYLISTS` is a JSON object keyed by Navidrome username; existing exclusions belong to `chic` only. Add a sibling array for each future user.
- Removed active `PLAYLIST_PREFIXES` rewriting. Playlist names are preserved as exported from Spotify; rename them at the source when needed.
- Full `album_db_diagnostics` and `album_cross_folder_review` reports are embedded in the main `e2m` log with start/end markers; standalone copies are deleted after embedding.
- The full MusicBrainz completeness report is merged into `mancanti_YYYY-MM-DD.txt` rather than a newly generated separate `album_incompleti` file.

### beta-0.69 — artist normalization, phase counter and MusicBrainz completeness

- Extends catalog-confirmed artist splitting to comma separators while preserving artist names that contain commas.
- Normalizes Kanji/CJK-only tags and their bilingual `CJK (gloss)` variants to one preferred existing Navidrome spelling where available.
- Improves `[Unknown Artist]` inference by using reliable album-artist tags, a non-generic artist folder or a clear track-artist consensus, while blocking unsafe compilation guesses.
- Prints each measured phase as `=== fase phase_name === (X/Y)` and continues to summarize per-phase and total elapsed time.
- Adds a MusicBrainz completeness phase in `--all` for albums with `MUSICBRAINZ_ALBUMID`; its complete missing-track report is appended to the end of `logs/mancanti_YYYY-MM-DD.txt`, without creating a separate `album_incompleti` report.
- After a successful Navidrome scan, reports newly found, changed and merged albums; reruns repair only for their affected paths and finishes with an incremental scan.
- Uses indexed album keys and paths to avoid comparing every scanned album against every previous album.

### beta-0.68 — diagnosis performance and safer tag writes

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
