# Engineering Requirements Document (ERD)

## Project: chat-ffs

### Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ZIP Export    │────▶│   chat-ffs      │────▶│      ffs        │
│ (Claude/ChatGPT)│     │   (Python)      │     │   (FUSE mount)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  Normalized     │
                        │  JSON Structure │
                        └─────────────────┘
```

### Component Design

#### 1. CLI Module (`cli.py`)

**Responsibility:** Command-line interface and argument parsing

**Commands:**
```
chat-ffs mount <zipfile> <mountpoint> [--provider auto|claude|chatgpt] [--readonly]
chat-ffs unmount <mountpoint>
chat-ffs info <zipfile>          # Show export metadata without mounting
chat-ffs export <zipfile> <outdir>  # Extract to flat files without FUSE
```

**Implementation:**
- Use `argparse` or `click` for CLI
- Validate paths and permissions before operations
- Check for ffs and FUSE availability on startup

#### 2. Provider Parsers (`providers/`)

**Responsibility:** Parse provider-specific JSON into normalized format

##### 2.1 Claude Parser (`providers/claude.py`)

Claude export structure:
```
export.zip/
├── README.txt
└── conversations/
    ├── {uuid}.json      # One file per conversation
    └── ...
```

Each conversation JSON:
```json
{
  "uuid": "...",
  "name": "Conversation Title",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:00Z",
  "chat_messages": [
    {
      "uuid": "...",
      "sender": "human",
      "text": "...",
      "created_at": "...",
      "attachments": []
    },
    {
      "uuid": "...",
      "sender": "assistant", 
      "text": "...",
      "created_at": "..."
    }
  ]
}
```

##### 2.2 ChatGPT Parser (`providers/chatgpt.py`)

ChatGPT export structure:
```
export.zip/
├── chat.html
├── conversations.json    # All conversations in one file
├── message_feedback.json
├── model_comparisons.json
├── shared_conversations.json
└── user.json
```

Conversations.json structure (simplified):
```json
[
  {
    "title": "...",
    "create_time": 1705312200.0,  // Unix timestamp
    "update_time": 1705315800.0,
    "mapping": {
      "node-id": {
        "message": {
          "author": {"role": "user"|"assistant"|"system"},
          "content": {"parts": ["..."]},
          "create_time": 1705312200.0
        },
        "parent": "parent-node-id",
        "children": ["child-node-id"]
      }
    }
  }
]
```

**Note:** ChatGPT uses a tree structure for conversation branching. Linearize by following the main branch (first child at each node).

#### 3. Normalizer (`normalizer.py`)

**Responsibility:** Convert parsed data to unified schema

**Normalized Schema:**
```json
{
  "conversations": [
    {
      "id": "uuid-or-generated",
      "title": "Conversation Title",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T11:45:00Z",
      "provider": "claude|chatgpt",
      "messages": [
        {
          "id": "msg-uuid",
          "role": "user|assistant|system",
          "content": "Message text...",
          "timestamp": "2024-01-15T10:30:00Z",
          "attachments": []
        }
      ]
    }
  ],
  "metadata": {
    "export_date": "...",
    "provider": "...",
    "conversation_count": 123,
    "message_count": 4567
  }
}
```

#### 4. Filesystem Generator (`fs_generator.py`)

**Responsibility:** Transform normalized data into ffs-compatible structure

**Output Structure:**
```json
{
  "2024-01-15_debugging-rust-lifetimes": {
    "_metadata.json": "{...}",
    "001_user.md": "How do I fix this lifetime error?...",
    "002_assistant.md": "The issue is...",
    "003_user.md": "That worked! But now..."
  },
  "2024-01-16_recipe-suggestions": {
    "_metadata.json": "{...}",
    "001_user.md": "...",
    "002_assistant.md": "..."
  },
  "_index.json": "{...}"
}
```

**Naming conventions:**
- Directory: `{YYYY-MM-DD}_{slugified-title}` (max 60 chars)
- Messages: `{NNN}_{role}.md` (zero-padded to 3 digits)
- Handle duplicates with suffix: `_2`, `_3`, etc.

#### 5. Mount Manager (`mount.py`)

**Responsibility:** Interface with ffs for mounting/unmounting

**Implementation:**
```python
def mount(json_path: Path, mountpoint: Path, readonly: bool = True) -> subprocess.Popen:
    """
    Spawn ffs process to mount JSON at mountpoint.
    Returns the process handle for lifecycle management.
    """
    args = ["ffs"]
    if readonly:
        args.append("--readonly")
    args.extend(["-m", str(mountpoint), str(json_path)])
    return subprocess.Popen(args)

