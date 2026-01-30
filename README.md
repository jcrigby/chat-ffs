# chat-ffs

**Mount your LLM chat exports as a filesystem**

chat-ffs is a tool that prepares and presents exported chat history data from LLM chatbots (Claude, ChatGPT) using [ffs](https://github.com/mgree/ffs), the file filesystem. Instead of parsing JSON or writing scripts, you navigate your conversations with `cd`, `ls`, `cat`, and `grep`.

## Why?

Both Anthropic and OpenAI let you export your chat history as ZIP files containing JSON. But JSON is awkward to explore:

- Deeply nested structures
- Unix timestamps instead of readable dates
- Inconsistent schemas between providers
- No easy way to search across conversations

chat-ffs solves this by:

1. Extracting and normalizing chat exports from multiple providers
2. Transforming them into a consistent, browsable structure
3. Mounting them via FUSE so you can use familiar shell tools

## Quick Example

```bash
# Mount your Claude export
chat-ffs mount claude-export.zip ~/chats

# Now explore with standard tools
cd ~/chats
ls
# 2024-01-15_debugging-rust-lifetimes/
# 2024-01-16_recipe-suggestions/
# 2024-01-17_project-planning/

cat 2024-01-15_debugging-rust-lifetimes/001_user.md
cat 2024-01-15_debugging-rust-lifetimes/002_assistant.md

# Search across all conversations
grep -r "async" ~/chats/

# When done
umount ~/chats
```

## Supported Exports

- **Claude** (claude.ai) - Settings → Privacy → Export data
- **ChatGPT** (chat.openai.com) - Settings → Data controls → Export data

## Requirements

- Python 3.10+
- FUSE (Linux: `libfuse`, macOS: `macFUSE`)
- [ffs](https://github.com/mgree/ffs) - the file filesystem

## License

MIT
