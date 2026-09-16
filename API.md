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
myinstall upgrade --manifest PATH --image IMAGE --confirm
myinstall secret ensure --manifest PATH
myinstall secret rotate --manifest PATH --name database --confirm
myinstall secret remove --manifest PATH --name KEY --confirm
```

All mutating operations acquire the per-application lock. Secret values and
connection strings are never present in JSON output or command arguments.

## Ownership

Applications own their manifest and health/migration contract. This project
owns host paths, secret lifecycle, PostgreSQL credentials, Compose lifecycle,
locks, rollback and redacted diagnostics. `cd` owns release/tag/image
publication; `application-audit` owns read-only cross-skill verification.

For a shared PostgreSQL cluster, the manifest declares `postgres.mode=shared`,
the cluster adapter and the app-specific database/role. Install/upgrade/remove
must never destroy the cluster or reuse another application's data directory.
