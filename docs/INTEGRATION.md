# Application integration contract

An application integrates with `myinstall` through one versioned manifest:

```text
deploy/bootstrap/manifest.json
deploy/bootstrap/install.sh
deploy/bootstrap/stack-compose.yml   # docker/mixed only
deploy/bootstrap/app                 # native/systemd/launchd artifact
```

The application owns its release artifact, health endpoint, migrations, and
application-specific configuration. `myinstall` owns host paths, generated
secrets, locking, application runtime lifecycle, application credentials,
redacted diagnostics, and rollback orchestration. The NAS infrastructure owner
owns the PostgreSQL service, Docker networks, storage, backups, Caddy, and DNS.
The application owns only its database/role declaration; its Compose must not
contain a PostgreSQL service.

## Install flow

```text
application repository
  -> pinned myinstall release
  -> manifest validation
  -> host directories and secrets
  -> PostgreSQL provision/check
  -> runtime adapter install
  -> migrations
  -> healthcheck
```

The bootstrap must pin both the `myinstall` release URL and its SHA-256:

```bash
MYINSTALL_URL="https://github.com/dimark57/myinstall/releases/download/v0.3.5/myinstall-v0.3.5-linux-amd64"
MYINSTALL_SHA256="..."
```

The bootstrap downloads the executable over HTTPS, verifies the checksum, and
executes `install --manifest ... [--image IMAGE] --confirm`. CI may pass the
fresh immutable digest on first install; the manifest remains the source of
truth for the application contract.

## Manifest ownership

Required fields are the stable API:

```json
{
  "schema_version": "1.0",
  "kind": "service",
  "runtime": "systemd",
  "app": "example",
  "zone": "apps",
  "release_source": "acme/example",
  "release_channel": "stable",
  "current_version": "v1.2.3",
  "release_asset_pattern": "example-{version}-{platform}",
  "artifact": {
    "url": "https://github.com/acme/example/releases/download/v1.2.3/example-linux-amd64",
    "sha256": "..."
  },
  "install_path": "/srv/nas/stacks/apps/example/releases/current/example",
  "service_name": "example",
  "stack_path": "/srv/nas/stacks/apps/example",
  "data_path": "/srv/nas/data/example",
  "secret_path": "/srv/nas/secrets/example.env",
  "secret_mount": "/run/example.env",
  "required_secrets": ["DATABASE_URL"],
  "generated_secrets": [],
  "healthcheck": {"url": "http://127.0.0.1:8080/health"}
}
```

Docker applications replace `artifact` and service fields with `image` and
`compose_source`. Docker image references must use a tag plus digest or a
digest directly; mutable tags such as `latest` are rejected.

For `postgres.mode=shared`, the stable fields are `cluster_name`,
`infrastructure_compose_path`, `service_name`, `network_name`, `admin_user`,
`admin_database`, `admin_secret_path`, `admin_password_key`, `app_role`,
`app_database`, `role_password_key`, and `database_url_key`. Infrastructure
admin credentials stay in the infrastructure secret and are never copied to
the application secret. Docker applications join the external `nas-infra`
network; their Compose reads `DATABASE_URL` through the mounted app secret
file.

## Commands used by other applications

```bash
myinstall plan --manifest deploy/bootstrap/manifest.json
myinstall install --manifest deploy/bootstrap/manifest.json --confirm
myinstall upgrade --manifest deploy/bootstrap/manifest.json --version v1.2.4 --confirm
myinstall rollback --manifest deploy/bootstrap/manifest.json --confirm
myinstall remove --manifest deploy/bootstrap/manifest.json --confirm
myinstall apps check --root /srv/nas/stacks
myinstall apps upgrade --root /srv/nas/stacks --confirm
myinstall doctor --manifest deploy/bootstrap/manifest.json
```

All commands emit JSON. Secret values and credentials are never emitted.
Application repositories should treat the JSON fields as the machine-readable
contract and avoid parsing human-readable stderr.

## Upgrade flow

The release publisher creates a new immutable application artifact or image.
An operator or scheduler updates the manifest release reference and invokes
`upgrade`. `myinstall` stages the new version, runs migrations according to
the manifest policy, restarts the service/runtime, and verifies health. A
failed verification triggers a checked rollback to the previous generation.

For stack-wide checks, `myinstall` discovers manifests directly from canonical
stack paths and queries each `release_source` on GitHub. It does not create or
require a local application registry or a separate update server.

Database data is never removed by install, upgrade, rollback, or remove.
Destructive schema changes require an application-owned migration policy and
backup strategy. `myinstall` performs readiness and connection checks only; it
does not implicitly run `pg_dump`, `pg_restore`, or replace existing
PostgreSQL containers. Shared PostgreSQL upgrades require a separate explicit
infrastructure operation.
