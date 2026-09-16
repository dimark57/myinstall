# GitHub application release contract

This is the single publication contract for applications managed by
`myinstall`.

## Source of truth

Each installable application repository must provide:

```text
deploy/bootstrap/manifest.json
deploy/bootstrap/install.sh
deploy/bootstrap/stack-compose.yml   # runtime=docker|mixed
```

The manifest is the application contract. Its stable release fields are:

```json
{
  "app": "mytask",
  "runtime": "docker",
  "release_source": "owner/repository",
  "release_channel": "stable",
  "current_version": "v1.2.3",
  "image_template": "ghcr.io/owner/app:{tag}",
  "image": "ghcr.io/owner/app:v1.2.3"
}
```

Native applications use `release_asset_pattern` and publish a platform
artifact plus `SHA256SUMS` instead of `image_template`.

## Publication pipeline

Every production release uses a SemVer tag:

```text
vMAJOR.MINOR.PATCH
```

The tag workflow must:

1. run the complete test gate for the tagged SHA;
2. publish an immutable Docker image to GHCR or immutable native artifacts to
   the GitHub Release;
3. create a GitHub Release for the same tag;
4. record release notes and the published image digest/artifact checksums;
5. only then allow NAS/VPS rollout.

A GHCR tag alone is not a release. `myinstall` discovers versions through the
GitHub Releases API, never by guessing mutable image tags.

## Operator command

On a host containing the application manifest:

```bash
myinstall mytask
```

`myinstall <app>` discovers the manifest in the canonical Project/stacks roots.
It installs the application if its runtime is absent; otherwise it finds the
latest stable GitHub Release and upgrades to its immutable image or artifact.

The same command works for every application that implements this contract:

```bash
myinstall myhealth
myinstall myotherapp
```

The application itself must expose the standard operator CLI:

```text
<app> --version
<app> --help
<app> help
<app> man
<app> doctor
```

The detailed behavior and exit-code contract is in
`docs/APPLICATION_CLI_CONTRACT.md`.

Use `sudo myinstall <app>` only when the operator intentionally needs elevated
host access. `myinstall` does not modify sudoers or silently elevate itself.

## Private repositories

For private GitHub repositories, the host supplies a read-only
`MYINSTALL_GITHUB_TOKEN` with access to repository Releases. The token is
never put in a manifest, command argument, image, or diagnostic output.

## Prohibited variants

- GHCR push without a GitHub Release;
- mutable-only image references such as `latest`;
- application-specific update registries;
- release discovery from a stack directory or a checked-in production secret;
- rollout before the tagged test gate is green.