def unmount(mountpoint: Path) -> None:
    """Unmount via fusermount/umount."""
    if sys.platform == "darwin":
        subprocess.run(["umount", str(mountpoint)], check=True)
    else:
        subprocess.run(["fusermount", "-u", str(mountpoint)], check=True)
```

### Data Flow

```
1. User runs: chat-ffs mount export.zip ~/chats

2. CLI validates inputs
   └── Check zip exists, mountpoint is empty directory

3. Extract ZIP to temp directory
   └── /tmp/chat-ffs-{uuid}/

4. Detect provider
   └── Claude: has conversations/ directory
   └── ChatGPT: has conversations.json file

5. Parse with appropriate provider parser
   └── Returns list of Conversation objects

6. Normalize to unified schema
   └── Timestamps to ISO 8601
   └── Roles to user/assistant/system

7. Generate filesystem JSON
   └── Write to /tmp/chat-ffs-{uuid}/fs.json

8. Mount via ffs
   └── ffs --readonly -m ~/chats /tmp/chat-ffs-{uuid}/fs.json

9. User explores filesystem
   └── ls, cd, cat, grep, etc.

10. User unmounts
    └── chat-ffs unmount ~/chats
    └── Cleanup temp directory
```

### Error Handling Strategy

| Error | Response |
|-------|----------|
| ffs not installed | Exit with install instructions |
| FUSE not available | Exit with platform-specific instructions |
| Corrupt ZIP | Skip bad files, warn user, continue with valid data |
| Unknown provider | Exit with message, suggest --provider flag |
| Mountpoint not empty | Exit with message |
| Permission denied | Exit with message about FUSE permissions |

### Testing Requirements

#### Unit Tests
- Provider parsers with sample JSON fixtures
- Normalizer with edge cases (empty conversations, missing fields)
- Filesystem generator naming/slugification
- Timestamp conversion

#### Integration Tests
- Full pipeline with real (anonymized) exports
- Mount/unmount lifecycle
- Concurrent access to mounted filesystem

#### Test Data
- Create synthetic exports for both providers
- Include edge cases: empty titles, unicode, very long messages
- Store in `tests/fixtures/`

### Performance Considerations

1. **Lazy Loading:** For exports with 10k+ conversations, generate filesystem JSON on-demand rather than loading everything into memory.

2. **Streaming ZIP Extraction:** Don't extract entire ZIP upfront; read entries as needed.

3. **Index Caching:** Cache conversation index for repeated mounts of same export.

### Security Considerations

1. **Temp File Cleanup:** Always clean up temp directories on unmount or crash.

2. **Path Traversal:** Sanitize all filenames derived from conversation titles.

3. **No Credential Storage:** Never cache or store any auth tokens.

### Dependencies

```toml
[project]
requires-python = ">=3.10"

[project.dependencies]
click = ">=8.0"       # CLI framework

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov",
    "black",
    "ruff",
    "mypy",
]
```

### File Structure

```
chat-ffs/
├── README.md
├── PRD.md
├── ERD.md
├── TOP.md
├── CLAUDE.md
├── pyproject.toml
├── src/
│   └── chat_ffs/
│       ├── __init__.py
│       ├── cli.py
│       ├── mount.py
│       ├── normalizer.py
│       ├── fs_generator.py
│       └── providers/
│           ├── __init__.py
│           ├── base.py
│           ├── claude.py
│           └── chatgpt.py
└── tests/
    ├── fixtures/
    │   ├── claude_sample.zip
    │   └── chatgpt_sample.zip
    ├── test_providers.py
    ├── test_normalizer.py
    └── test_integration.py
```
