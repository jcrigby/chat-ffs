"""Claude export parser."""

import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from .base import Attachment, BaseProvider, Conversation, Memories, Message, Project, ProjectDoc

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseProvider):
    """Parser for Claude conversation exports."""

    provider_name = "claude"

    def detect(self, zip_path: Path) -> bool:
        """Check if the ZIP contains Claude export format.

        Supports two formats:
        - Old: conversations/ directory with individual JSON files
        - New: conversations.json with array of all conversations

        Args:
            zip_path: Path to the ZIP export file.

        Returns:
            True if this is a Claude export, False otherwise.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                # Check for old format: conversations/*.json
                for name in names:
                    if name.startswith("conversations/") and name.endswith(".json"):
                        return True

                # Check for new format: conversations.json at root
                if "conversations.json" in names:
                    # Peek at the file to verify it's Claude format
                    # (has uuid/name/chat_messages, not ChatGPT's mapping structure)
                    with zf.open("conversations.json") as f:
                        # Read just enough to check structure
                        data = json.load(f)
                        if isinstance(data, list) and len(data) > 0:
                            first = data[0]
                            # Claude format has uuid, name, chat_messages (flat array)
                            # ChatGPT format would have mapping (tree structure)
                            if "uuid" in first and "chat_messages" in first and "mapping" not in first:
                                return True

        except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read ZIP file {zip_path}: {e}")
        return False

    def parse(self, zip_path: Path) -> list[Conversation]:
        """Parse Claude export ZIP and return normalized conversations.

        Supports two formats:
        - Old: conversations/ directory with individual JSON files
        - New: conversations.json with array of all conversations

        Args:
            zip_path: Path to the ZIP export file.

        Returns:
            List of Conversation objects parsed from the export.
        """
        conversations: list[Conversation] = []

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                # Check for new format first: conversations.json
                if "conversations.json" in names:
                    conversations = self._parse_conversations_json(zf)
                else:
                    # Old format: conversations/*.json
                    for name in names:
                        if not (name.startswith("conversations/") and name.endswith(".json")):
                            continue

                        try:
                            conversation = self._parse_conversation_file(zf, name)
                            if conversation:
                                conversations.append(conversation)
                        except Exception as e:
                            logger.warning(f"Skipping conversation {name}: {e}")

        except (zipfile.BadZipFile, OSError) as e:
            logger.error(f"Failed to read ZIP file {zip_path}: {e}")

        return conversations

    def _parse_conversations_json(self, zf: zipfile.ZipFile) -> list[Conversation]:
        """Parse the new format conversations.json file.

        Args:
            zf: Open ZipFile object.

        Returns:
            List of Conversation objects.
        """
        conversations: list[Conversation] = []

        with zf.open("conversations.json") as f:
            data = json.load(f)

        if not isinstance(data, list):
            logger.error("conversations.json is not a list")
            return conversations

        for i, conv_data in enumerate(data):
            try:
                conversation = self._parse_conversation_data(conv_data, f"conversation[{i}]")
                if conversation:
                    conversations.append(conversation)
            except Exception as e:
                logger.warning(f"Skipping conversation[{i}]: {e}")

        return conversations

    def _parse_conversation_file(
        self, zf: zipfile.ZipFile, name: str
    ) -> Conversation | None:
        """Parse a single conversation JSON file from the ZIP (old format).

        Args:
            zf: Open ZipFile object.
            name: Name of the file within the ZIP.

        Returns:
            Conversation object or None if parsing fails.
        """
        with zf.open(name) as f:
            data = json.load(f)

        return self._parse_conversation_data(data, name)

    def _parse_conversation_data(
        self, data: dict, source: str
    ) -> Conversation | None:
        """Parse a conversation from its JSON data.

        Args:
            data: Dictionary containing conversation data.
            source: Source identifier for logging (filename or index).

        Returns:
            Conversation object or None if parsing fails.
        """
        # Required fields
        conv_id = data.get("uuid")
        if not conv_id:
            logger.warning(f"Conversation {source} missing uuid, skipping")
            return None

        title = data.get("name", "Untitled")
        created_at = self._parse_timestamp(data.get("created_at"))
        updated_at = self._parse_timestamp(data.get("updated_at"))

        if not created_at:
            logger.warning(f"Conversation {source} missing created_at, skipping")
            return None

        # Use created_at as fallback for updated_at
        if not updated_at:
            updated_at = created_at

        # Parse messages
        messages: list[Message] = []
        chat_messages = data.get("chat_messages", [])

        for msg_data in chat_messages:
            message = self._parse_message(msg_data)
            if message:
                messages.append(message)

        return Conversation(
            id=conv_id,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
            provider="claude",
            messages=messages,
        )

    def _parse_message(self, msg_data: dict) -> Message | None:
        """Parse a single message from the chat_messages array.

        Args:
            msg_data: Dictionary containing message data.

        Returns:
            Message object or None if parsing fails.
        """
        msg_id = msg_data.get("uuid")
        if not msg_id:
            logger.warning("Message missing uuid, skipping")
            return None

        # Map sender to role
        sender = msg_data.get("sender", "")
        role = self._map_sender_to_role(sender)
        if not role:
            logger.warning(f"Message {msg_id} has unknown sender '{sender}', skipping")
            return None

        content = msg_data.get("text", "")
        timestamp = self._parse_timestamp(msg_data.get("created_at"))

        if not timestamp:
            logger.warning(f"Message {msg_id} missing created_at, skipping")
            return None

        # Parse attachments
        attachments: list[Attachment] = []
        for att_data in msg_data.get("attachments", []):
            attachment = self._parse_attachment(att_data)
            if attachment:
                attachments.append(attachment)

        return Message(
            id=msg_id,
            role=role,
            content=content,
            timestamp=timestamp,
            attachments=attachments,
        )

    def _parse_attachment(self, att_data: dict) -> Attachment | None:
        """Parse an attachment from a message.

        Args:
            att_data: Dictionary containing attachment data.

        Returns:
            Attachment object or None if parsing fails.
        """
        att_id = att_data.get("id", att_data.get("uuid", ""))
        filename = att_data.get("file_name", att_data.get("filename", ""))

        if not att_id or not filename:
            return None

        return Attachment(
            id=att_id,
            filename=filename,
            mime_type=att_data.get("mime_type", "application/octet-stream"),
            size=att_data.get("file_size", att_data.get("size")),
        )

    def _map_sender_to_role(self, sender: str) -> str | None:
        """Map Claude sender values to normalized roles.

        Args:
            sender: The sender value from Claude export ("human" or "assistant").

        Returns:
            Normalized role ("user" or "assistant") or None if unknown.
        """
        mapping = {
            "human": "user",
            "assistant": "assistant",
        }
        return mapping.get(sender)

    def _parse_timestamp(self, ts: str | None) -> datetime | None:
        """Parse an ISO 8601 timestamp string.

        Args:
            ts: Timestamp string in ISO 8601 format.

        Returns:
            datetime object or None if parsing fails.
        """
        if not ts:
            return None

        try:
            # Handle various ISO 8601 formats
            # Python 3.11+ has datetime.fromisoformat that handles Z suffix
            # For broader compatibility, replace Z with +00:00
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except ValueError as e:
            logger.warning(f"Failed to parse timestamp '{ts}': {e}")
            return None

    def parse_projects(self, zip_path: Path) -> list[Project]:
        """Parse projects.json from Claude export.

        Args:
            zip_path: Path to the ZIP export file.

        Returns:
            List of Project objects parsed from the export.
        """
        projects: list[Project] = []

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "projects.json" not in zf.namelist():
                    return projects

                with zf.open("projects.json") as f:
                    data = json.load(f)

                if not isinstance(data, list):
                    logger.error("projects.json is not a list")
                    return projects

                for i, proj_data in enumerate(data):
                    try:
                        project = self._parse_project(proj_data, f"project[{i}]")
                        if project:
                            projects.append(project)
                    except Exception as e:
                        logger.warning(f"Skipping project[{i}]: {e}")

        except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read projects from {zip_path}: {e}")

        return projects

    def _parse_project(self, data: dict, source: str) -> Project | None:
        """Parse a single project from its JSON data.

        Args:
            data: Dictionary containing project data.
            source: Source identifier for logging.

        Returns:
            Project object or None if parsing fails.
        """
        proj_id = data.get("uuid")
        if not proj_id:
            logger.warning(f"Project {source} missing uuid, skipping")
            return None

        name = data.get("name", "Untitled Project")
        description = data.get("description", "")
        created_at = self._parse_timestamp(data.get("created_at"))
        updated_at = self._parse_timestamp(data.get("updated_at"))

        if not created_at:
            logger.warning(f"Project {source} missing created_at, skipping")
            return None

        if not updated_at:
            updated_at = created_at

        # Parse docs
        docs: list[ProjectDoc] = []
        for doc_data in data.get("docs", []):
            doc = self._parse_project_doc(doc_data)
            if doc:
                docs.append(doc)

        return Project(
            id=proj_id,
            name=name,
            description=description,
            created_at=created_at,
            updated_at=updated_at,
            docs=docs,
        )

    def _parse_project_doc(self, data: dict) -> ProjectDoc | None:
        """Parse a project document.

        Args:
            data: Dictionary containing document data.

        Returns:
            ProjectDoc object or None if parsing fails.
        """
        doc_id = data.get("uuid", "")
        filename = data.get("filename", "")
        content = data.get("content", "")
        created_at = self._parse_timestamp(data.get("created_at"))

        if not filename:
            return None

        if not created_at:
            from datetime import timezone
            created_at = datetime.now(timezone.utc)

        return ProjectDoc(
            id=doc_id,
            filename=filename,
            content=content,
            created_at=created_at,
        )

    def parse_memories(self, zip_path: Path) -> Memories | None:
        """Parse memories.json from Claude export.

        Args:
            zip_path: Path to the ZIP export file.

        Returns:
            Memories object or None if not found.
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "memories.json" not in zf.namelist():
                    return None

                with zf.open("memories.json") as f:
                    data = json.load(f)

                if not isinstance(data, list) or len(data) == 0:
                    return None

                # memories.json is a list with typically one entry
                memory_data = data[0]

                conversations_memory = memory_data.get("conversations_memory", "")
                project_memories = memory_data.get("project_memories", {})

                return Memories(
                    conversations_memory=conversations_memory,
                    project_memories=project_memories,
                )

        except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read memories from {zip_path}: {e}")
            return None
