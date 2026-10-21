import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  cardsEqualCaseInsensitive,
  canonicalCardId,
  teamBattleSecondCardError,
} from './loginValidation.js'
import { buildResumeSnapshot, mergeResumeSnapshot } from './gameResumeStorage.js'

describe('loginValidation', () => {
  it('compares card ids case-insensitively', () => {
    assert.equal(cardsEqualCaseInsensitive('AbC', 'abc'), true)
    assert.equal(cardsEqualCaseInsensitive('AbC', 'xyz'), false)
  })

  it('prefers validate card_id over scan input', () => {
    assert.equal(canonicalCardId({ card_id: ' RFID-1 ' }, 'scan'), 'RFID-1')
  })

  it('rejects same group in team battle', () => {
    const err = teamBattleSecondCardError(
      { valid: true, card_id: 'A', group_id: 5 },
      { valid: true, card_id: 'B', group_id: 5 },
    )
    assert.match(err, /different groups/)
  })

  it('rejects same card case-insensitively', () => {
    const err = teamBattleSecondCardError(
      { valid: true, card_id: 'CARD1', group_id: 1 },
      { valid: true, card_id: 'card1', group_id: 2 },
    )
    assert.match(err, /different.*card/)
  })
})

describe('gameResumeStorage', () => {
  it('merges snapshot only when game_id matches', () => {
    const prev = { playMode: 'single', cardId: 'x', level: 'A1' }
    const snap = buildResumeSnapshot('g1', {
      playMode: 'multi',
      playerCount: 2,
      cardId: 'c1',
      cardId2: 'c2',
      rfidContext: { group_id: 1 },
      rfidContext2: null,
      playerName: 'P1',
      playerName2: 'P2',
      minutesRemaining: 10,
      minutesRemaining2: 9,
    })
    const merged = mergeResumeSnapshot(prev, 'g1', snap)
    assert.equal(merged.playMode, 'multi')
    assert.equal(merged.cardId2, 'c2')
    assert.equal(mergeResumeSnapshot(prev, 'other', snap).playMode, 'single')
  })
})
