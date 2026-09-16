# Security policy

## Supported versions

Only the latest minor release on the default branch is supported with security
fixes.

## Reporting a vulnerability

Do not open a public issue for a security vulnerability. Report it privately
through GitHub's private vulnerability reporting for this repository.

Include the affected version, platform, manifest runtime, reproduction steps,
and any relevant redacted logs. Do not include secrets or production
credentials.

`myinstall` executes commands described by an application manifest with host
privileges. Only install manifests from trusted application repositories and
pin release artifacts by checksum or digest.
