# DartSense

Automatic dart scoring with three cameras: a local computer-vision engine, a game engine
and a web UI you can open from any browser on the network.

> **Accuracy status:** accuracy numbers come from a synthetic 3-camera simulator
> (`docs/benchmarks/`). On a real board (Winmau Blade 6 lying flat, three 720p webcams) all
> darts thrown in the first tests were scored correctly, but no systematic real-world
> measurement exists yet.

## Requirements

- Windows 10/11 (Linux works too; use the commands without `.ps1`)
- Python 3.10–3.12, Node.js 20 LTS or newer, Git
- Three USB (UVC) cameras around the board — or none, to try the simulator

## Install on a new PC

```powershell
git clone git@github.com:cipsonnek/darts.git dartsense
cd dartsense
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

## Run

```powershell
# with the real cameras
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# or with three simulated cameras (no hardware needed)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Simulator
```

Open <http://localhost:8000>. Add `-Lan` to reach it from a phone, tablet or TV on the same
network (`http://<this-pc-ip>:8000`); Windows may ask to allow Python through the firewall.

## First-time setup with real cameras

1. **Check Windows sees three cameras** (Device Manager → Cameras). Plug them into different
   USB ports, preferably on the back panel; avoid unpowered hubs.
2. **Kamery → Wybierz kamery** shows a live picture from every USB device. Click which
   camera (1/2/3) each picture is. Identical webcams can swap numbers after re-plugging; if you
   pick a device another camera uses, the two swap *together with their calibration and
   position*, so no recalibration is needed. In each camera's **Konfiguruj** dialog set its
   position around the board (clock angle: 0 = above the 20, 90 = right, 180 = below, 270 = left).
3. **Kalibracja** (board empty, lights on):
   - optional but recommended: *Lens (intrinsics)* with the printable ChArUco target;
   - *Board position → Detect automatically* for each camera, check the overlay sits on the
     wires, then *Accept calibration*. If the board or a camera moves, the page says so;
     repeat this step.
4. **Players → Nowa gra → Rozpocznij grę**, throw. After a turn, pull the darts out: the next
   player's turn starts when the board is empty (or with **Dalej**). Darts seen while the
   previous turn is being pulled out are not scored.

Uncertain darts are scored immediately and marked so they can be corrected (click the dart);
set `vision.scoring.auto_accept: false` to confirm each of them instead.

Settings for one machine (camera indices, ports) can also go in `configs/local.yaml`, which
overrides `configs/default.yaml` and is not committed. Changes made in the UI are saved to
`data/runtime.yaml` (`data/runtime-simulator.yaml` in simulator mode) and win over both.

**Tips for real cameras:** light the board evenly (an LED ring is ideal), mount it on the
wall (a board lying loose shifts when darts are pulled), and keep the cameras 35–60° off the
board's axis so each sees the whole board.

## Operator panel (fleet of boards in venues)

The operator's central server keeps venues (bars, arcades) with their location and terms
(price per game, venue share), every installed board with its health, usage statistics,
monthly settlements and service tickets. It is the same backend in `central` mode, without
cameras:

```powershell
.venv\Scripts\python.exe -m backend --central            # http://localhost:8100/operator
.venv\Scripts\python.exe -m backend.fleet_demo           # optional: demo venues, boards and history
.venv\Scripts\python.exe -m backend.fleet_demo --live    # keep the demo boards online while it runs
```

Register a board under **Tarcze → Dodaj tarczę** and paste the generated `fleet:` block into
that board's `configs/local.yaml`. The board then sends a heartbeat every minute and a summary
of every finished game; games played offline are sent when the connection is back.
`python -m backend.fleet_demo --link-simulator` does this for the local simulator.
In development `npm run dev` proxies `/api/fleet` to the central server on port 8100.

## Development

```powershell
.venv\Scripts\python.exe -m pytest -m "not slow"   # fast tests
.venv\Scripts\python.exe -m pytest                 # everything (a few minutes)
.venv\Scripts\python.exe scripts\benchmark.py --quick
cd frontend; npm test; npm run lint                # frontend unit tests, typecheck + lint
cd frontend; npm run dev                           # UI with hot reload on :5173 (backend on :8000)
```

Architecture and roadmap: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/ROADMAP.md](docs/ROADMAP.md).
