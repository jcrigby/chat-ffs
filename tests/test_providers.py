"""Tests for provider parsers."""

import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from chat_ffs.providers.claude import ClaudeProvider
from chat_ffs.providers.chatgpt import ChatGPTProvider
from chat_ffs.providers.base import Conversation, Message


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
CLAUDE_ZIP = FIXTURES_DIR / "claude_sample.zip"
CHATGPT_ZIP = FIXTURES_DIR / "chatgpt_sample.zip"


class TestClaudeProvider:
    """Tests for ClaudeProvider."""

    @pytest.fixture
    def provider(self):
        return ClaudeProvider()

    def test_detect_valid_claude_zip(self, provider):
        """Test that detect() returns True for a valid Claude export."""
        assert provider.detect(CLAUDE_ZIP) is True

    def test_detect_chatgpt_zip_same_format(self, provider):
        """Test that detect() returns True for ChatGPT export (same format as Claude now)."""
        # Both Claude and ChatGPT now export in the same format:
        # conversations.json with uuid, name, chat_messages
        assert provider.detect(CHATGPT_ZIP) is True

    def test_detect_nonexistent_file_returns_false(self, provider, tmp_path):
        """Test that detect() returns False for non-existent files."""
        fake_path = tmp_path / "nonexistent.zip"
        assert provider.detect(fake_path) is False

    def test_detect_invalid_zip_returns_false(self, provider, tmp_path):
        """Test that detect() returns False for invalid ZIP files."""
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")
        assert provider.detect(invalid_zip) is False

    def test_detect_empty_zip_returns_false(self, provider, tmp_path):
        """Test that detect() returns False for empty ZIP files."""
        empty_zip = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w"):
            pass
        assert provider.detect(empty_zip) is False

    def test_parse_returns_conversations(self, provider):
        """Test that parse() returns a list of Conversation objects."""
        conversations = provider.parse(CLAUDE_ZIP)
        assert isinstance(conversations, list)
        assert len(conversations) == 2
        assert all(isinstance(c, Conversation) for c in conversations)

    def test_parse_conversation_fields(self, provider):
        """Test that parsed conversations have correct fields."""
        conversations = provider.parse(CLAUDE_ZIP)

        # Find the Python Data Processing conversation
        conv = next(c for c in conversations if "Python" in c.title)

        assert conv.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert conv.title == "Python Data Processing Help"
        assert conv.provider == "claude"
        assert isinstance(conv.created_at, datetime)
        assert isinstance(conv.updated_at, datetime)
        assert conv.created_at.year == 2024
        assert conv.created_at.month == 1
        assert conv.created_at.day == 15

    def test_parse_messages(self, provider):
        """Test that messages are parsed correctly."""
        conversations = provider.parse(CLAUDE_ZIP)
        conv = next(c for c in conversations if "Python" in c.title)

        assert len(conv.messages) == 3

        # Check first message (user)
        msg1 = conv.messages[0]
        assert msg1.id == "msg-001-user"
        assert msg1.role == "user"
        assert "CSV file" in msg1.content
        assert isinstance(msg1.timestamp, datetime)

        # Check second message (assistant)
        msg2 = conv.messages[1]
        assert msg2.id == "msg-002-assistant"
        assert msg2.role == "assistant"
        assert "pandas" in msg2.content

    def test_parse_unicode_conversation(self, provider):
        """Test parsing conversation with unicode characters."""
        conversations = provider.parse(CLAUDE_ZIP)
        conv = next(c for c in conversations if "Unicode" in c.title)

        assert "こんにちは" in conv.title
        assert len(conv.messages) == 5

        # Check unicode content in messages
        msg1 = conv.messages[0]
        assert "日本語" in msg1.content
        assert "العربية" in msg1.content

    def test_parse_sender_role_mapping(self, provider):
        """Test that sender is correctly mapped to role."""
        conversations = provider.parse(CLAUDE_ZIP)
        conv = conversations[0]

        for msg in conv.messages:
            assert msg.role in ("user", "assistant", "system")

    def test_parse_timestamp_with_z_suffix(self, provider):
        """Test that ISO 8601 timestamps with Z suffix are parsed correctly."""
        conversations = provider.parse(CLAUDE_ZIP)
        conv = conversations[0]
        msg = conv.messages[0]

        # Should be timezone-aware
        assert msg.timestamp.tzinfo is not None

    def test_parse_nonexistent_file_returns_empty(self, provider, tmp_path):
        """Test that parse() returns empty list for non-existent files."""
        fake_path = tmp_path / "nonexistent.zip"
        conversations = provider.parse(fake_path)
        assert conversations == []


