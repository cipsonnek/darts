# Synthetic benchmark — 2026-10-01T20:41:30

> **Synthetic footage** rendered by `vision/simulation`. These numbers validate the algorithms and
> guard against regressions. They are **not** real-world accuracy (see docs/TESTING.md).

Calibration mode: `auto` · 1280x720 @ 20.0 fps

| Metric | Value |
|---|---|
| Darts thrown | 81 |
| Detection rate | 97.5 % |
| Score accuracy (all thrown) | 95.1 % |
| Score accuracy (detected) | 97.5 % |
| Sector accuracy (detected) | 97.5 % |
| Ring accuracy (detected) | 98.7 % |
| Impact error mean / median / p95 / max | 1.071 / 0.438 / 4.708 / 11.57 mm |
| Missed darts | 2 (2.5 %) |
| False positives | 3 (3.7 %) |
| Duplicate scores | 2 (2.5 %) |
| Flagged uncertain | 57.0 % |
| Accuracy of auto-accepted darts | 100.0 % |
| Wrong scores auto-accepted | 0 |
| Wrong scores flagged uncertain | 100.0 % |
| Errors inside 95 % confidence ellipse | 86.1 % |
| Processing per settled scene (mean / p95) | 1238.51 / 1709.6 ms |
| Detection latency after landing (mean) | 0.66 s |

## By region

| Region | Darts | Accuracy |
|---|---|---|
| bull | 1 | 100.0 % |
| double | 8 | 87.5 % |
| triple | 9 | 100.0 % |
| single | 58 | 94.8 % |
| miss | 5 | 100.0 % |

## By condition

| Condition | Darts | Detected | Score acc. | Mean err (mm) | p95 err (mm) | FP | Dup |
|---|---|---|---|---|---|---|---|
| bright-mixed | 9 | 100.0 % | 77.8 % | 1.234 | 3.549 | 0 | 0 |
| dim-uniform | 9 | 100.0 % | 100.0 % | 0.347 | 0.705 | 0 | 0 |
| led_ring-cluster | 9 | 100.0 % | 100.0 % | 2.786 | 9.252 | 0 | 0 |
| neutral-handpass | 9 | 88.9 % | 88.9 % | 0.882 | 2.525 | 1 | 0 |
| neutral-lightchange | 9 | 100.0 % | 100.0 % | 1.619 | 4.637 | 1 | 1 |
| neutral-uniform | 9 | 100.0 % | 100.0 % | 0.675 | 1.995 | 0 | 0 |
| side_light-uniform | 9 | 100.0 % | 100.0 % | 1.032 | 2.367 | 0 | 1 |
| uneven-cluster | 9 | 88.9 % | 88.9 % | 0.79 | 1.661 | 1 | 0 |
| warm-boundary | 9 | 100.0 % | 100.0 % | 0.219 | 0.477 | 0 | 0 |

## Worst cases

- true S4 → predicted S4, error 11.57 mm, uncertain=False, cameras ['cam1', 'cam2']
- true S19 → predicted S19, error 5.77 mm, uncertain=True, cameras ['cam1', 'cam3']
- true S7 → predicted S7, error 5.12 mm, uncertain=False, cameras ['cam1', 'cam2']
- true S7 → predicted S19, error 4.91 mm, uncertain=True, cameras ['cam1', 'cam2', 'cam3']
- true S13 → predicted S13, error 4.69 mm, uncertain=True, cameras ['cam1', 'cam2', 'cam3']
- true S18 → predicted S18, error 3.9 mm, uncertain=True, cameras ['cam1', 'cam2', 'cam3']
- true S16 → predicted S16, error 3.01 mm, uncertain=True, cameras ['cam1', 'cam2', 'cam3']
- true S17 → predicted S17, error 2.88 mm, uncertain=True, cameras ['cam1', 'cam2', 'cam3']
