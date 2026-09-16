# Shared PostgreSQL migration runbook

This runbook is for an existing application-owned PostgreSQL container. It is
an operator workflow, not part of application install, upgrade, rollback, or
remove. Do not stop or delete the source container until the target data and
application health have been verified.

## Target contract

- Infrastructure Compose: `/srv/nas/stacks/infrastructure/postgres/compose.yml`
- Cluster: `nas-postgres`
- Service: `postgres`
- Network: `nas-infra`
- Data: `/srv/nas/data/postgres`
- Admin secret: `/srv/nas/secrets/postgres.env`, mode `0600`
- Application secrets: `/srv/nas/secrets/<app>.env`, mode `0600`

The infrastructure secret is read only by `myinstall` and the infrastructure
Compose project. It must never be copied into an application secret.

## Procedure

1. Identify the source Compose project, container, mounted data path, database
   names, owners, roles, extensions, and application connection URL. Record
   the source container and volume; it is the rollback boundary.
2. Verify a tested `pg_dump` for every application database, including globals
   where required. Keep the source PostgreSQL running during the dump.
3. Start the shared stack through `myinstall`/the infrastructure owner and
   verify the PostgreSQL 16 image, `nas-infra` network, persistent mount,
   readiness, and backup destination.
4. Create one database and one non-admin `LOGIN` role per application. Never
   use `postgres` in an application `DATABASE_URL`.
5. Restore each dump into its target database, assign ownership to the
   application role, run the application's migrations as that role, and
   verify row counts or application-specific checks.
6. Write only the application role password and `DATABASE_URL` to the
   application's secret file. Ensure mode `0600`; do not print the URL.
7. Replace the application Compose with an app-only stack that joins
   external `nas-infra`. It must not contain a PostgreSQL service, PostgreSQL
   volume, `POSTGRES_*` variables, or a `docker compose down` for the shared
   project.
8. Restart only the application stack, wait for PostgreSQL readiness before
   migrations, then run the app healthcheck and verify data through the
   application.
9. Keep the source PostgreSQL container and its data volume intact through a
   rollback window. Retire them only after the owner records successful
   validation and a fresh backup.

## Inventory findings (2026-09-16)

- `mytask`: legacy `/Volumes/Nas/stacks/apps/mytask/docker-compose.yml` still
  declares `postgres`, mounts `/srv/nas/data/mythings/postgres`, and uses
  `/Volumes/Nas/stacks/apps/mytask/runtime-db.env`.
- `myfactory`: legacy
  `/Volumes/Nas/stacks/apps/myfactory/docker-compose.yml` declares `postgres`,
  uses the named volume
  `myfactory-bluegreen_myfactory_postgres`, and embeds the application
  connection URL and password in Compose configuration.
- `myhealth`: no PostgreSQL dependency found in its deployed Compose.
- `dgPM`: no application stack or manifest was found under the mounted NAS
  application stacks; source access is required before changing ownership.
- No canonical shared PostgreSQL stack was found under the inspected NAS
  stack directories.

These findings are evidence for migration planning only. This repository does
not automatically execute dumps, restores, container stops, or volume
deletions.
