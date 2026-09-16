from __future__ import annotations

import json
import os
import stat
import tempfile
import urllib.error
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

    def test_registry_login_uses_dedicated_ghcr_token(self) -> None:
        completed = type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()
        with patch.dict(
            os.environ,
            {
                "MYINSTALL_GITHUB_TOKEN": "source-token",
                "MYINSTALL_GHCR_TOKEN": "ghcr-token",
                "MYINSTALL_GHCR_USER": "ghcr-user",
            },
            clear=True,
        ), patch("myinstall.runtime.subprocess.run", return_value=completed) as run_mock:
            self.assertTrue(runtime.ensure_registry_login("ghcr.io/example/demo:v1.2.3"))

        self.assertEqual(run_mock.call_args.kwargs["input"], "ghcr-token\n")
        self.assertEqual(run_mock.call_args.args[0][4], "ghcr-user")

    def test_run_result_preserves_stderr_and_stdout_diagnostics(self) -> None:
        completed = type(
            "Completed",
            (),
            {"returncode": 1, "stderr": "migration warning", "stdout": "alembic detail"},
        )()
        with patch("myinstall.runtime.subprocess.run", return_value=completed):
            ok, diagnostic = runtime.run_result(["migration"])

        self.assertFalse(ok)
        self.assertIn("migration warning", diagnostic)
        self.assertIn("alembic detail", diagnostic)

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
        with patch(
            "myinstall.postgres.ensure_shared",
            return_value=(True, {**values, "DATABASE_PASSWORD": "existing"}, "shared PostgreSQL verified"),
        ) as mocked:
            ok, updated, state = postgres.provision(data, values)
        self.assertTrue(ok)
        self.assertEqual(state, "shared PostgreSQL verified")
        self.assertEqual(updated["DATABASE_PASSWORD"], "existing")
        mocked.assert_called_once_with(data, values)

    def test_manifest_rejects_unknown_runtime(self) -> None:
        value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        value["runtime"] = "unknown"
        self.manifest_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            manifest.load(self.manifest_path)

    def test_immutable_image_requires_digest_or_semver_tag(self) -> None:
        self.assertTrue(manifest.immutable_image("ghcr.io/example/demo:v1.2.3"))
        self.assertTrue(manifest.immutable_image("ghcr.io/example/demo@sha256:" + "a" * 64))
        self.assertFalse(manifest.immutable_image("ghcr.io/example/demo@not-a-digest"))

    def test_compose_contract_rejects_application_postgres(self) -> None:
        compose = self.root / "docker-compose.yml"
        compose.write_text(
            "services:\n  postgres:\n    image: postgres:16\n"
            "  app:\n    image: ghcr.io/example/demo:v1.2.3\n"
            "    volumes:\n      - /srv/nas/secrets/demo.env:/run/demo.env:ro\n",
            encoding="utf-8",
        )
        data = manifest.load(self.manifest_path)
        data.update({"runtime": "docker", "image": "ghcr.io/example/demo:v1.2.3"})
        self.assertTrue(any("must not own shared PostgreSQL" in error for error in runtime.validate_compose(compose, data)))

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

    def test_github_unauthorized_response_identifies_token_problem(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.github.com/user",
            401,
            "Unauthorized",
            {},
            None,
        )
        with patch("myinstall.github.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(github.GitHubAuthError) as raised:
                github._request("https://api.github.com/user")
        self.assertIn("expired", str(raised.exception))

    def test_discovery_reads_manifests_without_registry(self) -> None:
        root = self.root / "stacks"
        manifest_path = root / "demo" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(self.manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
        discovered = discovery.load_all([root])
        self.assertEqual([data["app"] for _, data in discovered], ["demo"])

    def _shared_data(self) -> dict[str, object]:
        data = manifest.load(self.manifest_path)
        admin_secret = self.root / "postgres.env"
        admin_secret.write_text("POSTGRES_PASSWORD=admin-password\n", encoding="utf-8")
        os.chmod(admin_secret, 0o600)
        data["postgres"] = {
            "mode": "shared",
            "cluster_name": "infrastructure",
            "infrastructure_compose_path": "/srv/nas/stacks/infrastructure/compose.yml",
            "service_name": "postgres",
            "network_name": "nas-infra",
            "admin_user": "postgres",
            "admin_database": "postgres",
            "admin_secret_path": str(admin_secret),
            "admin_password_key": "POSTGRES_PASSWORD",
            "app_role": "demo",
            "app_database": "demo",
            "role_password_key": "DATABASE_PASSWORD",
            "database_url_key": "DATABASE_URL",
            "host": "postgres",
        }
        return data

    def test_shared_manifest_contract_requires_safe_fields(self) -> None:
        data = self._shared_data()
        del data["postgres"]["network_name"]
        self.assertTrue(postgres.validate_config(data))

    def test_shared_cluster_absent_is_started_once(self) -> None:
        data = self._shared_data()
        values: dict[str, str] = {}
        with patch("myinstall.postgres.cluster_exists", return_value=False), \
             patch("myinstall.postgres.wait_healthy", return_value=True), \
             patch("myinstall.postgres.tcp_ready", return_value=True), \
             patch("myinstall.postgres.run_result", side_effect=[
                 (True, ""), (True, ""), (True, ""), (True, "1"), (True, "")
             ]), \
             patch("myinstall.postgres.run", return_value=True) as run_mock:
            ok, updated, _ = postgres.ensure_shared(data, values)
        self.assertTrue(ok)
        self.assertIn("DATABASE_PASSWORD", updated)
        self.assertTrue(any("up" in call.args[0] and "-d" in call.args[0] for call in run_mock.call_args_list))

    def test_shared_existing_cluster_does_not_start_or_change_password(self) -> None:
        data = self._shared_data()
        values = {
            "DATABASE_PASSWORD": "existing",
            "DATABASE_URL": "postgresql://demo:existing@postgres:5432/demo",
        }
        with patch("myinstall.postgres.cluster_exists", return_value=True), \
             patch("myinstall.postgres.wait_healthy", return_value=True), \
             patch("myinstall.postgres.tcp_ready", return_value=True), \
             patch("myinstall.postgres.run_result", side_effect=[
                 (True, ""), (True, "1"), (True, "1")
             ]), \
             patch("myinstall.postgres.run", return_value=True) as run_mock:
            ok, updated, _ = postgres.ensure_shared(data, values)
        self.assertTrue(ok)
        self.assertEqual(updated["DATABASE_PASSWORD"], "existing")
        self.assertFalse(any(" up " in f" {call.args[0]} " for call in run_mock.call_args_list))
        self.assertFalse(any("CREATE ROLE" in str(call.kwargs.get("input_text", "")) for call in run_mock.call_args_list))

    def test_app_compose_rejects_postgres_service(self) -> None:
        source = self.project / "deploy" / "bootstrap" / "stack-compose.yml"
        source.write_text("services:\n  postgres:\n    image: postgres:16\n", encoding="utf-8")
        data = manifest.load(self.manifest_path)
        data.update({"runtime": "docker", "image": "ghcr.io/example/demo:v1.2.3"})
        errors = runtime.validate_compose(source, data)
        self.assertIn("shared PostgreSQL", " ".join(errors))

    def test_shared_compose_rejects_admin_environment_and_missing_network(self) -> None:
        source = self.project / "deploy" / "bootstrap" / "stack-compose.yml"
        source.write_text(
            "services:\n"
            "  app:\n"
            "    image: ghcr.io/example/demo:v1.2.3\n"
            "    environment:\n"
            "      POSTGRES_PASSWORD: leaked\n",
            encoding="utf-8",
        )
        data = self._shared_data()
        data.update({"runtime": "docker", "image": "ghcr.io/example/demo:v1.2.3"})
        errors = runtime.validate_compose(source, data)
        self.assertIn("PostgreSQL admin environment", " ".join(errors))
        self.assertIn("nas-infra", " ".join(errors))

    def test_rotation_rolls_back_without_secret_output(self) -> None:
        data = self._shared_data()
        values = {
            "DATABASE_URL": "postgresql://demo:old-password@postgres:5432/demo",
        }
        with patch("myinstall.postgres.run", side_effect=[True, False, True]) as run_mock, \
            patch(
                "myinstall.postgres.secret_store.read",
                return_value={"POSTGRES_PASSWORD": "admin-password"},
            ):
            ok, updated, state = postgres.rotate(
                "/srv/nas/stacks/infrastructure/compose.yml", data, values
            )
        self.assertFalse(ok)
        self.assertEqual(state, "rotation_failed")
        self.assertEqual(updated, values)
        self.assertNotIn("old-password", state)


if __name__ == "__main__":
    unittest.main()
