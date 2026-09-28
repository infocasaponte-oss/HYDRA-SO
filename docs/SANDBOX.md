# HYDRA OCI Sandbox

HYDRA's coding verifier can run repository tests in an ephemeral Docker-compatible container.

Security defaults:
- no network;
- read-only container root filesystem;
- all Linux capabilities dropped;
- no-new-privileges;
- non-root UID/GID;
- memory, CPU and PID limits;
- bounded execution time;
- only the task workspace is bind-mounted writable;
- no Docker socket inside the container.

The host-side HYDRA daemon controls container creation. Models never receive container-runtime credentials.

## Important limitation

A writable bind mount means malicious repository code can modify files inside its assigned task workspace. The workspace must therefore be an expendable task copy, never the original source checkout. Future Workspace Manager code will enforce copy-on-task semantics and controlled artifact export.
