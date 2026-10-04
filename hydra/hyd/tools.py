# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Operator CLI: python -m hydra.hyd.tools; no runtime activation commands."""
import argparse
import json
from pathlib import Path

from hydra.hyd.integration import contract
from hydra.hyd.lab import HydLab, JobRequest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--state", type=Path, default=Path("data/hyd-tools"))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("contract")
    submit = sub.add_parser("submit")
    submit.add_argument("request", type=Path, help="JSON JobRequest; paths relative to input root")
    for name in ("run", "status", "cancel"):
        command = sub.add_parser(name)
        command.add_argument("job_id")
    args = parser.parse_args(argv)
    try:
        if args.action == "contract":
            result = contract()
        else:
            lab = HydLab(args.root, args.state)
            if args.action == "submit":
                result = lab.submit(JobRequest.model_validate_json(args.request.read_text(encoding="utf-8")))
            else:
                result = {"run": lab.run, "status": lab.get, "cancel": lab.cancel}[args.action](args.job_id)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 1 if result.get("state") == "failed" else 0
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
