# API contract

The stable integration surface for skills and application installers is the
JSON CLI. Human-readable output is not an API.

## Read-only

```text
myinstall plan --manifest PATH
myinstall doctor --manifest PATH
myinstall check --manifest PATH
myinstall secret status --manifest PATH
myinstall apps list --root PATH
myinstall apps check --root PATH
myinstall apps doctor --root PATH
```

These commands do not change the application repository, secret file, Compose
file, data directory, image or running containers.

## Mutating

```text
myinstall install --manifest PATH --confirm
myinstall upgrade --manifest PATH [--version VERSION|--image IMAGE] --confirm
myinstall rollback --manifest PATH --confirm
myinstall remove --manifest PATH --confirm
myinstall apps upgrade --root PATH --confirm
myinstall app install --manifest-url HTTPS_URL --confirm
myinstall secret ensure --manifest PATH
myinstall secret rotate --manifest PATH --name database --confirm
myinstall secret remove --manifest PATH --name KEY --confirm
```

All mutating operations acquire the per-application lock. Secret values and
connection strings are never present in JSON output or command arguments.

## Ownership

Applications own their manifest, release artifact, health, and migration
contract. This project owns host paths, secret lifecycle, shared PostgreSQL
infrastructure and app credentials, runtime lifecycle, locks, rollback and
redacted diagnostics. Skills describe usage; CI/CD publishes immutable
artifacts and images.

When `release_source` is present, stack-level commands discover existing
manifests and query GitHub Releases directly. They do not create a local
application registry or require a separate update server.

For a shared PostgreSQL cluster, the manifest declares `postgres.mode=shared`,
the infrastructure Compose contract and the app-specific database/role.
Install/upgrade/remove must never destroy, stop, recreate, or `down` the
cluster, and must never reuse another application's data directory.

## Runtime values

`runtime=native` installs an executable artifact without managing a service.
`runtime=systemd` manages a Linux systemd unit. `runtime=launchd` manages a
macOS launch agent. `runtime=docker` manages app-only Compose and requires an
immutable `vX.Y.Z` tag or digest. `runtime=mixed` may use both an image and a
native sidecar. `runtime=none` only provisions host state and secrets.
