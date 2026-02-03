"""Base classes and data structures for provider parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class Attachment:
    """Represents a file attachment in a message."""

    id: str
    filename: str
    mime_type: str
    size: int | None = None


@dataclass
class Message:
    """Represents a single message in a conversation."""

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class Conversation:
    """Represents a complete conversation with metadata."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    provider: Literal["claude", "chatgpt"]
    messages: list[Message] = field(default_factory=list)


@dataclass
class ProjectDoc:
    """Represents a document attached to a project."""

    id: str
    filename: str
    content: str
    created_at: datetime


@dataclass
class Project:
    """Represents a Claude Project with attached documents."""

    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    docs: list[ProjectDoc] = field(default_factory=list)


class BaseProvider(ABC):
    """Abstract base class for provider-specific parsers."""

    provider_name: str = ""

    @abstractmethod
    def detect(self, zip_path: Path) -> bool:
        """Check if the given ZIP file is from this provider.

        Args:
            zip_path: Path to the ZIP export file.

        Returns:
            True if this provider can parse the file, False otherwise.
        """
        pass

    @abstractmethod
    def parse(self, zip_path: Path) -> list[Conversation]:
        """Parse the ZIP export and return normalized conversations.

        Args:
            zip_path: Path to the ZIP export file.

        Returns:
            List of Conversation objects parsed from the export.
        """
        pass
