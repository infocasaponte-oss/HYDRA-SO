# HYDRA Tool Runtime

The Tool Runtime is the only permitted bridge between cognition and host-side actions.

## Current tools

- `workspace.list` — read-only
- `workspace.read` — read-only
- `workspace.search` — read-only
- `python.test` — fixed pytest execution; explicit execute permission required

## Security model

Every path is resolved beneath a fixed workspace root. Path traversal is rejected.

Tools are described by risk and capabilities. The Policy Engine fails closed:
process execution, filesystem writes and network access require explicit permission.

`python.test` does **not** use a shell and does not accept an arbitrary command. This reduces command-injection risk, but it is not a security sandbox: pytest executes repository Python code. Therefore it must only be used with trusted workspaces until container isolation is implemented.

## Next hardening step

The next runtime moves execution into an ephemeral OCI container with:
- read-only root filesystem;
- writable task workspace only;
- network disabled by default;
- CPU/RAM/PID/time limits;
- non-root UID;
- no host Docker socket;
- artifact export through a controlled boundary.
