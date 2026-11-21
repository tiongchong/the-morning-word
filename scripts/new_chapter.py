#!/usr/bin/env python3
"""Scaffold a chapter Markdown file for a given language, book, and chapter number."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a chapter file.")
    parser.add_argument("--lang", choices=["zh", "en", "ms"], default="zh")
    parser.add_argument("--book", required=True, help="Book slug, e.g. 01-genesis")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number, e.g. 1")
    parser.add_argument("--verses", type=int, default=5, help="Number of verse sections to stub")
    args = parser.parse_args()

    chapter_slug = f"ch-{args.chapter:02d}.md"
    target = ROOT / "content" / args.lang / args.book / chapter_slug
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        raise SystemExit(f"Already exists: {target}")

    lines = [f"# Chapter {args.chapter}", ""]
    for v in range(1, args.verses + 1):
        lines.extend([f"## Verse {v} {{#v{v}}}", "", "<!-- Add text here -->", ""])

    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Created {target}")


if __name__ == "__main__":
    main()
