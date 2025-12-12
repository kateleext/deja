"""
Déjà - Your Claude Code history, chaptered by what was accomplished.
"""

import os

# Configuration
CLAUDE_PROJECTS_PATH = os.environ.get(
    "CLAUDE_PROJECTS_PATH",
    os.path.expanduser("~/.claude/projects")
)

NOTES_PATH = os.environ.get(
    "CLAUDE_MEMORY_NOTES_PATH",
    os.path.expanduser("~/.claude/memory-notes.json")
)

CACHE_PATH = os.environ.get(
    "CLAUDE_MEMORY_CACHE_PATH",
    os.path.expanduser("~/.claude/memory-cache.json")
)
