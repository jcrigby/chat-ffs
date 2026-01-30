# CLAUDE.md

## Getting Started

```bash
# First time setup - creates git repo and GitHub project
./init.sh
```

This initializes the repo with personal git identity (John Rigby, jcrigby@gmail.com) and creates the GitHub repo via `gh`.

## Workflow

This project enforces separation between **planning** and **implementation**:

```bash
# Planning/discussion mode - NO CODING
./plan.sh

# Implementation mode - automated task execution
./dotasks.sh
```

**Do not** slip into human-in-the-loop coding. If you catch yourself about to ask Claude to "just fix this one thing" - stop and add it as a task instead.

## Task Runner

This project uses a task-based development workflow. Tasks are defined in `TASKS.json` and executed via `dotasks.sh`.

```bash
# List all tasks
./dotasks.sh --list

# Show completion status
./dotasks.sh --status

# Run all tasks in order
./dotasks.sh

# Run specific task(s)
./dotasks.sh 03
./dotasks.sh 03 04 05
```

Each task has:
- **work_prompt**: Instructions for the implementation work
- **test_prompt**: Instructions to verify the work succeeded

The test phase must create a `.task_result` file containing "PASS" or "FAIL: reason". The script retries up to 5 times on failure.

## Project Overview

chat-ffs mounts LLM chat exports (Claude, ChatGPT) as a FUSE filesystem using [ffs](https://github.com/mgree/ffs). Users can then browse their conversation history with standard Unix tools.

## Key Documentation

Read these files for context:

- `README.md` - User-facing overview and quick start
- `PRD.md` - Product requirements and scope
- `ERD.md` - Engineering requirements, architecture, and data formats
- `TOP.md` - Theory of operation explaining design decisions

## Architecture Summary

```
ZIP export → Provider Parser → Normalizer → FS Generator → ffs mount
```

The code transforms provider-specific JSON into a ffs-compatible JSON structure where objects become directories and string values become files.

## Code Organization

```
src/chat_ffs/
├── cli.py           # Click-based CLI (mount, unmount, info, export)
├── mount.py         # ffs subprocess management
├── normalizer.py    # Unified conversation schema
├── fs_generator.py  # Generate ffs-compatible JSON
└── providers/
    ├── base.py      # Abstract base class for parsers
    ├── claude.py    # Parse Claude exports
    └── chatgpt.py   # Parse ChatGPT exports
```

## Development Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Format code
black src/ tests/
ruff check src/ tests/

# Run CLI
python -m chat_ffs mount export.zip ~/chats
```

## Provider Export Formats

### Claude
- ZIP contains `conversations/` directory with one JSON file per conversation
- Messages in `chat_messages` array with `sender: "human"|"assistant"`
- ISO 8601 timestamps

### ChatGPT  
- ZIP contains single `conversations.json` with all conversations
- Tree structure in `mapping` field (needs linearization - follow first child)
- Unix timestamps (convert to ISO 8601)
- Roles: `user`, `assistant`, `system`

## Normalized Schema

```python
@dataclass
class Message:
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    attachments: list[Attachment]

@dataclass  
class Conversation:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    provider: Literal["claude", "chatgpt"]
    messages: list[Message]
```

## Filesystem Output Structure

```
mountpoint/
├── _index.json
├── {YYYY-MM-DD}_{slugified-title}/
│   ├── _metadata.json
│   ├── 001_user.md
│   ├── 002_assistant.md
│   └── ...
```

Directory names: date prefix + slugified title (max 60 chars, dedupe with suffix).
Message files: zero-padded number + role + .md extension.

## Implementation Notes

### Provider Detection
Check for `conversations/` directory (Claude) or `conversations.json` file (ChatGPT).

### ChatGPT Tree Linearization
The `mapping` field is a tree supporting conversation branches. Linearize by following `children[0]` at each node. Store branch info in metadata for users who care.

### ffs JSON Format
For ffs, string values become file contents, objects become directories:

```json
{
  "dir_name": {
    "file.txt": "file contents here"
  }
}
```

### Temp Files
- Create temp dir: `/tmp/chat-ffs-{uuid}/`
- Write `fs.json` there
- Clean up on unmount or crash

### Error Handling
- Check ffs and FUSE availability before operations
- Skip corrupt conversations, warn user, continue
- Sanitize all filenames from conversation titles

## Testing

Test fixtures in `tests/fixtures/` with sample exports from both providers.

Key test cases:
- Empty conversations
- Unicode in titles
- Very long messages (>1MB)
- Missing fields in JSON
- Duplicate conversation titles
- Deep conversation threads (100+ messages)

## Dependencies

Runtime:
- Python 3.10+
- click (CLI)
- ffs binary (external)
- FUSE (system)

Dev:
- pytest, pytest-cov
- black, ruff
- mypy

## Common Tasks

### Add a new provider

1. Create `providers/newprovider.py` implementing `BaseProvider`
2. Add detection logic in provider factory
3. Add test fixtures
4. Update README with export instructions

### Modify filesystem structure

1. Update `fs_generator.py`
2. Update ERD.md and TOO.md documentation
3. Ensure backward compatibility or bump major version

### Debug ffs issues

```bash
# Run ffs with debug output
ffs -d ~/chats fs.json

# Check FUSE mounts
mount | grep fuse

# Force unmount
fusermount -uz ~/chats  # Linux
umount -f ~/chats       # macOS
```
