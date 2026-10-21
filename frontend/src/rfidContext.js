import { RFID_API_URL } from './config'

/** Map kiosk playMode to Step 0 play_mode contract values. */
export function playModeToSaveMode(playMode) {
  if (playMode === 'multi') return 'team_battle'
  if (playMode === 'group') return 'tournament'
  return 'quick_play'
}

/** Snapshot fields from /validate to keep on game config. */
export function rfidContextFromValidate(data) {
  if (!data || !data.valid) return null
  return {
    session_id: data.session_id ?? null,
    group_id: data.group_id ?? null,
    roster_size: data.roster_size ?? null,
    roster_player_ids: data.roster_player_ids ?? null,
  }
}

const VALIDATE_TIMEOUT_MS = 2000

/** Best-effort refresh before save; never throws; falls back to login-time context. */
export async function refreshRfidContext(cardId, fallback = null) {
  const id = String(cardId ?? '').trim()
  if (!id) return fallback
  const base = fallback && typeof fallback === 'object' ? { ...fallback } : {
    session_id: null,
    group_id: null,
    roster_size: null,
    roster_player_ids: null,
  }
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), VALIDATE_TIMEOUT_MS)
    const res = await fetch(
      `${RFID_API_URL}/validate?card_id=${encodeURIComponent(id)}`,
      { signal: ctrl.signal },
    )
    clearTimeout(timer)
    const data = await res.json()
    if (!data?.valid) return base
    return {
      session_id: data.session_id ?? base.session_id ?? null,
      group_id: data.group_id ?? base.group_id ?? null,
      roster_size: data.roster_size ?? base.roster_size ?? null,
      roster_player_ids: data.roster_player_ids ?? base.roster_player_ids ?? null,
    }
  } catch {
    return base
  }
}

/** Build optional save-score RFID fields for slot 1 and (Team Battle) slot 2. */
export function saveScoreRfidFields(slot1, slot2) {
  const out = {
    session_id: slot1?.session_id ?? null,
    group_id: slot1?.group_id ?? null,
    roster_size_at_play: slot1?.roster_size ?? null,
    roster_player_ids: slot1?.roster_player_ids ?? null,
  }
  if (slot2) {
    out.session_id2 = slot2.session_id ?? null
    out.group_id2 = slot2.group_id ?? null
    out.roster_size_at_play2 = slot2.roster_size ?? null
    out.roster_player_ids2 = slot2.roster_player_ids ?? null
  }
  return out
}
