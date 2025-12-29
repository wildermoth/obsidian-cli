#!/usr/bin/env python3
import argparse
import importlib
import json
import time

RUN_ORDER = [
    "frontmatter_fast",
    "frontmatter_rg",
    "frontmatter_pyyaml",
    "frontmatter_ryml",
    "frontmatter_ryml_min",
]


def load_runner(module_name: str):
    module = importlib.import_module(module_name)
    func = getattr(module, "collect_frontmatter", None)
    if func is None:
        raise RuntimeError(f"{module_name}.collect_frontmatter not found")
    return func


def run_one(name: str, func, vault_path: str):
    start = time.perf_counter()
    results = func(vault_path)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(name)
    print(f"total time: {elapsed_ms:.2f}ms")
    print(f"total results: {len(results)}")
    print("first result:")
    print(json.dumps(results[:1], indent=2, ensure_ascii=False, default=str))
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark frontmatter parsers.")
    parser.add_argument("vault_path", help="Path to the Obsidian vault")
    args = parser.parse_args()

    for module_name in RUN_ORDER:
        try:
            func = load_runner(module_name)
        except Exception as exc:
            print(module_name)
            print(f"error: {exc}")
            print()
            continue

        run_one(module_name, func, args.vault_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
