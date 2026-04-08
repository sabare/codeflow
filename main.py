from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis import build_analysis
from flow import build_flow_tree


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a call graph or a readable flow tree.")
    parser.add_argument("root", nargs="?", default=".", help="Project root to scan.")
    parser.add_argument("--function", "-f", help="Build a tree for one function.")
    parser.add_argument(
        "--depth",
        "-d",
        type=int,
        default=None,
        help="Tree depth to expand. Leave unset for the full tree.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    analysis = build_analysis(root)

    if args.function:
        result = build_flow_tree(analysis, args.function, args.depth)
    else:
        result = analysis

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
