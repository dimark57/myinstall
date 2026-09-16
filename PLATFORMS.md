# Supported platforms

## `myinstall` CLI

| Platform | Architecture | Status |
| --- | --- | --- |
| Linux | amd64 | Supported |
| Linux | arm64 | Supported |
| macOS | amd64 | Supported |
| macOS | arm64 | Supported |

The CLI itself is native and does not require Docker.

## Runtime adapters

- `native` works on Linux and macOS and manages a versioned executable.
- `systemd` is Linux-only.
- `launchd` is macOS-only.
- `docker` and `mixed` require Docker Engine and Docker Compose on the host.
- `none` manages secrets and directories without starting an application.

The first release does not claim Windows support. A Windows service adapter
must be added before Windows is listed as supported.
