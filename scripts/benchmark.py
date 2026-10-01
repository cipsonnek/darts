"""Synthetic accuracy benchmark.

Runs complete scenarios (turns of three darts with takeouts) through the real vision
engine on rendered 3-camera footage, in parallel processes, and reports detection and
scoring metrics against exact ground truth.

    python scripts/benchmark.py --turns 6 --workers 6
    python scripts/benchmark.py --quick

Results go to docs/benchmarks/<timestamp>.json and .md. They describe SYNTHETIC footage:
they validate the algorithms and catch regressions; they are not real-world accuracy.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

CONDITIONS = [
    # (name, lighting preset, throw mode, extra)
    ("neutral-uniform", "neutral", "uniform", {}),
    ("led_ring-cluster", "led_ring", "cluster", {}),
    ("warm-boundary", "warm", "boundary", {}),
    ("dim-uniform", "dim", "uniform", {}),
    ("uneven-cluster", "uneven", "cluster", {}),
    ("bright-mixed", "bright", "mixed", {}),
    ("side_light-uniform", "side_light", "uniform", {}),
    ("neutral-lightchange", "neutral", "mixed", {"lighting_changes": ["warm", "dim", "neutral"]}),
    ("neutral-handpass", "neutral", "uniform", {"hand_pass_prob": 0.35}),
]


def _run_one(job: dict) -> dict:
    from vision.evaluation import SimulationRunner, compute_metrics, turns_scenario

    t0 = time.time()
    runner = SimulationRunner(seed=job["seed"], fps=job["fps"], calibration=job["calibration"],
                              lighting=job["lighting"], width=job["width"], height=job["height"])
    rng = np.random.default_rng(job["seed"])
    sc = turns_scenario(job["turns"], rng, mode=job["mode"], lighting=job["lighting"], **job["extra"])
    res = runner.run(sc)
    m = compute_metrics([res])
    return {"condition": job["name"], "seed": job["seed"], "metrics": m, "wall_s": time.time() - t0,
            "calibration": runner.calibration_report,
            "result": {"gt": [g.to_dict() for g in res.ground_truth],
                       "events": [e.to_dict() for e in res.events if e.type == "dart_detected"]}}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--turns", type=int, default=4, help="turns of 3 darts per condition")
    ap.add_argument("--workers", type=int, default=max(1, min(8, (mp.cpu_count() or 2) - 1)))
    ap.add_argument("--fps", type=float, default=20.0)
    ap.add_argument("--calibration", choices=["auto", "board_only", "truth"], default="auto")
    ap.add_argument("--conditions", default="all", help="comma-separated names or 'all'")
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--quick", action="store_true", help="2 conditions x 2 turns")
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmarks"))
    args = ap.parse_args()

    conds = CONDITIONS if args.conditions == "all" else [c for c in CONDITIONS if c[0] in args.conditions.split(",")]
    turns = args.turns
    if args.quick:
        conds, turns = conds[:2], 2
    jobs = [{"name": n, "lighting": l, "mode": m, "extra": e, "seed": args.seed + i, "turns": turns,
             "fps": args.fps, "calibration": args.calibration, "width": args.width, "height": args.height}
            for i, (n, l, m, e) in enumerate(conds)]
    print(f"running {len(jobs)} conditions x {turns} turns ({len(jobs) * turns * 3} darts) on {args.workers} workers")
    t0 = time.time()
    ctx = mp.get_context("spawn")
    with ctx.Pool(args.workers) as pool:
        results = []
        for r in pool.imap_unordered(_run_one, jobs):
            m = r["metrics"]
            print(f"  {r['condition']:<22} darts={m['darts_thrown']:>3} det={m['detection_rate']} "
                  f"score_acc={m['score_accuracy_all_thrown']} err_mean={(m['impact_error_mm'] or {}).get('mean')} "
                  f"fp={m['false_positives']} dup={m['duplicates']} ({r['wall_s']:.0f}s)")
            results.append(r)
    from vision.evaluation import compute_metrics  # noqa: F401  (pooled metrics below)

    pooled = _pool_metrics(results)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "synthetic": True,
        "note": "Synthetic rendered footage (vision/simulation). Not a real-world accuracy claim.",
        "settings": vars(args),
        "overall": pooled,
        "by_condition": {r["condition"]: r["metrics"] for r in sorted(results, key=lambda r: r["condition"])},
        "calibration": {r["condition"]: r["calibration"] for r in results},
        "wall_seconds": round(time.time() - t0, 1),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out / f"benchmark_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / f"benchmark_{stamp}.md").write_text(_markdown(report), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(_markdown(report))
    print(f"written to {out}")


def _pool_metrics(results: list[dict]) -> dict:
    """Recompute metrics over all conditions together."""
    from vision.evaluation import RunResult, compute_metrics
    from vision.events import VisionEvent
    from vision.geometry.board import BoardGeometry
    from vision.simulation.world import GroundTruthDart

    board = BoardGeometry()
    runs = []
    for r in results:
        gts = []
        for g in r["result"]["gt"]:
            imp = np.array(g["impact_mm"])
            gts.append(GroundTruthDart(g["dart_id"], imp, np.array(g["axis"]), board.score(*imp), g["landed_at"],
                                       g["removed_at"], g["style"]))
        evs = [VisionEvent(e["type"], e["timestamp"], e["data"]) for e in r["result"]["events"]]
        runs.append(RunResult(r["condition"], gts, evs, r["wall_s"], 0, {"processing_ms": r["metrics"]["processing_ms"]}, {}))
    return compute_metrics(runs)


def _markdown(rep: dict) -> str:
    o = rep["overall"]
    e = o["impact_error_mm"] or {}
    lines = [
        f"# Synthetic benchmark — {rep['generated_at']}",
        "",
        "> **Synthetic footage** rendered by `vision/simulation`. These numbers validate the algorithms and",
        "> guard against regressions. They are **not** real-world accuracy (see docs/TESTING.md).",
        "",
        f"Calibration mode: `{rep['settings']['calibration']}` · {rep['settings']['width']}x{rep['settings']['height']} @ {rep['settings']['fps']} fps",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Darts thrown | {o['darts_thrown']} |",
        f"| Detection rate | {_pct(o['detection_rate'])} |",
        f"| Score accuracy (all thrown) | {_pct(o['score_accuracy_all_thrown'])} |",
        f"| Score accuracy (detected) | {_pct(o['score_accuracy_detected'])} |",
        f"| Sector accuracy (detected) | {_pct(o['sector_accuracy_detected'])} |",
        f"| Ring accuracy (detected) | {_pct(o['ring_accuracy_detected'])} |",
        f"| Impact error mean / median / p95 / max | {e.get('mean')} / {e.get('median')} / {e.get('p95')} / {e.get('max')} mm |",
        f"| Missed darts | {o['missed']} ({_pct(o['miss_rate'])}) |",
        f"| False positives | {o['false_positives']} ({_pct(o['false_positive_rate'])}) |",
        f"| Duplicate scores | {o['duplicates']} ({_pct(o['duplicate_rate'])}) |",
        f"| Flagged uncertain | {_pct(o['uncertain_rate'])} |",
        f"| Accuracy of auto-accepted darts | {_pct(o['auto_accepted_accuracy'])} |",
        f"| Wrong scores auto-accepted | {o['wrong_auto_accepted']} |",
        f"| Wrong scores flagged uncertain | {_pct(o['wrong_scores_flagged_uncertain'])} |",
        f"| Errors inside 95 % confidence ellipse | {_pct((o['confidence_calibration'] or {}).get('fraction_within_95pct_ellipse'))} |",
        f"| Processing per settled scene (mean / p95) | {(o['processing_ms'] or {}).get('mean')} / {(o['processing_ms'] or {}).get('p95')} ms |",
        f"| Detection latency after landing (mean) | {(o['latency_s'] or {}).get('mean')} s |",
        "",
        "## By region",
        "",
        "| Region | Darts | Accuracy |",
        "|---|---|---|",
    ]
    for k, v in o["accuracy_by_region"].items():
        lines.append(f"| {k} | {o['count_by_region'][k]} | {_pct(v)} |")
    lines += ["", "## By condition", "", "| Condition | Darts | Detected | Score acc. | Mean err (mm) | p95 err (mm) | FP | Dup |",
              "|---|---|---|---|---|---|---|---|"]
    for name, m in rep["by_condition"].items():
        ee = m["impact_error_mm"] or {}
        lines.append(f"| {name} | {m['darts_thrown']} | {_pct(m['detection_rate'])} | {_pct(m['score_accuracy_all_thrown'])} | "
                     f"{ee.get('mean')} | {ee.get('p95')} | {m['false_positives']} | {m['duplicates']} |")
    lines += ["", "## Worst cases", ""]
    for w in o["worst_cases"]:
        lines.append(f"- true {w['gt']} → predicted {w['pred']}, error {w['error_mm']} mm, uncertain={w['uncertain']}, cameras {w['cameras']}")
    return "\n".join(lines) + "\n"


def _pct(v) -> str:
    return "n/a" if v is None else f"{100 * v:.1f} %"


if __name__ == "__main__":
    main()
