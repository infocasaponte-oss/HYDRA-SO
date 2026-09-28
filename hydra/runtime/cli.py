from __future__ import annotations

import argparse

from hydra import __version__
from hydra.runtime.hardware import resolve_profile


def main() -> None:
    parser = argparse.ArgumentParser(prog="hydra")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    profile = sub.add_parser("profile")
    profile.add_argument("--gpu", required=True)
    profile.add_argument("--vram-mb", required=True, type=int)
    args = parser.parse_args()

    if args.version:
        print(__version__)
        return

    if args.command == "profile":
        print(resolve_profile(args.gpu, args.vram_mb).as_dict())
        return

    parser.print_help()
