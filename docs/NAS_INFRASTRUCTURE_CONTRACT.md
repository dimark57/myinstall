# NAS infrastructure ownership

This contract separates host infrastructure from application lifecycle.

## myNAS owns

- NAS host, Docker engine, Compose infrastructure stacks, and runner;
- Docker networks, including external `edge` and `nas-infra`;
- Caddy reverse proxy and CoreDNS zones;
- persistent storage layout and backup jobs;
- the shared PostgreSQL service, its container, data volume, and upgrades;
- infrastructure secrets such as the PostgreSQL admin secret.

## myinstall owns

- application manifest validation and discovery;
- immutable image/artifact installation, upgrade, rollback, and healthchecks;
- application secret files and permissions;
- application migrations;
- application PostgreSQL database and LOGIN role provisioning;
- application PostgreSQL credential rotation and `DATABASE_URL` generation.

`myinstall` may call the infrastructure PostgreSQL Compose project for
readiness and administrative SQL, but must not create, destroy, recreate, or
upgrade the shared PostgreSQL service during an application lifecycle command.

## Application boundary

An application repository provides:

```text
deploy/bootstrap/manifest.json
deploy/bootstrap/stack-compose.yml
deploy/bootstrap/install.sh
```

Its Compose may contain application services only. It must join external NAS
networks when declared by the manifest, mount its canonical application secret,
and never declare PostgreSQL, the shared PostgreSQL data volume, Caddy, DNS, or
backup jobs.

## Cutover rule

Legacy application stacks in the NAS repository are transitional inventory, not
the application source of truth. They may be removed from `myNAS` only after
the corresponding application repository has a validated manifest, immutable
release workflow, healthcheck, and rollback boundary. Removing tracked
configuration does not authorize deleting runtime data, secrets, database
volumes, or backups.
