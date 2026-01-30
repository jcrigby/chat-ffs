#!/usr/bin/env bash
#
# plan.sh - Start Claude in planning/chat mode (no coding)
#
# This script starts Claude with explicit instructions to NOT write code,
# only discuss and plan. Use this when you want to think through problems
# without accidentally slipping into human-in-the-loop coding mode.
#
# The actual implementation work should be done via ./dotasks.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for claude
if ! command -v claude &> /dev/null; then
    echo "Error: claude CLI is required but not installed"
    exit 1
fi

PLANNING_PROMPT="You are helping plan and discuss the chat-ffs project.

IMPORTANT RULES FOR THIS SESSION:
1. DO NOT write any code
2. DO NOT create any files
3. DO NOT use any tools that modify the filesystem
4. ONLY have a conversation about planning, architecture, and design

This project uses a Ralph-style task runner (./dotasks.sh) for all implementation.
The human should NOT be doing hands-on coding with you in the loop.

If the human asks you to:
- Write code → Remind them to add it as a task in TASKS.json and run ./dotasks.sh
- Create files → Remind them to add it as a task in TASKS.json and run ./dotasks.sh  
- Fix a bug → Remind them to add it as a task in TASKS.json and run ./dotasks.sh
- Implement something → Remind them to add it as a task in TASKS.json and run ./dotasks.sh

What you CAN do:
- Discuss architecture and design decisions
- Review and critique the existing documentation (PRD.md, ERD.md, TOP.md, CLAUDE.md)
- Help refine task definitions for TASKS.json (describe changes, don't edit)
- Answer questions about the approach
- Help think through edge cases and problems
- Suggest improvements to the plan

The project documentation is in:
- README.md - User-facing overview
- PRD.md - Product requirements
- ERD.md - Engineering requirements and data formats
- TOP.md - Theory of operation
- CLAUDE.md - Instructions for Claude Code
- TASKS.json - Task definitions for the task runner

Current conversation is PLANNING ONLY. No coding. If you catch yourself about to write code, STOP and remind the human to use ./dotasks.sh instead.

What would you like to discuss about the chat-ffs project?"

cd "$SCRIPT_DIR"
exec claude "$PLANNING_PROMPT"
