#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys


TOOLS = [
    ("frontmatter_yaml_rust2", "./target/release/obsidian_cli"),
    ("frontmatter_saphyr", "./target/release/frontmatter_saphyr"),
    ("frontmatter_ryml", "./target/release/frontmatter_ryml"),
    ("frontmatter_fast", "./target/release/frontmatter_fast"),
]


def build_release() -> None:
    subprocess.run(["cargo", "build", "--release"], check=True)


def ensure_binaries() -> None:
    missing = [path for _, path in TOOLS if not os.path.exists(path)]
    if missing:
        build_release()


def run_tool(path: str, vault_path: str, last_n: int | None, show_count: bool) -> str:
    args = [path, vault_path]
    if last_n is not None:
        args.extend(["--last-n", str(last_n)])
    if show_count:
        args.append("--count")
    return subprocess.check_output(args, text=True)


def parse_metrics(output: str) -> tuple[float, int | None]:
    time_match = re.search(r"total time: ([0-9.]+)ms", output)
    if not time_match:
        raise RuntimeError("missing total time")
    time_ms = float(time_match.group(1))

    count_match = re.search(r"count: (\d+)", output)
    count = int(count_match.group(1)) if count_match else None
    return time_ms, count


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Rust frontmatter parsers.")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    parser.add_argument(
        "-n", "--last-n", type=int, help="Print last N results before benchmark"
    )
    parser.add_argument("-c", "--count", action="store_true", help="Show count column")
    args = parser.parse_args()

    ensure_binaries()

    if args.last_n is not None:
        for name, path in TOOLS:
            print(f"{name} preview (last {args.last_n}):")
            output = run_tool(path, args.vault_path, args.last_n, False)
            print(output.rstrip())

    rows: list[tuple[str, float, int | None]] = []
    for name, path in TOOLS:
        output = run_tool(path, args.vault_path, None, args.count)
        time_ms, count = parse_metrics(output)
        rows.append((name, time_ms, count))

    name_width = max(len(name) for name, _, _ in rows)
    time_header = "time_ms"
    count_header = "count"
    if args.count:
        header = f"{'tool':<{name_width}}  {time_header:>10}  {count_header:>10}"
    else:
        header = f"{'tool':<{name_width}}  {time_header:>10}"
    print(header)
    print("-" * len(header))

    for name, time_ms, count in rows:
        if args.count:
            count_str = str(count if count is not None else "-")
            print(f"{name:<{name_width}}  {time_ms:>10.2f}  {count_str:>10}")
        else:
            print(f"{name:<{name_width}}  {time_ms:>10.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
