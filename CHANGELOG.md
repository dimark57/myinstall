# Changelog

All notable changes to `myinstall` are documented here.

## [0.3.16] - 2026-09-16

### Added

- Detect expired, revoked, or invalid GitHub tokens and print recovery
  instructions with `sudo myinstall auth setup`.
- Add `myinstall auth status` to validate the configured token without exposing
  its value.

### Fixed

- Preserve the `v` prefix when resolving a GitHub Release by tag.
- Include actionable repository and token guidance for GitHub 404 responses.
- Update the `mytask` catalog entry to `v0.1.63`.

## [0.3.15] - 2026-09-16

### Changed

- Make `--uninstall` the canonical host and application lifecycle command.
- Keep `--remove` as a compatibility alias.
- Standardize new-machine runtime paths under `stacks/utilites/<app>` and
  host-local `data` and `secrets` roots.

## [0.3.14] - 2026-09-16

### Added

- Add interactive progress output for install, upgrade, and remove lifecycle
  operations.
- Add application and host utility removal with explicit data/secret purge
  confirmation.
- Use the new-machine `stacks/utilites/<app>` layout on Linux and macOS.
- Localize application data and secrets under the host NAS root.

## [0.3.5] - 2026-09-16

### Added

- Allow first-time Docker installs to receive an immutable image digest from
  CI with `install --image`.
- Enforce the canonical NAS application Compose and shared PostgreSQL network
  contract.

## [0.3.4] - 2026-09-16

### Fixed

- Normalize the shared PostgreSQL example to the canonical field names.
- Limit doctor PostgreSQL readiness checks to shared clusters.

## [0.3.3] - 2026-09-16

### Fixed

- Preserve infrastructure Compose project selection during PostgreSQL rotation
  and rollback.
- Correct redaction of PostgreSQL URLs and secret-like diagnostics.
- Normalize duplicate PostgreSQL manifest schema properties.

## [0.3.2] - 2026-09-16

### Fixed

- Include the complete API, integration documentation, and NAS example in the
  audited release contract.

## [0.3.1] - 2026-09-16

### Fixed

- Make version upgrades resolve the requested GitHub release and artifact.
- Lock rollback and secret rotation operations and return failure on unhealthy rollback.
- Support native/service migrations and PostgreSQL admin secrets from a separate path.
- Add runtime dependency and health checks to `doctor`.

## [0.3.0] - 2026-09-16

### Added

- Direct GitHub Releases discovery without a local application registry.
- `apps list`, `apps check`, `apps doctor`, and `apps upgrade`.
- Generic `app install --manifest-url`.
- Manifest release source, channel, version, and asset selection fields.

## [0.2.3] - 2026-09-16

### Fixed

- Complete the shared PostgreSQL path in the native integration example.

## [0.2.2] - 2026-09-16

### Fixed

- Include PostgreSQL host/port fields in the manifest schema.
- Quote database identifiers safely during shared PostgreSQL provisioning.
- Add data directories and healthcheck contract to the Compose template.

## [0.2.1] - 2026-09-16

### Fixed

- Release CI installs the test dependencies before validating release artifacts.

## [0.2.0] - 2026-09-16

### Added

- Runtime declaration for native, systemd, Docker, mixed, and no-runtime applications.
- Versioned release artifacts and checksum-based bootstrap installation.
- JSON manifest validation and public integration contract.
- Native and service-manager lifecycle adapters.

### Changed

- Docker is optional and is required only by Docker/mixed manifests.
- The package version is sourced from `myinstall.__version__`.

## Versioning

Releases use Semantic Versioning. Tags and GitHub Releases are immutable:
`vMAJOR.MINOR.PATCH`.
