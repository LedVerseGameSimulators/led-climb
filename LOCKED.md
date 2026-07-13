# Locked baseline — simulator-ready headless stack

**Tag:** `sim-ready-2026-06-07`  
**Date:** 2026-06-07

This tag marks the **Climb** headless migration at simulator parity. Session marathon, overlap priority, 2P DK scoring, square 6×33 sim. Hardware serial I/O was **not yet** integrated at this tag.

> **Update (2026-06-30):** Hardware integration landed in commit
> `338392a` ("Hardware integration: fix decompiler slice bugs + add
> USE_SERIAL_HD mode") — `_hw_init()`, `USE_SERIAL_HD` env-var mode, and
> the per-frame `led.led_control` draw calls are real and were validated
> on real physical LED floor hardware as of that commit. Since then,
> this session's marathon loop / 5-heart lives / RFID login / credits /
> settings / true-2P rework has landed on top, and **none of it has been
> re-validated on real hardware yet**. See
> [`HARDWARE_VALIDATION.md`](./HARDWARE_VALIDATION.md) for the current
> validation status and the onsite re-validation checklist.

| Service | Port |
|---------|------|
| UI | 5174 |
| API | 8001 |
| ws_bridge | 8766 |

**Canonical doc:** [`docs/CLIMB_DEVELOPMENT_PLAYBOOK.md`](./CLIMB_DEVELOPMENT_PLAYBOOK.md)

**Checkout this baseline:**
```bash
git checkout sim-ready-2026-06-07
```
