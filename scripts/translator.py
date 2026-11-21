#!/usr/bin/env python3
"""
Automated Chinese Markdown Translator
- Monitors zh/ folder for new/modified Chinese markdown files
- Translates to en/ and ms/ folders
- Preserves folder structure and filename
"""

import re
import os
import sys
import json
import shutil
import time
import atexit
import urllib.parse
from typing import List, Tuple, Dict, Set
from pathlib import Path
from datetime import datetime
import hashlib

# Ensure user site-packages are in path
user_site_packages = os.path.expanduser("~/.local/lib/python3.10/site-packages")
if user_site_packages not in sys.path and os.path.exists(user_site_packages):
    sys.path.insert(0, user_site_packages)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("Installing required packages...")
    os.system("pip install selenium webdriver-manager")
    # Try again with updated path
    user_site_packages = os.path.expanduser("~/.local/lib/python3.10/site-packages")
    if user_site_packages not in sys.path:
        sys.path.insert(0, user_site_packages)
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager


# Browser singleton for Selenium-based translation
_driver = None
_requests_since_restart = 0
_max_requests_before_restart = 5  # Restart browser after every 5 requests to avoid memory leak


def _get_driver():
    """Get or create a Chrome WebDriver instance (singleton pattern)"""
    global _driver, _requests_since_restart

    # Restart driver periodically to avoid memory buildup
    if _requests_since_restart >= _max_requests_before_restart:
        _close_driver()
        _requests_since_restart = 0

    if _driver is None:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-breakpad")
        options.add_argument("--disable-client-side-phishing-detection")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-sync")
        # Suppress logging noise
        options.add_argument("--log-level=3")

        try:
            _driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
        except Exception as e:
            raise Exception(f"Failed to initialize Chrome WebDriver: {e}")

    return _driver


def _close_driver():
    """Close the Chrome WebDriver instance"""
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


# Register cleanup function to run on exit
atexit.register(_close_driver)


def translate_text(text: str, target_lang: str = "en", max_retries: int = 3) -> str:
    """
    Translate text using browser automation with Google Translate website
    Uses text input instead of URL parameters to avoid length limits
    """
    global _requests_since_restart

    for attempt in range(max_retries):
        try:
            # Add aggressive delay to avoid rate limiting
            if attempt > 0:
                # Exponential backoff: 10s, 20s, 40s...
                wait_time = 10 * (2 ** (attempt - 1))
                print(f"      ⏳ Retrying in {wait_time}s...", flush=True)
                time.sleep(wait_time)
                # Force browser restart on retry to recover from crashes
                _close_driver()
            else:
                # Initial delay to avoid hammering
                time.sleep(1.5)

            driver = _get_driver()

            # Load page with language parameters (but no text in URL)
            # This avoids long URL issues while setting target language
            url = f"https://translate.google.com.my/?sl=auto&tl={target_lang}"
            driver.get(url)

            # Wait for input field to be ready
            wait = WebDriverWait(driver, 10)
            # Try multiple selectors for the source textarea (Google changes them sometimes)
            source_input = None
            for selector in ["textarea[aria-label*='Source']", "textarea[jsname]", "textarea"]:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        source_input = elements[0]
                        break
                except:
                    pass

            if not source_input:
                raise Exception("Could not find source text input field")

            # Clear and input text using JavaScript (more reliable for special chars and newlines)
            driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", source_input, text)

            # Wait for translation result to appear
            wait = WebDriverWait(driver, 15)
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.ryNqvb"))
            )

            # Give it a moment to finish rendering
            time.sleep(0.5)

            # Collect all spans (long text may be split across multiple spans)
            spans = driver.find_elements(By.CSS_SELECTOR, "span.ryNqvb")
            translated = " ".join(s.text for s in spans if s.text.strip())

            if not translated:
                raise Exception("Translation result was empty")

            # Successfully translated, increment counter
            _requests_since_restart += 1
            return translated

        except Exception as e:
            error_msg = str(e)
            # Retry on timeout, crashes, or temporary errors
            if attempt < max_retries - 1:
                # On error, close driver and retry
                _close_driver()
                _requests_since_restart = 0
                continue
            else:
                # Final attempt failed, raise
                raise Exception(f"Browser translation error (attempt {attempt + 1}/{max_retries}): {e}")


