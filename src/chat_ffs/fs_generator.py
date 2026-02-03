"""Filesystem generator for ffs-compatible JSON output.

This module transforms normalized Conversation objects into a JSON structure
that ffs can mount as a FUSE filesystem.
"""

import json
import re
import unicodedata
from datetime import datetime

from .providers.base import Conversation, Memories, Project


def slugify(title: str, max_len: int = 50) -> str:
    """Convert a title to a filesystem-safe slug.

    Args:
        title: The original title string.
        max_len: Maximum length of the resulting slug.

    Returns:
        A lowercase, hyphenated slug safe for filesystem use.
    """
    # Normalize unicode characters
    slug = unicodedata.normalize("NFKD", title)
    # Encode to ASCII, ignoring non-ASCII characters
    slug = slug.encode("ascii", "ignore").decode("ascii")
    # Convert to lowercase
    slug = slug.lower()
    # Replace any non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Truncate to max length, avoiding mid-word cuts
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    # Handle empty result
    if not slug:
        slug = "untitled"
    return slug


def generate_dirname(conv: Conversation) -> str:
    """Generate a directory name for a conversation.

    Format: {YYYY-MM-DD}_{slugified-title}

    Args:
        conv: The conversation to generate a dirname for.

    Returns:
        A filesystem-safe directory name.
    """
    date_prefix = conv.created_at.strftime("%Y-%m-%d")
    title_slug = slugify(conv.title)
    return f"{date_prefix}_{title_slug}"


def _generate_metadata(conv: Conversation) -> str:
    """Generate _metadata.json content for a conversation.

    Args:
        conv: The conversation to generate metadata for.

    Returns:
        JSON string containing conversation metadata.
    """
    metadata = {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "provider": conv.provider,
        "message_count": len(conv.messages),
    }
    return json.dumps(metadata, indent=2)


def _generate_index(
    conversations: list[Conversation],
    projects: list[Project] | None = None,
    memories: Memories | None = None,
) -> str:
    """Generate _index.json content listing all conversations, projects, and memories.

    Args:
        conversations: List of all conversations.
        projects: Optional list of all projects.
        memories: Optional memories object.

    Returns:
        JSON string containing the index.
    """
    index = {
        "conversation_count": len(conversations),
        "generated_at": datetime.now().isoformat(),
        "conversations": [
            {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "provider": conv.provider,
                "message_count": len(conv.messages),
            }
            for conv in conversations
        ],
    }

    if projects:
        index["project_count"] = len(projects)
        index["projects"] = [
            {
                "id": proj.id,
                "name": proj.name,
                "created_at": proj.created_at.isoformat(),
                "doc_count": len(proj.docs),
            }
            for proj in projects
        ]

    if memories:
        index["has_memories"] = True
        index["project_memory_count"] = len(memories.project_memories)

    return json.dumps(index, indent=2)


def _generate_project_metadata(proj: Project) -> str:
    """Generate _metadata.json content for a project.

    Args:
        proj: The project to generate metadata for.

    Returns:
        JSON string containing project metadata.
    """
    metadata = {
        "id": proj.id,
        "name": proj.name,
        "description": proj.description,
        "created_at": proj.created_at.isoformat(),
        "updated_at": proj.updated_at.isoformat(),
        "doc_count": len(proj.docs),
        "docs": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "created_at": doc.created_at.isoformat(),
            }
            for doc in proj.docs
        ],
    }
    return json.dumps(metadata, indent=2)


def _generate_projects_index(projects: list[Project]) -> str:
    """Generate _index.json content for the projects directory.

    Args:
        projects: List of all projects.

    Returns:
        JSON string containing the projects index.
    """
    index = {
        "project_count": len(projects),
        "generated_at": datetime.now().isoformat(),
        "projects": [
            {
                "id": proj.id,
                "name": proj.name,
                "description": proj.description,
                "created_at": proj.created_at.isoformat(),
                "doc_count": len(proj.docs),
            }
            for proj in projects
        ],
    }
    return json.dumps(index, indent=2)


