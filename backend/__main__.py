"""Run the DartSense server: ``python -m backend``.

Options mirror the most common configuration overrides; everything else lives in
configs/*.yaml (see docs/DEVELOPMENT.md).
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend", description="DartSense server")
    ap.add_argument("--host", help="bind address (default from config: 127.0.0.1)")
    ap.add_argument("--port", type=int, help="port (default 8000)")
    ap.add_argument("--config", help="extra YAML config layer (e.g. configs/simulator.yaml)")
    ap.add_argument("--simulator", action="store_true", help="shortcut for --config configs/simulator.yaml")
    ap.add_argument("--central", action="store_true", help="operator's fleet server (--config configs/central.yaml)")
    ap.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    args = ap.parse_args()
    if args.simulator:
        os.environ["DARTSENSE_CONFIG"] = "configs/simulator.yaml"
    elif args.central:
        os.environ["DARTSENSE_CONFIG"] = "configs/central.yaml"
    elif args.config:
        os.environ["DARTSENSE_CONFIG"] = args.config
    if args.host:
        os.environ["DARTSENSE_HOST"] = args.host
    if args.port:
        os.environ["DARTSENSE_PORT"] = str(args.port)

    import uvicorn

    from backend.settings import load_settings

    s = load_settings()
    # One worker only: cameras and the engine live in this process.
    uvicorn.run("backend.app:create_app", factory=True, host=s.server.host, port=s.server.port,
                reload=args.reload, workers=1, log_config=None)


if __name__ == "__main__":
    main()
