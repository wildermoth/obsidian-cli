#!/usr/bin/env python3
"""
Blazingly fast YAML field analyzer for Obsidian vaults using rapidyaml.
Extracts all unique YAML fields and counts notes containing each field.
"""

import os
import sys
import time
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Set

import ryml


@contextmanager
def suppress_stderr():
    """Suppress stderr output from ryml C++ errors."""
    stderr_fd = sys.stderr.fileno()
    with os.fdopen(os.dup(stderr_fd), 'wb') as old_stderr:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stderr_fd)
        os.close(devnull)
        try:
            yield
        finally:
            os.dup2(old_stderr.fileno(), stderr_fd)


@dataclass
class VaultStats:
    """Statistics about YAML fields in the vault."""
    field_counts: dict[str, int]
    total_notes: int
    notes_with_frontmatter: int
    parse_time_ms: float
    failed_parses: int


def decode_ryml_key(key_bytes: object) -> str:
    """Decode ryml key bytes/memoryview to a string."""
    if isinstance(key_bytes, str):
        return key_bytes
    try:
        return bytes(key_bytes).decode("utf-8", errors="ignore")
    except Exception:
        return str(key_bytes)


def extract_frontmatter_bytes(content: bytes) -> bytes | None:
    """Extract YAML frontmatter as bytes (ryml needs bytes)."""
    if not content.startswith(b"---"):
        return None
    try:
        end_idx = content.index(b"\n---", 4)
        return content[4:end_idx]
    except ValueError:
        return None


def _ryml_val(tree: ryml.Tree, node_id: int) -> str:
    try:
        return decode_ryml_key(tree.val(node_id)).strip()
    except Exception:
        return ""


def ryml_to_python(tree: ryml.Tree, node_id: int):
    if tree.is_map(node_id):
        out: dict[str, object] = {}
        child = tree.first_child(node_id)
        while child != ryml.NONE:
            if tree.has_key(child):
                key = decode_ryml_key(tree.key(child)).strip()
                if tree.is_container(child):
                    out[key] = ryml_to_python(tree, child)
                else:
                    out[key] = _ryml_val(tree, child)
            child = tree.next_sibling(child)
        return out
    if tree.is_seq(node_id):
        items: list[object] = []
        child = tree.first_child(node_id)
        while child != ryml.NONE:
            if tree.is_container(child):
                items.append(ryml_to_python(tree, child))
            else:
                items.append(_ryml_val(tree, child))
            child = tree.next_sibling(child)
        return items
    return _ryml_val(tree, node_id)


def parse_frontmatter_ryml(yaml_bytes: bytes) -> dict | None:
    if not yaml_bytes or not yaml_bytes.strip():
        return None
    try:
        tree = ryml.parse_in_arena(yaml_bytes)
    except Exception:
        return None
    root = tree.root_id()
    if not tree.is_map(root):
        return None
    data = ryml_to_python(tree, root)
    if not isinstance(data, dict):
        return None
    return data


def collect_frontmatter(vault_path: str, suppress_errors: bool = True) -> list[dict]:
    vault = Path(vault_path).expanduser()
    md_files = list(vault.rglob("*.md"))
    notes: list[dict] = []

    suppress_ctx = suppress_stderr() if suppress_errors else nullcontext()
    with suppress_ctx:
        for file_path in md_files:
            try:
                content = file_path.read_bytes()
                yaml_bytes = extract_frontmatter_bytes(content)
                if yaml_bytes is None:
                    continue

                data = parse_frontmatter_ryml(yaml_bytes)
                if not data:
                    continue

                title = data.get("title") or file_path.stem
                notes.append(
                    {
                        "filepath": str(file_path),
                        "title": title,
                        "frontmatter": data,
                    }
                )
            except Exception:
                continue

    return notes

def extract_title_ryml(yaml_bytes: bytes) -> str | None:
    """Extract the top-level title field from YAML."""
    if not yaml_bytes or not yaml_bytes.strip():
        return None

    try:
        tree = ryml.parse_in_arena(yaml_bytes)
        root = tree.root_id()
        if not tree.is_map(root):
            return None

        child = tree.first_child(root)
        while child != ryml.NONE:
            if tree.has_key(child):
                key = decode_ryml_key(tree.key(child)).strip()
                if key == "title":
                    return decode_ryml_key(tree.val(child)).strip()
            child = tree.next_sibling(child)

        return None
    except Exception:
        return None


