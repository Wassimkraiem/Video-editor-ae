"""Permission policy passed to Claude Agent SDK tool callbacks."""

from __future__ import annotations

import shlex
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_BINARIES = {"npx", "node", "ffmpeg", "ffprobe", "python", "python3"}
ALLOWED_NPX_COMMANDS = {"hyperframes", "skills"}


class ProjectSandboxPolicy:
    def __init__(self, project_dir: str | Path, allowed_hosts: set[str] | None = None):
        self.project_dir = Path(project_dir).resolve()
        self.allowed_hosts = allowed_hosts or set()

    def path_allowed(self, value: str | Path) -> bool:
        try:
            return Path(value).resolve().is_relative_to(self.project_dir)
        except (OSError, RuntimeError):
            return False

    def bash_allowed(self, command: str) -> bool:
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv or Path(argv[0]).name not in ALLOWED_BINARIES:
            return False
        if Path(argv[0]).name == "npx":
            if len(argv) < 2 or argv[1] not in ALLOWED_NPX_COMMANDS:
                return False
        # A command may only mention project-local paths. URLs are limited to
        # explicitly approved hosts, and shell metacharacters are rejected by
        # the allowlist parser before the command reaches an executor.
        if any(token in command for token in (";", "&&", "||", "`", "$(", ">", "<")):
            return False
        for token in argv[1:]:
            if token.startswith(("http://", "https://")):
                if urlparse(token).hostname not in self.allowed_hosts:
                    return False
            elif token.startswith(("/", "./", "../")) and not self.path_allowed(token):
                return False
        return True

    def can_use_tool(self, tool_name: str, tool_input: dict) -> tuple[bool, str]:
        if tool_name == "Bash":
            command = str(tool_input.get("command", ""))
            return (True, "allowed") if self.bash_allowed(command) else (False, "Bash command is outside the project sandbox allowlist")
        for key in ("file_path", "path", "notebook_path"):
            if key in tool_input:
                candidate = Path(str(tool_input[key])).resolve()
                if not self.path_allowed(candidate):
                    return False, "File access is outside the project folder"
                if tool_name in {"Write", "Edit"} and candidate.is_relative_to(self.project_dir / "raw"):
                    return False, "Raw uploads are read-only"
        return True, "allowed"
