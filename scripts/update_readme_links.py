#!/usr/bin/env python3
"""Sync links to index.md files inside content/ into README.md."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
README_PATH = ROOT / "README.md"

START_MARKER = "<!-- CONTENT_LINKS_START -->"
END_MARKER = "<!-- CONTENT_LINKS_END -->"

# Explicit labels and ordering for known index.md paths
LABEL_ORDER: list[tuple[str, str]] = [
    ("content/zh/index.md", "中文"),
    ("content/zh/01-genesis/index.md", "中文/创世记"),
    ("content/en/index.md", "Englsh"),
    ("content/ms/index.md", "Malay"),
]


def fallback_label(rel_path: str) -> str:
    # Fallback for future book index files like content/zh/02-exodus/index.md
    parts = Path(rel_path).parts
    if len(parts) >= 4 and parts[0] == "content":
        lang = parts[1]
        book = parts[2]
        return f"{lang}/{book}"
    return rel_path


def build_links_block() -> str:
    if not CONTENT_DIR.exists():
        return "_No content files found yet._"

    existing_index_files = {
        p.relative_to(ROOT).as_posix()
        for p in CONTENT_DIR.rglob("index.md")
    }

    if not existing_index_files:
        return "_No `index.md` files inside `content/` yet._"

    lines: list[str] = []
    seen: set[str] = set()

    # 1. Emit explicitly ordered/labeled index files first
    for rel_path, label in LABEL_ORDER:
        if rel_path in existing_index_files:
            lines.append(f"- [{label}]({rel_path})")
            seen.add(rel_path)

    # 2. Emit any additional index.md files added later in sorted order
    for rel_path in sorted(existing_index_files):
        if rel_path not in seen:
            lines.append(f"- [{fallback_label(rel_path)}]({rel_path})")

    return "\n".join(lines)


def main() -> None:
    # Blank lines before and after the list satisfy MD032 (blanks-around-lists)
    block = f"{START_MARKER}\n\n{build_links_block()}\n\n{END_MARKER}"
    readme_text = README_PATH.read_text(encoding="utf-8")

    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )

    if pattern.search(readme_text):
        updated = pattern.sub(block, readme_text, count=1)
    else:
        updated = readme_text.rstrip() + f"\n\n## Content Index\n\n{block}\n"

    README_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated {README_PATH} with index links from {CONTENT_DIR}")


if __name__ == "__main__":
    main()
