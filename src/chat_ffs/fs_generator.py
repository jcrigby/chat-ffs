"""Filesystem generator for ffs-compatible JSON output.

This module transforms normalized Conversation objects into a JSON structure
that ffs can mount as a FUSE filesystem.
"""

import json
import re
import unicodedata
from datetime import datetime

from .providers.base import Conversation, Project


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


def _generate_index(conversations: list[Conversation], projects: list[Project] | None = None) -> str:
    """Generate _index.json content listing all conversations and projects.

    Args:
        conversations: List of all conversations.
        projects: Optional list of all projects.

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
) -> dict:
    """Generate ffs-compatible JSON from conversations and projects.

    Creates a nested dictionary structure where:
    - Each conversation becomes a directory named {YYYY-MM-DD}_{slug}
    - Messages become files named {NNN}_{role}.md
    - Each conversation directory contains _metadata.json
    - Root contains _index.json
    - Projects are in _projects/ directory with their attached docs

    Duplicate directory names are handled with _2, _3 suffixes.

    Args:
        conversations: List of normalized conversations.
        projects: Optional list of projects with attached documents.

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

    # Add root index
    fs["_index.json"] = _generate_index(conversations, projects)

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
