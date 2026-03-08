import os
import glob
import shutil
import logging

from interfaces.memory import MemoryBackend
from config import Config

logger = logging.getLogger(__name__)


class VaultManager:
    """
    Manages all file operations within the Obsidian vault.

    Provides secure read/write/list/move operations with automatic
    vector index updates. Includes path security to prevent escaping
    the vault directory.
    """

    def __init__(self, config: Config, memory: MemoryBackend):
        self.config = config
        self.memory = memory
        self.vault_dir = config.VAULT_DIR

    # --- Path Security ---

    def get_secure_path(self, filepath: str) -> str:
        """Resolve and validate that a path falls strictly within VAULT_DIR."""
        filepath = os.path.expanduser(filepath)
        if os.path.isabs(filepath):
            if not filepath.startswith(self.vault_dir):
                filepath = os.path.join(self.vault_dir, filepath.lstrip("/"))
        else:
            filepath = os.path.join(self.vault_dir, filepath)

        real_vault = os.path.realpath(self.vault_dir)
        real_path = os.path.realpath(filepath)

        if not real_path.startswith(real_vault):
            raise ValueError(f"Path outside vault: {filepath}")

        return real_path

    # --- File Operations ---

    def read_file(self, filepath: str) -> str:
        """Read a markdown file from the vault."""
        try:
            secure_path = self.get_secure_path(filepath)
            with open(secure_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    def overwrite_file(self, filepath: str, new_content: str) -> str:
        """Create or overwrite a file and update the vector index."""
        try:
            secure_path = self.get_secure_path(filepath)
            os.makedirs(os.path.dirname(secure_path), exist_ok=True)
            with open(secure_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            self.memory.upsert(secure_path, new_content)
            return f"Successfully saved to {secure_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def list_files(self, directory: str) -> str:
        """List all .md files under a vault subdirectory."""
        try:
            secure_path = self.get_secure_path(directory)
            if not os.path.isdir(secure_path):
                return f"Not a directory: {secure_path}"
            files = glob.glob(os.path.join(secure_path, "**", "*.md"), recursive=True)
            rel_paths = [os.path.relpath(f, self.vault_dir) for f in files]
            if not rel_paths:
                return "No .md files found."
            return "\n".join(sorted(rel_paths))
        except Exception as e:
            return f"Error listing files: {e}"

    def move_file(self, source: str, destination: str) -> str:
        """Move a file between vault locations and update the index."""
        try:
            secure_src = self.get_secure_path(source)
            secure_dst = self.get_secure_path(destination)

            if not os.path.exists(secure_src):
                return f"Source file not found: {secure_src}"

            os.makedirs(os.path.dirname(secure_dst), exist_ok=True)
            shutil.move(secure_src, secure_dst)

            self.memory.remove(secure_src)
            with open(secure_dst, "r", encoding="utf-8") as f:
                content = f.read()
            self.memory.upsert(secure_dst, content)

            return f"Moved {secure_src} → {secure_dst}"
        except Exception as e:
            return f"Error moving file: {e}"

    # --- Tool Dispatch ---

    def get_tool_functions(self) -> dict:
        """Returns the tool name → handler mapping for the orchestrator."""
        return {
            "read_vault_file": lambda args: self.read_file(args.get("filepath", "")),
            "overwrite_vault_file": lambda args: self.overwrite_file(
                args.get("filepath", ""), args.get("new_content", "")
            ),
            "list_vault_files": lambda args: self.list_files(args.get("directory", "")),
            "move_vault_file": lambda args: self.move_file(
                args.get("source_filepath", ""), args.get("destination_filepath", "")
            ),
        }

    @staticmethod
    def get_tool_schemas() -> list[dict]:
        """Returns the OpenAI-format tool schemas for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_vault_file",
                    "description": "Reads a markdown file from the vault and returns its content as a string.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {
                                "type": "string",
                                "description": "The filepath to read from (absolute or relative to vault root).",
                            }
                        },
                        "required": ["filepath"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "overwrite_vault_file",
                    "description": (
                        "Overwrites or creates a markdown file with new content and automatically "
                        "updates the vector index. You MUST read the file first before overwriting "
                        "to avoid clobbering existing content."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {
                                "type": "string",
                                "description": "The filepath to write to (absolute or relative to vault root).",
                            },
                            "new_content": {
                                "type": "string",
                                "description": "The full markdown content of the file, including YAML frontmatter.",
                            },
                        },
                        "required": ["filepath", "new_content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_vault_files",
                    "description": (
                        "Lists all .md files under a subdirectory of the vault. Use this to discover "
                        "existing files when semantic search doesn't find a match. Example directories: "
                        "'1-Projects', '2-Areas', '3-Resources', '4-Archives', 'Inbox'."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "The subdirectory to list (e.g., '1-Projects' or '3-Resources/shower-thoughts').",
                            }
                        },
                        "required": ["directory"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "move_vault_file",
                    "description": (
                        "Moves a file from one vault location to another. Use this for PARA tag "
                        "evolution (e.g., moving a resource to projects). Updates the vector index automatically."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_filepath": {
                                "type": "string",
                                "description": "Current filepath of the file to move.",
                            },
                            "destination_filepath": {
                                "type": "string",
                                "description": "New filepath to move the file to.",
                            },
                        },
                        "required": ["source_filepath", "destination_filepath"],
                    },
                },
            },
        ]
