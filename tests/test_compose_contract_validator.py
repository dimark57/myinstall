import importlib.util
import json
from pathlib import Path


VALIDATOR = Path(__file__).parents[1] / ".cursor/skills/application-compose-contract/scripts/validate_compose_contract.py"
SPEC = importlib.util.spec_from_file_location("compose_validator", VALIDATOR)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def manifest() -> dict:
    return {
        "runtime": "docker",
        "image": "example.invalid/application:v1",
        "secret_path": "/srv/secrets/application.env",
        "secret_mount": "/run/application.env",
        "data_path": "/srv/data/application",
        "healthcheck": {"url": "http://127.0.0.1:8080/health"},
        "postgres": {"network_name": "database-network"},
    }


def compose_template() -> str:
    return """services:
  app:
    image: {{IMAGE}}
    environment:
      APP_ENV_FILE: {{SECRET_MOUNT}}
    volumes:
      - {{SECRET_PATH}}:{{SECRET_MOUNT}}:ro
      - {{DATA_PATH}}:/var/lib/application
    networks:
      - database
    healthcheck:
      test: ["CMD", "curl", "-f", "{{HEALTH_URL}}"]

networks:
  database:
    external: true
    name: database-network
"""


def write_inputs(tmp_path: Path, compose: str) -> tuple[Path, Path]:
    manifest_path = tmp_path / "manifest.json"
    compose_path = tmp_path / "stack-compose.yml"
    manifest_path.write_text(json.dumps(manifest()))
    compose_path.write_text(compose)
    return manifest_path, compose_path


def test_validator_rejects_missing_image_placeholder(tmp_path: Path) -> None:
    manifest_path, compose_path = write_inputs(
        tmp_path, compose_template().replace("image: {{IMAGE}}", "image: example:latest")
    )

    violations, _ = validator.validate(manifest_path, compose_path)

    assert any("image: {{IMAGE}}" in violation for violation in violations)


def test_validator_accepts_contract_template_without_docker(tmp_path: Path, monkeypatch) -> None:
    manifest_path, compose_path = write_inputs(tmp_path, compose_template())
    monkeypatch.setattr(validator.shutil, "which", lambda _: None)

    violations, notes = validator.validate(manifest_path, compose_path)

    assert violations == []
    assert "docker compose config: skipped (Docker unavailable)" in notes
