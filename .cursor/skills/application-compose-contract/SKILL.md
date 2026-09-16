---
name: application-compose-contract
description: Validate Docker and mixed-runtime application Compose templates against the myinstall manifest contract. Use when creating, modifying, auditing, testing, or releasing an application integrated with myinstall.
---

# Application Compose Contract

Use this skill for every application repository integrated with `myinstall`.
It is reusable: do not add a project name, repository name, or image value to
the skill or to its validator.

## Source of truth

The only editable Compose source is:

```text
deploy/bootstrap/stack-compose.yml
```

Never repair a generated `docker-compose.yml` or another rendered file by
hand. Generated Compose is an output of the install flow.

For `runtime=docker` and `runtime=mixed`, the source template must:

- contain exactly one application `image`;
- use exactly `image: {{IMAGE}}`;
- contain `{{SECRET_PATH}}`, `{{SECRET_MOUNT}}`, `{{DATA_PATH}}`, and
  `{{HEALTH_URL}}`;
- use no hardcoded image tag, digest, `${VARIABLE}`, or versioned `ghcr.io`
  image;
- contain no PostgreSQL/Postgres service, PostgreSQL data volume,
  `POSTGRES_*` environment variable, or direct `DATABASE_URL` value;
- join the external PostgreSQL network declared by
  `manifest.json` (`postgres.network_name`).

## Required workflow

1. Read `deploy/bootstrap/manifest.json` and determine `runtime`.
2. For Docker/mixed runtime, verify that
   `deploy/bootstrap/stack-compose.yml` exists.
3. Run the validator shipped with this skill:

   ```bash
   python3 .cursor/skills/application-compose-contract/scripts/validate_compose_contract.py \
     --manifest deploy/bootstrap/manifest.json \
     --compose deploy/bootstrap/stack-compose.yml
   ```

4. Ensure the validator is committed or copied into the application project
   and called by an automatic test/validation command. The command must fail
   when `{{IMAGE}}` is absent. A release workflow must run the same command
   before publishing and must stop when it returns non-zero.
5. Before completing any task and again before release, inspect the report for:
   - all contract violations;
   - the file that was fixed;
   - validation result;
   - whether release publication is allowed.

Use this report format:

```text
contract violations: <none, or every violation>
fixed file: <path, or none>
validation: <passed/failed; include Docker Compose result>
release allowed: <yes/no>
```

The validator materializes the template with manifest values, verifies that
the materialized Compose contains the manifest image, and runs
`docker compose config` when Docker is available. If Docker is unavailable,
the static and materialization checks still run, but the report must say that
the Docker check was skipped; do not claim full validation.

## Manifest correspondence

Check that the template's placeholders materialize from the manifest's:

```text
runtime                  -> manifest.runtime
{{SECRET_PATH}}          -> manifest.secret_path
{{SECRET_MOUNT}}         -> manifest.secret_mount
{{DATA_PATH}}            -> manifest.data_path
{{HEALTH_URL}}           -> manifest.healthcheck.url
PostgreSQL network       -> manifest.postgres.network_name
```

Do not release while any check fails. The release report must explicitly say
`release allowed: yes` only after validation succeeds.
