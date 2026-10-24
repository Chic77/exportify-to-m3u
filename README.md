# Exportify to M3U

`exportify_to_m3u.py` converts playlists exported by Spotify's Exportify into M3U playlists that reference files in a local music library. It is designed for a multi-user Navidrome setup and also includes library maintenance utilities.

## Quick start

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
- Generates M3U playlists while preserving Spotify playlist names and associated artwork metadata, and reports tracks that could not be matched.
- Synchronizes fetched exports safely, removes stale generated playlists for users whose export was successfully refreshed, and cleans corresponding imported Navidrome playlist records.
- Can apply Navidrome favorites for liked tracks, saved albums and artists represented by the available exports.
- Includes optional maintenance for duplicate playlists/tracks/releases, format cleanup, tags, album metadata and missing album artwork.
- Produces execution logs, per-phase durations and summaries of missing tracks.

## Configuration

`exportify_names.json` contains deployment-specific naming rules, playlist filters, user mappings and matching preferences. It is intended to survive script updates; prefer changing these settings over editing the Python source when a behavior is configurable. The file must be valid JSON: comments and trailing commas are not valid JSON syntax.

### Artist and name normalization

- **`NAME_FIXES`** maps a source name to the name or reading that should be used for normalization and matching. It is especially useful when the same artist appears in Kanji, Hangul, another transliteration, or a known alternate spelling. For example, a rule can map a Japanese-script name to the romanized artist name used in the music library. Add a direct, explicit mapping when automatic transliteration or fuzzy matching is not reliable.
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

### Missing album artwork

- **`MISSING_ARTWORK`** controls the final missing-cover search/download stage. `enabled` turns the feature on or off; `max_per_run` limits the number of albums examined in a run (a value of `0` removes the limit); timeout and image-size limits constrain remote requests; `retry_days` controls how long failed searches are cached; `check_embedded_art` controls whether existing embedded artwork is considered; `scan_after_download` requests a Navidrome scan after successful downloads; and `cover_basename` selects the standard cover filename.
- Artwork lookup is meant to fill gaps, not replace a cover that already exists. A missing-art run can make remote requests and write image files, so keep it enabled only if that behavior is wanted for the deployment.

The configuration may also include `FORCE_ARTIST` and `CSV_FIX` for persistent per-track overrides, `UNIFY_FORCE` for album metadata normalization, and `EMOJI_WORDS` for handling emoji-related words. These are specialist overrides; see the in-script help and configuration comments for the exact structure expected by the current version.

Environment variables and the local `.env` file can provide Navidrome credentials. Keep credentials, browser session files and exported cookies private; they should not be committed to a repository. Paths for the library, playlist directories, ZIP storage and Navidrome database are configured in the script for the deployment environment.

## Usage reference

The script's built-in `--help` provides the detailed, current list of options and their descriptions. That help text is maintained inside the script so it remains the authoritative reference as options change. The built-in `--changelog` prints the full changelog embedded in the script.

## Dependencies and optional capabilities

The script uses Python's standard library plus optional libraries for transliteration and waveform analysis. Fetching exports requires Playwright and a browser runtime. Audio metadata inspection and FLAC maintenance use `ffprobe`, `ffmpeg`, and/or `metaflac`, depending on the selected phases. Features requiring an optional dependency report when that capability is unavailable.

## Safety notes

Some maintenance phases can modify files, tags, or the Navidrome database. Review the built-in help and the execution log before enabling destructive operations. Playlist cleanup is restricted to users with a successfully fetched and extracted export, and is suspended when selected CSV conversion fails. Artwork downloads are intended to fill missing covers rather than overwrite existing artwork.
