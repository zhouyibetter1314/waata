import argparse
import json
from pathlib import Path

from waata_api.main import create_app

SNAPSHOT = Path(__file__).resolve().parents[1] / "contracts/http/openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not SNAPSHOT.exists() or SNAPSHOT.read_text(encoding="utf-8") != content:
            parser.exit(
                1, "OpenAPI snapshot is stale. Run scripts/export_openapi.py.\n"
            )
    else:
        SNAPSHOT.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