def extract_field_names_ryml_toplevel_only(yaml_bytes: bytes) -> Set[str] | None:
    """
    Extract only top-level field names (faster, simpler).
    Returns None on parse error.
    """
    if not yaml_bytes or not yaml_bytes.strip():
        return set()

    try:
        tree = ryml.parse_in_arena(yaml_bytes)
        root = tree.root_id()
        if not tree.is_map(root):
            return set()

        fields = set()
        child = tree.first_child(root)
        while child != ryml.NONE:
            if tree.has_key(child):
                key = decode_ryml_key(tree.key(child))
                fields.add(key)
            child = tree.next_sibling(child)

        return fields

    except Exception:
        return None


def extract_field_names_ryml(yaml_bytes: bytes) -> Set[str] | None:
    """
    Extract all field names from YAML using ryml tree traversal.
    Returns None on parse error.
    """
    if not yaml_bytes or not yaml_bytes.strip():
        return set()

    try:
        tree = ryml.parse_in_arena(yaml_bytes)
        root = tree.root_id()
        fields = set()

        def traverse_node(node_id: int, prefix: str = ""):
            """Recursively extract all field names (including nested)."""
            if tree.is_map(node_id):
                child = tree.first_child(node_id)
                while child != ryml.NONE:
                    if tree.has_key(child):
                        key = decode_ryml_key(tree.key(child))
                        full_key = f"{prefix}{key}" if prefix else key
                        fields.add(full_key)

                        if tree.is_container(child):
                            traverse_node(child, f"{full_key}.")

                    child = tree.next_sibling(child)

            elif tree.is_seq(node_id):
                child = tree.first_child(node_id)
                while child != ryml.NONE:
                    if tree.is_container(child):
                        traverse_node(child, prefix)
                    child = tree.next_sibling(child)

        traverse_node(root)
        return fields

    except Exception:
        return None


def process_note(file_path: Path, include_nested: bool) -> Set[str] | None:
    """Process a single note and return its field set (or None on parse error)."""
    try:
        content = file_path.read_bytes()
        yaml_bytes = extract_frontmatter_bytes(content)

        if yaml_bytes is None:
            return set()

        if include_nested:
            return extract_field_names_ryml(yaml_bytes)

        return extract_field_names_ryml_toplevel_only(yaml_bytes)
    except Exception:
        return None


def process_note_batch(file_paths: list[Path], include_nested: bool) -> list[Set[str] | None]:
    """Process a batch of notes and return their field sets."""
    return [process_note(file_path, include_nested) for file_path in file_paths]


def collect_titles(vault_path: str, suppress_errors: bool = True) -> list[tuple[str, Path]]:
    """Collect note titles with their file paths."""
    vault = Path(vault_path)
    md_files = list(vault.rglob("*.md"))
    entries: list[tuple[str, Path]] = []

    suppress_ctx = suppress_stderr() if suppress_errors else nullcontext()
    with suppress_ctx:
        for file_path in md_files:
            try:
                content = file_path.read_bytes()
                yaml_bytes = extract_frontmatter_bytes(content)

                title = None
                if yaml_bytes is not None:
                    title = extract_title_ryml(yaml_bytes)

                if not title:
                    title = file_path.stem

                title = title.replace("\t", " ").replace("\n", " ").strip()
                entries.append((title, file_path))
            except Exception:
                continue

    return entries


def fzf_pick_note(vault_path: str) -> Path | None:
    """Pipe titles to fzf and return the selected note path."""
    if shutil.which("fzf") is None:
        print("Error: fzf not found in PATH")
        return None

    entries = collect_titles(vault_path)
    if not entries:
        print("No markdown files found")
        return None

    lines = [f"{title}\t{path}" for title, path in entries]
    proc = subprocess.run(
        ["fzf", "--delimiter=\t", "--with-nth=1"],
        input="\n".join(lines),
        text=True,
        stdout=subprocess.PIPE,
    )

    if proc.returncode != 0:
        return None

    selection = proc.stdout.strip()
    if not selection:
        return None

    try:
        _, path_str = selection.split("\t", 1)
        return Path(path_str)
    except ValueError:
        return None


