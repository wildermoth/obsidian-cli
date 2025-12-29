#!/usr/bin/env python3
"""
Minimal, optimized ryml frontmatter parser.
Focuses on a few top-level fields and avoids full YAML conversion.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import ryml


class _SuppressStderr:
    def __enter__(self):
        self._stderr_fd = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        os.close(devnull)
        return self

    def __exit__(self, exc_type, exc, tb):
        os.dup2(self._stderr_fd, 2)
        os.close(self._stderr_fd)
        return False

FRONTMATTER_MAX_BYTES = 64 * 1024
READ_CHUNK_BYTES = 4 * 1024

WANT_FIELDS = {
    "title": ("title", 2),
    "aliases": ("aliases", 2),
    "alias": ("aliases", 1),
    "date created": ("date_created", 2),
    "date_created": ("date_created", 2),
    "created": ("date_created", 1),
    "date": ("date_created", 0),
}


@dataclass(frozen=True)
class Note:
    filepath: str
    title: str
    date_created: Optional[str]
    aliases: list[str]


def decode_ryml_value(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return bytes(value).decode("utf-8", errors="ignore")
    except Exception:
        return str(value)


def _find_frontmatter_end(buffer: bytes, start: int) -> Optional[int]:
    idx = buffer.find(b"\n---", start)
    while idx != -1:
        cursor = idx + 4
        while cursor < len(buffer) and buffer[cursor] in (32, 9):
            cursor += 1
        if cursor >= len(buffer):
            return idx
        if buffer[cursor:cursor + 1] == b"\n":
            return idx
        if buffer[cursor:cursor + 1] == b"\r":
            if cursor + 1 >= len(buffer) or buffer[cursor + 1:cursor + 2] == b"\n":
                return idx
        idx = buffer.find(b"\n---", idx + 1)
    return None


def _read_frontmatter_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as handle:
            buffer = bytearray(handle.read(READ_CHUNK_BYTES))
            if not buffer:
                return None

            newline_idx = buffer.find(b"\n")
            while newline_idx == -1 and len(buffer) < FRONTMATTER_MAX_BYTES:
                chunk = handle.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                buffer.extend(chunk)
                newline_idx = buffer.find(b"\n")
            if newline_idx == -1:
                return None

            first_line = bytes(buffer[:newline_idx]).rstrip(b"\r")
            if first_line.strip() != b"---":
                return None

            start = newline_idx + 1
            end_idx = _find_frontmatter_end(buffer, start)
            while end_idx is None and len(buffer) < FRONTMATTER_MAX_BYTES:
                chunk = handle.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                buffer.extend(chunk)
                end_idx = _find_frontmatter_end(buffer, start)
            if end_idx is None:
                return None

            return bytes(buffer[start:end_idx])
    except (OSError, UnicodeDecodeError):
        return None


def _iter_markdown_files(vault_path: str) -> Iterator[str]:
    stack = [vault_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".md"):
                        yield entry.path
        except OSError:
            continue


def _extract_fields_min(yaml_bytes: bytes) -> Optional[dict]:
    if not yaml_bytes or not yaml_bytes.strip():
        return None
    try:
        tree = ryml.parse_in_arena(yaml_bytes)
    except Exception:
        return None

    root = tree.root_id()
    if not tree.is_map(root):
        return None

    out: dict[str, object] = {}
    priority: dict[str, int] = {}

    child = tree.first_child(root)
    while child != ryml.NONE:
        if tree.has_key(child):
            key = decode_ryml_value(tree.key(child)).strip()
            if key not in WANT_FIELDS:
                child = tree.next_sibling(child)
                continue
            field, score = WANT_FIELDS[key]

            if field == "aliases":
                if tree.is_seq(child):
                    items: list[str] = []
                    item = tree.first_child(child)
                    while item != ryml.NONE:
                        if not tree.is_container(item):
                            val = decode_ryml_value(tree.val(item)).strip()
                            if val:
                                items.append(val)
                        item = tree.next_sibling(item)
                    if items:
                        out["aliases"] = items
                elif not tree.is_container(child):
                    val = decode_ryml_value(tree.val(child)).strip()
                    if val:
                        out["aliases"] = [val]
            elif field == "date_created":
                if field in priority and score < priority[field]:
                    child = tree.next_sibling(child)
                    continue
                if not tree.is_container(child):
                    val = decode_ryml_value(tree.val(child)).strip()
                    if val:
                        out[field] = val
                        priority[field] = score
            elif field == "title":
                if not tree.is_container(child):
                    val = decode_ryml_value(tree.val(child)).strip()
                    if val:
                        out[field] = val

        child = tree.next_sibling(child)

    return out


def collect_frontmatter(vault_path: str) -> list[dict]:
    vault_path = os.path.expanduser(vault_path)
    notes: list[dict] = []
    with _SuppressStderr():
        for path in _iter_markdown_files(vault_path):
            yaml_bytes = _read_frontmatter_bytes(path)
            if yaml_bytes is None:
                continue

            fields = _extract_fields_min(yaml_bytes)
            if fields is None:
                continue

            title = fields.get("title") or os.path.splitext(os.path.basename(path))[0]
            aliases = fields.get("aliases") or []
            date_created = fields.get("date_created")
            notes.append(
                {
                    "filepath": path,
                    "title": title,
                    "aliases": aliases,
                    "date_created": date_created,
                }
            )
    return notes


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Minimal ryml frontmatter parser.")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    args = parser.parse_args()

    start_time = time.perf_counter()
    notes = collect_frontmatter(args.vault_path)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print("frontmatter_ryml_min")
    print(f"total time: {elapsed_ms:.2f}ms")
    print("first 5 results:")
    print(json.dumps(notes[:5], indent=2, ensure_ascii=False, default=str))
