"""Utility to parse LLM-generated code output and save it to the project's code/ folder."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CodeSaver:
    """Parses LLM code output into individual files and writes them to disk."""

    def __init__(self, project_folder: str):
        self.project_folder = Path(project_folder)
        self.code_dir = self.project_folder / "code"

    def save(
        self,
        code_content: str,
        story_key: str,
        story_title: str = "",
        user_query: str = "",
    ) -> dict[str, Any]:
        """Parse and save generated code to {project_folder}/code/{story_key}/.

        Returns a dict with success status, saved file paths, and any errors.
        """
        story_dir = self.code_dir / story_key
        story_dir.mkdir(parents=True, exist_ok=True)

        # Parse the LLM output into individual files
        files = self._parse_code_blocks(code_content)

        if not files:
            # If no structured files found, save as a single file
            filename = self._derive_filename(story_key, story_title)
            files = [{"filename": filename, "content": self._extract_raw_code(code_content)}]

        saved_files = []
        errors = []

        for file_info in files:
            filename = file_info["filename"]
            content = file_info["content"]
            filepath = story_dir / filename

            try:
                # Create subdirectories if filename contains path separators
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content, encoding="utf-8")
                saved_files.append(str(filepath))
                logger.info("Saved generated code: %s", filepath)
            except OSError as e:
                errors.append(f"Failed to write {filename}: {e}")
                logger.error("Failed to save %s: %s", filepath, e)

        # Write a manifest file with metadata
        self._write_manifest(story_dir, story_key, story_title, user_query, saved_files)

        return {
            "success": len(errors) == 0,
            "story_key": story_key,
            "directory": str(story_dir),
            "files": saved_files,
            "file_count": len(saved_files),
            "errors": errors,
        }

    def _parse_code_blocks(self, content: str) -> list[dict[str, str]]:
        """Extract files from LLM output.

        Supports two conventions:
        1. Explicit filename markers: ```python # filename: path/to/file.py
        2. Header comments: # File: path/to/file.py or # filename: file.py
        3. Multiple code blocks with language hints
        """
        files: list[dict[str, str]] = []

        # Pattern 1: ```lang\n# filename: xxx\n or ```lang filename: xxx
        # Matches code blocks that start with a filename marker
        pattern_explicit = re.compile(
            r"```(\w*)\s*\n"
            r"(?:#\s*(?:filename|file|File|Filename):\s*(.+?)\n)?"
            r"(.*?)"
            r"\n```",
            re.DOTALL,
        )

        # Pattern 2: Header before code block like "**`path/to/file.py`**:" or "### file.py"
        pattern_header = re.compile(
            r"(?:\*\*`?|###?\s+|`)"
            r"([\w./\-]+\.(?:py|js|ts|jsx|tsx|java|go|rs|rb|sh|sql|yaml|yml|json|toml|cfg|ini|html|css))"
            r"(?:`?\*\*|`)?:?\s*\n"
            r"```(\w*)\s*\n"
            r"(.*?)"
            r"\n```",
            re.DOTALL,
        )

        # Try pattern 2 first (more specific — has filename in header)
        for match in pattern_header.finditer(content):
            filename = match.group(1).strip()
            code = match.group(3).strip()
            if code:
                files.append({"filename": filename, "content": code + "\n"})

        if files:
            return files

        # Try pattern 1 (filename inside the code block)
        for match in pattern_explicit.finditer(content):
            lang = match.group(1) or ""
            filename = match.group(2)
            code = match.group(3).strip()
            if not code:
                continue

            if filename:
                filename = filename.strip()
            else:
                # No explicit filename — check first line for a comment-style filename
                first_line = code.split("\n", 1)[0]
                fname_match = re.match(
                    r"^(?:#|//|/\*)\s*(?:filename|file|File):\s*(.+?)(?:\s*\*/)?$",
                    first_line,
                )
                if fname_match:
                    filename = fname_match.group(1).strip()
                    code = code.split("\n", 1)[1].strip() if "\n" in code else code
                else:
                    # Derive filename from lang
                    ext = self._lang_to_ext(lang)
                    filename = f"main{ext}" if not files else f"module_{len(files)}{ext}"

            files.append({"filename": filename, "content": code + "\n"})

        return files

    def _extract_raw_code(self, content: str) -> str:
        """Extract code from a single code block, or return content as-is."""
        # Try to find a single code block
        match = re.search(r"```\w*\s*\n(.*?)\n```", content, re.DOTALL)
        if match:
            return match.group(1).strip() + "\n"
        # No code block found — return content stripped of markdown formatting
        return content.strip() + "\n"

    def _derive_filename(self, story_key: str, story_title: str) -> str:
        """Generate a reasonable filename from story key and title."""
        if story_title:
            # Convert title to snake_case filename
            slug = re.sub(r"[^a-z0-9]+", "_", story_title.lower()).strip("_")
            slug = slug[:50]  # Limit length
            return f"{slug}.py"
        return f"{story_key.lower().replace('-', '_')}_implementation.py"

    def _lang_to_ext(self, lang: str) -> str:
        """Map a language identifier to a file extension."""
        ext_map = {
            "python": ".py", "py": ".py",
            "javascript": ".js", "js": ".js",
            "typescript": ".ts", "ts": ".ts",
            "jsx": ".jsx", "tsx": ".tsx",
            "java": ".java",
            "go": ".go", "golang": ".go",
            "rust": ".rs", "rs": ".rs",
            "ruby": ".rb", "rb": ".rb",
            "bash": ".sh", "sh": ".sh", "shell": ".sh",
            "sql": ".sql",
            "yaml": ".yaml", "yml": ".yaml",
            "json": ".json",
            "html": ".html",
            "css": ".css",
            "toml": ".toml",
        }
        return ext_map.get(lang.lower(), ".py")

    def _write_manifest(
        self,
        story_dir: Path,
        story_key: str,
        story_title: str,
        user_query: str,
        saved_files: list[str],
    ) -> None:
        """Write a manifest.json with metadata about the generated code."""
        manifest = {
            "story_key": story_key,
            "story_title": story_title,
            "user_query": user_query,
            "generated_at": datetime.utcnow().isoformat(),
            "files": [str(Path(f).name) for f in saved_files],
            "file_count": len(saved_files),
        }
        manifest_path = story_dir / "manifest.json"
        try:
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to write manifest: %s", e)
