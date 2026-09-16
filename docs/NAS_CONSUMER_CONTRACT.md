# NAS consumer contract

`myinstall` is the single host-side lifecycle owner for applications that
declare the manifest contract. CI builds and publishes the immutable image;
the NAS runner invokes `myinstall`.

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

## myTask status

The repo-owned myTask manifest and Compose contract use app-only Compose,
shared PostgreSQL metadata, and the read-only canonical secret mount. Its
deployment workflow must pass the immutable image digest to:

```bash
myinstall upgrade --manifest ... --version vX.Y.Z --image IMAGE@sha256:... --confirm
```

The legacy stack under `myNAS/stacks/apps/mythings` is not equivalent to this
contract: it owns PostgreSQL, uses a local `.env`, and runs Compose directly.
It must not be used for production after cutover.

## myHealth status

The myHealth repository was not available at the audited NAS paths. It is
therefore `blocked`, not silently treated as compliant. Before deployment,
myHealth must publish the same manifest/Compose contract and explicitly declare
whether it uses the shared PostgreSQL cluster. `myinstall` must not infer
ownership or invent its secret paths.

## New applications

New applications need only a compatible manifest and release workflow. They do
not add application-specific install logic to `myinstall` and do not require
editing existing installations. `myinstall apps check` discovers manifests and
queries the configured GitHub release source directly.

If an application repository or its manifest is unavailable, the audit result
is `blocked`; the installer must not guess paths, secrets, or PostgreSQL
ownership.
