"""Write the reproducible C1 OpenAPI snapshot without starting the service."""

import argparse
import json
from pathlib import Path

from waata_api.main import app


def write_openapi(path: Path) -> None:
    schema = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(schema + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    write_openapi(parser.parse_args().path)
