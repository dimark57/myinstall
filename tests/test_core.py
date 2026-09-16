from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from myinstall import manifest, secrets


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
                    "app": "demo",
                    "zone": "apps",
                    "image": "ghcr.io/example/demo:v1",
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


if __name__ == "__main__":
    unittest.main()
