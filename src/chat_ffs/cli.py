"""Command-line interface for chat-ffs."""

import json
import sys
from pathlib import Path

import click

from . import __version__
from .fs_generator import generate_fs_json
from .mount import (
    check_ffs_available,
    check_fuse_available,
    cleanup_temp_dir,
    create_temp_dir,
    mount as ffs_mount,
    unmount as ffs_unmount,
)
from .providers.claude import ClaudeProvider
from .providers.chatgpt import ChatGPTProvider


def detect_provider(zip_path: Path) -> str | None:
    """Auto-detect the provider from a ZIP export.

    Args:
        zip_path: Path to the ZIP export file.

    Returns:
        Provider name ('claude' or 'chatgpt') or None if not detected.
    """
    claude = ClaudeProvider()
    chatgpt = ChatGPTProvider()

    if claude.detect(zip_path):
        return "claude"
    elif chatgpt.detect(zip_path):
        return "chatgpt"
    return None


def get_provider(provider_name: str):
    """Get a provider instance by name.

    Args:
        provider_name: The provider name ('claude' or 'chatgpt').

    Returns:
        Provider instance.

    Raises:
        ValueError: If provider name is unknown.
    """
    if provider_name == "claude":
        return ClaudeProvider()
    elif provider_name == "chatgpt":
        return ChatGPTProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def validate_zip_file(ctx, param, value):
    """Validate that the ZIP file exists and is readable."""
    path = Path(value)
    if not path.exists():
        raise click.BadParameter(f"File not found: {value}")
    if not path.is_file():
        raise click.BadParameter(f"Not a file: {value}")
    if not path.suffix.lower() == ".zip":
        raise click.BadParameter(f"Not a ZIP file: {value}")
    return path


def validate_mountpoint(ctx, param, value):
    """Validate that the mountpoint is a valid directory."""
    path = Path(value)
    if path.exists() and not path.is_dir():
        raise click.BadParameter(f"Not a directory: {value}")
    if path.exists() and any(path.iterdir()):
        raise click.BadParameter(f"Directory not empty: {value}")
    return path


def validate_outdir(ctx, param, value):
    """Validate the output directory for export command."""
    path = Path(value)
    if path.exists() and not path.is_dir():
        raise click.BadParameter(f"Not a directory: {value}")
    return path


@click.group()
@click.version_option(version=__version__)
def main():
    """Mount LLM chat exports as a FUSE filesystem.

    chat-ffs transforms Claude and ChatGPT exports into browseable directories.
    Use standard Unix tools (ls, cd, cat, grep) to explore your conversations.
    """
    pass


