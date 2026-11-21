from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG = ROOT / "zensical.toml"
SITE_ROOT = ROOT / "site"
BASE_PATH = "/the-morning-word"

LOCALES = [
    ("zh", "zh", "The Morning Word (中文)"),
    ("en", "en", "The Morning Word (English)"),
    ("ms", "ms", "The Morning Word (Bahasa Melayu)"),
]


def build_locale(lang: str, html_lang: str, title: str) -> None:
    src_dir = ROOT / "content" / lang
    out_dir = SITE_ROOT / lang

    if not src_dir.exists():
        print(f"[skip] Missing source directory: {src_dir}")
        return

    if out_dir.exists():
        shutil.rmtree(out_dir)

    base_text = BASE_CONFIG.read_text(encoding="utf-8")
    # Keep paths relative to ROOT since the temp config file lives inside ROOT
    lines = []
    for line in base_text.splitlines():
        if line.startswith("docs_dir"):
            lines.append(f'docs_dir = "content/{lang}"')
        elif line.startswith("site_dir"):
            lines.append(f'site_dir = "site/{lang}"')
        elif line.startswith("language"):
            lines.append(f'language = "{html_lang}"')
        elif line.startswith("site_name"):
            lines.append(f'site_name = "{title}"')
        else:
            lines.append(line)

    with tempfile.NamedTemporaryFile(
        "w",
        prefix=".zensical_",
        suffix=".toml",
        dir=ROOT,
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write("\n".join(lines) + "\n")
        tmp_path = Path(tmp.name)

    try:
        print(f"[build] Locale '{lang}' -> {out_dir}")
        subprocess.run(
            ["zensical", "build", "--config-file", tmp_path.name],
            cwd=ROOT,
            check=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def write_root_switcher() -> None:
    SITE_ROOT.mkdir(parents=True, exist_ok=True)
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="0; url={BASE_PATH}/zh/" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>The Morning Word</title>
</head>
<body>
  <p>Redirecting to <a href="{BASE_PATH}/zh/">中文 (ZH)</a>…</p>
  <ul>
    <li><a href="{BASE_PATH}/zh/">中文 (ZH)</a></li>
    <li><a href="{BASE_PATH}/en/">English (EN)</a></li>
    <li><a href="{BASE_PATH}/ms/">Bahasa Melayu (MS)</a></li>
  </ul>
</body>
</html>
"""
    (SITE_ROOT / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    for code, html_code, site_title in LOCALES:
        build_locale(code, html_code, site_title)
    write_root_switcher()
    print("[done] Multi-language build complete.")