def generate_fs_json(
    conversations: list[Conversation],
    projects: list[Project] | None = None,
    memories: Memories | None = None,
) -> dict:
    """Generate ffs-compatible JSON from conversations, projects, and memories.

    Creates a nested dictionary structure where:
    - Each conversation becomes a directory named {YYYY-MM-DD}_{slug}
    - Messages become files named {NNN}_{role}.md
    - Each conversation directory contains _metadata.json
    - Root contains _index.json
    - Projects are in _projects/ directory with their attached docs
    - Memories are in _memories/ directory

    Duplicate directory names are handled with _2, _3 suffixes.

    Args:
        conversations: List of normalized conversations.
        projects: Optional list of projects with attached documents.
        memories: Optional memories object with conversation and project memories.

    Returns:
        A dictionary that ffs can mount as a filesystem.
    """
    fs: dict[str, str | dict] = {}
    dirname_counts: dict[str, int] = {}

    for conv in conversations:
        # Generate base dirname
        base_dirname = generate_dirname(conv)

        # Handle duplicates
        if base_dirname in dirname_counts:
            dirname_counts[base_dirname] += 1
            dirname = f"{base_dirname}_{dirname_counts[base_dirname]}"
        else:
            dirname_counts[base_dirname] = 1
            dirname = base_dirname

        # Create conversation directory
        conv_dir: dict[str, str] = {}

        # Add metadata
        conv_dir["_metadata.json"] = _generate_metadata(conv)

        # Add messages
        for i, msg in enumerate(conv.messages, start=1):
            filename = f"{i:03d}_{msg.role}.md"
            conv_dir[filename] = msg.content

        fs[dirname] = conv_dir

    # Add projects if present
    if projects:
        projects_dir = _generate_projects_fs(projects)
        fs["_projects"] = projects_dir

    # Add memories if present
    if memories:
        memories_dir = _generate_memories_fs(memories, projects)
        fs["_memories"] = memories_dir

    # Add root index
    fs["_index.json"] = _generate_index(conversations, projects, memories)

    return fs


def _generate_projects_fs(projects: list[Project]) -> dict:
    """Generate the _projects directory structure.

    Args:
        projects: List of projects.

    Returns:
        Dictionary representing the _projects directory.
    """
    projects_fs: dict[str, str | dict] = {}
    dirname_counts: dict[str, int] = {}

    for proj in projects:
        # Generate directory name from project name
        base_dirname = slugify(proj.name)

        # Handle duplicates
        if base_dirname in dirname_counts:
            dirname_counts[base_dirname] += 1
            dirname = f"{base_dirname}_{dirname_counts[base_dirname]}"
        else:
            dirname_counts[base_dirname] = 1
            dirname = base_dirname

        # Create project directory
        proj_dir: dict[str, str] = {}

        # Add metadata
        proj_dir["_metadata.json"] = _generate_project_metadata(proj)

        # Add docs
        for doc in proj.docs:
            # Use original filename, sanitize if needed
            filename = doc.filename
            # Ensure unique filenames within project
            if filename in proj_dir:
                base, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
                counter = 2
                while f"{base}_{counter}.{ext}" in proj_dir if ext else f"{base}_{counter}" in proj_dir:
                    counter += 1
                filename = f"{base}_{counter}.{ext}" if ext else f"{base}_{counter}"

            proj_dir[filename] = doc.content

        projects_fs[dirname] = proj_dir

    # Add projects index
    projects_fs["_index.json"] = _generate_projects_index(projects)

    return projects_fs


def _generate_memories_fs(memories: Memories, projects: list[Project] | None = None) -> dict:
    """Generate the _memories directory structure.

    Args:
        memories: Memories object containing conversation and project memories.
        projects: Optional list of projects to map UUIDs to names.

    Returns:
        Dictionary representing the _memories directory.
    """
    memories_fs: dict[str, str | dict] = {}

    # Add main conversations memory
    if memories.conversations_memory:
        memories_fs["conversations.md"] = memories.conversations_memory

    # Add project memories
    if memories.project_memories:
        # Build UUID to name mapping from projects
        project_names: dict[str, str] = {}
        if projects:
            for proj in projects:
                project_names[proj.id] = proj.name

        projects_memories_dir: dict[str, str] = {}
        for proj_id, memory_content in memories.project_memories.items():
            # Try to get project name, fall back to UUID
            proj_name = project_names.get(proj_id, proj_id[:8])
            filename = f"{slugify(proj_name)}.md"

            # Handle duplicates
            if filename in projects_memories_dir:
                base = filename[:-3]  # remove .md
                counter = 2
                while f"{base}_{counter}.md" in projects_memories_dir:
                    counter += 1
                filename = f"{base}_{counter}.md"

            projects_memories_dir[filename] = memory_content

        if projects_memories_dir:
            memories_fs["projects"] = projects_memories_dir

    # Add memories index
    memories_fs["_index.json"] = _generate_memories_index(memories, projects)

    return memories_fs


def _generate_memories_index(memories: Memories, projects: list[Project] | None = None) -> str:
    """Generate _index.json content for the memories directory.

    Args:
        memories: Memories object.
        projects: Optional list of projects to map UUIDs to names.

    Returns:
        JSON string containing the memories index.
    """
    # Build UUID to name mapping
    project_names: dict[str, str] = {}
    if projects:
        for proj in projects:
            project_names[proj.id] = proj.name

    index = {
        "generated_at": datetime.now().isoformat(),
        "has_conversations_memory": bool(memories.conversations_memory),
        "conversations_memory_length": len(memories.conversations_memory),
        "project_memory_count": len(memories.project_memories),
        "project_memories": [
            {
                "project_id": proj_id,
                "project_name": project_names.get(proj_id, "Unknown"),
                "memory_length": len(content),
            }
            for proj_id, content in memories.project_memories.items()
        ],
    }
    return json.dumps(index, indent=2)
