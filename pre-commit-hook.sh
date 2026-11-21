#!/bin/bash
# Pre-commit hook for automated markdown translation
# Install: cp pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Pre-commit: Checking for untranslated Chinese markdown files...${NC}"

# Find the content directory (adjust path if needed)
CONTENT_DIR="the-morning-word/content"
if [ ! -d "$CONTENT_DIR" ]; then
    CONTENT_DIR="content"
fi

if [ ! -d "$CONTENT_DIR" ]; then
    echo -e "${YELLOW}⚠️  Content directory not found, skipping translation check${NC}"
    exit 0
fi

# Find scripts directory
SCRIPTS_DIR="the-morning-word/scripts"
if [ ! -d "$SCRIPTS_DIR" ]; then
    SCRIPTS_DIR="scripts"
fi

if [ ! -d "$SCRIPTS_DIR" ]; then
    echo -e "${RED}❌ Scripts directory not found${NC}"
    exit 1
fi

# Check if translator.py exists in scripts directory
if [ ! -f "$SCRIPTS_DIR/translator.py" ]; then
    echo -e "${RED}❌ translator.py not found in $SCRIPTS_DIR${NC}"
    exit 1
fi

# Get staged Chinese markdown files
STAGED_ZH_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep "^zh/" | grep "\.md$" || true)

if [ -z "$STAGED_ZH_FILES" ]; then
    echo -e "${GREEN}✅ No new Chinese markdown files staged${NC}"
    exit 0
fi

echo -e "${YELLOW}📝 Found staged Chinese markdown files:${NC}"
echo "$STAGED_ZH_FILES" | sed 's/^/  - /'

# Change to content directory for relative paths
cd "$CONTENT_DIR"

# Run translator on all new/modified files
echo -e "${BLUE}🔄 Running translator...${NC}"
python3 "../scripts/translator.py" --all > /tmp/translator_output.log 2>&1 || {
    echo -e "${RED}❌ Translation failed:${NC}"
    cat /tmp/translator_output.log
    exit 1
}

cat /tmp/translator_output.log

# Check if all translations were created
echo -e "${BLUE}✓ Verifying translations...${NC}"

MISSING_TRANSLATIONS=0

for zh_file in $STAGED_ZH_FILES; do
    # Remove 'zh/' prefix to get relative path
    relative_path=${zh_file#zh/}
    en_file="en/$relative_path"
    ms_file="ms/$relative_path"

    if [ ! -f "$en_file" ]; then
        echo -e "${RED}❌ Missing English translation: $en_file${NC}"
        MISSING_TRANSLATIONS=$((MISSING_TRANSLATIONS + 1))
    fi

    if [ ! -f "$ms_file" ]; then
        echo -e "${RED}❌ Missing Malay translation: $ms_file${NC}"
        MISSING_TRANSLATIONS=$((MISSING_TRANSLATIONS + 1))
    fi
done

if [ $MISSING_TRANSLATIONS -gt 0 ]; then
    echo -e "${RED}❌ Commit blocked: $MISSING_TRANSLATIONS missing translation(s)${NC}"
    exit 1
fi

# Stage translated files
echo -e "${BLUE}📦 Staging translated files...${NC}"

for zh_file in $STAGED_ZH_FILES; do
    relative_path=${zh_file#zh/}
    en_file="en/$relative_path"
    ms_file="ms/$relative_path"

    if [ -f "$en_file" ]; then
        git add "$en_file"
        echo -e "  ${GREEN}✓${NC} Staged $en_file"
    fi

    if [ -f "$ms_file" ]; then
        git add "$ms_file"
        echo -e "  ${GREEN}✓${NC} Staged $ms_file"
    fi
done

# Also stage the translation history
if [ -f ".translation_config.json" ]; then
    git add ".translation_config.json"
    echo -e "  ${GREEN}✓${NC} Staged .translation_config.json"
fi

echo -e "${GREEN}✅ All translations verified and staged!${NC}"
exit 0
