# Climb — MP Phase A + B test levels

**Scope:** Team Battle (`.ledb`) only. Quick Play / Tournament unchanged.

---

## Level files (`games/source/---/`)

| Level | Use |
|-------|-----|
| **DK01.ledb** | Primary smoke — P1 blue + P2 orange + red hazards; staggered waves |
| **DK02.ledb** | Wave timing / auto-jump after either-player clear |
| **DK04.ledb** | Longer stagger — confirm discard does not wipe future waves |
| **DK05.ledb** | Mixed hazard + scoreable timing |
| **DK06.ledb** | Additional wave cadence |
| **DK07.ledb** | Green-mask edge case (masked goals) |
| **DK08.ledb** | Later DK pack regression |
| **DK09.ledb** | Later DK pack regression |
| **DK10.ledb** | End-of-series smoke |

1P regression: any `.led` tier file under `games/source/` (e.g. `games/source/-/001.led`).

---

## Start Team Battle (simulator)

```bash
cd led-climb
./scripts/start-dev.sh
# FE: Mode → Team Battle → pick DK01 → Login → Play
# API: POST /start-game with player_count=2 and level DK01
```

---

## Phase A + B verify checklist

### Phase A (hazard + HUD)

- [ ] `multiplayer: true` in `/game-state` for `.ledb` sessions
- [ ] Plain red hit → life down, `score` / `score2` unchanged
- [ ] DEDUCT hit → life down, scores unchanged (when present)
- [ ] HUD shows blue P1 + orange P2 goal swatches

### Phase B (either-player advance)

- [ ] Clear P1 wave while P2 tiles remain → wave advances without waiting
- [ ] P2 leftovers for **current time window only** are discarded (future waves intact)
- [ ] P1-only wave (P2 never lit) → no false advance from empty P2
- [ ] 1P `.led` session → unchanged (both-side empty gate still applies)

---

## Pytest

```bash
cd led-climb
python -m pytest tests/test_mp_phase_a.py tests/test_mp_phase_b.py -q
```

Expected: all tests green.
