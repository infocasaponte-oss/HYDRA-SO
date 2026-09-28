# HYDRA sandbox image

Build locally:

    docker build -t hydra-sandbox:py311-v1 -f infra/sandbox/Dockerfile .

The CodeAgent expects this image by default. It contains Python 3.11, pytest and pytest-asyncio. Network remains disabled at runtime and the root filesystem is mounted read-only by HYDRA.

This tag is a development identity, not an immutable supply-chain pin. A future release gate will replace it with an image digest produced by CI.
