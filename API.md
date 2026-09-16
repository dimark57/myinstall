# API contract

The stable integration surface for skills and application installers is the
JSON CLI. Human-readable output is not an API.

Application publication and release discovery follow
[the GitHub application release contract](docs/GITHUB_APPLICATION_RELEASE_CONTRACT.md).

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
myinstall install --manifest PATH [--image IMAGE] --confirm
myinstall upgrade --manifest PATH [--version VERSION|--image IMAGE] --confirm
myinstall rollback --manifest PATH --confirm
myinstall remove --manifest PATH --confirm
myinstall apps upgrade --root PATH --confirm
myinstall app install --manifest-url HTTPS_URL --confirm
myinstall APP
myinstall --help
myinstall --update
myinstall APP --update
myinstall secret ensure --manifest PATH
myinstall secret rotate --manifest PATH --name database --confirm
myinstall secret remove --manifest PATH --name KEY --confirm
```

All mutating operations acquire the per-application lock. Secret values and
connection strings are never present in JSON output or command arguments.

`myinstall APP` is the idempotent operator entrypoint: it discovers the
application manifest, installs when the runtime is absent, and upgrades to the
latest release when the runtime is already installed. `sudo myinstall APP`
uses the same behavior with privileges supplied by the operator; myinstall
does not alter sudoers or acquire privileges implicitly.

`--help` and `--update` are internal `myinstall` commands. `APP` is always the
positional application selector, and `myinstall APP --update` updates that
application. Positional tokens are never interpreted as internal commands.

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
the infrastructure Compose contract, the `nas-infra` network, a separate
admin secret, and the app-specific database/role. App Compose must not declare
PostgreSQL services, `POSTGRES_*` variables, or `DATABASE_URL` values.
Install/upgrade/remove must never destroy, stop, recreate, or `down` the
cluster, and must never reuse another application's data directory.

## Runtime values

`runtime=native` installs an executable artifact without managing a service.
`runtime=systemd` manages a Linux systemd unit. `runtime=launchd` manages a
macOS launch agent. `runtime=docker` manages app-only Compose and requires an
immutable `vX.Y.Z` tag or digest. `runtime=mixed` may use both an image and a
native sidecar. `runtime=none` only provisions host state and secrets.
