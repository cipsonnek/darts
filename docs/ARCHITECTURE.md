# DartSense — Architecture

This document describes the architecture of the system, the technology choices and their
justification, and the hard problems we know about. The phase plan lives in [ROADMAP.md](ROADMAP.md).

---

## 1. Starting point

This is a new, standalone project (`dartsense`) with its own repository. It does not reuse
code from other projects on the development machine.

### Environment found

- Windows 11 Home, Python 3.10.11, Node 20.12, npm 10.5.
- CPU + NVIDIA RTX 3070 (8 GB). The classical pipeline is CPU-only by design; ONNX Runtime is optional.
- Six DirectShow capture devices are visible. **All of them are virtual** (OBS Virtual Camera and blank test devices), so **no physical board cameras are available in this environment.** Consequences:
  - Everything that needs real optics (real-world accuracy, lens calibration of the actual cameras, lighting robustness on real boards) **cannot be measured here.** No such claim is made anywhere in this repository.
  - Accuracy is measured on a **physically based synthetic 3-camera renderer** (`vision/simulation/`) with exact ground truth. Synthetic numbers are labelled as such wherever they appear.
  - The recording, replay and ground-truth annotation tools exist so that real-world accuracy can be measured as soon as cameras are connected (see [TESTING.md](TESTING.md)).

---

## 2. System architecture

```text
 3x cameras (USB/UVC, RTSP, replay, simulator)
        │   vision/cameras  — Camera interface, one capture thread per camera,
        │                     latest-frame slot (no unbounded queues), health, reconnect
        ▼
 ┌──────────────────────────── vision/ (pure library, no web code) ───────────────────────────┐
 │ calibration/    intrinsics (ChArUco / chessboard), board pose (auto + manual), edge-based   │
 │                 pose refinement, quality metrics, movement validation                       │
 │ board_detection/ red/green ring segmentation → sector-boundary correspondences              │
 │ geometry/       BoardGeometry (polar scoring, configurable mm), CameraModel (project/       │
 │                 back-project/planes), line & plane math                                     │
 │ tracking/       per-camera motion/settle detector, BoardState (known darts, takeout)         │
 │ dart_detection/ photometric change detection, shadow suppression, dart-axis line           │
 │                 extraction, tip localisation, plausibility                                  │
 │ fusion/         cross-camera correspondence, plane–plane / line–line least squares with     │
 │                 covariance, outlier rejection                                               │
 │ scoring/        probabilistic scoring (score probability, alternatives)                     │
 │ engine.py       VisionEngine: orchestrates all of the above, emits typed events             │
 │ recording/      session recorder + deterministic replay                                     │
 │ simulation/     synthetic renderer used by tests, benchmarks and the dev simulator          │
 │ diagnostics/    overlays, image-quality metrics                                             │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ VisionEvent (dart_detected / dart_uncertain / darts_removed / state / calibration…)
        ▼
 ┌──────────────────────────── backend/ (FastAPI) ───────────────────────────────────────────┐
 │ services/vision_service  — owns the engine, persists events, forwards to the event hub    │
 │ game_engine/             — X01 / Cricket / Around the Clock / … as pure-Python modules    │
 │ services/game_service    — binds detected darts to the active game, corrections, undo     │
 │ database/                — SQLAlchemy 2 models, Alembic migrations (SQLite / PostgreSQL)  │
 │ api/                     — REST routers; MJPEG camera streams with server-side overlays   │
 │ ws/                      — event hub, /ws/events and /ws/detection                        │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ REST + WebSocket (+ MJPEG for video)
        ▼
 frontend/ (React + TS) — Live board, scores, camera views, calibration, detection
                          diagnostics, games, players, statistics, settings, developer tools
```

### Dependency rules (enforced by package layout and tests)

- `vision` imports nothing from `backend` or `frontend`. It is testable with no server.
- `backend.game_engine` imports nothing from `vision`, FastAPI or the database. It consumes
  plain `DartScore` values. Detection is independent from game rules.
- The frontend contains **no** computer-vision logic and **no** game rules. It renders state
  received from the API and sends user intents (start game, correct dart, undo…).

### Process model

The vision engine runs **in the backend process** in its own threads (one capture thread per
camera plus one engine thread). OpenCV releases the GIL in its heavy kernels, so threads give
real parallelism without the cost of shipping frames between processes. Isolation is provided by:

- a supervisor around the engine loop that restarts it after an unexpected exception and reports
  the crash as a diagnostics event,
- camera threads that reconnect with exponential back-off,
- `scripts/run_server.py --supervise`, which restarts the whole process if it dies (native crash).

The engine talks to the backend only through `VisionEngine.subscribe(callback)` and a small
query API, so moving it to a separate process later (shared memory + a socket) does not change
either side.

### Why MJPEG for video

Browsers decode MJPEG natively in an `<img>` tag. Frames are downscaled and JPEG-encoded **per
stream on demand**, only while a client is watching, at a client-selected size/quality/FPS, with
optional server-side overlays. Full-resolution frames never cross the API. WebSockets carry
events only.

---

## 3. Technology choices

