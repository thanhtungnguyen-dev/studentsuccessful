"""Generate contracts offline using installed dependencies, or check without writing."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.main import app  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    spec = json.dumps(app.openapi(), indent=2) + "\n"
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "openapi.json"
        target = Path(directory) / "schema.d.ts"
        source.write_text(spec, encoding="utf-8", newline="\n")
        subprocess.run(
            ["node", str(ROOT / "frontend/node_modules/openapi-typescript/bin/cli.js"),
             str(source), "-o", str(target)], check=True, cwd=ROOT,
        )
        generated = {
            ROOT / "backend/openapi.json": spec,
            ROOT / "frontend/lib/api/schema.d.ts": target.read_text(encoding="utf-8"),
        }
        for path, content in generated.items():
            if args.check:
                if path.read_text(encoding="utf-8") != content:
                    raise SystemExit(f"Stale contract: {path.relative_to(ROOT)}")
            else:
                path.write_text(content, encoding="utf-8", newline="\n")
    print("Contracts synchronized" if args.check else "Contracts generated")


if __name__ == "__main__":
    main()
