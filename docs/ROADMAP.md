# Development roadmap

Each phase ends with tests run, docs updated and integration checked before the next starts.
Status is kept current in this file.

| # | Phase | Deliverables | Status |
|---|---|---|---|
| 1 | Repository analysis + architecture | ARCHITECTURE.md, this roadmap, monorepo layout, config system, logging | done |
| 2 | Camera abstraction + capture | `Camera` interface; OpenCV (USB/UVC), RTSP, replay and synthetic cameras; capture threads, health, sync metrics; recorder | planned |
| 3 | Board geometry, detection + calibration | Regulation geometry in mm; ChArUco/chessboard intrinsics; automatic board detection (ring colours → sector correspondences); manual 4-point fallback; edge-based pose refinement; quality metrics; movement validation | planned |
| 4 | Dart detection | Settle detection, photometric change detection, shadow suppression, dart-axis extraction, tip localisation, plausibility checks, multi-dart candidates | planned |
| 5 | Multi-camera fusion | Back-projected axis planes → board lines; correspondence search; weighted least squares with covariance; outlier rejection; 3D axis | planned |
| 6 | Impact-point estimation | Line/tip fusion, covariance, probability-based score confidence and alternatives | planned |
| 7 | Scoring + game engine | DartScore events; X01 / Cricket / Around the Clock / Shanghai / Bob's 27; plug-in registry; corrections; undo | planned |
| 8 | Backend API + WebSockets | REST, WS hub, MJPEG streams with overlays, DB + migrations, admin token, structured logs | planned |
| 9 | Web frontend | Dashboard/live game, cameras, calibration wizard, detection diagnostics, games, players, statistics, settings, developer tools, TV mode, themes | planned |
| 10 | Testing + accuracy | Synthetic benchmark, metrics, regression thresholds, recording evaluation | planned |
| 11 | Performance | Downscaled motion path, ROI processing, per-stream JPEG encoding, latency/FPS metrics | planned |
| 12 | Packaging | Docker, run scripts, production build served by the backend | planned |

## Known follow-ups that need physical hardware

- Measure real-world accuracy with recorded, annotated throws (tools exist; see TESTING.md).
- Tune default thresholds (`configs/default.yaml → detection`) on real footage from the target cameras.
- Validate automatic board detection on boards whose colours differ from the red/green standard
  (manual 4-point calibration covers those today).
- Hardware-triggered synchronisation (the `Camera` interface has a `trigger()` hook; no driver yet).
