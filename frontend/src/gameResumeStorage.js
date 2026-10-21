const STORAGE_PREFIX = 'led-climb:game-resume:'

export function resumeStorageKey(gameId) {
  return `${STORAGE_PREFIX}${gameId}`
}

/** Fields to restore after /active-game reload (client-only). */
export function buildResumeSnapshot(gameId, config) {
  if (!gameId) return null
  return {
    game_id: gameId,
    playMode: config.playMode,
    playerCount: config.playerCount,
    cardId: config.cardId,
    cardId2: config.cardId2,
    rfidContext: config.rfidContext,
    rfidContext2: config.rfidContext2,
    playerName: config.playerName,
    playerName2: config.playerName2,
    minutesRemaining: config.minutesRemaining,
    minutesRemaining2: config.minutesRemaining2,
  }
}

/** Merge snapshot into config only when game_id matches resumeGameId. */
export function mergeResumeSnapshot(prevConfig, resumeGameId, snapshot) {
  if (!resumeGameId || !snapshot || snapshot.game_id !== resumeGameId) {
    return prevConfig
  }
  return {
    ...prevConfig,
    playMode: snapshot.playMode ?? prevConfig.playMode,
    playerCount: snapshot.playerCount ?? prevConfig.playerCount,
    cardId: snapshot.cardId ?? prevConfig.cardId,
    cardId2: snapshot.cardId2 ?? prevConfig.cardId2,
    rfidContext: snapshot.rfidContext ?? prevConfig.rfidContext,
    rfidContext2: snapshot.rfidContext2 ?? prevConfig.rfidContext2,
    playerName: snapshot.playerName ?? prevConfig.playerName,
    playerName2: snapshot.playerName2 ?? prevConfig.playerName2,
    minutesRemaining: snapshot.minutesRemaining ?? prevConfig.minutesRemaining,
    minutesRemaining2: snapshot.minutesRemaining2 ?? prevConfig.minutesRemaining2,
  }
}

export function saveResumeSnapshot(storage, gameId, config) {
  const snap = buildResumeSnapshot(gameId, config)
  if (!snap || !storage) return
  try {
    storage.setItem(resumeStorageKey(gameId), JSON.stringify(snap))
  } catch {
    /* quota / private mode */
  }
}

export function loadResumeSnapshot(storage, gameId) {
  if (!gameId || !storage) return null
  try {
    const raw = storage.getItem(resumeStorageKey(gameId))
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function clearResumeSnapshot(storage, gameId) {
  if (!gameId || !storage) return
  try {
    storage.removeItem(resumeStorageKey(gameId))
  } catch {
    /* ignore */
  }
}
