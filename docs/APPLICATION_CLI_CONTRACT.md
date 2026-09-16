# Application CLI contract

Every project with `kind=application` exposes a stable operator CLI. The
manifest declares it under `cli`:

```json
{
  "cli": {
    "name": "mytask",
    "commands": ["--version", "--help", "--man", "--doctor", "--update"]
  }
}
```

## Required commands

| Command | Contract |
|---|---|
| `<app> --version` | Print the released application version and exit `0`; no network or mutation. |
| `<app> --help` | Print concise usage and command help; exit `0`; no mutation. |
| `<app> --man` | Print the operator manual/reference; exit `0`; no mutation. |
| `<app> --doctor` | Read-only diagnostics for configuration, dependencies, storage and runtime connectivity. Exit `0` when healthy, non-zero when a required check fails. Never print secret values. |
| `<app> --update` | Delegate host update to `myinstall <app> --update`; it never receives Docker socket or production secrets. |

`--help` must also be accepted for every subcommand that the application
exposes. `--version`, `--help` and `--man` output must be available before a production
secret or database is present.

## Naming standard

- application id, executable and subcommands: lowercase `kebab-case`;
- application id pattern: `^[a-z][a-z0-9-]*$`;
- global/options flags: long `--kebab-case`, with short aliases only for
  universal conventions such as `-h` and `-V`;
- environment variables: uppercase `SNAKE_CASE`;
- repository display names may use CamelCase, but the manifest `app` and CLI
  name use the stable lowercase id;
- command names are verbs/actions (`doctor`, `update`), not mixed aliases or
  CamelCase names.

## Optional commands

Applications may add domain-specific commands. `status`, `health`, `config
validate`, `migrate`, `export` and `completion` are allowed when documented.

`start`, `stop`, `restart`, `upgrade`, `rollback` and `remove` are not required
application commands. Host lifecycle belongs to `myinstall`, Compose or the
declared service adapter; duplicating it in every application creates two
conflicting owners.

## Installation relationship

The application CLI is the in-container/native executable contract. Host
installation is always performed by the shared utility:

```bash
myinstall <app>
myinstall <app> --update
sudo myinstall <app> --update
```

The application must not ship a private installer, updater, registry or secret
bootstrapper. `application-audit-skill` checks the manifest declaration and
the documented CLI surface before deployment.
