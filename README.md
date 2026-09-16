# myinstall

Единая host-side utility для установки приложений на серверах пользователей.
Сам `myinstall` — native CLI, не Docker-приложение. Он может использовать
Docker/Compose как один из runtime adapters устанавливаемого приложения, но
не требует Docker для запуска собственной CLI или для native/systemd
проектов.

Latest release: `v0.3.18`

- Install contract: [docs/INTEGRATION.md](docs/INTEGRATION.md)
- GitHub application release contract: [docs/GITHUB_APPLICATION_RELEASE_CONTRACT.md](docs/GITHUB_APPLICATION_RELEASE_CONTRACT.md)
- Application CLI contract: [docs/APPLICATION_CLI_CONTRACT.md](docs/APPLICATION_CLI_CONTRACT.md)
- Upgrade error catalog: [docs/UPGRADE_ERROR_CODES.md](docs/UPGRADE_ERROR_CODES.md)
- Platform matrix: [PLATFORMS.md](PLATFORMS.md)
- API contract: [API.md](API.md)
- Releases: https://github.com/dimark57/myinstall/releases

Приложения не вендорят собственный bootstrap и не создают PostgreSQL secrets.
Они поставляют только `deploy/bootstrap/manifest.json` и Compose contract.
Skills (`cd`, `nas-layout`, `project-bootstrap`, `application-audit`) используют
этот проект как общий API/CLI.

## Responsibilities

```text
CI/CD:             test → build → release (immutable artifact/image)
myinstall:  validate → secrets → PostgreSQL → manual deploy → migrate → health
application:      read runtime configuration
```

Canonical runtime layout:

```text
Linux:
/srv/nas/stacks/utilites/<app>/
/srv/nas/data/<app>/
/srv/nas/secrets/<app>.env

macOS:
~/nas/stacks/utilites/<app>/
~/nas/data/<app>/
~/nas/secrets/<app>.env
```

New applications always use their own directory under `stacks/utilites`; the
directory name is intentionally `utilites`. Legacy `/Volumes/Nas` and
`stacks/apps` paths are not used for new-machine installs.

PostgreSQL is a shared infrastructure service. Each application declares only
its database and LOGIN role:

```json
"postgres": {
  "mode": "shared",
  "cluster_name": "infrastructure",
  "infrastructure_compose_path": "/srv/nas/stacks/infrastructure/postgres/compose.yml",
  "service_name": "postgres",
  "network_name": "nas-infra",
  "admin_user": "postgres",
  "admin_database": "postgres",
  "app_role": "demo",
  "app_database": "demo",
  "role_password_key": "DATABASE_PASSWORD",
  "database_url_key": "DATABASE_URL",
  "host": "postgres"
}
```

`myNAS` owns the shared PostgreSQL service lifecycle, storage, networks, and
backups. `myinstall` provisions and rotates only application roles, databases,
and credentials through the infrastructure contract. The application owns only
its declaration. Skills describe the usage contract, while CI/CD owns release
and immutable image publication. The operator connects to the target server
and runs `myinstall <app> --update`; runtime auto-deploy is an explicit
project-level exception.
Application Compose must not contain a PostgreSQL service. Install, upgrade,
rollback, and uninstall never delete, recreate, stop, or `down` the shared stack.
PostgreSQL data migration is an explicit operator workflow; it is never an
implicit `pg_dump`/`pg_restore`.

`uninstall` stops and deletes only the application runtime and generated wrapper.
Application data and secrets are preserved by default. `--purge-data` and
`--purge-secrets` explicitly delete those application-owned resources; shared
PostgreSQL infrastructure remains untouched.

## Usage

