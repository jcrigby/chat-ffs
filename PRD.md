# Product Requirements Document (PRD)

## Product: chat-ffs

### Overview

chat-ffs enables users to mount exported LLM chat history as a FUSE filesystem, allowing exploration and manipulation of conversation data using standard Unix tools.

### Problem Statement

Users who export their chat history from Claude or ChatGPT receive ZIP files containing JSON with:

- Complex nested structures that are hard to navigate
- Provider-specific schemas requiring different parsing approaches
- Unix timestamps requiring conversion for human readability
- No built-in search or browsing capability

Power users and developers want to:
- Search across thousands of conversations efficiently
- Extract specific exchanges without writing custom scripts
- Diff conversations or track how topics evolved
- Integrate chat history into existing text-based workflows

### Target Users

1. **Developers** who want to grep their coding conversations
2. **Researchers** analyzing their interaction patterns with LLMs
3. **Power users** who prefer command-line tools over GUIs
4. **Data hoarders** who want their chat history in an accessible format

### Functional Requirements

#### FR-1: ZIP Extraction
- Accept ZIP files from Claude and ChatGPT exports
- Handle nested directory structures within ZIPs
- Gracefully handle malformed or partial exports

#### FR-2: Provider Detection
- Auto-detect export source (Claude vs ChatGPT) from file structure
- Support explicit provider override flag
- Extensible architecture for future providers

#### FR-3: Schema Normalization
- Parse Claude's JSON format (conversations array with chat_messages)
- Parse ChatGPT's JSON format (conversations.json with mapping structure)
- Normalize to unified internal representation

#### FR-4: Filesystem Structure Generation
- Create directory per conversation named: `{date}_{sanitized-title}/`
- Create numbered message files: `001_user.md`, `002_assistant.md`
- Include metadata file per conversation: `_metadata.json`
- Generate index file at root: `_index.json`

#### FR-5: FUSE Mounting via ffs
- Generate ffs-compatible JSON structure
- Mount to user-specified directory
- Support read-only and read-write modes
- Clean unmount with data persistence option

#### FR-6: Content Formatting
- Convert message content to Markdown
- Preserve code blocks with language hints
- Handle attachments/artifacts as separate files or links
- Convert timestamps to ISO 8601 format

### Non-Functional Requirements

#### NFR-1: Performance
- Mount exports with 10,000+ conversations in under 30 seconds
- Lazy loading for large exports (don't parse everything upfront)

#### NFR-2: Compatibility
- Linux (Ubuntu 20.04+, Fedora 38+)
- macOS (12+ with macFUSE)
- Python 3.10+

#### NFR-3: Error Handling
- Clear error messages for missing dependencies (FUSE, ffs)
- Graceful degradation for partially corrupt exports
- Logging with configurable verbosity

### Out of Scope (v1)

- GUI interface
- Real-time sync with chat platforms
- Import/write-back to chat platforms
- Windows support (no native FUSE)
- Encryption of mounted filesystem

### Success Metrics

- Successfully mount and browse exports from both Claude and ChatGPT
- grep performance comparable to grepping equivalent flat files
- User can find a specific conversation in under 10 seconds

### Dependencies

| Dependency | Purpose | Required |
|------------|---------|----------|
| ffs | FUSE filesystem for JSON | Yes |
| libfuse/macFUSE | FUSE kernel support | Yes |
| Python 3.10+ | Runtime | Yes |

### Timeline

| Milestone | Deliverable |
|-----------|-------------|
| M1 | Claude export parsing and mounting |
| M2 | ChatGPT export support |
| M3 | Search optimization and lazy loading |
| M4 | Documentation and packaging |
