# myinstall

Единый host-side runtime manager для приложений, устанавливаемых на серверах
пользователей.

Приложения не вендорят собственный bootstrap и не создают PostgreSQL secrets.
Они поставляют только `deploy/bootstrap/manifest.json` и Compose contract.
Skills (`cd`, `nas-layout`, `project-bootstrap`, `application-audit`) используют
этот проект как общий API/CLI.

## Responsibilities

```text
CI/CD:             test → build → push immutable image
myinstall:  install → secrets → PostgreSQL → deploy → health
application:      read mounted runtime configuration
```

Canonical runtime layout:

```text
/srv/nas/stacks/<zone>/<app>/
/srv/nas/data/<app>/
/srv/nas/secrets/<app>.env
```

PostgreSQL is a shared infrastructure service. Each application gets its own
database and role; an application manifest must never own or remove the shared
cluster or its data volume. `myinstall` serializes role/password
operations per application and uses the PostgreSQL cluster adapter.

## Usage

```bash
myinstall plan --manifest deploy/bootstrap/manifest.json
myinstall install --manifest deploy/bootstrap/manifest.json --confirm
myinstall upgrade --manifest deploy/bootstrap/manifest.json \
  --image ghcr.io/org/app:v1.2.3 --confirm
myinstall doctor --manifest deploy/bootstrap/manifest.json
myinstall secret rotate --manifest deploy/bootstrap/manifest.json --name database --confirm
```

The application installer downloads a pinned release bundle and verifies its
SHA-256. The target host therefore needs Docker/Compose, but does not need
`myinstall` preinstalled.

## Layout

- `src/myinstall/` — public CLI and runtime adapters;
- `schema/` — versioned application manifest schema;
- `templates/application/` — files generated into application repositories;
- `tests/` — deterministic, no-Docker smoke tests.

No production secret values belong in this repository, manifests, images, or
CI logs.
