# NAS application migration status

This is the cutover inventory for removing duplicate application lifecycle
logic from `myNAS`.

## Compliant

### myHealth

- Consumer repository: `/Users/dmitrijstolarov/repos/myHealth`
- NAS test manifest: `deploy/bootstrap/manifest.json`
- Compose: app-only, immutable image, canonical secret mount, healthcheck
- Rollout: GitHub Actions self-hosted NAS runner invokes pinned `myinstall`
- PostgreSQL: not declared; the application uses vault storage
- VPS production: remains the separate `deploy/deploy.sh` flow

## Blocked legacy consumers

### mytask

The application repository is available at `/Users/dmitrijstolarov/repos/mytask`
and now has the canonical manifest, app-only Compose, immutable image rollout,
and pinned `myinstall` runner. Its shared PostgreSQL network was normalized to
`nas-infra`.

The removed `myNAS/stacks/apps/mytask` files are not restored automatically.

### legacy mythings

The legacy stack remains under `myNAS/stacks/apps/mythings` and owns
PostgreSQL, local `.env`, direct Compose rollout, and application data paths.
It is not the source of truth for `mytask`. Do not delete its runtime data or
remove its tracked stack until the owner verifies that no legacy runtime still
uses it.

### myFactory

The available repository at `/Volumes/Nas/Project/myFactory` still uses a
blue/green Compose deployment with application-owned PostgreSQL and MinIO,
mutable/local build semantics, and a separate SSH/VPS deployment workflow. It
does not yet publish a canonical `myinstall` manifest and app-only Compose.
Its dirty worktree must not be mixed into this cutover.

Do not remove `myNAS/stacks/apps/myfactory` until myFactory publishes the
canonical manifest, immutable release artifact, app-only Compose, healthcheck,
and rollback boundary.

## Removal rule

Only the duplicate application lifecycle files may be removed from `myNAS`
after the corresponding consumer is compliant. Never remove application data,
secrets, PostgreSQL volumes, MinIO/S3 data, Caddy routes, DNS records, or
backup archives as part of this repository cleanup.
