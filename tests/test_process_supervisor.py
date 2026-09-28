import sys

import pytest

from hydra.process_supervisor import ProcessSupervisor


@pytest.mark.asyncio
async def test_supervisor_stops_process():
    managed = await ProcessSupervisor().start(
        [sys.executable, "-c", "import time; time.sleep(30)"]
    )
    await managed.stop(grace_seconds=0.1)
    assert managed.process.returncode is not None
