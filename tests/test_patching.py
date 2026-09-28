import pytest

from hydra.patching import PatchTool
from hydra.tools import Workspace


def test_patch_rejects_parent_escape(tmp_path):
    patcher = PatchTool(Workspace(tmp_path))
    diff = "--- a/../escape.txt\n+++ b/../escape.txt\n@@ -0,0 +1 @@\n+x\n"
    with pytest.raises(ValueError):
        patcher.apply(diff)


def test_patch_applies_inside_git_workspace(tmp_path):
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("old\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    diff = "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
    result = PatchTool(Workspace(tmp_path)).apply(diff)
    assert result.ok
    assert (tmp_path / "a.txt").read_text() == "new\n"
