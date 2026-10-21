# DartSense

Automatic steel-tip dart scoring with **three USB cameras**. A local computer-vision engine
finds every dart, works out where it hit the board and scores it; a game engine runs the
match (501, Cricket, …) and a web interface shows everything in any browser — on the PC, a
phone, a tablet or a TV on the same network. The interface is in Polish.

> **Accuracy status.** Accuracy is measured systematically on a synthetic 3-camera simulator
> (`docs/benchmarks/`, latest: 97.5 % correct scores, 100 % of darts detected, 0 false
> darts, mean position error 0.76 mm). On a real board (Winmau Blade 6, three 720p webcams)
> the darts thrown in the first tests were all scored correctly, but no systematic real-world
> measurement exists yet — see [Measuring accuracy](#measuring-real-world-accuracy).

---

## Contents

1. [What you need](#1-what-you-need)
2. [Installation (Windows)](#2-installation-windows)
3. [Starting the app](#3-starting-the-app)
4. [Try it without cameras (simulator)](#4-try-it-without-cameras-simulator)
5. [Setting up the board and cameras](#5-setting-up-the-board-and-cameras)
6. [First-time setup in the app](#6-first-time-setup-in-the-app)
7. [Playing](#7-playing)
8. [Using phones, tablets and TVs](#8-using-phones-tablets-and-tvs)
9. [Configuration](#9-configuration)
10. [Troubleshooting](#10-troubleshooting)
11. [Operator panel (many boards in venues)](#11-operator-panel-many-boards-in-venues)
12. [Development](#12-development)
13. [Project structure](#13-project-structure)
14. [How it works](#14-how-it-works)
15. [Installation on Linux / macOS](#15-installation-on-linux--macos)

---

## 1. What you need

**Software**

| | Version | Where |
|---|---|---|
| Windows | 10 or 11 (Linux works too, see [§15](#15-installation-on-linux--macos)) | |
| Python | **3.10, 3.11 or 3.12** | <https://www.python.org/downloads/> — during installation tick **“Add python.exe to PATH”** |
| Node.js | **20 LTS** or newer | <https://nodejs.org/> |
| Git | any recent | <https://git-scm.com/download/win> |

Check in a new PowerShell window:

```powershell
python --version
node --version
git --version
```

**Hardware**

- A PC with a reasonably modern CPU (no GPU needed). The vision engine uses about one CPU
  core per camera while analysing a throw.
- **Three USB (UVC) webcams**, 1280×720 at 30 fps, that support MJPG (almost all do).
  Identical cameras are fine.
- A regulation dartboard (451 mm, standard number ring), ideally **mounted on the wall**.
- Even lighting on the board — an LED ring around the board is ideal.
- USB ports on **different USB controllers** if possible (e.g. back-panel ports, not all
  three on one cheap hub). Three 720p streams need real bandwidth.

No cameras yet? Everything except real scoring can be tried with the built-in simulator
([§4](#4-try-it-without-cameras-simulator)).

---

## 2. Installation (Windows)

Open **PowerShell** and run:

```powershell
git clone git@github.com:cipsonnek/darts.git dartsense
cd dartsense
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

If you have no SSH key on GitHub, clone over HTTPS instead:
`git clone https://github.com/cipsonnek/darts.git dartsense`.

`setup.ps1` does everything once:

1. checks that Python ≥ 3.10 and Node.js are installed,
2. creates a private Python environment in `.venv\`,
3. installs the Python packages (`pip install -e ".[dev]"`, a few minutes),
4. installs the frontend packages and builds the web interface into `frontend\dist\`.

It ends with **“Setup complete.”** Run it again after pulling a new version from git
(`git pull`) — it is safe to repeat.

---

## 3. Starting the app

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Then open **<http://localhost:8000>** in a browser. Stop the app with **Ctrl+C** in the
PowerShell window.

| Option | Meaning |
|---|---|
| *(none)* | real cameras, interface only on this PC |
| `-Lan` | also reachable from other devices on the network (phone, tablet, TV) — see [§8](#8-using-phones-tablets-and-tvs) |
| `-Simulator` | three simulated cameras instead of real ones — see [§4](#4-try-it-without-cameras-simulator) |

Options can be combined, e.g. `scripts\start.ps1 -Simulator -Lan`.

The same can be started directly (useful for shortcuts or other ports):

```powershell
.venv\Scripts\python.exe -m backend                     # real cameras
.venv\Scripts\python.exe -m backend --simulator         # simulator
.venv\Scripts\python.exe -m backend --host 0.0.0.0      # reachable from the network
.venv\Scripts\python.exe -m backend --port 8080         # another port
```

The interactive API documentation is at <http://localhost:8000/docs>.

---

## 4. Try it without cameras (simulator)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Simulator
```

The simulator renders a realistic board seen by three virtual cameras (a yellow
**SYMULATOR** badge is shown). It has its own database and settings, so it never mixes with
the real board's data.

1. **Kalibracja** → calibrate each camera with **Wykryj automatycznie** → **Zatwierdź
   kalibrację** (or **Narzędzia → Symulator → Autokalibracja wszystkich kamer** for all three
   at once).
2. **Nowa gra** → choose a game and players → **Rozpocznij grę**.
3. **Narzędzia → Symulator**: click on the board picture to throw a dart there, then
   **Wyjmij lotki** to pull them out. You can also simulate a hand in front of the board and
   lighting changes.

---

## 5. Setting up the board and cameras

Good physical setup matters more than any setting.

```
                    20
          cam ●            ● cam          cameras about 120° apart around the board,
             \     ____     /             25–45 cm from the board surface,
              \   /    \   /              looking at the board at 35–60° from its axis
               \ | BULL | /
                  \____/
                    ●
                   cam
```

- **Mount the board on the wall.** A board lying loose moves a few millimetres every time
  darts are pulled out, and the calibration then has to be repeated.
- **Place the three cameras roughly 120° apart** around the board (any rotation is fine —
  e.g. one above the 20, one by the 3, one by the 11). Each camera must see the **whole
  board including the double ring** without anything in the way.
- **Distance and angle:** close enough that the board fills most of the image, at a clear
  angle (35–60°) so the dart shafts are visible sideways. Cameras looking straight at the
  board from the front see darts end-on and work badly.
- **Fix the cameras rigidly.** If a camera is bumped, the app warns you and you recalibrate
  it (one click).
- **Lighting:** bright and even, without hard shadows. An LED ring around the board is best.
  Dim rooms make the webcams noisy.
- **USB:** connect each camera to its own port, preferably directly on the PC.

---

## 6. First-time setup in the app

Open <http://localhost:8000>. The left menu has **Gra** (game) and **System** sections.

### 6.1 Check the cameras — *Kamery*

Every camera shows a live picture and its health (connected, frames per second, brightness,
sharpness).

### 6.2 Choose which camera is which — *Kamery → Wybierz kamery*

Windows numbers identical webcams in an arbitrary order (and may renumber them after
re-plugging). The **Wybierz kamery** dialog shows a live picture from **every USB video
device** on the PC:

- under each picture, click which camera it is: **Camera 1**, **Camera 2** or **Camera 3**;
- if that device is already used by another camera, the two **swap** — together with their
  calibration and position — so nothing has to be recalibrated;
- choosing a device nobody used before marks that camera as *needing calibration*.

Empty/virtual devices (e.g. OBS Virtual Camera) are hidden; **Pokaż puste urządzenia** shows
them.

### 6.3 Tell the app where each camera is — *Kamery → Konfiguruj*

Set **Pozycja (kąt jak na zegarze, °)** — the camera's position around the board as seen
from the front: **0 = above the 20, 90 = right (the 6), 180 = below (the 3),
270 = left (the 11)**. A rough value (±30°) is enough; it helps the automatic calibration
find the board's rotation. You can also rename the cameras here, e.g. *“Camera 1 (by the 10)”*.

Other options in this dialog: resolution, FPS, auto-exposure, exposure/gain, or an RTSP
network camera instead of USB.

### 6.4 Calibrate — *Kalibracja*

With the **board empty** and the lights on, for each camera (camera tabs at the top, then the
**Położenie tarczy** tab):

1. **Wykryj automatycznie** (detect automatically). The app finds the board in the image,
   determines its rotation and computes the exact position of the camera.
2. Check the preview: the drawn wires and numbers must sit **on the real wires and the
   right numbers**.
3. **Zatwierdź kalibrację** (accept).

If the automatic detection picks the wrong rotation (numbers shifted), use
**Wskaż pole 20…** and click once inside the single 20 segment. If the board cannot be found
at all, **Punkty ręcznie…** lets you click at least 4 known points (bull, wire crossings).

The status card shows a quality grade (*dobra / średnia / słaba* — good / fair / poor) with
the measured edge alignment in pixels. **Optional, recommended:** the **Obiektyw** (lens)
tab calibrates each camera's lens with a printed ChArUco pattern (link on that page; print
at 100 % scale on stiff card): **Rozpocznij sesję**, hold the pattern in 15–25 different
positions and angles pressing **Zrób ujęcie** each time, then **Oblicz** and **Zatwierdź**, and
afterwards repeat the board calibration for that camera. This improves accuracy at the edge
of the image and the grade.

**Sprawdź kalibrację teraz** checks whether cameras or the board moved. The app also checks
this by itself every 30 s and warns on the Kalibracja page — then simply repeat
*Wykryj automatycznie → Zatwierdź kalibrację* for that camera.

### 6.5 Players — *Gracze*

Add the players (name and colour). Each player gets their own statistics.

---

## 7. Playing

1. **Nowa gra** (or a tile on the home screen **Graj**): choose the game, its rules and the
   players (click players in throwing order) → **Rozpocznij grę**.
2. **Throw.** A dart is scored about half a second after it stops moving. The board picture
   shows where it landed; the score panel updates automatically.
3. **After three darts** the screen says **“Wyjmij lotki z tarczy”**: pull the darts out.
   As soon as the board is empty, the next player's turn begins. Darts that move while being
   pulled out are **not** scored.
4. **Dalej** (next) ends the turn manually — e.g. when a dart bounced out, or the cameras
   missed the takeout.

**Corrections**

- **Wrong value?** Click the dart on the game screen and choose the right one (or *To nie
  była lotka* to delete it). Totals, checkouts and statistics are recomputed.
- **Cofnij** (undo) removes the last dart.
- **Wpisz** enters a dart by hand (e.g. a dart the cameras did not see).

Darts the system is not sure about are scored immediately but shown in orange (uncertain) so
you can check them. To be asked about each uncertain dart instead, set
`vision.scoring.auto_accept: false` ([§9](#9-configuration)).

**Games:** X01 (301/501/701/901, single/double/master in & out, legs and sets), Cricket
(incl. cut-throat), Around the Clock (Dookoła tarczy), Shanghai, Bob's 27.

**Without a running game** detected darts are shown on the board but not counted
(free throwing).

**Other pages**

- **Statystyki** — averages, first-9 average, checkout rate, 180s, triples/doubles hit rate,
  Cricket MPR, heatmap of hits.
- **Tryb TV** — a large scoreboard for a TV or projector (F = full screen).
- **Detekcja** — live view of what the vision engine sees and decides (diagnostics).
  **Tarcza pusta → reset** tells the app the board is empty right now; use it only when no
  darts are in the board.
- **Ustawienia** — theme, colours, board style, screen layout, admin token.
- **Narzędzia** — simulator, recordings, benchmark, logs, events, system information.

---

## 8. Using phones, tablets and TVs

Start with `-Lan`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Lan
```

Find the PC's address with `ipconfig` (e.g. `192.168.1.20`) and open
`http://192.168.1.20:8000` on the other device. Windows asks once whether Python may accept
network connections — allow it for **private networks**.

**Admin token.** From other devices, everyday use (playing, scoring, corrections) works
freely, but settings that can break the setup (calibration, cameras, deleting data) need the
**admin token**. It is generated on the first start and stored in `data\admin_token.txt` on
the PC. Enter it once on the other device under **Ustawienia → Token administratora**. On
the PC itself no token is needed.

---

## 9. Configuration

Settings are layered; later layers win:

| File | Purpose | In git? |
|---|---|---|
| `configs/default.yaml` | all defaults, documented | yes |
| `configs/local.yaml` | **this PC only**: camera numbers, port, … (create it yourself) | no |
| `configs/simulator.yaml` / `central.yaml` | simulator / operator server mode | yes |
| `data/runtime.yaml` | changes made **in the web interface** (`runtime-simulator.yaml` in simulator mode) | no |

Example `configs/local.yaml`:

```yaml
vision:
  cameras:
    - id: cam1
      name: Camera 1 (by the 20)
      source: {type: opencv, device: 0, api: dshow, fourcc: MJPG}
      width: 1280
      height: 720
      fps: 30
      auto_exposure: true
      mount: {azimuth_deg: 0, description: "by the 20"}
    - id: cam2
      name: Camera 2 (by the 6)
      source: {type: opencv, device: 1, api: dshow, fourcc: MJPG}
      width: 1280
      height: 720
      fps: 30
      auto_exposure: true
      mount: {azimuth_deg: 120, description: "by the 6"}
    - id: cam3
      name: Camera 3 (by the 11)
      source: {type: opencv, device: 2, api: dshow, fourcc: MJPG}
      width: 1280
      height: 720
      fps: 30
      auto_exposure: true
      mount: {azimuth_deg: 240, description: "by the 11"}
  scoring:
    auto_accept: true            # false = confirm every uncertain dart
    confidence_threshold: 0.90   # below this a dart counts as uncertain

server:
  port: 8000
```

Camera numbers are easiest to set with **Kamery → Wybierz kamery** instead of editing files.
`api: dshow` is the reliable capture backend on Windows (`auto` also works).

Environment variables override everything: `DARTSENSE_PORT`, `DARTSENSE_HOST`,
`DARTSENSE_DATABASE_URL`, `DARTSENSE_MODE`, `DARTSENSE_ADMIN_TOKEN`, and `DARTSENSE_CONFIG`
(path of an extra YAML layer).

**Where data lives** (all ignored by git):

| Path | Content |
|---|---|
| `data/dartsense.db` | players, games, every detected dart, corrections (SQLite) |
| `data/calibration/` | camera calibrations (one JSON per camera, with history) |
| `data/admin_token.txt` | admin token |
| `data/runtime.yaml` | settings changed in the interface |
| `logs/` | log files |
| `recordings/` | recorded camera sessions (Narzędzia → Nagrania) |

**Backup:** stop the app and copy the `data\` folder. **Move to another PC:** copy `data\`
and `configs\local.yaml`; after moving the cameras, recalibrate.

---

## 10. Troubleshooting

**Windows shows only one camera / cameras are “hidden” in Device Manager.**
In Device Manager choose *View → Show hidden devices*. Greyed-out entries are cameras that
were connected earlier (or on another port) and are not present now — they can be ignored or
uninstalled. Make sure all three cameras are plugged in (preferably into different ports on
the back of the PC) and appear without a warning icon under *Cameras* or *Imaging devices*.

**A camera shows “error” / “cannot open N”.**
The device number changed (typically after re-plugging). Open **Kamery → Wybierz kamery** and
assign the pictures again. Close other programs that use the camera (Teams, Zoom, Camera app,
OBS) — a webcam can be used by only one program at a time.

**A camera runs at a low frame rate or drops out.**
Too many cameras on one USB controller/hub. Move one to another port (back panel, or a
USB 3 port). Keep `fourcc: MJPG` (the default).

**Calibration says the board cannot be found.**
The whole board including the double ring must be visible and lit; no darts in the board.
Set the camera position (§6.3) roughly right. Use **Wskaż pole 20…**, or **Punkty ręcznie…**.

**Numbers in the calibration preview are shifted by one or more segments.**
The rotation was guessed wrong: correct the camera position angle (§6.3) or use **Wskaż
pole 20…**, then accept again.

**Darts are scored in the wrong segment.**
Check **Kalibracja** — if a camera reports *moved* or a shift above ~1.5 mm, recalibrate it.
A board that is not fixed to the wall moves when darts are pulled out.

**Darts are detected that were not thrown / detection is erratic.**
Usually too little light (noisy images) or auto-exposure changing the brightness. Add light,
then press **Detekcja → Tarcza pusta → reset** with the board empty. Make sure no dart was
left in the board when the app started.

**The next player's turn does not start after pulling the darts out.**
A dart may still be in the board, or one camera missed the takeout — press **Dalej**.

**The page is blank or does not update.**
Reload with **Ctrl+F5**. If the app was updated, run `scripts\setup.ps1` again (it rebuilds
the interface).

**`start.ps1` cannot be run (“running scripts is disabled”).**
Always start it with `powershell -ExecutionPolicy Bypass -File scripts\start.ps1` as shown.

**Port 8000 is in use.** Start with `.venv\Scripts\python.exe -m backend --port 8080` or set
`server.port` in `configs/local.yaml`.

**Logs:** **Narzędzia → Logi** in the interface, or the files in `logs\`.

---

## 11. Operator panel (many boards in venues)

For an operator who installs boards in bars and arcades there is a **central server**: the
same program in `central` mode, without cameras. It keeps venues (with location, price per
game and the venue's share), every board with its health and alerts (offline, camera down,
uncalibrated, calibration drift), usage statistics, monthly settlements (CSV export) and
service tickets.

```powershell
.venv\Scripts\python.exe -m backend --central            # http://localhost:8100/operator
.venv\Scripts\python.exe -m backend.fleet_demo           # optional: demo venues, boards and history
.venv\Scripts\python.exe -m backend.fleet_demo --live    # keep the demo boards online while it runs
```

**Connecting a board:** in the operator panel open **Tarcze → Dodaj tarczę**, then paste
the generated `fleet:` block (server address and the board's key — shown once) into **that
board's** `configs/local.yaml` and restart the board's app. The board then sends a heartbeat
every minute and a summary of every finished game; games played while offline are sent
later. `python -m backend.fleet_demo --link-simulator` does this for the local simulator.

---

## 12. Development

```powershell
# backend tests
.venv\Scripts\python.exe -m pytest -m "not slow"   # fast tests (~40 s)
.venv\Scripts\python.exe -m pytest                 # everything incl. simulator tests (~4 min)

# frontend
cd frontend
npm test                # unit tests (Vitest)
npm run lint            # typecheck + ESLint
npm run dev             # UI with hot reload on http://localhost:5173 (start the backend on :8000 too)
npm run build           # production build into frontend/dist (served by the backend)

# accuracy benchmark on synthetic footage
.venv\Scripts\python.exe scripts\benchmark.py --quick                     # ~2 min
.venv\Scripts\python.exe scripts\benchmark.py --turns 3 --conditions all  # full, ~10 min
```

Benchmark reports go to `docs/benchmarks/` (`latest.json` is shown under **Narzędzia →
Benchmark**). They measure the algorithms on rendered footage with exact ground truth under
nine lighting/throwing conditions; they are not real-world accuracy.

- Backend auto-reload: `.venv\Scripts\python.exe -m backend --reload`.
- Database migrations (Alembic) run automatically at start-up
  (`backend/migrations/versions/`).
- API: REST + WebSockets, documented at `/docs` while the app runs.
- Code style: Python 3.10+ with type hints; TypeScript strict; follow the surrounding code.

### Measuring real-world accuracy

**Narzędzia → Nagrania i wzorzec**: **Zacznij nagrywać**, throw, **Zatrzymaj**. Open the
recording, mark where each dart really landed, **Zapisz wzorzec** (ground truth) and run
**Oceń** (evaluate) — the recording is replayed through the engine and compared. This is how real accuracy should be measured and tuned.

---

## 13. Project structure

```
dartsense/
├── backend/                  FastAPI application
│   ├── app.py                app factory, start-up, WebSockets, serving the UI
│   ├── settings.py           configuration layers
│   ├── api/                  REST routes (system, vision, games, dev tools, fleet)
│   ├── services/             vision service, game service, statistics, fleet
│   ├── game_engine/          X01, Cricket, Around the Clock, Shanghai, Bob's 27, checkouts
│   ├── database/             SQLAlchemy models and session
│   ├── migrations/           Alembic migrations
│   └── ws/                   WebSocket hub (live events to browsers)
├── vision/                   computer-vision engine (no web code)
│   ├── cameras/              USB/RTSP/replay/synthetic cameras, capture threads
│   ├── calibration/          lens (ChArUco) and board-pose calibration, validation
│   ├── board_detection/      finds the board's red/green rings and rotation
│   ├── dart_detection/       change detection and dart candidates per camera
│   ├── fusion/               combines the cameras into one 3D dart and impact point
│   ├── scoring/              score probability and alternatives
│   ├── tracking/             motion/settle detection, darts currently in the board
│   ├── simulation/           synthetic 3-camera renderer (simulator, tests, benchmark)
│   ├── recording/            session recording and replay
│   ├── engine.py             the real-time engine (state machine)
│   └── config.py             every vision tunable with documentation
├── frontend/                 React + TypeScript + Tailwind web interface
│   └── src/  pages/ components/ operator/ lib/ store/ hooks/
├── configs/                  default.yaml, simulator.yaml, central.yaml (+ your local.yaml)
├── scripts/                  setup.ps1, start.ps1, benchmark.py
├── tests/                    unit, vision and integration tests (pytest)
└── docs/                     ARCHITECTURE.md, ROADMAP.md, benchmarks/
```

---

## 14. How it works

1. **Calibration.** For every camera the app finds the board's red/green double and triple
   rings, determines the board's rotation from the colour pattern and the camera's position
   hint, and then fits the camera's exact 3D position and lens focal length so that the
   drawn wires line up with the real wires (sub-pixel edge matching).
2. **Waiting for a throw.** Each camera watches for motion. When everything has been still
   for ~0.3 s, the still frames are averaged (to remove webcam noise) and compared with the
   previous still scene.
3. **Finding the dart.** In each camera the new, elongated change is the dart; its axis is
   fitted with a robust line fit. Shadows, lighting changes and hands are rejected.
4. **3D fusion.** Each camera's dart axis defines a plane in space; the planes of two or three
   cameras intersect in the dart's 3D axis, which meets the board at the impact point. A dart
   must be confirmed by at least two cameras.
5. **Scoring.** The impact point and its uncertainty give the score and the probability of
   neighbouring scores (e.g. T20 vs S20 near a wire). Low-probability darts are marked
   uncertain.
6. **Board state.** The app remembers which darts are in the board, notices when they are
   pulled out, and only then starts the next player's turn.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), roadmap: [docs/ROADMAP.md](docs/ROADMAP.md).

---

## 15. Installation on Linux / macOS

`setup.ps1`/`start.ps1` are for Windows; on Linux or macOS run the same steps by hand:

```bash
git clone git@github.com:cipsonnek/darts.git dartsense
cd dartsense
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
(cd frontend && npm ci && npm run build)

.venv/bin/python -m backend                  # real cameras  → http://localhost:8000
.venv/bin/python -m backend --simulator      # simulator
.venv/bin/python -m backend --host 0.0.0.0   # reachable from the network
```

On Linux the cameras are `/dev/video*` (numbers as on Windows); add your user to the
`video` group if they cannot be opened. In `configs/local.yaml` use `api: auto` (or `v4l2`)
instead of `dshow`.