| Concern | Choice | Why |
|---|---|---|
| Vision | Python 3.10+, OpenCV 4.10+, NumPy, SciPy | Mature, deterministic, fast native kernels. SciPy's robust least squares is used for pose refinement. |
| ML | Optional ONNX Runtime hook, not in the default path | Classical geometry is more precise, explainable and data-free for this problem (see VISION.md §8). A learned segmentation model can slot into `dart_detection` later through the same interface. |
| API | FastAPI + Uvicorn | Async WebSockets, Pydantic validation, OpenAPI docs for free. |
| DB | SQLAlchemy 2 + Alembic; SQLite by default, PostgreSQL via `DARTPULSE_DATABASE_URL` | Runs offline with zero setup and scales to Postgres without code changes. |
| Config | One YAML file (`configs/default.yaml`) validated by Pydantic, overridable per machine (`configs/local.yaml`) and by env vars | No magic numbers scattered in code. |
| Frontend | React 19, TypeScript, Vite, Tailwind 4, Zustand, Recharts, Vitest | Matches the existing code. |
| Live transport | WebSocket (events), MJPEG (video) | No per-frame polling. |

---

## 4. Directory structure

```text
dartsense/
├── vision/                 CV library + engine (no web dependencies)
├── backend/                FastAPI app, game engine, DB, services
│   └── migrations/         Alembic migrations
├── frontend/               React web application
├── tests/
│   ├── unit/               geometry, game engine, scoring
│   ├── vision/             calibration, detection, fusion, temporal, benchmarks
│   ├── integration/        REST + WebSocket end-to-end against the simulator
│   └── fixtures/
├── configs/                default.yaml, simulator.yaml, (local.yaml — machine-specific, ignored)
├── scripts/                calibrate, record, replay, benchmark, list_cameras, charuco, run_server
├── docs/                   this documentation
├── docker/                 Dockerfile + compose
└── recordings/             recorded sessions (ignored by git)
```

---

## 5. Coordinate systems

**Board frame** (all geometry, fusion and scoring), millimetres:

- origin = centre of the bull, on the board surface
- **+X** to the right as seen by the player (towards the 6)
- **+Y** up (towards the 20)
- **+Z** out of the board towards the player (right-handed); the board surface is **Z = 0**,
  darts stick out at Z > 0
- polar angle θ measured **clockwise from +Y** (i.e. from the centre of the 20), in degrees

**Camera frame**: OpenCV convention (x right, y down, z forward). Extrinsics map board → camera:
`X_cam = R · X_board + t`.

**API impact coordinates**: `impact.x_mm`, `impact.y_mm` in the board frame, plus
`impact.r_mm` and `impact.theta_deg`. For convenience `impact.x_norm`/`y_norm` are the board frame
divided by the double-ring outer radius (170 mm on a regulation board) — still **y-up**.

---

## 6. Hard problems and risks

| Risk | Why it is hard | Mitigation |
|---|---|---|
| Shallow viewing angles | A pixel of error along the viewing direction is several mm on the board. | Use the dart **axis line** (well conditioned perpendicular to the view) from ≥2 cameras; per-camera covariance; ambiguity reported as low confidence. |
| Occlusion by earlier darts | The new dart can be hidden behind existing darts in one camera. | Change mask relative to the previous *stable* frame (existing darts cancel), robust line fitting with gaps, per-camera tip-occlusion test, fusion from the remaining cameras. |
| Lighting changes and shadows | Global gain changes and dart shadows show up as "change". | Photometric normalisation against a static ring, chromaticity-based shadow suppression, noise-adaptive thresholds, exposure locking. |
| Wobble / sag after impact | A settling dart keeps moving for a few hundred ms. | Settle detector with noise-adaptive thresholds; changes that overlap a known dart update that dart and are not scored. |
| Hands, bodies in front of the board | Large changes that are not darts. | Shape/size/length plausibility using calibrated geometry; obstruction state that holds the reference until the scene returns. |
| Bounce-outs and misses | A dart that does not stay in the board leaves no trace. | Motion-without-change is surfaced as a "possible bounce-out"; manual entry of a miss in the UI. |
| Camera or board movement | Silent calibration drift corrupts every score. | Periodic edge-alignment check on idle frames + cross-camera residual monitoring; status shown in the UI, low-confidence policy tightens. |
| No hardware in development | Real optics, noise and lighting can't be measured here. | Synthetic renderer with lens distortion, noise, shadows, lighting changes; recording/replay/annotation tools for when hardware is available. **Real accuracy is not claimed.** |
| Camera sync without hardware triggering | Free-running cameras capture at different moments. | Detection works on *settled* scenes, so sub-frame sync is irrelevant for scoring; timestamps and sync spread are still measured and shown. |

---

## 7. Testing strategy (summary — details in [TESTING.md](TESTING.md))

1. **Unit**: board geometry (every sector × ring, boundaries, bull), camera model round-trips,
   line/plane math, game rules (X01 busts, double-out, cricket closing/points, ATC).
2. **Vision**: calibration recovers known poses from rendered images; detection, overlapping darts,
   removed darts and false positives (hands, lighting changes) on rendered sequences.
3. **Integration**: the FastAPI app running against the simulator camera rig; REST endpoints,
   WebSocket events, game flow end-to-end.
4. **Benchmark** (`scripts/benchmark.py`): N synthetic throws under several lighting/dart
   presets → detection rate, impact error mean / p95, sector, ring and bull accuracy, false
   positives, misses, duplicates, latency. Results are written to `docs/benchmarks/`.
5. **Real-world** (needs hardware): record sessions, annotate ground truth in the web UI,
   `scripts/evaluate_recording.py` computes the same metrics.
