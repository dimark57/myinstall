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
myinstall auth status
```

These commands do not change the application repository, secret file, Compose
file, data directory, image or running containers.

## Mutating

```text
myinstall install --manifest PATH [--image IMAGE] --confirm
myinstall upgrade --manifest PATH [--version VERSION|--image IMAGE] --confirm
myinstall rollback --manifest PATH --confirm
myinstall uninstall --manifest PATH --confirm
myinstall uninstall --manifest PATH --confirm [--purge-data] [--purge-secrets]
myinstall --uninstall [--purge-secrets]
myinstall apps upgrade --root PATH --confirm
myinstall app install --manifest-url HTTPS_URL --confirm
myinstall APP
myinstall --help
myinstall --plan
myinstall --doctor
myinstall --update
myinstall APP --update
myinstall auth setup
myinstall secret ensure --manifest PATH
myinstall secret rotate --manifest PATH --name database --confirm
myinstall secret remove --manifest PATH --name KEY --confirm
```

All mutating operations acquire the per-application lock. Secret values and
connection strings are never present in JSON output or command arguments.
Interactive install, upgrade, and remove commands render progress on stderr;
JSON output remains on stdout. Progress is disabled automatically when stderr
is not a terminal or when `MYINSTALL_NO_PROGRESS=1` is set.

Upgrade failures include stable `error_code`/`reason` fields, a numbered
Russian `stage`, human-readable `message`, actionable `hint`, and
`retryable`. Automation must branch on the code rather than parse message
text. Docker upgrades distinguish image pull, runtime start, migration,
healthcheck, and rollback failures; see
[docs/UPGRADE_ERROR_CODES.md](docs/UPGRADE_ERROR_CODES.md).

`myinstall APP` is the idempotent operator entrypoint: it discovers the
application manifest locally or from the public catalog, installs when the
runtime is absent, and upgrades to the latest release when the runtime is
already installed. Private release sources use `MYINSTALL_GITHUB_TOKEN`, and
private GHCR images use `MYINSTALL_GHCR_TOKEN`.
The public catalog contains only non-secret metadata; private GitHub release
and Compose requests use that token.
`myinstall auth setup` validates two hidden token prompts—a Fine-grained token
for private GitHub repositories and a Classic PAT with `read:packages` for
GHCR—and persists them with mode `0600` in `/srv/nas/secrets/myinstall.env`.
`myinstall auth status` validates both configured tokens without printing them.
GitHub `401` responses are reported as an expired, revoked, or invalid token
and include the recovery command `sudo myinstall auth setup` plus a link to
create a replacement source or GHCR token.
`sudo myinstall APP`
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
Install/upgrade/uninstall must never destroy, stop, recreate, or `down` the
shared cluster, and must never reuse another application's data directory.
Uninstall deletes only the application runtime by default. Data and secrets are
preserved unless the operator explicitly passes `--purge-data` and/or
`--purge-secrets`.
`myinstall --uninstall` deletes the host utility itself, preserves installed
applications, and asks interactively whether its saved GitHub token should be
removed.

## Runtime values

`runtime=native` installs an executable artifact without managing a service.
`runtime=systemd` manages a Linux systemd unit. `runtime=launchd` manages a
macOS launch agent. `runtime=docker` manages app-only Compose and requires an
immutable `vX.Y.Z` tag or digest. `runtime=mixed` may use both an image and a
native sidecar. `runtime=none` only provisions host state and secrets.

New-machine application roots are `/srv/nas/stacks/utilites/<app>` on Linux
and `~/nas/stacks/utilites/<app>` on macOS. Application data and secrets are
stored under the matching `<nas-root>/data/<app>` and
`<nas-root>/secrets/<app>.env` paths.
