from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from myinstall import discovery, github, manifest, postgres, runtime, secrets


class CoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="myinstall-"))
        self.project = self.root / "project"
        (self.project / "deploy" / "bootstrap").mkdir(parents=True)
        self.secret = self.root / "secrets" / "demo.env"
        self.data = self.root / "data" / "demo"
        self.stack = self.root / "stack" / "demo"
        self.manifest_path = self.project / "deploy" / "bootstrap" / "manifest.json"
        self.manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "runtime": "native",
                    "app": "demo",
                    "zone": "apps",
                    "artifact": {
                        "url": "https://github.com/example/demo/releases/download/v1/demo",
                        "sha256": "a" * 64,
                    },
                    "install_path": "/srv/nas/stacks/apps/demo/releases/current/demo",
                    "stack_path": "/srv/nas/stacks/apps/demo",
                    "data_path": "/srv/nas/data/demo",
                    "secret_path": str(self.secret),
                    "secret_mount": "/run/demo.env",
                    "required_secrets": ["DATABASE_URL"],
                    "generated_secrets": [{"name": "APP_TOKEN", "length": 32}],
                    "healthcheck": {"url": "http://127.0.0.1:9/health"},
                }
            ),
            encoding="utf-8",
        )

    def test_manifest_and_secret_ensure_are_idempotent(self) -> None:
        data = manifest.load(self.manifest_path)
        production_data = {**data, "secret_path": "/srv/nas/secrets/demo.env"}
        self.assertEqual(manifest.validate_paths(production_data), [])
        self.assertEqual(secrets.ensure(data), ["APP_TOKEN"])
        first = self.secret.read_text(encoding="utf-8")
        self.assertEqual(secrets.ensure(data), [])
        self.assertEqual(first, self.secret.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(self.secret.stat().st_mode), 0o600)

    def test_secret_status_contains_names_only(self) -> None:
        self.secret.parent.mkdir(parents=True)
        self.secret.write_text("DATABASE_URL=postgresql://u:private@db/app\n", encoding="utf-8")
        os.chmod(self.secret, 0o600)
        status = secrets.status(manifest.load(self.manifest_path))
        self.assertEqual(status["keys"], ["DATABASE_URL"])
        self.assertNotIn("private", json.dumps(status))

    def test_compose_renderer_materializes_runtime_contract(self) -> None:
        source = self.project / "deploy" / "bootstrap" / "stack-compose.yml"
        source.write_text(
            "services:\n"
            "  app:\n"
            "    image: {{IMAGE}}\n"
            "    volumes:\n"
            "      - {{SECRET_PATH}}:{{SECRET_MOUNT}}:ro\n",
            encoding="utf-8",
        )
        data = manifest.load(self.manifest_path)
        data.update(
            {
                "runtime": "docker",
                "image": "ghcr.io/example/demo@sha256:" + "a" * 64,
                "stack_path": str(self.stack),
            }
        )
        target = runtime.materialize(self.manifest_path, data)
        rendered = target.read_text(encoding="utf-8")
        self.assertIn("ghcr.io/example/demo@sha256:" + "a" * 64, rendered)
        self.assertIn("/run/demo.env", rendered)
        self.assertNotIn("{{", rendered)

    def test_docker_runtime_requires_immutable_release_reference(self) -> None:
        data = manifest.load(self.manifest_path)
        data.update({"runtime": "docker", "image": "ghcr.io/example/demo:v1.2.3"})
        data["secret_path"] = "/srv/nas/secrets/demo.env"
        self.assertEqual(manifest.validate_paths(data), [])
        data["image"] = "ghcr.io/example/demo:latest"
        self.assertIn("immutable image", " ".join(manifest.validate_paths(data)))

    def test_shared_postgres_uses_admin_compose_and_existing_password(self) -> None:
        data = manifest.load(self.manifest_path)
        data["postgres"] = {
            "mode": "shared",
            "admin_compose_path": "/srv/nas/stacks/services/postgres/docker-compose.yml",
            "service": "postgres",
            "role": "demo",
            "database": "demo",
            "database_url_key": "DATABASE_URL",
            "role_password_key": "DATABASE_PASSWORD",
            "host": "shared-postgres",
        }
        values = {"DATABASE_URL": "postgresql://demo:existing@shared-postgres:5432/demo"}
        with patch("myinstall.postgres.run", return_value=True) as mocked:
            ok, updated, state = postgres.provision(data, values)
        self.assertTrue(ok)
        self.assertEqual(state, "postgres provisioned")
        self.assertEqual(updated["DATABASE_PASSWORD"], "existing")
        command = mocked.call_args.args[0]
        self.assertIn("/srv/nas/stacks/services/postgres/docker-compose.yml", command)
        self.assertNotIn("/srv/nas/data", " ".join(command))

    def test_manifest_rejects_unknown_runtime(self) -> None:
        value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        value["runtime"] = "unknown"
        self.manifest_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            manifest.load(self.manifest_path)

    def test_secret_parser_rejects_duplicate_keys(self) -> None:
        self.secret.parent.mkdir(parents=True)
        self.secret.write_text("A=one\nA=two\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            secrets.read(self.secret)

    def test_github_release_selects_platform_asset(self) -> None:
        payload = json.dumps(
            {
                "tag_name": "v1.2.3",
                "prerelease": False,
                "assets": [
                    {"name": "myapp-darwin-arm64", "browser_download_url": "https://example.test/app"},
                ],
            }
        ).encode()
        with patch("myinstall.github._request", return_value=(200, payload, '"etag"')):
            release = github.latest("acme/myapp")
        with patch("myinstall.github.platform_name", return_value="darwin-arm64"):
            selected = github.asset(release, "myapp-{platform}")
        self.assertEqual(selected["name"], "myapp-darwin-arm64")

    def test_discovery_reads_manifests_without_registry(self) -> None:
        root = self.root / "stacks"
        manifest_path = root / "demo" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(self.manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
        discovered = discovery.load_all([root])
        self.assertEqual([data["app"] for _, data in discovered], ["demo"])


if __name__ == "__main__":
    unittest.main()
