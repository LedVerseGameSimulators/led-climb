/**
 * Placeholder playlists for Climb FE redesign.
 * Real 20-level lists will replace these when the team delivers them.
 * Backend still receives real file ids (stems); UI may show 1..N.
 */

/** Quick Play (1P) — 20 placeholders from casual (A*) + medium (B*). */
export const QUICK_PLAY_LEVELS = [
  'A001', 'A002', 'A003', 'A004', 'A005', 'A006', 'A007', 'A008', 'A009', 'A010',
  'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B09', 'B10',
]

/**
 * Team Battle (2P) — DK01–DK10 placeholders (+ medium B* pad to 20).
 * Note: source/--- is missing DK03 on disk; list still includes it as placeholder.
 */
export const TEAM_BATTLE_LEVELS = [
  'DK01', 'DK02', 'DK03', 'DK04', 'DK05', 'DK06', 'DK07', 'DK08', 'DK09', 'DK10',
  'B11', 'B12', 'B13', 'B14', 'B15', 'B16', 'B17', 'B18', 'B19', 'B20',
]

/**
 * Tournament playlist order (source_group/-- B01…B10).
 */
export const TOURNAMENT_LEVEL_ORDER = [
  'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B09', 'B10',
]

export const HOW_TO = {
  single:
    'Climb glowing holds that match the goal. Avoid red hazards. Clear each wave to advance.',
  multi:
    'Each player scores their own colour. Watch the wall — red hurts both. Clear targets to progress.',
  group:
    'A fixed set of levels runs in order. No level pick — just play through 1, 2, 3… as a group session.',
}

export function playlistForMode(playMode) {
  if (playMode === 'multi') return TEAM_BATTLE_LEVELS
  if (playMode === 'group') return TOURNAMENT_LEVEL_ORDER
  return QUICK_PLAY_LEVELS
}

/** Map backend level stem → UI number (1-based) within the active playlist. */
export function displayLevelNumber(playMode, levelId) {
  const stem = String(levelId ?? '')
    .replace(/\.(led|ledb)$/i, '')
    .trim()
  if (!stem || stem === 'auto') return null
  const list = playlistForMode(playMode)
  const idx = list.findIndex(
    (id) => id === stem || stem.startsWith(id) || id.startsWith(stem)
  )
  if (idx >= 0) return idx + 1
  // Fallback: numeric stems display as themselves when in tournament-style lists
  if (/^\d+$/.test(stem)) return Number(stem)
  return null
}

export function formatLevelLabel(playMode, levelId) {
  const n = displayLevelNumber(playMode, levelId)
  if (n != null) return String(n)
  return String(levelId ?? '—')
}
