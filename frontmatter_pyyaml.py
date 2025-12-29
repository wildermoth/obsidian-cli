import json
import os
import time
from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterator, Optional

import yaml

# --- CONFIG ---
FRONTMATTER_MAX_BYTES = 64 * 1024


def _get_yaml_loader():
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    loader.yaml_implicit_resolvers = {
        k: [pair for pair in v if pair[0] != "tag:yaml.org,2002:timestamp"]
        for k, v in loader.yaml_implicit_resolvers.items()
    }
    return loader


YAML_LOADER = _get_yaml_loader()


def _read_frontmatter_block(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            first_line = handle.readline()
            if first_line.strip() != "---":
                return None

            lines: list[str] = []
            total = 0
            for line in handle:
                if line.strip() == "---":
                    return "".join(lines)
                lines.append(line)
                total += len(line)
                if total > FRONTMATTER_MAX_BYTES:
                    return None
    except (UnicodeDecodeError, OSError):
        return None

    return None


# --- DATA MODELS ---
@dataclass(frozen=True)
class NoteFrontmatter:
    title: str = "Untitled"
    aliases: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict) -> "NoteFrontmatter":
        title_value = data.get("title")
        title = "Untitled" if title_value in (None, "") else str(title_value)

        aliases = data.get("aliases", [])
        if aliases is None:
            alias_list: list[str] = []
        elif isinstance(aliases, list):
            alias_list = [str(alias) for alias in aliases if alias is not None]
        else:
            alias_list = [str(aliases)]

        return cls(title=title, aliases=alias_list)


@dataclass
class MarkdownNote:
    filepath: str

    @cached_property
    def frontmatter(self) -> Optional[NoteFrontmatter]:
        """Lazy-loaded frontmatter - only parsed when first accessed, then cached."""
        block = _read_frontmatter_block(self.filepath)
        if block is None:
            return None

        try:
            data = yaml.load(block, Loader=YAML_LOADER)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        return NoteFrontmatter.from_mapping(data)

    @property
    def has_frontmatter(self) -> bool:
        """Check if note has valid frontmatter."""
        return self.frontmatter is not None


def _parse_frontmatter_mapping(block: str) -> Optional[dict]:
    try:
        data = yaml.load(block, Loader=YAML_LOADER)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def collect_frontmatter(vault_path: str) -> list[dict]:
    vault = Vault(vault_path=vault_path)
    notes: list[dict] = []

    for note in vault:
        block = _read_frontmatter_block(note.filepath)
        if block is None:
            continue
        data = _parse_frontmatter_mapping(block)
        if data is None:
            continue

        frontmatter = NoteFrontmatter.from_mapping(data)
        notes.append(
            {
                "filepath": note.filepath,
                "title": frontmatter.title,
                "aliases": frontmatter.aliases,
                "frontmatter": data,
            }
        )

    return notes


@dataclass
class Vault:
    vault_path: str

    def __post_init__(self):
        # Expand ~ to home directory
        self.vault_path = os.path.expanduser(self.vault_path)

    def __iter__(self) -> Iterator[MarkdownNote]:
        """Yields notes one at a time (memory efficient)."""
        for root, _, files in os.walk(self.vault_path):
            for filename in files:
                if filename.endswith(".md"):
                    yield MarkdownNote(filepath=os.path.join(root, filename))

    def __len__(self) -> int:
        """Count of markdown files in vault."""
        count = 0
        for _, _, files in os.walk(self.vault_path):
            for filename in files:
                if filename.endswith(".md"):
                    count += 1
        return count


# --- EXECUTION ---
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse frontmatter with PyYAML.")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    args = parser.parse_args()

    start_time = time.perf_counter()
    notes = collect_frontmatter(args.vault_path)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print("frontmatter_pyyaml")
    print(f"total time: {elapsed_ms:.2f}ms")
    print("first 5 results:")
    print(json.dumps(notes[:5], indent=2, ensure_ascii=False, default=str))
