"""
Shared utilities for command implementations.
"""


def resolve_session_id(partial_id: str, cache: dict) -> tuple:
    """
    Resolve a partial session ID to a full ID.

    Returns: (full_id, error_or_matches)
    - If exact match: (full_id, None)
    - If unique prefix match: (full_id, None)
    - If multiple matches: (None, list of matching session_ids)
    - If no match: (None, error string)
    """
    # Exact match
    if partial_id in cache:
        return partial_id, None

    # Prefix match
    matches = [sid for sid in cache.keys() if sid.startswith(partial_id)]

    if len(matches) == 1:
        return matches[0], None
    elif len(matches) > 1:
        # Return list of matches for caller to display
        return None, matches
    else:
        return None, f'Session "{partial_id}" not found.'
