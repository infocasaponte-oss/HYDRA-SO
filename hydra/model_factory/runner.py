# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""External tool execution (llama.cpp, ollama, mlx_lm, optimum, llm-compressor...)."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

from pydantic import BaseModel


class CommandResult(BaseModel):
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ToolMissing(RuntimeError):
    pass


class CommandRunner:
    """Runs external commands. Tests inject a fake runner; production uses real processes."""

    async def run(self, cmd: list[str], cwd: Path | None = None, timeout: float = 24 * 3600,
                  stdin: bytes | None = None) -> CommandResult:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd) if cwd else None,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            out, err = await proc.communicate()
            return CommandResult(cmd=cmd, returncode=-9, stdout=out.decode(errors="replace")[-20000:],
                                 stderr="timeout\n" + err.decode(errors="replace")[-20000:])
        return CommandResult(cmd=cmd, returncode=proc.returncode or 0,
                             stdout=out.decode(errors="replace")[-50000:],
                             stderr=err.decode(errors="replace")[-20000:])


class ToolLocator:
    """Finds the external toolchain: llama.cpp binaries/scripts, ollama, python modules."""

    def __init__(self, llamacpp_dir: Path | None = None) -> None:
        env = os.environ.get("HYDRA_LLAMACPP_DIR")
        self.llamacpp_dir = llamacpp_dir or (Path(env) if env else None)

    def binary(self, name: str) -> str | None:
        candidates = [name, f"{name}.exe"]
        if self.llamacpp_dir:
            for sub in ("", "build/bin", "bin", "build/bin/Release"):
                for c in candidates:
                    p = self.llamacpp_dir / sub / c
                    if p.exists():
                        return str(p)
        return shutil.which(name)

    def llamacpp_script(self, name: str = "convert_hf_to_gguf.py") -> str | None:
        if self.llamacpp_dir and (self.llamacpp_dir / name).exists():
            return str(self.llamacpp_dir / name)
        return None

    @staticmethod
    def python_module(module: str) -> bool:
        import importlib.util

        return importlib.util.find_spec(module) is not None

    def require_binary(self, name: str) -> str:
        path = self.binary(name)
        if path is None:
            raise ToolMissing(f"'{name}' not found (install llama.cpp and set HYDRA_LLAMACPP_DIR)")
        return path

    def availability(self) -> dict[str, bool]:
        return {
            "llama-quantize": self.binary("llama-quantize") is not None,
            "llama-imatrix": self.binary("llama-imatrix") is not None,
            "llama-perplexity": self.binary("llama-perplexity") is not None,
            "llama-server": self.binary("llama-server") is not None,
            "convert_hf_to_gguf.py": self.llamacpp_script() is not None,
            "ollama": self.binary("ollama") is not None,
            "mlx_lm": self.python_module("mlx_lm"),
            "optimum": self.python_module("optimum"),
            "llmcompressor": self.python_module("llmcompressor"),
            "awq": self.python_module("awq"),
            "gptqmodel": self.python_module("gptqmodel"),
            "transformers": self.python_module("transformers"),
            "peft": self.python_module("peft"),
            "huggingface_hub": self.python_module("huggingface_hub"),
        }

    @staticmethod
    def python() -> str:
        return sys.executable