@main.command()
@click.argument("zipfile", callback=validate_zip_file)
@click.argument("mountpoint", callback=validate_mountpoint)
@click.option(
    "--provider",
    type=click.Choice(["auto", "claude", "chatgpt"]),
    default="auto",
    help="Chat provider (default: auto-detect)",
)
@click.option(
    "--readonly/--no-readonly",
    default=True,
    help="Mount as read-only (default: true)",
)
def mount(zipfile: Path, mountpoint: Path, provider: str, readonly: bool):
    """Mount a chat export ZIP as a FUSE filesystem.

    ZIPFILE is the path to the exported ZIP file from Claude or ChatGPT.
    MOUNTPOINT is the directory where the filesystem will be mounted.

    Examples:

        chat-ffs mount export.zip ~/chats

        chat-ffs mount claude-export.zip ~/chats --provider claude

        chat-ffs mount export.zip ~/chats --no-readonly
    """
    # Check dependencies
    if not check_ffs_available():
        click.echo("Error: ffs is not installed or not in PATH.", err=True)
        click.echo("Install from: https://github.com/mgree/ffs", err=True)
        sys.exit(1)

    if not check_fuse_available():
        click.echo("Error: FUSE is not available.", err=True)
        if sys.platform == "darwin":
            click.echo("Install macFUSE: https://osxfuse.github.io/", err=True)
        else:
            click.echo("Install FUSE: sudo apt install fuse (Debian/Ubuntu)", err=True)
        sys.exit(1)

    # Detect or validate provider
    if provider == "auto":
        detected = detect_provider(zipfile)
        if not detected:
            click.echo("Error: Could not detect export provider.", err=True)
            click.echo("Use --provider to specify: claude or chatgpt", err=True)
            sys.exit(1)
        provider = detected
        click.echo(f"Detected provider: {provider}")

    # Create mountpoint if it doesn't exist
    if not mountpoint.exists():
        mountpoint.mkdir(parents=True)

    # Parse the export
    try:
        provider_instance = get_provider(provider)
        click.echo(f"Parsing {zipfile.name}...")
        conversations = provider_instance.parse(zipfile)

        if not conversations:
            click.echo("Warning: No conversations found in export.", err=True)
            sys.exit(1)

        click.echo(f"Found {len(conversations)} conversation(s)")

        # Parse projects if Claude provider
        projects = None
        if provider == "claude":
            projects = provider_instance.parse_projects(zipfile)
            if projects:
                click.echo(f"Found {len(projects)} project(s)")

    except Exception as e:
        click.echo(f"Error parsing export: {e}", err=True)
        sys.exit(1)

    # Generate filesystem JSON
    try:
        fs_json = generate_fs_json(conversations, projects)
        temp_dir = create_temp_dir()
        json_path = temp_dir / "fs.json"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(fs_json, f, ensure_ascii=False)

    except Exception as e:
        click.echo(f"Error generating filesystem: {e}", err=True)
        sys.exit(1)

    # Mount via ffs
    try:
        ffs_mount(json_path, mountpoint, readonly=readonly)
        click.echo(f"Mounted at {mountpoint}")
        click.echo(f"Temp directory: {temp_dir}")
        click.echo("")
        click.echo("Browse with: ls, cd, cat, grep, etc.")
        click.echo(f"Unmount with: chat-ffs unmount {mountpoint}")

    except Exception as e:
        cleanup_temp_dir(temp_dir)
        click.echo(f"Error mounting filesystem: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("mountpoint", type=click.Path(exists=True, file_okay=False, path_type=Path))
def unmount(mountpoint: Path):
    """Unmount a chat-ffs filesystem.

    MOUNTPOINT is the directory where the filesystem is mounted.

    Example:

        chat-ffs unmount ~/chats
    """
    try:
        ffs_unmount(mountpoint)
        click.echo(f"Unmounted {mountpoint}")

    except Exception as e:
        click.echo(f"Error unmounting: {e}", err=True)
        click.echo("Try: fusermount -uz {mountpoint} (Linux) or umount -f {mountpoint} (macOS)", err=True)
        sys.exit(1)


@main.command()
@click.argument("zipfile", callback=validate_zip_file)
@click.option(
    "--provider",
    type=click.Choice(["auto", "claude", "chatgpt"]),
    default="auto",
    help="Chat provider (default: auto-detect)",
)
def info(zipfile: Path, provider: str):
    """Show metadata about a chat export without mounting.

    ZIPFILE is the path to the exported ZIP file from Claude or ChatGPT.

    Displays:
    - Provider (Claude or ChatGPT)
    - Number of conversations
    - Date range of conversations
    - Total message count

    Example:

        chat-ffs info export.zip
    """
    # Detect or validate provider
    if provider == "auto":
        detected = detect_provider(zipfile)
        if not detected:
            click.echo("Error: Could not detect export provider.", err=True)
            click.echo("Use --provider to specify: claude or chatgpt", err=True)
            sys.exit(1)
        provider = detected

    # Parse the export
    try:
        provider_instance = get_provider(provider)
        conversations = provider_instance.parse(zipfile)

        # Parse projects if Claude provider
        projects = []
        if provider == "claude":
            projects = provider_instance.parse_projects(zipfile)

    except Exception as e:
        click.echo(f"Error parsing export: {e}", err=True)
        sys.exit(1)

    # Gather statistics
    conv_count = len(conversations)
    if conv_count == 0 and not projects:
        click.echo(f"Provider: {provider}")
        click.echo("Conversations: 0")
        return

    total_messages = sum(len(c.messages) for c in conversations)

    # Display info
    click.echo(f"File: {zipfile.name}")
    click.echo(f"Provider: {provider}")
    click.echo(f"Conversations: {conv_count}")
    click.echo(f"Total messages: {total_messages}")

    if conv_count > 0:
        dates = [c.created_at for c in conversations]
        earliest = min(dates)
        latest = max(dates)
        click.echo(f"Date range: {earliest.strftime('%Y-%m-%d')} to {latest.strftime('%Y-%m-%d')}")

    if projects:
        total_docs = sum(len(p.docs) for p in projects)
        click.echo(f"Projects: {len(projects)}")
        click.echo(f"Project documents: {total_docs}")


@main.command()
@click.argument("zipfile", callback=validate_zip_file)
@click.argument("outdir", callback=validate_outdir)
@click.option(
    "--provider",
    type=click.Choice(["auto", "claude", "chatgpt"]),
    default="auto",
    help="Chat provider (default: auto-detect)",
)
def export(zipfile: Path, outdir: Path, provider: str):
    """Extract chat export to flat files without FUSE.

    ZIPFILE is the path to the exported ZIP file from Claude or ChatGPT.
    OUTDIR is the directory where files will be extracted.

    Creates the same directory structure as the mounted filesystem:
    - Each conversation becomes a directory named {date}_{title}
    - Messages become files named {NNN}_{role}.md
    - Metadata in _metadata.json per conversation
    - Index in _index.json at root

    Example:

        chat-ffs export export.zip ~/chats-extracted
    """
    # Detect or validate provider
    if provider == "auto":
        detected = detect_provider(zipfile)
        if not detected:
            click.echo("Error: Could not detect export provider.", err=True)
            click.echo("Use --provider to specify: claude or chatgpt", err=True)
            sys.exit(1)
        provider = detected
        click.echo(f"Detected provider: {provider}")

    # Parse the export
    try:
        provider_instance = get_provider(provider)
        click.echo(f"Parsing {zipfile.name}...")
        conversations = provider_instance.parse(zipfile)

        if not conversations:
            click.echo("Warning: No conversations found in export.", err=True)
            sys.exit(1)

        click.echo(f"Found {len(conversations)} conversation(s)")

        # Parse projects if Claude provider
        projects = None
        if provider == "claude":
            projects = provider_instance.parse_projects(zipfile)
            if projects:
                click.echo(f"Found {len(projects)} project(s)")

    except Exception as e:
        click.echo(f"Error parsing export: {e}", err=True)
        sys.exit(1)

    # Generate filesystem structure
    try:
        fs_json = generate_fs_json(conversations, projects)

    except Exception as e:
        click.echo(f"Error generating filesystem structure: {e}", err=True)
        sys.exit(1)

    # Create output directory
    outdir.mkdir(parents=True, exist_ok=True)

    # Write files recursively
    try:
        files_written, dirs_created = _write_fs_recursive(fs_json, outdir)

        click.echo(f"Created {dirs_created} directories")
        click.echo(f"Wrote {files_written} files")
        click.echo(f"Output: {outdir}")

    except Exception as e:
        click.echo(f"Error writing files: {e}", err=True)
        sys.exit(1)


def _write_fs_recursive(fs_dict: dict, base_path: Path) -> tuple[int, int]:
    """Recursively write filesystem structure to disk.

    Args:
        fs_dict: Dictionary representing filesystem structure.
        base_path: Base path to write files to.

    Returns:
        Tuple of (files_written, dirs_created).
    """
    files_written = 0
    dirs_created = 0

    for name, content in fs_dict.items():
        if isinstance(content, str):
            # File
            file_path = base_path / name
            file_path.write_text(content, encoding="utf-8")
            files_written += 1
        elif isinstance(content, dict):
            # Directory
            dir_path = base_path / name
            dir_path.mkdir(exist_ok=True)
            dirs_created += 1

            # Recurse into subdirectory
            sub_files, sub_dirs = _write_fs_recursive(content, dir_path)
            files_written += sub_files
            dirs_created += sub_dirs

    return files_written, dirs_created


if __name__ == "__main__":
    main()
