# myinstall

Единая host-side utility для установки приложений на серверах пользователей.
Сам `myinstall` — native CLI, не Docker-приложение. Он может использовать
Docker/Compose как один из runtime adapters устанавливаемого приложения, но
не требует Docker для запуска собственной CLI или для native/systemd
проектов.

Latest release: `v0.2.1`

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

PostgreSQL is a shared infrastructure service. Each application gets its own
database and role; an application manifest must never own or remove the shared
cluster or its data volume. `myinstall` serializes role/password
operations per application and uses the PostgreSQL cluster adapter.

## Usage

```bash
myinstall plan --manifest deploy/bootstrap/manifest.json
myinstall install --manifest deploy/bootstrap/manifest.json --confirm
myinstall upgrade --manifest deploy/bootstrap/manifest.json \
  --version v1.2.3 --confirm
myinstall rollback --manifest deploy/bootstrap/manifest.json --confirm
myinstall doctor --manifest deploy/bootstrap/manifest.json
myinstall secret rotate --manifest deploy/bootstrap/manifest.json --name database --confirm
```

The application bootstrap downloads a pinned `myinstall` release bundle and
verifies its SHA-256. Target prerequisites depend on the manifest runtime:
Docker/Compose only for `runtime=docker|mixed`; native/systemd projects do not
need Docker.

## Layout

- `src/myinstall/` — public CLI and runtime adapters;
- `schema/` — versioned application manifest schema;
- `templates/application/` — files generated into application repositories;
  Docker Compose template is used only for `runtime=docker|mixed`;
- `examples/` — complete application integration examples;
- `.github/workflows/` — test and immutable release automation;
- `tests/` — deterministic, no-Docker smoke tests.

No production secret values belong in this repository, manifests, images, or
CI logs.
