# NAS consumer contract

`myinstall` is the single host-side lifecycle owner for applications that
declare the manifest contract. CI builds and publishes the immutable image;
the NAS runner invokes `myinstall`.

The NAS infrastructure owner retains Caddy/DNS, external networks, storage,
backups, the shared PostgreSQL service, and the NAS runner. The current
consumer cutover inventory is in
`docs/NAS_APPLICATION_MIGRATION_STATUS.md`.

## Required application repository files

```text
deploy/bootstrap/manifest.json
deploy/bootstrap/stack-compose.yml
deploy/bootstrap/install.sh
```

The application Compose file must contain only application services. It must
not declare the shared PostgreSQL service or mount the shared PostgreSQL data
directory. Production secrets are mounted from:

```text
/srv/nas/secrets/<app>.env
```

Every installable application publishes a SemVer GitHub Release after its
green test gate and immutable GHCR/artifact publication. The manifest
`release_source` points to that repository. A GHCR-only tag is not a complete
release because `myinstall <app>` discovers updates through GitHub Releases.
The application CLI must expose `--version`, `--help`, `--man`, `--doctor`, and
`--update`; host installation and updates remain owned by `myinstall`.

Shared PostgreSQL applications must join the external `nas-infra` network.
The canonical infrastructure Compose is provided at
`templates/infrastructure/postgres/compose.yml`; its production copy is
owned by the infrastructure/myinstall operator, not by an application stack.

## myTask status

The repo-owned myTask manifest and Compose contract use app-only Compose,
shared PostgreSQL metadata, and the read-only canonical secret mount. Its
deployment workflow must pass the immutable image digest to:

```bash
myinstall upgrade --manifest ... --version vX.Y.Z --image IMAGE@sha256:... --confirm
```

The former legacy stack under `myNAS/stacks/apps/mythings` was not equivalent
to this contract: it owned PostgreSQL, used a local `.env`, and ran Compose
directly. Its tracked files were removed from myNAS without deleting runtime
data. Use `docs/SHARED_POSTGRES_MIGRATION.md` for any remaining explicit
dump/restore cutover.

The audited `myNAS` and `mytask` worktrees contain unrelated uncommitted WIP,
including legacy stack edits and deletions. The cutover is intentionally
blocked until the owner chooses the canonical stack and migration window;
`myinstall` must not restore or delete those files automatically.

## myHealth status

The myHealth repository is available at `/Users/dmitrijstolarov/repos/myHealth`
and now provides `deploy/bootstrap/manifest.json` plus an app-only Compose
contract for the NAS test environment. Its test workflow invokes `myinstall`
with the immutable GHCR digest. Its VPS production `deploy/deploy.sh` flow
remains separate by design.

myHealth does not declare PostgreSQL: it uses vault storage. `myinstall` must
not infer database ownership or invent secret paths.

## New applications

New applications need only a compatible manifest and release workflow. They do
not add application-specific install logic to `myinstall` and do not require
editing existing installations. `myinstall apps check` discovers manifests and
queries the configured GitHub release source directly.

If an application repository or its manifest is unavailable, the audit result
is `blocked`; the installer must not guess paths, secrets, or PostgreSQL
ownership.
