/** Trim scanner noise from card id input. */
export function normalizeCardId(raw) {
  return String(raw ?? '').replace(/[\r\n]/g, '').trim()
}

/** Prefer /validate card_id when present; else trimmed scan value. */
export function canonicalCardId(validateData, scannedFallback = '') {
  const fromApi = validateData?.card_id ?? validateData?.cardId
  if (fromApi != null && String(fromApi).trim()) {
    return normalizeCardId(fromApi)
  }
  return normalizeCardId(scannedFallback)
}

export function cardsEqualCaseInsensitive(a, b) {
  const left = normalizeCardId(a).toLowerCase()
  const right = normalizeCardId(b).toLowerCase()
  return Boolean(left && right && left === right)
}

/**
 * Team Battle: two distinct group leader cards.
 * Returns user-facing error string, or null if OK.
 */
export function teamBattleSecondCardError(p1Info, p2Info) {
  if (!p1Info?.valid || !p2Info?.valid) return null

  const c1 = canonicalCardId(p1Info)
  const c2 = canonicalCardId(p2Info)
  if (cardsEqualCaseInsensitive(c1, c2)) {
    return 'Team Battle requires two different group leader cards'
  }

  const g1 = p1Info.group_id
  const g2 = p2Info.group_id
  if (g1 != null && g2 != null && g1 === g2) {
    return 'Team Battle requires cards from two different groups'
  }

  return null
}
