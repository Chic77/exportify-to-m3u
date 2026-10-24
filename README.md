Exportify to M3U
exportify_to_m3u.py converts playlists exported by Spotify's Exportify into M3U playlists that reference files in a local music library. It is designed for a multi-user Navidrome setup and also includes library maintenance utilities.
Features
- Fetches Exportify playlist exports for configured accounts and processes per-user ZIP/CSV collections.
- Matches Spotify tracks against the local library using title, artist and album metadata, including Unicode, Japanese/Kanji and romaji aliases.
- Scores likely recording variants so an unqualified original track is preferred over alternatives such as live, demo, instrumental, rehearsal, extended and expanded editions, unless the CSV explicitly requests a variant.
- Generates M3U playlists while preserving Spotify playlist names and associated artwork metadata, and reports tracks that could not be matched.
- Synchronizes fetched exports safely, removes stale generated playlists for users whose export was successfully refreshed, and cleans corresponding imported Navidrome playlist records.
- Can apply Navidrome favorites for liked tracks, saved albums and artists represented by the available exports.
- Includes optional maintenance for duplicate playlists/tracks/releases, format cleanup, tags, album metadata and missing album artwork.
- Produces execution logs, per-phase durations and summaries of missing tracks.
Configuration
exportify_names.json contains the user-specific mapping and behavior settings. Common configuration sections include:
- NAME_FIXES and ARTIST_GROUPS for aliases and artist-name normalization.
- SKIP_PLAYLISTS and PLAYLIST_PREFIXES for controlling playlist selection.
- SPOTIFY_USERS for mapping Spotify identities to Navidrome usernames.
- FETCH_IGNORED_USERS for accounts excluded from Exportify fetching while their existing local exports remain available to other processing stages.
- TITLE_MATCH_PENALTIES for scoring alternate recordings and edition labels.
- MISSING_ARTWORK for the final missing-album-cover lookup and download stage.
Environment variables and the local .env file can provide Navidrome credentials. Keep credentials and browser session files private; they should not be committed to a repository. Paths for the library, playlist directories, ZIP storage, and Navidrome database are configured in the script for the deployment environment.
Usage reference
The script's built-in --help provides the detailed, current list of options and their descriptions. That help text is maintained inside the script so it remains the authoritative reference as options change. The built-in --changelog prints the full changelog embedded in the script.
Dependencies and optional capabilities
The script uses Python's standard library plus optional libraries for transliteration and waveform analysis. Fetching exports requires Playwright and a browser runtime. Audio metadata inspection and FLAC maintenance use ffprobe, ffmpeg, and/or metaflac, depending on the selected phases. Features requiring an optional dependency report when that capability is unavailable.
Safety notes
Some maintenance phases can modify files, tags, or the Navidrome database. Review the built-in help and the execution log before enabling destructive operations. Playlist cleanup is restricted to users with a successfully fetched and extracted export, and is suspended when selected CSV conversion fails. Artwork downloads are intended to fill missing covers rather than overwrite existing artwork.
