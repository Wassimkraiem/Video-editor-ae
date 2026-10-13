"""Permission policy passed to Claude Agent SDK tool callbacks."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_BINARIES = {"npx", "node", "ffmpeg", "ffprobe", "python", "python3"}
ALLOWED_NPX_COMMANDS = {"hyperframes", "skills"}
SHELL_METACHARACTERS = (";", "&", "|", "`", "$(", "${", ">", "<", "\n", "\r")
FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class ProjectSandboxPolicy:
    def __init__(self, project_dir: str | Path, allowed_hosts: set[str] | None = None):
        self.project_dir = Path(project_dir).resolve()
        self.allowed_hosts = allowed_hosts or set()

    def resolve(self, value: str | Path) -> Path:
        """Resolve a tool path the way the agent sees it: relative to the project."""

        candidate = Path(value).expanduser()
        return (candidate if candidate.is_absolute() or candidate.anchor else self.project_dir / candidate).resolve()

    def path_allowed(self, value: str | Path) -> bool:
        try:
            return self.resolve(value).is_relative_to(self.project_dir)
        except (OSError, RuntimeError):
            return False

    def bash_allowed(self, command: str) -> bool:
        # Pipes, chaining, redirection, and substitution are rejected outright:
        # the command must be exactly one allowlisted program.
        if any(token in command for token in SHELL_METACHARACTERS):
            return False
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv:
            return False
        binary = Path(argv[0]).name.lower().removesuffix(".exe").removesuffix(".cmd")
        if binary not in ALLOWED_BINARIES:
            return False
        if binary == "npx":
            # Allow a pinned version such as ``hyperframes@0.8.152``.
            package = argv[1].split("@", 1)[0] if len(argv) > 1 else ""
            if package not in ALLOWED_NPX_COMMANDS:
                return False
        for token in argv[1:]:
            value = token.split("=", 1)[1] if token.startswith("-") and "=" in token else token
            if value.startswith(("http://", "https://")):
                if urlparse(value).hostname not in self.allowed_hosts:
                    return False
            elif self._looks_like_path(value) and not self.path_allowed(value):
                return False
        return True

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        return value.startswith(("/", "./", "../", "~", "\\")) or bool(_DRIVE_PATH.match(value)) or ".." in Path(value).parts

    def can_use_tool(self, tool_name: str, tool_input: dict) -> tuple[bool, str]:
        if tool_name == "Bash":
            command = str(tool_input.get("command", ""))
            return (True, "allowed") if self.bash_allowed(command) else (False, "Bash command is outside the project sandbox allowlist: run one allowlisted program (npx hyperframes, ffmpeg, ffprobe, node, python) on project-relative paths, without pipes or redirection")
        for key in ("file_path", "path", "notebook_path"):
            if key in tool_input:
                if not self.path_allowed(str(tool_input[key])):
                    return False, "File access is outside the project folder"
                if tool_name in FILE_WRITE_TOOLS and self.resolve(str(tool_input[key])).is_relative_to(self.project_dir / "raw"):
                    return False, "Raw uploads are read-only"
        return True, "allowed"