class TestChatGPTProvider:
    """Tests for ChatGPTProvider."""

    @pytest.fixture
    def provider(self):
        return ChatGPTProvider()

    def test_detect_valid_chatgpt_zip(self, provider):
        """Test that detect() returns True for a valid ChatGPT export."""
        assert provider.detect(CHATGPT_ZIP) is True

    def test_detect_claude_zip_returns_false(self, provider):
        """Test that detect() returns False for a Claude export."""
        assert provider.detect(CLAUDE_ZIP) is False

    def test_detect_nonexistent_file_returns_false(self, provider, tmp_path):
        """Test that detect() returns False for non-existent files."""
        fake_path = tmp_path / "nonexistent.zip"
        assert provider.detect(fake_path) is False

    def test_detect_invalid_zip_returns_false(self, provider, tmp_path):
        """Test that detect() returns False for invalid ZIP files."""
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")
        assert provider.detect(invalid_zip) is False

    def test_parse_returns_conversations(self, provider):
        """Test that parse() returns a list of Conversation objects."""
        conversations = provider.parse(CHATGPT_ZIP)
        assert isinstance(conversations, list)
        assert len(conversations) == 2
        assert all(isinstance(c, Conversation) for c in conversations)

    def test_parse_conversation_fields(self, provider):
        """Test that parsed conversations have correct fields."""
        conversations = provider.parse(CHATGPT_ZIP)
        conv = next(c for c in conversations if "JavaScript" in c.title)

        assert conv.id == "conv-gpt-001"
        assert conv.title == "JavaScript Async Patterns"
        assert conv.provider == "chatgpt"
        assert isinstance(conv.created_at, datetime)
        assert isinstance(conv.updated_at, datetime)

    def test_parse_unix_timestamps(self, provider):
        """Test that Unix timestamps are correctly converted to datetime."""
        conversations = provider.parse(CHATGPT_ZIP)
        conv = next(c for c in conversations if "JavaScript" in c.title)

        # Unix timestamp 1705320000.0 = 2024-01-15 10:00:00 UTC
        assert conv.created_at.year == 2024
        assert conv.created_at.month == 1
        assert conv.created_at.day == 15
        assert conv.created_at.tzinfo == timezone.utc

    def test_parse_message_order(self, provider):
        """Test that messages are parsed in correct order."""
        conversations = provider.parse(CHATGPT_ZIP)
        conv = next(c for c in conversations if "JavaScript" in c.title)

        # Should have: assistant, user, assistant, user, assistant
        assert len(conv.messages) == 5

        roles = [m.role for m in conv.messages]
        assert roles == ["assistant", "user", "assistant", "user", "assistant"]

    def test_parse_branching_follows_first_child(self, provider):
        """Test that linearization follows first child at branch points."""
        conversations = provider.parse(CHATGPT_ZIP)
        conv = next(c for c in conversations if "Git Branching" in c.title)

        # The second conversation has a branch after node-a-001
        # It should follow first child (node-u-002) not the alternative (node-u-002-alt)
        messages = conv.messages

        # Find the message after the assistant's first response
        # Should be about hotfixes, not GitFlow
        user_messages = [m for m in messages if m.role == "user"]
        # Second user message should be about hotfixes (first child path)
        assert any("hotfixes" in m.content.lower() for m in user_messages)

    def test_parse_message_content_from_parts(self, provider):
        """Test that message content is extracted from parts array."""
        conversations = provider.parse(CHATGPT_ZIP)
        conv = conversations[0]

        for msg in conv.messages:
            assert isinstance(msg.content, str)
            assert len(msg.content) > 0

    def test_parse_filters_empty_messages(self, provider):
        """Test that messages with empty content are filtered out."""
        conversations = provider.parse(CHATGPT_ZIP)
        for conv in conversations:
            for msg in conv.messages:
                assert msg.content.strip() != ""

    def test_parse_nonexistent_file_returns_empty(self, provider, tmp_path):
        """Test that parse() returns empty list for non-existent files."""
        fake_path = tmp_path / "nonexistent.zip"
        conversations = provider.parse(fake_path)
        assert conversations == []

    def test_parse_missing_conversations_json_returns_empty(self, provider, tmp_path):
        """Test that parse() returns empty list if conversations.json is missing."""
        zip_path = tmp_path / "no_conversations.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("other_file.txt", "some content")

        conversations = provider.parse(zip_path)
        assert conversations == []


class TestProviderDetection:
    """Tests for provider auto-detection scenarios."""

    def test_claude_detects_both_formats(self):
        """Test that Claude provider detects both Claude and ChatGPT exports.

        Both providers now export in the same format (uuid, name, chat_messages),
        so the Claude provider handles both. The CLI prioritizes Claude in detection.
        """
        claude = ClaudeProvider()
        chatgpt = ChatGPTProvider()

        # Claude ZIP (conversations/ directory)
        assert claude.detect(CLAUDE_ZIP) is True
        assert chatgpt.detect(CLAUDE_ZIP) is False  # No conversations.json

        # ChatGPT ZIP (conversations.json with same format as Claude)
        assert claude.detect(CHATGPT_ZIP) is True  # Same format now
        assert chatgpt.detect(CHATGPT_ZIP) is True  # Has conversations.json

    def test_provider_name_attribute(self):
        """Test that providers have correct provider_name attribute."""
        claude = ClaudeProvider()
        chatgpt = ChatGPTProvider()

        assert claude.provider_name == "claude"
        assert chatgpt.provider_name == "chatgpt"
