from __future__ import annotations

import argparse
import shutil
import tempfile
import zipapp
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary)
        shutil.copytree(root / "src" / "myinstall", source / "myinstall")
        (source / "__main__.py").write_text(
            "from myinstall.cli import main\nraise SystemExit(main())\n",
            encoding="utf-8",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        zipapp.create_archive(source, args.output, interpreter="/usr/bin/env python3")
        args.output.chmod(0o755)


if __name__ == "__main__":
    main()