class MarkdownTranslator:
    """Translate markdown while preserving syntax"""

    def __init__(self, target_language: str = "en"):
        """
        Args:
            target_language: 'en' for English, 'ms' for Malay
        """
        self.target_language = target_language
        self.lang_names = {"en": "English", "ms": "Malay"}

    def read_markdown(self, filepath: str) -> str:
        """Read markdown file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()

    def split_into_sections(self, content: str) -> List[Tuple[str, int]]:
        """
        Split markdown by headers, respecting word count limits (500-1000 words per section)
        Returns: List of (section_text, word_count) tuples
        """
        header_pattern = r'^(#{1,6})\s+'
        lines = content.split('\n')

        sections = []
        current_section = []
        current_word_count = 0
        min_words_before_header_split = 500  # Minimum words before splitting at a header
        max_words_per_section = 1000  # Target max words per section (within 500-1000 range)

        for line in lines:
            line_word_count = len(line.split())

            # Split at header if we have enough content (>500 words)
            if re.match(header_pattern, line) and current_section and current_word_count > min_words_before_header_split:
                section_text = '\n'.join(current_section)
                sections.append((section_text, current_word_count))
                current_section = [line]
                current_word_count = line_word_count
            else:
                current_section.append(line)
                current_word_count += line_word_count

                # Split if section exceeds max words
                if current_word_count > max_words_per_section:
                    section_text = '\n'.join(current_section)
                    sections.append((section_text, current_word_count))
                    current_section = []
                    current_word_count = 0

        if current_section:
            section_text = '\n'.join(current_section)
            sections.append((section_text, current_word_count))

        return sections

    def extract_translatable_text(self, section: str) -> Tuple[str, List[Tuple[int, str]]]:
        """Extract text to translate while preserving markdown structure"""
        replacements = []
        processed = section

        # Protect code blocks
        code_pattern = r'```[\s\S]*?```'
        for match in re.finditer(code_pattern, processed):
            placeholder = f"__CODE_BLOCK_{len(replacements)}__"
            replacements.append((len(replacements), match.group()))
            processed = processed.replace(match.group(), placeholder, 1)

        # Protect inline code
        inline_code_pattern = r'`[^`]+`'
        for match in re.finditer(inline_code_pattern, processed):
            placeholder = f"__INLINE_CODE_{len(replacements)}__"
            replacements.append((len(replacements), match.group()))
            processed = processed.replace(match.group(), placeholder, 1)

        # Protect URLs
        url_pattern = r'https?://[^\s\)"\]]*'
        for match in re.finditer(url_pattern, processed):
            placeholder = f"__URL_{len(replacements)}__"
            replacements.append((len(replacements), match.group()))
            processed = processed.replace(match.group(), placeholder, 1)

        # Protect image syntax
        img_pattern = r'!\[([^\]]*)\]\(([^\)]*)\)'
        for match in re.finditer(img_pattern, processed):
            placeholder = f"__IMG_{len(replacements)}__"
            replacements.append((len(replacements), match.group()))
            processed = processed.replace(match.group(), placeholder, 1)

        # Note: Headers are NOT protected - let Google Translate handle them
        # Google will naturally preserve the # symbols and translate the text

        # Protect HTML comments
        comment_pattern = r'<!--[\s\S]*?-->'
        for match in re.finditer(comment_pattern, processed):
            placeholder = f"__COMMENT_{len(replacements)}__"
            replacements.append((len(replacements), match.group()))
            processed = processed.replace(match.group(), placeholder, 1)

        # Protect markdown links [text](url) - keep structure, replace only display text
        # This is tricky, so we'll protect the entire link
        link_pattern = r'\[([^\]]*)\]\(([^\)]*)\)'
        for match in re.finditer(link_pattern, processed):
            placeholder = f"__LINK_{len(replacements)}__"
            replacements.append((len(replacements), match.group()))
            processed = processed.replace(match.group(), placeholder, 1)

        # Protect markdown list markers (but allow text to be translated)
        lines = processed.split('\n')
        for i, line in enumerate(lines):
            match = re.match(r'^([\*\-\+]\s+)', line)
            if match:
                # Extract marker (e.g., "- ") and text
                marker = match.group(1)  # e.g., "- "
                list_text = line[len(marker):]  # e.g., "第 1 ~ 2 节"
                # Protect only the marker, let text be translated
                placeholder = f"__LIST_MARKER_{len(replacements)}__"
                replacements.append((len(replacements), marker))
                lines[i] = placeholder + list_text
        processed = '\n'.join(lines)

        return processed, replacements

    def restore_protected_elements(self, text: str, replacements: List[Tuple[int, str]]) -> str:
        """Restore protected code blocks, URLs, markdown syntax, etc."""
        for idx, original in replacements:
            for placeholder_type in ["__CODE_BLOCK_", "__INLINE_CODE_", "__URL_", "__IMG_",
                                     "__COMMENT_", "__LINK_", "__LIST_MARKER_"]:
                placeholder = f"{placeholder_type}{idx}__"
                if placeholder in text:
                    text = text.replace(placeholder, original)
                    break
        return text

    def translate_section(self, section: str) -> str:
        """Translate a section of markdown"""
        processed_text, replacements = self.extract_translatable_text(section)

        if not processed_text.strip():
            return section

        try:
            translated = translate_text(processed_text, self.target_language)
            translated = self.restore_protected_elements(translated, replacements)
            return translated

        except Exception as e:
            print(f"    ⚠️  Translation error: {e}")
            return section

    def translate_file_content(self, content: str) -> str:
        """Translate entire file content in sections (500-1000 words each)"""
        sections = self.split_into_sections(content)
        translated_sections = []

        if len(sections) > 1:
            print(f"      📑 Split into {len(sections)} sections", end="", flush=True)

        for i, (section, word_count) in enumerate(sections):
            # Add delay between sections to avoid rate limiting
            if i > 0:
                time.sleep(3.0)  # 3 seconds between sections

            if len(sections) > 1:
                print(f"\r      📑 Translating section {i + 1}/{len(sections)} ({word_count} words)...", end="", flush=True)

            translated = self.translate_section(section)
            translated_sections.append(translated)

        if len(sections) > 1:
            print()  # Newline after section progress

        return '\n'.join(translated_sections)


class TranslationManager:
    """Manage translation workflow and file detection"""

    def __init__(self, base_dir: str = ".", config_file: str = ".translation_config.json"):
        """
        Args:
            base_dir: Base directory containing zh/, en/, ms/ folders
            config_file: Path to configuration and translation history file
        """
        self.base_dir = Path(base_dir).resolve()
        self.config_file = self.base_dir / config_file

        # Language folders
        self.zh_dir = self.base_dir / "zh"
        self.en_dir = self.base_dir / "en"
        self.ms_dir = self.base_dir / "ms"

        # Verify required directories exist
        if not self.zh_dir.exists():
            raise FileNotFoundError(f"zh/ folder not found at {self.zh_dir}")
        if not self.en_dir.exists():
            self.en_dir.mkdir(parents=True, exist_ok=True)
        if not self.ms_dir.exists():
            self.ms_dir.mkdir(parents=True, exist_ok=True)

        self.history = self.load_history()

    def load_history(self) -> Dict:
        """Load translation history"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"translated_files": {}, "last_check": None}

    def save_history(self) -> None:
        """Save translation history"""
        self.history["last_check"] = datetime.now().isoformat()
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)

    def get_file_hash(self, filepath: Path) -> str:
        """Calculate file hash for change detection"""
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def find_chinese_markdown_files(self) -> Set[Path]:
        """Find all Chinese markdown files in zh/ folder"""
        chinese_files = set()

        for md_file in self.zh_dir.rglob("*.md"):
            chinese_files.add(md_file)

        return chinese_files

    def get_new_or_modified_files(self) -> Set[Path]:
        """Get newly added or modified Chinese markdown files"""
        all_chinese_files = self.find_chinese_markdown_files()
        new_or_modified = set()

        for filepath in all_chinese_files:
            file_key = str(filepath.relative_to(self.zh_dir))
            current_hash = self.get_file_hash(filepath)

            if file_key not in self.history["translated_files"]:
                # New file
                new_or_modified.add(filepath)
                print(f"🆕 New file detected: zh/{file_key}")
            else:
                # Check if modified
                previous_hash = self.history["translated_files"][file_key].get("hash")
                if previous_hash != current_hash:
                    new_or_modified.add(filepath)
                    print(f"✏️  Modified file detected: zh/{file_key}")

        return new_or_modified

    def get_output_path(self, input_path: Path, language: str) -> Path:
        """
        Get output path in en/ or ms/ folder with same relative structure
        Input:  zh/01-genesis/ch-01_01-02.md
        Output: en/01-genesis/ch-01_01-02.md or ms/01-genesis/ch-01_01-02.md
        """
        relative_path = input_path.relative_to(self.zh_dir)

        if language == "en":
            return self.en_dir / relative_path
        elif language == "ms":
            return self.ms_dir / relative_path
        else:
            raise ValueError(f"Unknown language: {language}")

    def translate_file(self, input_path: Path, language: str) -> bool:
        """Translate a single file to specified language"""
        try:
            translator = MarkdownTranslator(target_language=language)
            lang_name = translator.lang_names[language]

            print(f"  📝 Translating to {lang_name}...", end=" ", flush=True)
            content = translator.read_markdown(str(input_path))
            translated_content = translator.translate_file_content(content)

            # Create output directory
            output_path = self.get_output_path(input_path, language)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write translated file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_content)

            lang_code = "en" if language == "en" else "ms"
            print(f"✅ saved to {lang_code}/{output_path.relative_to(self.base_dir / lang_code)}")
            return True

        except Exception as e:
            print(f"❌ Error: {e}")
            return False

    def process_file(self, input_path: Path) -> None:
        """Process a file by translating to both languages"""
        file_key = str(input_path.relative_to(self.zh_dir))
        file_hash = self.get_file_hash(input_path)

        print(f"\n📄 Processing: zh/{file_key}")

        success = True
        for i, lang in enumerate(["en", "ms"]):
            # Add delay between language translations to avoid rate limiting
            if i > 0:
                time.sleep(5.0)  # 5 seconds between languages
            success = self.translate_file(input_path, lang) and success

        # Update history
        self.history["translated_files"][file_key] = {
            "hash": file_hash,
            "translated_at": datetime.now().isoformat(),
            "languages": ["en", "ms"]
        }

    def process_all_new_files(self) -> None:
        """Process all new or modified Chinese markdown files"""
        new_files = self.get_new_or_modified_files()

        if not new_files:
            print("\n✨ No new or modified Chinese markdown files found.")
            return

        print(f"\n🔄 Found {len(new_files)} file(s) to process")
        print("=" * 70)

        for idx, filepath in enumerate(sorted(new_files), 1):
            # Add delay between files to avoid rate limiting
            if idx > 1:
                time.sleep(10.0)  # 10 seconds between files
            print(f"\n[{idx}/{len(new_files)}]", end=" ")
            self.process_file(filepath)

        print("\n" + "=" * 70)
        self.save_history()
        print(f"\n✅ All files processed!")
        print(f"📁 Translations saved to: en/ and ms/ folders")
        print(f"📋 History saved to: {self.config_file.name}")

    def show_status(self) -> None:
        """Show translation status"""
        print("\n📊 Translation Status")
        print("=" * 70)

        all_chinese = self.find_chinese_markdown_files()
        print(f"Total Chinese markdown files in zh/: {len(all_chinese)}")

        translated = len(self.history.get("translated_files", {}))
        print(f"Translated files: {translated}")
        print(f"Pending: {len(all_chinese) - translated}")

        if self.history.get("last_check"):
            print(f"Last check: {self.history['last_check']}")

        if translated > 0:
            print("\n📝 Translated files:")
            for file_key, info in sorted(self.history.get("translated_files", {}).items()):
                print(f"  ✅ zh/{file_key}")
                print(f"     → en/{file_key}")
                print(f"     → ms/{file_key}")
                print(f"     Time: {info.get('translated_at', 'N/A')}")

    def show_folder_structure(self) -> None:
        """Display current folder structure"""
        print("\n📂 Folder Structure")
        print("=" * 70)

        def print_tree(path, prefix="", is_last=True):
            if not path.exists():
                return

            items = sorted(path.iterdir())
            md_items = [item for item in items if item.suffix == ".md" or item.is_dir()]

            for i, item in enumerate(md_items):
                is_last_item = i == len(md_items) - 1
                current_prefix = "└── " if is_last_item else "├── "
                print(f"{prefix}{current_prefix}{item.name}")

                if item.is_dir():
                    next_prefix = prefix + ("    " if is_last_item else "│   ")
                    print_tree(item, next_prefix, is_last_item)

        print(f"{self.base_dir.name}/")
        print_tree(self.base_dir)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Automated Chinese Markdown Translator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python translator.py --all                 # Translate all new/modified files
  python translator.py --status              # Show translation status
  python translator.py --file zh/01-genesis/file.md  # Translate specific file
  python translator.py --tree                # Show folder structure
        """
    )
    parser.add_argument(
        "-d", "--directory",
        default=".",
        help="Base directory (should contain zh/, en/, ms/ folders)"
    )
    parser.add_argument(
        "-s", "--status",
        action="store_true",
        help="Show translation status"
    )
    parser.add_argument(
        "-f", "--file",
        help="Translate specific file (path in zh/ folder)"
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Translate all new or modified Chinese markdown files"
    )
    parser.add_argument(
        "-t", "--tree",
        action="store_true",
        help="Show folder structure"
    )
    parser.add_argument(
        "--reset-history",
        action="store_true",
        help="Reset translation history"
    )

    args = parser.parse_args()

    try:
        manager = TranslationManager(base_dir=args.directory)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return

    # Reset history if requested
    if args.reset_history:
        manager.history = {"translated_files": {}, "last_check": None}
        manager.save_history()
        print("✅ Translation history reset")
        return

    # Show folder structure
    if args.tree:
        manager.show_folder_structure()
        return

    # Show status
    if args.status:
        manager.show_status()
        return

    # Translate specific file
    if args.file:
        file_path = manager.zh_dir / args.file
        if not file_path.exists():
            print(f"❌ File not found: zh/{args.file}")
            return
        print(f"📝 Translating specific file: zh/{args.file}")
        manager.process_file(file_path)
        manager.save_history()
        return

    # Process all new/modified files
    if args.all:
        manager.process_all_new_files()
    else:
        # Default: show help
        parser.print_help()


if __name__ == "__main__":
    main()
