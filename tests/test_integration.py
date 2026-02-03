"""Integration tests for the full chat-ffs pipeline without FUSE."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLAUDE_SAMPLE = FIXTURES_DIR / "claude_sample.zip"
CHATGPT_SAMPLE = FIXTURES_DIR / "chatgpt_sample.zip"

# Set up environment with PYTHONPATH pointing to src
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"


def run_cli(*args):
    """Run the chat-ffs CLI with given arguments.

    Returns:
        subprocess.CompletedProcess with stdout/stderr captured as text.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)

    return subprocess.run(
        [sys.executable, "-m", "chat_ffs", *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestExportClaude:
    """Test the export command with Claude sample."""

    def test_export_creates_expected_structure(self, tmp_path):
        """Export Claude sample and verify directory structure."""
        result = run_cli("export", str(CLAUDE_SAMPLE), str(tmp_path))

        assert result.returncode == 0, f"Export failed: {result.stderr}"
        assert "Detected provider: claude" in result.stdout
        assert "Found 2 conversation(s)" in result.stdout

        # Verify _index.json exists at root
        index_path = tmp_path / "_index.json"
        assert index_path.exists(), "_index.json not found"

        index_data = json.loads(index_path.read_text())
        assert index_data["conversation_count"] == 2
        assert len(index_data["conversations"]) == 2

    def test_export_conversation_directories(self, tmp_path):
        """Verify conversation directory naming format."""
        run_cli("export", str(CLAUDE_SAMPLE), str(tmp_path))

        # Get conversation directories (exclude _index.json)
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(dirs) == 2

        # Verify naming format: {YYYY-MM-DD}_{slug}
        for d in dirs:
            parts = d.name.split("_", 1)
            assert len(parts) == 2, f"Directory name should be date_slug format: {d.name}"
            # Check date format
            date_part = parts[0]
            assert len(date_part) == 10, f"Date should be YYYY-MM-DD: {date_part}"
            assert date_part.count("-") == 2

    def test_export_message_files(self, tmp_path):
        """Verify message files are created correctly."""
        run_cli("export", str(CLAUDE_SAMPLE), str(tmp_path))

        # Find the Python Data Processing conversation (has 3 messages)
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        python_dir = next((d for d in dirs if "python" in d.name.lower()), None)
        assert python_dir is not None, "Python conversation directory not found"

        # Verify message files exist
        msg_files = sorted([f for f in python_dir.iterdir() if f.name.endswith(".md")])
        assert len(msg_files) == 3

        # Verify naming format: {NNN}_{role}.md
        expected_names = ["001_user.md", "002_assistant.md", "003_user.md"]
        actual_names = [f.name for f in msg_files]
        assert actual_names == expected_names

    def test_export_message_content(self, tmp_path):
        """Verify message file contents match source."""
        run_cli("export", str(CLAUDE_SAMPLE), str(tmp_path))

        # Find the Python conversation
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        python_dir = next((d for d in dirs if "python" in d.name.lower()), None)

        # Read first user message
        msg1 = (python_dir / "001_user.md").read_text()
        assert "CSV file" in msg1
        assert "filter rows" in msg1

        # Read assistant message
        msg2 = (python_dir / "002_assistant.md").read_text()
        assert "pandas" in msg2
        assert "import pandas" in msg2

    def test_export_metadata_json(self, tmp_path):
        """Verify _metadata.json in each conversation directory."""
        run_cli("export", str(CLAUDE_SAMPLE), str(tmp_path))

        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        for d in dirs:
            metadata_path = d / "_metadata.json"
            assert metadata_path.exists(), f"_metadata.json not found in {d.name}"

            metadata = json.loads(metadata_path.read_text())
            assert "id" in metadata
            assert "title" in metadata
            assert "created_at" in metadata
            assert "updated_at" in metadata
            assert "provider" in metadata
            assert "message_count" in metadata
            assert metadata["provider"] == "claude"

    def test_export_unicode_conversation(self, tmp_path):
        """Verify Unicode content is preserved correctly."""
        run_cli("export", str(CLAUDE_SAMPLE), str(tmp_path))

        # Find Unicode test conversation
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        unicode_dir = next((d for d in dirs if "unicode" in d.name.lower()), None)
        assert unicode_dir is not None, "Unicode test conversation not found"

        # Read user message with Unicode
        msg1 = (unicode_dir / "001_user.md").read_text()
        assert "日本語" in msg1
        assert "emoji" in msg1.lower()


class TestExportChatGPT:
    """Test the export command with ChatGPT sample."""

    def test_export_creates_expected_structure(self, tmp_path):
        """Export ChatGPT sample and verify directory structure."""
        result = run_cli("export", str(CHATGPT_SAMPLE), str(tmp_path))

        assert result.returncode == 0, f"Export failed: {result.stderr}"
        # ChatGPT now uses same format as Claude, so Claude provider detects it
        assert "Detected provider: claude" in result.stdout
        assert "Found 2 conversation(s)" in result.stdout

        # Verify _index.json exists at root
        index_path = tmp_path / "_index.json"
        assert index_path.exists(), "_index.json not found"

        index_data = json.loads(index_path.read_text())
        assert index_data["conversation_count"] == 2

    def test_export_linearization(self, tmp_path):
        """Verify ChatGPT messages are exported correctly."""
        run_cli("export", str(CHATGPT_SAMPLE), str(tmp_path))

        # Find the JavaScript Async conversation
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        js_dir = next((d for d in dirs if "javascript" in d.name.lower()), None)
        assert js_dir is not None, "JavaScript conversation not found"

        # Should have 5 messages: assistant, user, assistant, user, assistant
        msg_files = [f for f in js_dir.iterdir() if f.name.endswith(".md")]
        assert len(msg_files) == 5, f"Expected 5 messages, got {len(msg_files)}"

        # Verify roles are correct in order
        expected_roles = ["assistant", "user", "assistant", "user", "assistant"]
        for i, expected_role in enumerate(expected_roles, start=1):
            filename = f"{i:03d}_{expected_role}.md"
            assert (js_dir / filename).exists(), f"Missing {filename}"

    def test_export_branched_conversation_linearization(self, tmp_path):
        """Verify ChatGPT conversation messages are all exported."""
        run_cli("export", str(CHATGPT_SAMPLE), str(tmp_path))

        # Find the Git Branching conversation
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        git_dir = next((d for d in dirs if "git" in d.name.lower()), None)
        assert git_dir is not None, "Git branching conversation not found"

        # This conversation has 7 messages: assistant, user, assistant, user, assistant, user, assistant
        msg_files = sorted([f for f in git_dir.iterdir() if f.name.endswith(".md")])
        assert len(msg_files) == 7, f"Expected 7 messages, got {len(msg_files)}"

        # Verify content includes hotfixes question
        msg4 = (git_dir / "004_user.md").read_text()
        assert "hotfix" in msg4.lower(), "Should have hotfixes question"

    def test_export_message_content_chatgpt(self, tmp_path):
        """Verify ChatGPT message content is extracted correctly."""
        run_cli("export", str(CHATGPT_SAMPLE), str(tmp_path))

        # Find JavaScript conversation
        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        js_dir = next((d for d in dirs if "javascript" in d.name.lower()), None)

        # Verify assistant content has code examples
        msg3 = (js_dir / "003_assistant.md").read_text()
        assert "Callbacks" in msg3 or "callbacks" in msg3.lower()
        assert "Promise" in msg3

    def test_export_metadata_provider_chatgpt(self, tmp_path):
        """Verify metadata identifies provider (Claude now detects ChatGPT format)."""
        run_cli("export", str(CHATGPT_SAMPLE), str(tmp_path))

        dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        for d in dirs:
            metadata = json.loads((d / "_metadata.json").read_text())
            # ChatGPT now uses same format as Claude, so provider is "claude"
            assert metadata["provider"] == "claude"


class TestInfoCommand:
    """Test the info command with both samples."""

    def test_info_claude_provider_detection(self):
        """Verify Claude provider is correctly detected."""
        result = run_cli("info", str(CLAUDE_SAMPLE))

        assert result.returncode == 0
        assert "Provider: claude" in result.stdout

    def test_info_claude_conversation_count(self):
        """Verify correct conversation count for Claude."""
        result = run_cli("info", str(CLAUDE_SAMPLE))

        assert "Conversations: 2" in result.stdout

    def test_info_claude_message_count(self):
        """Verify total message count for Claude."""
        result = run_cli("info", str(CLAUDE_SAMPLE))

        # conv1 has 3 messages, conv2 has 5 messages = 8 total
        assert "Total messages: 8" in result.stdout

    def test_info_chatgpt_provider_detection(self):
        """Verify ChatGPT sample is detected (Claude provider handles both formats)."""
        result = run_cli("info", str(CHATGPT_SAMPLE))

        assert result.returncode == 0
        # ChatGPT now uses same format as Claude, so Claude provider detects it
        assert "Provider: claude" in result.stdout

    def test_info_chatgpt_conversation_count(self):
        """Verify correct conversation count for ChatGPT."""
        result = run_cli("info", str(CHATGPT_SAMPLE))

        assert "Conversations: 2" in result.stdout

    def test_info_chatgpt_message_count(self):
        """Verify total message count for ChatGPT."""
        result = run_cli("info", str(CHATGPT_SAMPLE))

        # conv1 has 5, conv2 has 7 = 12 total
        assert "Total messages: 12" in result.stdout

    def test_info_date_range(self):
        """Verify date range is displayed."""
        result = run_cli("info", str(CLAUDE_SAMPLE))

        assert "Date range:" in result.stdout
        # Claude sample has dates in 2024-01 and 2024-02
        assert "2024-01" in result.stdout
        assert "2024-02" in result.stdout

    def test_info_explicit_provider(self):
        """Verify explicit provider option works."""
        result = run_cli("info", str(CLAUDE_SAMPLE), "--provider", "claude")

        assert result.returncode == 0
        assert "Provider: claude" in result.stdout
