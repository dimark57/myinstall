# Native service example

This example shows the files an application repository provides to
`myinstall`. Replace the artifact URL and checksum with the application's
immutable GitHub Release asset.

Install:

```bash
myinstall install --manifest deploy/bootstrap/manifest.json --confirm
```

Upgrade:

```bash
myinstall upgrade --manifest deploy/bootstrap/manifest.json \
  --version v1.2.4 --confirm
```
