"""
Notes storage - breadcrumbs left on sessions for future searches.
"""

import os
import json
from typing import Dict, List

from config import NOTES_PATH


# In-memory cache
_notes_cache: Dict[str, List[str]] = {}
_notes_loaded = False


def load_notes():
    """Load notes from disk"""
    global _notes_cache, _notes_loaded
    if _notes_loaded:
        return
    try:
        if os.path.exists(NOTES_PATH):
            with open(NOTES_PATH, 'r') as f:
                _notes_cache = json.load(f)
    except Exception as e:
        print(f"Error loading notes: {e}", file=__import__('sys').stderr)
        _notes_cache = {}
    _notes_loaded = True


def save_notes():
    """Save notes to disk"""
    try:
        os.makedirs(os.path.dirname(NOTES_PATH), exist_ok=True)
        with open(NOTES_PATH, 'w') as f:
            json.dump(_notes_cache, f, indent=2)
    except Exception as e:
        print(f"Error saving notes: {e}", file=__import__('sys').stderr)


def get_notes_for_session(session_id: str) -> List[str]:
    """Get notes for a specific session"""
    load_notes()
    return _notes_cache.get(session_id, [])


def add_note_to_session(session_id: str, note: str) -> int:
    """Add a note to a session, returns total notes count"""
    load_notes()

    if session_id not in _notes_cache:
        _notes_cache[session_id] = []

    _notes_cache[session_id].append(note)
    save_notes()

    return len(_notes_cache[session_id])
