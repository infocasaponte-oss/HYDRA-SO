import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from hydra.workspaces import WorkspaceManager


def _can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            (Path(tmp) / "probe").symlink_to(tmp, target_is_directory=True)
        except OSError:
            return False
    return True


requires_symlinks = pytest.mark.skipif(
    not _can_symlink(), reason="creating symlinks requires privileges on this platform"
)


@requires_symlinks
def test_workspace_rejects_file_symlink(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (source / "leak.txt").symlink_to(outside)

    manager = WorkspaceManager(tmp_path / "workspaces")

    with pytest.raises(ValueError, match="symlink"):
        manager.create(uuid4(), source)


@requires_symlinks
def test_workspace_rejects_directory_symlink(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (source / "linked").symlink_to(outside, target_is_directory=True)

    manager = WorkspaceManager(tmp_path / "workspaces")

    with pytest.raises(ValueError, match="symlink"):
        manager.create(uuid4(), source)


def test_workspace_enforces_file_count_limit(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("a")
    (source / "b.py").write_text("b")

    manager = WorkspaceManager(tmp_path / "workspaces", max_files=1)

    with pytest.raises(ValueError, match="file count"):
        manager.create(uuid4(), source)


def test_workspace_enforces_byte_limit(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "large.bin").write_bytes(b"x" * 11)

    manager = WorkspaceManager(tmp_path / "workspaces", max_bytes=10)

    with pytest.raises(ValueError, match="byte size"):
        manager.create(uuid4(), source)


def test_workspace_copies_regular_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.py").write_text("print('ok')")

    manager = WorkspaceManager(tmp_path / "workspaces")
    workspace = manager.create(uuid4(), source)

    assert (workspace.root / "main.py").read_text() == "print('ok')"
