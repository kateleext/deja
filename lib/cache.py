"""
Cache management for conversation data.

The cache persists to disk (~/.claude/memory-cache.json) for fast startup.
On each operation, we check freshness by file mtime and re-parse as needed.
"""

import os
import json
import glob as glob_module
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from config import CLAUDE_PROJECTS_PATH, CACHE_PATH
from extraction import extract_conversation_data


# In-memory cache (loaded from disk on first access)
_conversation_cache: Dict[str, Dict[str, Any]] = {}
_cache_loaded = False


def is_entry_stale(entry: Dict[str, Any]) -> bool:
    """
    Check if a cached entry is stale (missing expected fields).
    Update this function when the index format changes.
    """
    # v2: unified term_counts replaces user_term_counts
    if 'term_counts' not in entry:
        return True
    # v3: chapters renamed to episodes
    if 'episodes' not in entry:
        return True
    return False


def load_cache_from_disk():
    """Load cache from disk if it exists."""
    global _conversation_cache, _cache_loaded

    if _cache_loaded:
        return

    _cache_loaded = True

    if not os.path.exists(CACHE_PATH):
        return

    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            _conversation_cache = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load cache from {CACHE_PATH}: {e}", file=__import__('sys').stderr)
        _conversation_cache = {}


def save_cache_to_disk():
    """Save cache to disk."""
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)

        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_conversation_cache, f)
    except IOError as e:
        print(f"Warning: Could not save cache to {CACHE_PATH}: {e}", file=__import__('sys').stderr)


def get_cache() -> Dict[str, Dict[str, Any]]:
    """Get the conversation cache."""
    return _conversation_cache


def index_files():
    """
    Check file mtimes and staleness, re-parse as needed.
    """
    global _conversation_cache

    all_files = glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*", "*.jsonl"))
    cache_modified = False

    for file_path in all_files:
        try:
            current_mtime = os.path.getmtime(file_path)
            filename = os.path.basename(file_path)
            session_id = filename.replace('.jsonl', '')

            needs_reparse = False

            if session_id not in _conversation_cache:
                needs_reparse = True
            elif _conversation_cache[session_id].get('mtime', 0) < current_mtime:
                needs_reparse = True
            elif is_entry_stale(_conversation_cache[session_id]):
                needs_reparse = True

            if needs_reparse:
                data = extract_conversation_data(file_path)
                data['mtime'] = current_mtime
                data['file_path'] = file_path
                _conversation_cache[session_id] = data
                cache_modified = True

        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=__import__('sys').stderr)
            continue

    if cache_modified:
        save_cache_to_disk()


def ensure_cache_fresh():
    """
    Load cache from disk and index any new/stale files.
    """
    load_cache_from_disk()
    index_files()


def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime, normalized to UTC."""
    if not ts:
        return None
    try:
        ts = ts.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return None
