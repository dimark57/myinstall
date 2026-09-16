#!/usr/bin/env python3
"""Validate an application's myinstall Compose template without YAML packages."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REQUIRED_PLACEHOLDERS = (
    "{{SECRET_PATH}}",
    "{{SECRET_MOUNT}}",
    "{{DATA_PATH}}",
    "{{HEALTH_URL}}",
)
PLACEHOLDER_VALUES = {
    "{{IMAGE}}": ("image",),
    "{{SECRET_PATH}}": ("secret_path",),
    "{{SECRET_MOUNT}}": ("secret_mount",),
    "{{DATA_PATH}}": ("data_path",),
    "{{HEALTH_URL}}": ("healthcheck", "url"),
}


def nested_value(document: dict, path: tuple[str, ...]) -> object | None:
    value: object = document
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def service_names(text: str) -> list[str]:
    in_services = False
    names: list[str] = []
    for line in text.splitlines():
        if re.fullmatch(r"services:\s*", line):
            in_services = True
            continue
        if in_services and line and not line.startswith((" ", "\t")):
            in_services = False
        if in_services:
            match = re.fullmatch(r" {2}([A-Za-z0-9_.-]+):\s*", line)
            if match:
                names.append(match.group(1))
    return names


def image_values(text: str) -> list[str]:
    return re.findall(r"(?m)^\s+image:\s*(\S+)\s*$", text)


def compose_network_name(text: str) -> str | None:
    match = re.search(r"(?m)^\s+name:\s*([^\s#]+)\s*$", text)
    return match.group(1) if match else None


def materialize(template: str, manifest: dict) -> tuple[str, list[str]]:
    result = template
    errors: list[str] = []
    for placeholder, path in PLACEHOLDER_VALUES.items():
        value = nested_value(manifest, path)
        if not isinstance(value, str) or not value:
            errors.append(f"manifest value for {placeholder} is missing")
            continue
        result = result.replace(placeholder, value)
    return result, errors


def validate(manifest_path: Path, compose_path: Path) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    notes: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot read manifest {manifest_path}: {error}"], notes

    runtime = manifest.get("runtime")
    if runtime not in {"docker", "mixed"}:
        notes.append(f"runtime={runtime!r}; Docker Compose contract is not applicable")
        return violations, notes

    if not compose_path.is_file():
        return [f"missing Compose source: {compose_path}"], notes

    template = compose_path.read_text()
    images = image_values(template)
    if len(images) != 1:
        violations.append(f"expected exactly one application image, found {len(images)}")
    if not re.search(r"(?m)^ {4}image:\s*\{\{IMAGE\}\}\s*$", template):
        violations.append("application image must be exactly `image: {{IMAGE}}`")
    if "${" in template:
        violations.append("Compose template contains a `${VARIABLE}` reference")
    for placeholder in REQUIRED_PLACEHOLDERS:
        if placeholder not in template:
            violations.append(f"missing placeholder: {placeholder}")

    names = {name.lower() for name in service_names(template)}
    if any("postgres" in name or name == "postgre" for name in names):
        violations.append("Compose defines a PostgreSQL service")
    if re.search(r"(?im)^\s*-\s*[^#\n]*postgres(?:ql)?[^#\n]*$", template):
        violations.append("Compose contains a PostgreSQL data volume")
    if re.search(r"(?im)\bPOSTGRES_[A-Z0-9_]*\b", template):
        violations.append("Compose contains a POSTGRES_* environment variable")
    if re.search(r"(?im)(?:^|\s)(?:-\s*)?DATABASE_URL\s*[:=]", template):
        violations.append("Compose contains a direct DATABASE_URL value")
    if any(
        re.search(r"ghcr\.io/[^ \t\n:{}]+(?::[^ \t\n{}]+|@sha256:[^ \t\n{}]+)", image)
        for image in images
    ):
        violations.append("Compose contains a hardcoded ghcr.io image version")

    postgres = manifest.get("postgres") or {}
    expected_network = postgres.get("network_name")
    if not isinstance(expected_network, str) or not expected_network:
        violations.append("manifest postgres.network_name is missing")
    else:
        network_block = re.search(
            r"(?ms)^networks:\s*\n(?P<body>(?:^[ \t]+.*\n?)*)", template
        )
        if not network_block or not re.search(
            r"(?m)^\s+external:\s*true\s*$", network_block.group("body")
        ):
            violations.append("Compose must declare an external PostgreSQL network")
        if compose_network_name(template) != expected_network:
            violations.append(
                "Compose external network name does not match "
                f"manifest postgres.network_name ({expected_network})"
            )

    materialized, materialization_errors = materialize(template, manifest)
    violations.extend(materialization_errors)
    image = manifest.get("image")
    if not isinstance(image, str) or not image:
        violations.append("manifest image is missing")
    elif image not in materialized:
        violations.append("materialized Compose does not contain manifest image")
    if any(value in materialized for value in PLACEHOLDER_VALUES):
        violations.append("materialized Compose still contains an unresolved placeholder")

    if not violations and shutil.which("docker"):
        with tempfile.TemporaryDirectory(prefix="myinstall-compose-") as directory:
            rendered = Path(directory) / "compose.yml"
            rendered.write_text(materialized)
            result = subprocess.run(
                ["docker", "compose", "-f", str(rendered), "config"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip().splitlines()
                violations.append(
                    "docker compose config failed"
                    + (f": {detail[-1]}" if detail else "")
                )
            else:
                notes.append("docker compose config: passed")
    elif not violations:
        notes.append("docker compose config: skipped (Docker unavailable)")

    return violations, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--compose", type=Path, required=True)
    args = parser.parse_args()

    violations, notes = validate(args.manifest, args.compose)
    print("contract violations:")
    if violations:
        print("\n".join(f"- {violation}" for violation in violations))
    else:
        print("- none")
    print("file checked:", args.compose)
    print("validation:", "failed" if violations else "passed")
    print("release allowed:", "no" if violations else "yes")
    for note in notes:
        print("note:", note)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
