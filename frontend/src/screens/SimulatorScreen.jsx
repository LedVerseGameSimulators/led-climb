import { useEffect, useState, useRef } from 'react'

import { API_URL, WS_BRIDGE_URL } from '../config'

function countdownDisplay(state) {
  if (state?.phase !== 'countdown') return null
  const step = state.phase_step
  if (step === 0) return 'GO!'
  return step != null ? String(step) : null
}

function isInputBlocked(state) {
  if (!state) return true
  if (state.accepting_input === false) return true
  return state.phase && state.phase !== 'playing'
}

function showPhaseOverlay(state) {
  return ['countdown', 'level_clear', 'level_fail'].includes(state?.phase)
}

function HeartRow({ life, maxLife }) {
  const total = Math.max(1, Math.min(10, Math.round(maxLife) || 5))
  const filled = Math.max(0, Math.min(total, Math.round(life)))
  return (
    <div className="hud-hearts" aria-label={`${filled} of ${total} lives`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`hud-heart ${i < filled ? 'filled' : 'empty'}`}>♥</span>
      ))}
    </div>
  )
}

export default function SimulatorScreen({ config, onGameEnd }) {
  const [gameState, setGameState] = useState(null)
  const [gameId, setGameId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [phaseReady, setPhaseReady] = useState(false)
  const [error, setError] = useState(null)
  const [stopping, setStopping] = useState(false)
  const [showSim, setShowSim] = useState(false)
  const iframeRef = useRef(null)
  const gameIdRef = useRef(null)
  const endedRef = useRef(false)
  const stateRef = useRef(null)
  const audioCtxRef = useRef(null)
  const prevLifeRef = useRef(null)
  const lastInputEventSeqRef = useRef(null)
  const startedRef = useRef(false)

  const beep = (freq, durMs, type = 'sine', gain = 0.15) => {
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)()
      }
      const ctx = audioCtxRef.current
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})
      const osc = ctx.createOscillator()
      const g = ctx.createGain()
      osc.type = type
      osc.frequency.value = freq
      g.gain.value = gain
      osc.connect(g); g.connect(ctx.destination)
      osc.start()
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durMs / 1000)
      osc.stop(ctx.currentTime + durMs / 1000)
    } catch (e) { /* audio not available */ }
  }
  const playPress = () => {
    if (stateRef.current?.bgm_active) return
    beep(660, 70, 'triangle', 0.12)
  }
  const playHurt = () => {
    if (stateRef.current?.bgm_active) return
    beep(140, 220, 'sawtooth', 0.22)
  }

  const applyState = (st) => {
    if (!st || typeof st !== 'object') return
    setGameState(st)
    stateRef.current = st
    if (st.phase) setPhaseReady(true)
  }

  // Start game on mount (or resume an already-running game after reload)
  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    if (config.resumeGameId) {
      setGameId(config.resumeGameId)
      gameIdRef.current = config.resumeGameId
      setLoading(false)
      return
    }
    const startGame = async () => {
      try {
        const response = await fetch(`${API_URL}/start-game`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            card_id: config.cardId,
            level: config.playMode === 'group' ? (config.level || 'auto') : (config.level || 'A001'),
            difficulty: config.difficulty || 'normal',
            ...(config.playMode === 'group' ? { mode: 'group' } : {}),
          })
        })
        const data = await response.json()
        if (data.success) {
          setGameId(data.game_id)
          gameIdRef.current = data.game_id
          setLoading(false)
        } else {
          setError(data.error || 'Failed to start game')
        }
      } catch (err) {
        setError(err.message)
      }
    }
    startGame()
  }, [config])

  // Soft boot: show simulator after gameId; wait for first phase poll or 2 s timeout
  useEffect(() => {
    if (!gameId) return undefined
    const timeout = window.setTimeout(() => setPhaseReady(true), 2000)
    return () => window.clearTimeout(timeout)
  }, [gameId])

  // Poll game-state for phase overlay sync (~100 ms)
  useEffect(() => {
    if (!gameId) return undefined
    const pollState = async () => {
      try {
        const response = await fetch(`${API_URL}/game-state/${gameId}`)
        const data = await response.json()
        if (data.success) {
          applyState(data.state)
          if (data.state?.game_over && !endedRef.current) endGame('timeout')
        }
      } catch (err) {
        console.error('Poll error:', err)
      }
    }
    pollState()
    const interval = window.setInterval(pollState, 100)
    return () => window.clearInterval(interval)
  }, [gameId])

  // End the game: stop on backend, record, route to result panel
  const endGame = async (reason) => {
    if (endedRef.current) return
    endedRef.current = true
    setStopping(true)
    const id = gameIdRef.current
    const st = stateRef.current || {}
    const finalScore = st.score || 0
    const finalScore2 = st.score2 || 0
    const finalMultiplayer = st.multiplayer || false
    const finalTime = st.time_elapsed || 0
    const finalLife = st.life ?? 0
    const finalReason = st.game_over_reason === 'out_of_life'
      ? 'out_of_life' : (reason || 'stopped')
    try {
      await fetch(`${API_URL}/save-score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          card_id: config.cardId,
          card_id2: config.cardId2 || null,
          level: config.level,
          end_level: st.current_level ?? config.level,
          score: finalScore,
          score2: finalScore2,
          final_score: st.final_score ?? finalScore,
          final_score2: st.final_score2 ?? finalScore2,
          multiplayer: finalMultiplayer,
          life: finalLife,
          lives_start: st.max_life ?? 0,
          result: st.result ?? null,
          time_used: finalTime,
          levels_cleared: st.levels_cleared ?? 0,
          difficulty: config.difficulty ?? '',
          started_at: st.started_at ?? ''
        })
      })
      await fetch(`${API_URL}/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_id: config.cardId, game_id: id })
      })
    } catch (err) {
      console.error('Stop/save error:', err)
    }
    onGameEnd({
      score: finalScore,
      score2: finalScore2,
      multiplayer: finalMultiplayer,
      time_elapsed: finalTime,
      life: finalLife,
      level: config.level,
      game: config.game,
      difficulty: config.difficulty,
      reason: finalReason
    })
  }

  // Bridge: input-event audio cues (press edges)
  useEffect(() => {
    if (!gameId) return undefined
    const bridgeOrigin = new URL(WS_BRIDGE_URL).origin
    const onBridgeState = (event) => {
      if (event.origin !== bridgeOrigin) return
      const message = event.data
      if (message?.type !== 'led-climb-state') return
      if (message.gameId && message.gameId !== gameId) return
      const st = message.state
      if (!st || typeof st !== 'object') return

      const events = Array.isArray(st.input_events) ? st.input_events : []
      const newestSeq = events.reduce(
        (latest, inputEvent) => Math.max(latest, Number(inputEvent.seq) || 0),
        0,
      )
      if (lastInputEventSeqRef.current === null) {
        lastInputEventSeqRef.current = newestSeq
      } else {
        const unseen = events.filter(
          inputEvent => Number(inputEvent.seq) > lastInputEventSeqRef.current,
        )
        unseen.forEach((inputEvent, index) => {
          if (inputEvent.type === 'press') {
            window.setTimeout(playPress, Math.min(index, 10) * 30)
          }
        })
        if (newestSeq > lastInputEventSeqRef.current) {
          lastInputEventSeqRef.current = newestSeq
        }
      }

      if (prevLifeRef.current !== null && st.life < prevLifeRef.current) playHurt()
      prevLifeRef.current = st.life
      applyState(st)
      if (st.game_over && !endedRef.current) endGame('timeout')
    }
    window.addEventListener('message', onBridgeState)
    return () => window.removeEventListener('message', onBridgeState)
  }, [gameId])

  if (loading) {
    return (
      <div className="screen">
        <div className="card">
          <h2>Starting Game...</h2>
          <p style={{ textAlign: 'center', marginTop: '20px' }}>
            {config.game.toUpperCase()} - Level {config.level} ({config.difficulty})
          </p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="screen">
        <div className="card">
          <h2>Error</h2>
          <p style={{ color: 'var(--color-error)', marginTop: '20px' }}>{error}</p>
        </div>
      </div>
    )
  }

  const timeLeft = gameState?.time_left != null ? gameState.time_left : 300
  const phase = gameState?.phase || 'playing'
  const inputLocked = isInputBlocked(gameState)
  const countdownLabel = countdownDisplay(gameState)
  const overlayVisible = showPhaseOverlay(gameState)
  const life = gameState?.display_lives ?? gameState?.life ?? gameState?.max_life ?? 0
  const maxLife = gameState?.display_max ?? gameState?.max_life ?? 5
  const isOver = gameState?.game_over
  const isMulti = !!(gameState?.multiplayer || config.playerCount === 2)
  const p1Name = config.playerName || 'Player 1'
  const p2Name = config.playerName2 || 'Player 2'
  const currentLevel = gameState?.current_level ?? config.level

  return (
    <div className="simulator-container">
      <div className="simulator-header">
        <div>
          <h2 style={{ margin: 0 }}>
            {config.game.toUpperCase()} - Level {currentLevel}
          </h2>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {config.difficulty?.toUpperCase()}
            {config.playMode === 'group' ? ' · GROUP' : ''}
          </span>
        </div>

        <div className="game-info">
          <button
            type="button"
            className="view-toggle-btn"
            onClick={() => setShowSim(v => !v)}
          >
            {showSim ? 'Show game board' : 'Show simulator'}
          </button>
          <button
            type="button"
            className="stop-game-btn"
            onClick={() => endGame('stopped')}
            disabled={stopping}
          >
            {stopping ? 'Stopping...' : '■ Stop Game'}
          </button>
        </div>
      </div>

      <div className="simulator-stage">
        <iframe
          ref={iframeRef}
          className={`simulator-iframe ${showSim ? '' : 'simulator-iframe--hidden'}`}
          src={`${WS_BRIDGE_URL}?game_id=${encodeURIComponent(gameId)}`}
          title="Game Simulator"
        />

        {!phaseReady && (
          <div className="boot-banner" aria-live="polite">
            <p className="boot-banner-title">Starting Game…</p>
            <p className="boot-banner-sub">
              {config.game.toUpperCase()} · Level {config.level}
            </p>
          </div>
        )}

        {overlayVisible && !isOver && phase === 'countdown' && countdownLabel && (
          <div className="phase-overlay countdown-overlay" aria-live="polite">
            <div className={`countdown-num${gameState?.phase_step === 0 ? ' go' : ''}`}>
              {countdownLabel}
            </div>
            <p className="countdown-meta">Level {currentLevel}</p>
          </div>
        )}

        {overlayVisible && !isOver && phase === 'level_clear' && (
          <div className="phase-overlay level-clear-overlay" aria-live="polite">
            Level clear!
          </div>
        )}

        {overlayVisible && !isOver && phase === 'level_fail' && (
          <div className="phase-overlay level-fail-overlay" aria-live="polite">
            Try again!
          </div>
        )}

        {!showSim && (
          <div className={`play-hud${inputLocked ? ' play-hud--locked' : ''}`}>
            <div className="hud-board">
              <div className="hud-meta">
                <span className="hud-level">Level {currentLevel}</span>
                <span className="hud-diff">{config.difficulty?.toUpperCase()}</span>
                <span className={`hud-status ${isOver ? 'ended' : phase === 'playing' ? 'playing' : 'transition'}`}>
                  {isOver ? '● ENDED' : phase === 'playing' ? '● PLAYING' : `● ${phase.toUpperCase()}`}
                </span>
              </div>

              <div className={`hud-players ${isMulti ? 'multi' : 'solo'}`}>
                <div className="hud-player">
                  <div className="hud-player-name">{p1Name}</div>
                  {config.minutesRemaining != null && (
                    <div className="hud-session-mins">
                      {Math.round(config.minutesRemaining)} min left
                    </div>
                  )}
                  <div className="hud-score">{gameState?.score ?? 0}</div>
                  <div className="hud-score-label">{isMulti ? 'P1 Score' : 'Score'}</div>
                </div>
                {isMulti && (
                  <div className="hud-player hud-player--p2">
                    <div className="hud-player-name">{p2Name}</div>
                    {config.minutesRemaining2 != null && (
                      <div className="hud-session-mins">
                        {Math.round(config.minutesRemaining2)} min left
                      </div>
                    )}
                    <div className="hud-score">{gameState?.score2 ?? 0}</div>
                    <div className="hud-score-label">P2 Score</div>
                  </div>
                )}
              </div>

              <div className="hud-stats">
                <div className="hud-stat">
                  <span
                    className="hud-stat-value"
                    style={{ color: timeLeft < 30 ? 'var(--color-error)' : 'var(--text-primary)' }}
                  >
                    {Math.max(0, timeLeft).toFixed(0)}s
                  </span>
                  <span className="hud-stat-label">Time Left</span>
                </div>
                <div className="hud-stat">
                  <HeartRow life={life} maxLife={maxLife} />
                  <span className="hud-stat-label">Lives {life}/{maxLife}</span>
                </div>
              </div>

              <button
                type="button"
                className="stop-game-btn stop-game-btn--lg"
                onClick={() => endGame('stopped')}
                disabled={stopping}
              >
                {stopping ? 'Stopping...' : '■ Stop Game'}
              </button>
            </div>
          </div>
        )}
      </div>

      {(config.playerName || config.playerName2) && (
        <div className="sim-player-bar">
          {config.playerName && (
            <span>
              {config.playerName}
              {config.minutesRemaining != null
                ? ` — ${Math.round(config.minutesRemaining)} min left`
                : ''}
            </span>
          )}
          {config.playerName2 && (
            <span className="sim-player-bar-p2">
              {config.playerName2}
              {config.minutesRemaining2 != null
                ? ` — ${Math.round(config.minutesRemaining2)} min left`
                : ''}
            </span>
          )}
        </div>
      )}

      {showSim && inputLocked && !isOver && (
        <div className="sim-input-lock" aria-hidden="true">
          Input paused ({phase})
        </div>
      )}

      {showSim && (
        <div className="sim-debug-footer">
          Game ID: {gameId} | P1: {config.cardId}
          {config.cardId2 ? ` | P2: ${config.cardId2}` : ''}
        </div>
      )}
    </div>
  )
}
