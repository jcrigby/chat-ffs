#!/usr/bin/env bash
#
# init.sh - Initialize git repo and create GitHub project
#
# This script:
# 1. Initializes a git repo with personal identity (not work)
# 2. Creates a GitHub repo using gh CLI
# 3. Pushes initial commit
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="chat-ffs"
GITHUB_USER="jcrigby"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

cd "$SCRIPT_DIR"

# Check for required tools
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is required${NC}"
    exit 1
fi

if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: gh (GitHub CLI) is required${NC}"
    echo "Install: https://cli.github.com/"
    exit 1
fi

# Check gh auth status
if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: gh is not authenticated${NC}"
    echo "Run: gh auth login"
    exit 1
fi

echo -e "${BLUE}Initializing chat-ffs repository...${NC}"

# Initialize git if not already
if [[ ! -d .git ]]; then
    git init
    echo -e "${GREEN}✓ Git initialized${NC}"
else
    echo -e "${BLUE}Git already initialized${NC}"
fi

# Apply local git config (personal identity, not work)
git config --local include.path ../.gitconfig
# Also set directly in case include doesn't work everywhere
git config --local user.name "John Rigby"
git config --local user.email "jcrigby@gmail.com"
echo -e "${GREEN}✓ Git identity set to John Rigby <jcrigby@gmail.com>${NC}"

# Create .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
.venv/

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# mypy
.mypy_cache/

# Task runner
.task_results/
.task_result

# Temp
*.tmp
*.temp
/tmp/

# OS
.DS_Store
Thumbs.db
EOF
echo -e "${GREEN}✓ Created .gitignore${NC}"

# Initial commit
git add -A
git commit -m "Initial commit: project documentation and task runner

- README.md: User-facing overview
- PRD.md: Product requirements
- ERD.md: Engineering requirements
- TOP.md: Theory of operation
- CLAUDE.md: Claude Code instructions
- TASKS.json: Task definitions
- dotasks.sh: Ralph-style task runner
- plan.sh: Planning mode (no coding)
- init.sh: This script"
echo -e "${GREEN}✓ Created initial commit${NC}"

# Check if repo already exists on GitHub
if gh repo view "$GITHUB_USER/$REPO_NAME" &> /dev/null; then
    echo -e "${BLUE}GitHub repo already exists${NC}"
    git remote add origin "git@github.com:$GITHUB_USER/$REPO_NAME.git" 2>/dev/null || true
else
    # Create GitHub repo
    echo -e "${BLUE}Creating GitHub repository...${NC}"
    gh repo create "$REPO_NAME" \
        --public \
        --description "Mount LLM chat exports (Claude, ChatGPT) as a FUSE filesystem using ffs" \
        --source . \
        --push
    echo -e "${GREEN}✓ Created GitHub repo: https://github.com/$GITHUB_USER/$REPO_NAME${NC}"
fi

# Push if we have a remote
if git remote get-url origin &> /dev/null; then
    git push -u origin main 2>/dev/null || git push -u origin master
    echo -e "${GREEN}✓ Pushed to GitHub${NC}"
fi

echo ""
echo -e "${GREEN}Done! Repository initialized at:${NC}"
echo -e "  Local:  $SCRIPT_DIR"
echo -e "  GitHub: https://github.com/$GITHUB_USER/$REPO_NAME"
