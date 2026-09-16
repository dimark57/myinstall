# Changelog

All notable changes to `myinstall` are documented here.

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