def analyze_vault(
    vault_path: str, 
    max_workers: int = 1, 
    include_nested: bool = False,
    batch_size: int = 50,
    suppress_errors: bool = True,
) -> VaultStats:
    """
    Analyze all YAML fields in an Obsidian vault.

    Args:
        vault_path: Path to the Obsidian vault
        max_workers: Number of parallel workers for file I/O
        include_nested: If True, include nested fields with dot notation
        batch_size: Files per batch (tune for optimal performance)

    Returns:
        VaultStats with field counts and timing information
    """
    start_time = time.perf_counter()

    vault = Path(vault_path)
    md_files = list(vault.rglob("*.md"))

    # Batch the files for better threading performance
    batches = [md_files[i:i + batch_size] for i in range(0, len(md_files), batch_size)]

    field_counter = Counter()
    notes_with_frontmatter = 0
    failed_parses = 0

    suppress_ctx = suppress_stderr() if suppress_errors else nullcontext()
    with suppress_ctx:
        if max_workers <= 1:
            for file_path in md_files:
                fields = process_note(file_path, include_nested)
                if fields is None:
                    failed_parses += 1
                elif fields:
                    notes_with_frontmatter += 1
                    for field in fields:
                        field_counter[field] += 1
        else:
            # Process batches in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                batch_results = executor.map(
                    lambda batch: process_note_batch(batch, include_nested),
                    batches
                )

                for batch_result in batch_results:
                    for fields in batch_result:
                        if fields is None:
                            failed_parses += 1
                        elif fields:
                            notes_with_frontmatter += 1
                            for field in fields:
                                field_counter[field] += 1

    parse_time = (time.perf_counter() - start_time) * 1000

    return VaultStats(
        field_counts=dict(field_counter),
        total_notes=len(md_files),
        notes_with_frontmatter=notes_with_frontmatter,
        parse_time_ms=parse_time,
        failed_parses=failed_parses,
    )


def print_analysis(stats: VaultStats, top_n: int = 20):
    """Pretty print the analysis results."""
    print(f"\n{'=' * 70}")
    print(f"OBSIDIAN VAULT YAML FIELD ANALYSIS")
    print(f"{'=' * 70}")
    print(f"Total notes: {stats.total_notes}")
    print(f"Notes with frontmatter: {stats.notes_with_frontmatter}")
    print(f"Failed parses: {stats.failed_parses}")
    print(f"Unique YAML fields: {len(stats.field_counts)}")
    print(f"Parse time: {stats.parse_time_ms:.1f}ms")
    print(f"Per-file avg: {stats.parse_time_ms / stats.total_notes * 1000:.1f}μs")
    print(f"{'=' * 70}\n")

    sorted_fields = sorted(stats.field_counts.items(), key=lambda x: x[1], reverse=True)

    print(f"Top {top_n} most common fields:\n")
    print(f"{'Field':<30} {'Count':<10} {'% of Notes'}")
    print(f"{'-' * 50}")

    for field, count in sorted_fields[:top_n]:
        percentage = (count / stats.total_notes) * 100
        print(f"{field:<30} {count:<10} {percentage:>6.1f}%")

    if len(sorted_fields) > top_n:
        print(f"\n... and {len(sorted_fields) - top_n} more fields")


def export_to_csv(stats: VaultStats, output_path: str = "field_analysis.csv"):
    """Export results to CSV for further analysis."""
    import csv

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["field_name", "note_count", "percentage"])

        for field, count in sorted(
            stats.field_counts.items(), key=lambda x: x[1], reverse=True
        ):
            percentage = (count / stats.total_notes) * 100
            writer.writerow([field, count, f"{percentage:.2f}"])

    print(f"\nExported to {output_path}")


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Parse frontmatter with ryml."
    )
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    args = parser.parse_args()

    start_time = time.perf_counter()
    notes = collect_frontmatter(args.vault_path)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print("frontmatter_ryml")
    print(f"total time: {elapsed_ms:.2f}ms")
    print("first 5 results:")
    print(json.dumps(notes[:5], indent=2, ensure_ascii=False, default=str))

    # Optionally export to CSV
    if sys.stdout.isatty():  # Only prompt if running interactively
        export_choice = input("\nExport to CSV? (y/n): ").strip().lower()
        if export_choice == "y":
            export_to_csv(stats)
