# Theory of Operation (TOP)

## Project: chat-ffs

### Executive Summary

chat-ffs transforms LLM chat exports into a browsable filesystem by leveraging ffs (file filesystem), a FUSE-based tool that mounts JSON as a directory tree. This document explains how the system works, why key design decisions were made, and how the pieces fit together.

### The Core Insight

Both Claude and ChatGPT export chat history as JSON. JSON is inherently tree-structured. Unix filesystems are also trees. The ffs tool bridges these representations—it takes a JSON document and mounts it as a filesystem where objects become directories and values become files.

chat-ffs is essentially a **translation layer** that:
1. Parses provider-specific export formats
2. Normalizes them to a consistent schema
3. Restructures the data into a filesystem-friendly JSON layout
4. Hands off to ffs for FUSE mounting

### How ffs Works

ffs (https://github.com/mgree/ffs) is a Rust tool that uses FUSE (Filesystem in Userspace) to present JSON as a filesystem:

```json
{"name": "Alice", "age": 30}
```

Becomes:

```
mountpoint/
├── name    (contains: Alice)
└── age     (contains: 30)
```

Arrays become directories with numeric names:

```json
{"items": ["a", "b", "c"]}
```

Becomes:

```
mountpoint/
└── items/
    ├── 0    (contains: a)
    ├── 1    (contains: b)
    └── 2    (contains: c)
```

ffs handles the FUSE protocol, inode management, and file operations. We only need to produce the right JSON.

### Provider Export Formats

#### Claude Exports

Claude's export arrives as a ZIP containing individual JSON files per conversation:

```
export.zip/
└── conversations/
    ├── abc123.json
    ├── def456.json
    └── ...
```

Each file is self-contained:

```json
{
  "uuid": "abc123",
  "name": "Debugging Rust",
  "created_at": "2024-01-15T10:30:00Z",
  "chat_messages": [
    {"sender": "human", "text": "...", "created_at": "..."},
    {"sender": "assistant", "text": "...", "created_at": "..."}
  ]
}
```

**Characteristics:**
- ISO 8601 timestamps (good)
- One file per conversation (easy to stream)
- Flat message array (simple to process)
- sender is "human"/"assistant" (needs normalization)

#### ChatGPT Exports

ChatGPT exports a single `conversations.json` containing all conversations:

```json
[
  {
    "title": "Debugging Rust",
    "create_time": 1705312200.0,
    "mapping": {
      "node-1": {
        "message": {"author": {"role": "user"}, "content": {"parts": ["..."]}},
        "parent": null,
        "children": ["node-2"]
      },
      "node-2": {
        "message": {"author": {"role": "assistant"}, "content": {"parts": ["..."]}},
        "parent": "node-1",
        "children": []
      }
    }
  }
]
```

**Characteristics:**
- Unix timestamps (needs conversion)
- Single monolithic file (memory concerns for large exports)
- Tree structure for branching conversations (needs linearization)
- role is "user"/"assistant"/"system" (already normalized)

### The Linearization Problem

ChatGPT's tree structure supports conversation branching (editing a message creates a new branch). For filesystem representation, we need a linear sequence.

**Strategy:** Follow the "main branch" by always taking the first child at each node.

```
       root
        │
      node-1 (user)
        │
      node-2 (assistant)
       / \
  node-3  node-4 (branches)
    │
  node-5
```

Linearized: node-1 → node-2 → node-3 → node-5

This loses branch information, but branches are rarely used and complicate the filesystem metaphor. We store branch existence in metadata for users who care.

### Filesystem Structure Design

We transform normalized conversations into this layout:

```
mountpoint/
├── _index.json
├── 2024-01-15_debugging-rust/
│   ├── _metadata.json
│   ├── 001_user.md
│   ├── 002_assistant.md
│   └── 003_user.md
└── 2024-01-16_recipe-ideas/
    ├── _metadata.json
    ├── 001_user.md
    └── 002_assistant.md
```

**Design rationale:**

1. **Date prefix on directories:** Enables natural chronological sorting with `ls`. Users often remember "that conversation from last week."

2. **Slugified titles:** Filesystem-safe names derived from conversation titles. Truncated to 60 chars to avoid path length issues.

3. **Numbered message files:** Zero-padded numbers preserve order. The role suffix (user/assistant) provides quick visual scanning.

4. **Markdown extension:** Messages often contain code blocks, links, and formatting. .md signals this and enables syntax highlighting in editors.

5. **Underscore prefix on metadata:** `_metadata.json` and `_index.json` sort first and are visually distinct from content files.

### JSON Structure for ffs

The filesystem layout above requires this JSON:

```json
{
  "_index.json": "{ \"conversations\": [...] }",
  "2024-01-15_debugging-rust": {
    "_metadata.json": "{ \"title\": \"...\", ... }",
    "001_user.md": "How do I fix this lifetime error?",
    "002_assistant.md": "The issue is that...",
    "003_user.md": "That worked, thanks!"
  }
}
```

**Key insight:** In ffs, if a JSON value is a string, it becomes a file with that string as content. If it's an object, it becomes a directory. We exploit this to create our hybrid structure.

### Processing Pipeline

```
┌─────────────┐
│  ZIP File   │
└──────┬──────┘
       │ extract
       ▼
┌─────────────┐
│  Raw JSON   │  (provider-specific format)
└──────┬──────┘
       │ parse (provider module)
       ▼
┌─────────────┐
│ Conversation│  (Python objects)
│   Objects   │
└──────┬──────┘
       │ normalize
       ▼
┌─────────────┐
│ Normalized  │  (unified schema)
│   Schema    │
└──────┬──────┘
       │ generate filesystem
       ▼
┌─────────────┐
│ ffs-ready   │  (JSON with string leaves = files)
│    JSON     │
└──────┬──────┘
       │ write to temp file
       ▼
┌─────────────┐
│  ffs mount  │  (subprocess)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Browsable  │
│ Filesystem  │
└─────────────┘
```

### Memory Management Strategy

Large exports (10k+ conversations) could exhaust memory. We use a two-phase approach:

**Phase 1: Index Building**
- Stream through ZIP entries without full extraction
- Build lightweight index: `{conversation_id: (title, date, message_count)}`
- Store index in memory (~100 bytes per conversation = 1MB for 10k)

**Phase 2: On-Demand Generation**
- Generate full filesystem JSON only when mounting
- For truly massive exports, consider chunked JSON generation

In practice, even heavy users have <5k conversations, and modern systems handle this fine. The streaming approach is future-proofing.

### Temp File Lifecycle

```
mount:
  1. Create temp dir: /tmp/chat-ffs-{uuid}/
  2. Write fs.json to temp dir
  3. Spawn ffs process
  4. Store temp dir path and process handle

unmount:
  1. Send SIGTERM to ffs process
  2. Wait for clean exit
  3. Delete temp dir recursively

crash recovery:
  - On startup, scan /tmp/chat-ffs-*/
  - Check if corresponding ffs process exists
  - Clean up orphaned temp dirs
```

### Why Not Direct FUSE Implementation?

We could implement FUSE directly in Python using `fusepy`. We use ffs instead because:

1. **ffs is battle-tested:** Handles edge cases in FUSE protocol we'd miss.

2. **ffs handles JSON natively:** No need to implement read/write/getattr for JSON structures.

3. **Separation of concerns:** We focus on data transformation; ffs handles filesystem semantics.

4. **Write support for free:** If user wants to edit messages and save back, ffs supports this.

The tradeoff is an external dependency, but ffs is a single static binary and easy to install.

### Platform Considerations

**Linux:**
- FUSE is kernel-native since 2.6.14
- Install fuse3 package for userspace tools
- fusermount for non-root mounting

**macOS:**
- Requires macFUSE (third-party kernel extension)
- Security settings may block installation
- Some users on Apple Silicon report issues
- Alternative: FUSE-T (newer, no kernel extension)

**Windows:**
- No native FUSE support
- WinFsp exists but ffs doesn't support it
- Recommend WSL2 for Windows users

### Future Considerations

1. **Incremental Updates:** Currently we regenerate everything on mount. Could diff against previous mount for faster startup.

2. **Search Index:** Build sqlite index alongside filesystem for faster grep-like operations via custom commands.

3. **Write-back:** Allow editing messages and generating updated export ZIP.

4. **Additional Providers:** Gemini, Copilot, local LLMs—same pipeline, new parser module.

5. **Attachments:** Claude and ChatGPT both support file attachments. Currently stored as references; could fetch and include actual files.
