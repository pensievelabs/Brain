import os
import re
import glob
import shutil
import logging
from datetime import date

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

    def append_to_file(self, filepath: str, content: str) -> str:
        """Append content to the end of an existing vault file and update the index."""
        try:
            secure_path = self.get_secure_path(filepath)
            if not os.path.exists(secure_path):
                return f"File not found: {secure_path}"

            with open(secure_path, "r", encoding="utf-8") as f:
                existing = f.read()

            updated = existing.rstrip("\n") + "\n" + content + "\n"

            with open(secure_path, "w", encoding="utf-8") as f:
                f.write(updated)

            self.memory.upsert(secure_path, updated)
            return f"Appended to {secure_path}"
        except Exception as e:
            return f"Error appending to file: {e}"

    def create_reading_stub(
        self, title: str, source_url: str, content_type: str, tags: list[str]
    ) -> str:
        """
        Create a reading-queue stub file in 3-Resources/.

        Returns a JSON-like string with filepath and wiki_link.
        """
        try:
            # Generate kebab-case filename
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            filename = f"{slug}.md"
            filepath = f"3-Resources/{filename}"
            secure_path = self.get_secure_path(filepath)

            # Don't overwrite if it already exists
            if os.path.exists(secure_path):
                wiki_link = f"[[{slug}]]"
                return f'{{"filepath": "{filepath}", "wiki_link": "{wiki_link}", "status": "already_exists"}}'

            # Build content
            today = date.today().isoformat()
            tag_list = ["#resource", "#to-read", f"#{content_type}"]
            for t in tags:
                tag_str = t if t.startswith("#") else f"#{t}"
                if tag_str not in tag_list:
                    tag_list.append(tag_str)

            tag_yaml = "\n".join(f'  - "{t}"' for t in tag_list)
            content = (
                f"---\n"
                f"date: {today}\n"
                f"tags:\n{tag_yaml}\n"
                f"---\n\n"
                f"# {title}\n\n"
                f"## Source\n"
                f"{source_url}\n\n"
                f"## Key Concepts\n\n\n"
                f"## Notes\n\n"
            )

            os.makedirs(os.path.dirname(secure_path), exist_ok=True)
            with open(secure_path, "w", encoding="utf-8") as f:
                f.write(content)

            self.memory.upsert(secure_path, content)

            wiki_link = f"[[{slug}]]"
            return f'{{"filepath": "{filepath}", "wiki_link": "{wiki_link}", "status": "created"}}'
        except Exception as e:
            return f"Error creating reading stub: {e}"

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
            "create_reading_stub": lambda args: self.create_reading_stub(
                args.get("title", ""),
                args.get("source_url", ""),
                args.get("content_type", "article"),
                args.get("tags", []),
            ),
            "append_to_file": lambda args: self.append_to_file(
                args.get("filepath", ""), args.get("content", "")
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

    @staticmethod
    def get_reading_tool_schemas() -> list[dict]:
        """Returns tool schemas for reading queue operations."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_reading_stub",
                    "description": (
                        "Creates a reading-queue stub file in 3-Resources/ for a book, "
                        "article, or URL. Returns the filepath and wiki-link. Use this when "
                        "the user shares a reading recommendation, book title, or article URL."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Title of the book, article, or resource.",
                            },
                            "source_url": {
                                "type": "string",
                                "description": "URL or source reference. Use empty string if not a URL.",
                            },
                            "content_type": {
                                "type": "string",
                                "enum": ["book", "article"],
                                "description": "Type of reading material.",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Additional context tags (e.g., 'psychology', 'ai').",
                            },
                        },
                        "required": ["title", "source_url", "content_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "append_to_file",
                    "description": (
                        "Appends content to the end of an existing vault file. Use this to "
                        "add reading tasks to a project's Next Actions section."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filepath": {
                                "type": "string",
                                "description": "The vault filepath to append to.",
                            },
                            "content": {
                                "type": "string",
                                "description": "The content to append (e.g., '- [ ] Read: [[wiki-link]]').",
                            },
                        },
                        "required": ["filepath", "content"],
                    },
                },
            },
        ]
