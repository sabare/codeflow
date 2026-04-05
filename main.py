from __future__ import annotations

import json
import sys
from pathlib import Path

from analysis import build_analysis, build_call_graph, build_call_map


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    result = build_analysis(root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
