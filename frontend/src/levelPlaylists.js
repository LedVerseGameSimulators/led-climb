/**
 * Mode playlist helpers — ordered lists come from GET /playlists at runtime.
 */

export const HOW_TO = {
  single:
    'Climb glowing holds that match the goal. Avoid red hazards. Clear each wave to advance.',
  multi:
    'Each player scores their own colour. Watch the wall — red hurts both. Clear targets to progress.',
  group:
    'A fixed set of levels runs in order. No level pick — just play through 1, 2, 3… as a group session.',
}

/** Bullet copy for Setup screen (mock-style how-to). */
export const HOW_TO_BULLETS = {
  single: [
    'Watch the goal colour on the HUD.',
    'Hit matching glowing holds as fast as you can.',
    'Avoid red hazards — clear each wave to advance.',
  ],
  multi: [
    'Each player scores their own colour on the wall.',
    'Red hurts both — climb sharp together.',
    'Clear your targets to progress through levels.',
  ],
  group: [
    'A fixed tournament set runs in order — no level pick.',
    'Play through levels 1, 2, 3… as a group session.',
    'Clear each stage to keep climbing.',
  ],
}

export function playlistModeKey(playMode) {
  if (playMode === 'multi') return 'multi'
  if (playMode === 'group') return 'group'
  return 'single'
}

/** Entries for a play mode from API payload { single, multi, group }. */
export function entriesForPlayMode(playlists, playMode) {
  if (!playlists) return []
  const key = playlistModeKey(playMode)
  return playlists[key] || []
}

export function idsForPlayMode(playlists, playMode) {
  return entriesForPlayMode(playlists, playMode).map((e) => e.id)
}

/** Map backend level stem → UI number (1-based) within the full mode playlist. */
export function displayLevelNumber(playMode, levelId, playlists) {
  const stem = String(levelId ?? '')
    .replace(/\.(led|ledb)$/i, '')
    .trim()
  if (!stem || stem === 'auto') return null
  const ids = idsForPlayMode(playlists, playMode)
  const idx = ids.findIndex((id) => id === stem)
  if (idx >= 0) return idx + 1
  return null
}

export function formatLevelLabel(playMode, levelId, playlists) {
  const n = displayLevelNumber(playMode, levelId, playlists)
  if (n != null) return String(n)
  return String(levelId ?? '—')
}

export function firstPlaylistId(playlists, playMode) {
  const entries = entriesForPlayMode(playlists, playMode)
  return entries.length ? entries[0].id : null
}
