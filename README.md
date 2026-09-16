# myinstall

Единая host-side utility для установки приложений на серверах пользователей.
Сам `myinstall` — native CLI, не Docker-приложение. Он может использовать
Docker/Compose как один из runtime adapters устанавливаемого приложения, но
не требует Docker для запуска собственной CLI или для native/systemd
проектов.

Latest release: `v0.3.5`

- Install contract: [docs/INTEGRATION.md](docs/INTEGRATION.md)
- Platform matrix: [PLATFORMS.md](PLATFORMS.md)
- API contract: [API.md](API.md)
- Releases: https://github.com/dimark57/myinstall/releases

Приложения не вендорят собственный bootstrap и не создают PostgreSQL secrets.
Они поставляют только `deploy/bootstrap/manifest.json` и Compose contract.
Skills (`cd`, `nas-layout`, `project-bootstrap`, `application-audit`) используют
этот проект как общий API/CLI.

## Responsibilities

```text
CI/CD:             test → build → publish immutable artifact/image
myinstall:  validate → secrets → PostgreSQL → deploy → migrate → health
application:      read runtime configuration
```

Canonical runtime layout:

```text
/srv/nas/stacks/<zone>/<app>/
/srv/nas/data/<app>/
/srv/nas/secrets/<app>.env
```

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
and immutable image delivery.
Application Compose must not contain a PostgreSQL service. Install, upgrade,
rollback, and remove never delete, recreate, stop, or `down` the shared stack.
PostgreSQL data migration is an explicit operator workflow; it is never an
implicit `pg_dump`/`pg_restore`.

## Usage

```bash
myinstall plan --manifest deploy/bootstrap/manifest.json
myinstall install --manifest deploy/bootstrap/manifest.json --confirm
myinstall upgrade --manifest deploy/bootstrap/manifest.json \
  --version v1.2.3 --confirm
myinstall rollback --manifest deploy/bootstrap/manifest.json --confirm
myinstall doctor --manifest deploy/bootstrap/manifest.json
myinstall secret rotate --manifest deploy/bootstrap/manifest.json --name database --confirm
myinstall remove --manifest deploy/bootstrap/manifest.json --confirm
myinstall mytask
myinstall apps check --root /srv/nas/stacks
myinstall apps upgrade --root /srv/nas/stacks --confirm
```

`myinstall <app>` finds the application's manifest in the canonical NAS roots.
It installs an absent application and upgrades an installed application to the
latest release. Use `sudo myinstall <app>` only when the operator has
intentionally prepared the target with elevated privileges; the command does
not grant or manage sudo permissions itself.

The application bootstrap downloads a pinned `myinstall` release bundle and
verifies its SHA-256. Target prerequisites depend on the manifest runtime:
Docker/Compose only for `runtime=docker|mixed`; native/systemd projects do not
need Docker.

## Layout

- `src/myinstall/` — public CLI and runtime adapters;
- `schema/` — versioned application manifest schema;
- `templates/application/` — files generated into application repositories;
  Docker Compose template is used only for `runtime=docker|mixed`;
- `templates/infrastructure/postgres/compose.yml` — canonical shared
  PostgreSQL 16 infrastructure stack;
- `examples/` — complete application integration examples;
- `docs/NAS_CONSUMER_CONTRACT.md` — NAS application ownership and cutover rules;
- `docs/NAS_INFRASTRUCTURE_CONTRACT.md` — infrastructure/application ownership;
- `docs/NAS_APPLICATION_MIGRATION_STATUS.md` — consumer cutover inventory;
- `docs/SHARED_POSTGRES_MIGRATION.md` — explicit legacy-instance migration
  runbook;
- `.github/workflows/` — test and immutable release automation;
- `tests/` — deterministic, no-Docker smoke tests.

No production secret values belong in this repository, manifests, images, or
CI logs.