```bash
sudo myinstall plan --manifest deploy/bootstrap/manifest.json
sudo myinstall install --manifest deploy/bootstrap/manifest.json --confirm
sudo myinstall upgrade --manifest deploy/bootstrap/manifest.json \
  --version v1.2.3 --confirm
sudo myinstall rollback --manifest deploy/bootstrap/manifest.json --confirm
sudo myinstall uninstall --manifest deploy/bootstrap/manifest.json --confirm
sudo myinstall uninstall --manifest deploy/bootstrap/manifest.json --confirm \
  --purge-data --purge-secrets
sudo myinstall doctor --manifest deploy/bootstrap/manifest.json
sudo myinstall secret rotate --manifest deploy/bootstrap/manifest.json --name database --confirm
sudo myinstall mytask
sudo myinstall myqa
sudo myinstall --uninstall
myinstall --help
sudo myinstall --plan
sudo myinstall --doctor
sudo myinstall --update
sudo myinstall mytask --update
sudo myinstall auth setup
sudo myinstall auth status
sudo myinstall apps check --root /srv/nas/stacks
sudo myinstall apps upgrade --root /srv/nas/stacks --confirm
```

`myinstall <app>` first searches the canonical NAS roots. If no local manifest
exists, it resolves non-secret metadata from the public `catalog/apps.json`.
It installs an absent application and upgrades an installed application to the
latest release. Private GitHub releases require `MYINSTALL_GITHUB_TOKEN`, while
private GHCR images require `MYINSTALL_GHCR_TOKEN`; the application repository
itself is not cloned. Use `sudo myinstall <app> --update` only when the operator has
intentionally prepared the target with elevated privileges; the command does
not grant or manage sudo permissions itself.

`sudo myinstall --uninstall` removes only the host-side `myinstall` executable.
Installed applications remain untouched. The command asks whether the saved
myinstall GitHub token should also be removed; use `--purge-secrets` for a
non-interactive explicit choice.

`--help` and `--update` are internal commands of `myinstall`; an application
is always the positional token: `myinstall mytask`. Application updates use
`myinstall mytask --update`. A positional token is never treated as an
internal command.

For private applications, configure both tokens once with
`sudo myinstall auth setup`: a Fine-grained token with `Contents: Read-only`
for private source/release repositories and a Classic PAT with
`read:packages` for GHCR. It validates the hidden inputs and stores only
`/srv/nas/secrets/myinstall.env` with mode `0600`.
Check both tokens at any time with `sudo myinstall auth status`. If GitHub
returns `401` because either token expired, was revoked, or is invalid,
myinstall prints the recovery hint. The token values are never printed.

The application bootstrap downloads a pinned `myinstall` release bundle and
verifies its SHA-256. Target prerequisites depend on the manifest runtime:
Docker/Compose only for `runtime=docker|mixed`; native/systemd projects do not
need Docker.

## Layout

- `src/myinstall/` — public CLI and runtime adapters;
- `schema/` — versioned application manifest schema;
- `catalog/` — public non-secret application catalog used for first install;
- `templates/application/` — files generated into application repositories;
  Docker Compose template is used only for `runtime=docker|mixed`;
- `.cursor/skills/application-compose-contract/` — reusable application
  Compose-contract skill and validation script for Docker/mixed integrations;
- `templates/infrastructure/postgres/compose.yml` — canonical shared
  PostgreSQL 16 infrastructure stack;
- `examples/` — complete application integration examples;
- `docs/NAS_CONSUMER_CONTRACT.md` — NAS application ownership and cutover rules;
- `docs/NAS_INFRASTRUCTURE_CONTRACT.md` — infrastructure/application ownership;
- `docs/NAS_APPLICATION_MIGRATION_STATUS.md` — consumer cutover inventory;
- `docs/SHARED_POSTGRES_MIGRATION.md` — explicit legacy-instance migration
  runbook;
- `docs/UPGRADE_ERROR_CODES.md` — stable numbered upgrade stages, error codes,
  operator hints, and rollback diagnostics;
- `.github/workflows/` — test and immutable release automation;
- `AGENTS.md` — explicit CD recipe declaration for release automation;
- `tests/` — deterministic, no-Docker smoke tests.

No production secret values belong in this repository, manifests, images, or
CI logs.
