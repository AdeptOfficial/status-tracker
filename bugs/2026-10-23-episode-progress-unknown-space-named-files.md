# Episode progress shows "progress unknown" for space-separated release names

**Created:** 2026-10-23
**Status:** Open (fix proposed, not implemented)
**Severity:** Medium (per-episode progress missing on the dashboard and detail page; no state or data impact)
**Found:** DEV regular-TV test, 2026-10-23 (Gotham S5, request 25)
**Related:** [episode progress UI improvements](../issues/2026-01-22-ui-episode-progress-improvements.md)

## Problem

While all twelve episodes were downloading, each episode row showed `Downloading · progress unknown`
although qBittorrent reported real per-file progress (E02 29%, E03 45%). The request-level progress
(20–30%) displayed correctly, because it is aggregated from whole torrents and does not use file matching.

## Cause

`file_progress()` in `app/services/episode_progress.py` matches each video file to an episode by its
`SxxEyy` marker, then (line 34) skips files it believes are multi-episode, so a combined file is never
credited to one episode:

```python
if re.match(r'(?i)(?:e\d|[-_ ]+(?:e|s\d+e)?\d)', name[match.end():]):
    continue
```

The second branch accepts **any digit** after a space, `-` or `_`. This release names its files with
spaces, for example `Gotham S05E02 1080p BluRay DD5 1 x264-CtrlHD.mkv`. The text after the marker is
` 1080p`, so the resolution is read as a second episode number, the file is skipped, no episode is
matched, and `download_progress` stays `None` for every episode. The template then renders
`progress unknown` (`templates/detail.html`, `templates/components/card.html`).

Checked against the real file names (no code change):

| File name | After marker | Treated as multi-episode |
|---|---|---|
| `Gotham S05E02 1080p BluRay DD5 1 x264-CtrlHD.mkv` | ` 1080p` | **yes (wrong)** |
| `Gotham.S05E02.1080p.BluRay.DD5.1.x264-CtrlHD.mkv` | `.1080p` | no (correct) |
| `Show S01E02-E03 1080p.mkv` | `-E03` | yes (correct) |

Dot-separated names, the common scene format, are unaffected, which is why earlier tests passed.
Any space- or underscore-separated name followed by a number (`720p`, `1080p`, `2160p`, `2019`,
`DD5 1`) is affected.

## Proposed fix

Only treat the remainder as a further episode when it actually looks like one:

- `E`/`e` plus digits directly (`S01E02E03`), or
- a separator plus an episode marker: `-E03`, ` E03`, `-S01E03`, or
- a separator plus a bare episode number that is **not** a resolution or year: `-03`, ` - 03`, i.e.
  1–3 digits not followed by another digit or `p`/`i`.

For example (to be confirmed with tests):

```python
RANGE = re.compile(r'(?i)^(?:e\d|[-_ ]+(?:s\d+)?e\d|[-_ ]*-[-_ ]*\d{1,3}(?![\dpi]))')
```

The bare-number branch requires a `-`, so ` 1080p`, ` 720p`, ` 2019` and ` 5 1` no longer match.
Checked against all eleven cases below on 2026-10-23 (pattern only, outside the app): all correct.

## Tests to add (`tests/test_episode_progress.py`)

- Space-separated single episode with a resolution (`Show S05E02 1080p BluRay.mkv`) → matched.
- Underscore-separated (`Show_S05E02_720p.mkv`) → matched.
- Year after the marker (`Show S01E01 2019 WEB.mkv`) → matched.
- Episode title or resolution after a dash (`Show S01E02 - Title Here 1080p.mkv`, `Show S01E02 - 1080p.mkv`) → matched.
- Ranges still skipped: `S01E02E03`, `S01E02-E03`, `S01E02-03`, `S01E02 - E03`, `S01E02-S01E03`.
- Existing dot-separated cases unchanged.

## Acceptance

Regressions pass including the new cases; on DEV, a space-named per-episode download shows each
episode's percentage while downloading.
