import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterator, Optional


FRONTMATTER_MAX_BYTES = 64 * 1024
READ_CHUNK_BYTES = 4 * 1024
WANT_FIELDS = {
    "title": ("title", 2),
    "date created": ("date_created", 2),
    "date_created": ("date_created", 2),
    "created": ("date_created", 1),
    "date": ("date_created", 0),
}
MAX_WORKERS = min(8, (os.cpu_count() or 4))
THREAD_THRESHOLD = 2000



@dataclass(frozen=True)
class Note:
    filepath: str
    title: str
    date_created: Optional[str]


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


def _read_frontmatter_block(path: str) -> Optional[str]:
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

            return bytes(buffer[start:end_idx]).decode("utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _parse_frontmatter_fields(block: str) -> dict[str, str]:
    want = WANT_FIELDS
    out: dict[str, str] = {}
    priority: dict[str, int] = {}

    for raw in block.splitlines():
        if not raw:
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if raw[:1].isspace():
            continue

        key, sep, value = line.partition(":")
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
            if field == "date_created" and score == 2 and "title" in out:
                break

    return out


def _parse_note_from_file(path: str) -> Optional[Note]:
    block = _read_frontmatter_block(path)
    if block is None:
        return None
    fields = _parse_frontmatter_fields(block)
    title = fields.get("title", "Untitled")
    date_created = fields.get("date_created")
    return Note(filepath=path, title=title, date_created=date_created)


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


def iter_notes_fast(vault_path: str) -> Iterator[Note]:
    vault_path = os.path.expanduser(vault_path)
    paths = list(_iter_markdown_files(vault_path))
    if len(paths) < THREAD_THRESHOLD or MAX_WORKERS <= 1:
        for path in paths:
            note = _parse_note_from_file(path)
            if note is not None:
                yield note
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for note in executor.map(_parse_note_from_file, paths, chunksize=64):
            if note is not None:
                yield note


def collect_frontmatter(vault_path: str) -> list[dict]:
    notes: list[dict] = []
    for note in iter_notes_fast(vault_path):
        notes.append(
            {
                "filepath": note.filepath,
                "title": note.title,
                "date_created": note.date_created,
            }
        )
    return notes


def fzf_pick_note(vault_path: str) -> str | None:
    if shutil.which("fzf") is None:
        print("Error: fzf not found in PATH")
        return None
    entries = []
    for note in iter_notes_fast(vault_path):
        title = note.title.replace("\t", " ").replace("\n", " ").strip()
        entries.append((title, note.filepath))
    if not entries:
        print("No markdown files found")
        return None
    lines = [f"{title}\t{path}" for title, path in entries]
    preview_cmd = "sed -n '1,120p' {2} 2>/dev/null"
    if shutil.which("bat") is not None:
        preview_cmd = "bat --style=plain --color=always --line-range 1:120 {2} 2>/dev/null"

    proc = subprocess.run(
        [
            "fzf",
            "--delimiter=\t",
            "--with-nth=1",
            "--preview",
            preview_cmd,
        ],
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
        return path_str
    except ValueError:
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse frontmatter quickly (no YAML).")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    parser.add_argument(
        "--fzf",
        action="store_true",
        help="Pick a note title via fzf and open in nvim",
    )
    args = parser.parse_args()

    if args.fzf:
        selected = fzf_pick_note(args.vault_path)
        if selected:
            subprocess.run(["nvim", selected])
        raise SystemExit(0)

    start_time = time.perf_counter()
    notes = collect_frontmatter(args.vault_path)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print("frontmatter_fast")
    print(f"total time: {elapsed_ms:.2f}ms")
    print("first 5 results:")
    print(json.dumps(notes[:5], indent=2, ensure_ascii=False, default=str))
