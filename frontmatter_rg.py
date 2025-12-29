import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Iterator, Optional

FRONTMATTER_PATTERN = r"(?s)\A---\s*\n.*?\n---\s*(?:\n|$)"
WANT_FIELDS = {
    "title": ("title", 2),
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


def _strip_frontmatter_block(block: str) -> str:
    if block.startswith("---"):
        _, _, block = block.partition("\n")
    end_idx = block.rfind("\n---")
    if end_idx != -1:
        block = block[:end_idx]
    return block


def _parse_frontmatter_fields(block: str) -> dict[str, str]:
    want = WANT_FIELDS
    out: dict[str, str] = {}
    priority: dict[str, int] = {}

    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1].isspace():
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key not in want:
            continue
        field, score = want[key]
        if field in priority and score < priority[field]:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            out[field] = value
            priority[field] = score

    return out


def _iter_frontmatter_blocks_rg(vault_path: str) -> Iterator[tuple[str, str]]:
    rg_path = shutil.which("rg")
    if not rg_path:
        raise RuntimeError("ripgrep (rg) not found on PATH")

    cmd = [
        rg_path,
        "-U",
        "-P",
        "--json",
        "--no-messages",
        "-g",
        "*.md",
        FRONTMATTER_PATTERN,
        vault_path,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "match":
            continue
        data = payload.get("data", {})
        path = data.get("path", {}).get("text")
        block = data.get("lines", {}).get("text")
        if not path or not block:
            continue
        yield path, block

    proc.stdout.close()
    proc.wait()


def iter_notes_with_rg(vault_path: str) -> Iterator[Note]:
    vault_path = os.path.expanduser(vault_path)
    for path, block in _iter_frontmatter_blocks_rg(vault_path):
        fields = _parse_frontmatter_fields(_strip_frontmatter_block(block))
        title = fields.get("title", "Untitled")
        date_created = fields.get("date_created")
        yield Note(filepath=path, title=title, date_created=date_created)


def collect_frontmatter(vault_path: str) -> list[dict]:
    notes: list[dict] = []
    for note in iter_notes_with_rg(vault_path):
        notes.append(
            {
                "filepath": note.filepath,
                "title": note.title,
                "date_created": note.date_created,
            }
        )
    return notes


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse frontmatter using ripgrep.")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    args = parser.parse_args()

    start_time = time.perf_counter()
    notes = collect_frontmatter(args.vault_path)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print("frontmatter_rg")
    print(f"total time: {elapsed_ms:.2f}ms")
    print("first 5 results:")
    print(json.dumps(notes[:5], indent=2, ensure_ascii=False, default=str))
