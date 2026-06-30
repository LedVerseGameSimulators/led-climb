# On-Site Hardware Integration Guide — LED Climb

> **For Cursor agent:** Follow every step in order. Do not skip verification steps. Do not touch the RFID server, SQL server, or any service already running on this PC.

---

## Game Config

| Key | Value |
|-----|-------|
| Game | LED Climb |
| Grid | 6 rows × 33 cols |
| COM ports | 3 (read from shelve — see Step 4) |
| Layout type | 5 (read from shelve to confirm) |
| Display var | `led_display` |
| Zip extract dir | `C:\activerse\led-climb` |
| Python version | 3.10 or 3.11 |
| Server port | 8002 (adjust if already assigned differently) |

---

## Step 1 — Extract the zip

```
C:\activerse\led-climb\
  api\
  games\
  requirements.txt
  ...
```

Open **Command Prompt as Administrator**. Use for all remaining steps.

---

## Step 2 — Check Python

```cmd
python --version
pip --version
```

**If missing:** install Python 3.11 (winget or python.org, add to PATH). See HOOPS_ONSITE.md Step 2.

---

## Step 3 — Install dependencies

```cmd
cd C:\activerse\led-climb
pip install -r requirements.txt
```

---

## Step 4 — Verify shelve

```cmd
cd C:\activerse\led-climb\games
python -c "import shelve; db=shelve.open('setting/led_parameter',flag='r'); [print(k,'=',db[k]) for k in db.keys()]; db.close()"
```

**Expected:**
- `list_com_info` — 3 COM port entries
- `led_layout_type` — 5
- `value_high` — 6
- `value_width` — 33

---

## Step 5 — Verify COM ports

```cmd
python -c "import serial.tools.list_ports; [print(p) for p in serial.tools.list_ports.comports()]"
```

All 3 COM ports from shelve must be present.

---

## Step 6 — Run hardware diagnostic

```cmd
cd C:\activerse\led-climb\games
python test_hardware.py
```

**Expected:**
1. `All COM ports opened OK` (3 ports)
2. Full 6×33 floor lights **green** for 3s
3. Step on tiles → `PRESS detected: row=X col=Y`
4. `Floor cleared. Done.`

Climb floor is wide (33 cols = full climbing wall width). All sections should light uniformly.

---

## Step 7 — Start game server

```cmd
cd C:\activerse\led-climb
set USE_SERIAL_HD=1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8002
```

**Expected log:**
```
Hardware ready: 3 port(s), 6×33, layout=5
```

**PowerShell:**
```powershell
$env:USE_SERIAL_HD="1"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8002
```

---

## Step 8 — Verify sim + hardware

1. Browser → `http://localhost:8002`
2. Start a Climb game
3. Climbing tiles light on physical floor per game state
4. Stepping on tiles registers input

---

## What NOT to touch

- RFID server / SQL server — leave untouched
- `games/setting/led_parameter` shelve — do not modify

---

## Troubleshooting

**Only part of the floor lights:** one COM port controls one section. If 2/3 ports open OK, 2/3 of the floor lights. Trace the failing section's cable.

**Port 8002 in use:** `netstat -ano | findstr :8002` → `taskkill /PID <pid> /F`
