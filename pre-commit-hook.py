#!/usr/bin/env python3
"""
Pre-commit hook for automated markdown translation
Ensures all new Chinese markdown files are translated to English and Malay
"""

import sys
import os
import subprocess
from pathlib import Path

class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'

def run_command(cmd):
    """Run shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def print_color(message, color):
    """Print colored message"""
    print(f"{color}{message}{Colors.NC}")

def get_staged_chinese_files():
    """Get list of staged Chinese markdown files"""
    returncode, stdout, stderr = run_command("git diff --cached --name-only --diff-filter=ACM | grep '^zh/' | grep '.md$'")
    if returncode == 0 and stdout.strip():
        return [f.strip() for f in stdout.strip().split('\n') if f.strip()]
    return []

def run_translator(content_dir, scripts_dir):
    """Run the translator script"""
    translator_script = scripts_dir / "translator.py"
    if not translator_script.exists():
        print_color(f"❌ translator.py not found in {scripts_dir}", Colors.RED)
        return False

    # Change to scripts directory to run translator
    os.chdir(scripts_dir)
    # Add scripts directory to Python path so imports work
    returncode, stdout, stderr = run_command(f"python3 {translator_script} --all")

    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)

    return returncode == 0

def verify_translations(content_dir, staged_files):
    """Verify that translations were created for all staged files"""
    missing = []

    for zh_file in staged_files:
        # Remove 'zh/' prefix to get relative path
        relative_path = zh_file.replace('zh/', '', 1)
        en_file = content_dir / 'en' / relative_path
        ms_file = content_dir / 'ms' / relative_path

        if not en_file.exists():
            missing.append(f"English: en/{relative_path}")

        if not ms_file.exists():
            missing.append(f"Malay: ms/{relative_path}")

    return missing

def stage_translations(content_dir, staged_files):
    """Stage translated files"""
    staged_count = 0

    for zh_file in staged_files:
        relative_path = zh_file.replace('zh/', '', 1)
        en_file = f"en/{relative_path}"
        ms_file = f"ms/{relative_path}"

        if (content_dir / 'en' / relative_path).exists():
            run_command(f"git add '{en_file}'")
            print_color(f"  ✓ Staged {en_file}", Colors.GREEN)
            staged_count += 1

        if (content_dir / 'ms' / relative_path).exists():
            run_command(f"git add '{ms_file}'")
            print_color(f"  ✓ Staged {ms_file}", Colors.GREEN)
            staged_count += 1

    # Stage translation history
    config_file = content_dir / ".translation_config.json"
    if config_file.exists():
        run_command("git add '.translation_config.json'")
        print_color(f"  ✓ Staged .translation_config.json", Colors.GREEN)
        staged_count += 1

    return staged_count

def find_content_and_scripts_dir():
    """Find content and scripts directories"""
    possible_paths = [
        Path.cwd() / "the-morning-word" / "content",
        Path.cwd() / "content",
        Path.cwd(),
    ]

    for path in possible_paths:
        if (path / "zh").exists() and (path / "en").exists():
            # Find scripts directory (usually ../scripts relative to content)
            scripts_dir = path.parent / "scripts"
            if not scripts_dir.exists():
                scripts_dir = Path.cwd() / "scripts"
            if not scripts_dir.exists():
                scripts_dir = Path(__file__).parent
            return path, scripts_dir

    return None, None

def main():
    """Main pre-commit hook logic"""
    print_color("🔍 Pre-commit: Checking for untranslated Chinese markdown files...", Colors.BLUE)

    # Find content and scripts directories
    content_dir, scripts_dir = find_content_and_scripts_dir()
    if not content_dir or not scripts_dir:
        print_color("⚠️  Content or scripts directory not found, skipping translation check", Colors.YELLOW)
        return 0

    # Get staged Chinese files
    staged_files = get_staged_chinese_files()
    if not staged_files:
        print_color("✅ No new Chinese markdown files staged", Colors.GREEN)
        return 0

    print_color("📝 Found staged Chinese markdown files:", Colors.YELLOW)
    for f in staged_files:
        print(f"  - {f}")

    # Run translator
    print_color("🔄 Running translator...", Colors.BLUE)
    if not run_translator(content_dir, scripts_dir):
        print_color("❌ Translation failed", Colors.RED)
        return 1

    # Verify translations
    print_color("✓ Verifying translations...", Colors.BLUE)
    missing = verify_translations(content_dir, staged_files)

    if missing:
        print_color(f"❌ Commit blocked: Missing {len(missing)} translation(s):", Colors.RED)
        for m in missing:
            print_color(f"  - {m}", Colors.RED)
        return 1

    # Stage translations
    print_color("📦 Staging translated files...", Colors.BLUE)
    staged_count = stage_translations(content_dir, staged_files)

    print_color(f"✅ All translations verified and {staged_count} file(s) staged!", Colors.GREEN)
    return 0

if __name__ == "__main__":
    sys.exit(main())
