# API contract

The stable integration surface for skills and application installers is the
JSON CLI. Human-readable output is not an API.

## Read-only

```text
myinstall plan --manifest PATH
myinstall doctor --manifest PATH
myinstall check --manifest PATH
myinstall secret status --manifest PATH
```

These commands do not change the application repository, secret file, Compose
file, data directory, image or running containers.

## Mutating

```text
myinstall install --manifest PATH --confirm
myinstall upgrade --manifest PATH [--version VERSION|--image IMAGE] --confirm
myinstall rollback --manifest PATH --confirm
myinstall secret ensure --manifest PATH
myinstall secret rotate --manifest PATH --name database --confirm
myinstall secret remove --manifest PATH --name KEY --confirm
```

All mutating operations acquire the per-application lock. Secret values and
connection strings are never present in JSON output or command arguments.

## Ownership

Applications own their manifest, release artifact, health, and migration
contract. This project owns host paths, secret lifecycle, PostgreSQL
credentials, runtime lifecycle, locks, rollback and redacted diagnostics.
Release artifacts are published through immutable GitHub Releases.

For a shared PostgreSQL cluster, the manifest declares `postgres.mode=shared`,
the cluster adapter and the app-specific database/role. Install/upgrade/remove
must never destroy the cluster or reuse another application's data directory.

## Runtime values

`runtime=native` installs an executable artifact without managing a service.
`runtime=systemd` manages a Linux systemd unit. `runtime=launchd` manages a
macOS launch agent. `runtime=docker` manages Compose and requires an immutable
image. `runtime=mixed` may use both an image and a native sidecar. `runtime=none`
only provisions host state and secrets.
