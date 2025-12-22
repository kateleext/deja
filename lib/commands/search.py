"""
Search command implementation for Déjà.
"""

import os

from cache import ensure_cache_fresh, get_cache, parse_timestamp
from extraction import parse_jsonl_file, extract_text_content
from stemmer import stem_query
from notes import load_notes, get_notes_for_session
from formatters import short_project, short_timestamp, recency_boost


# Search scoring weights
SCORE_WORK_ITEMS = 3  # Todos and episode titles
SCORE_NOTES = 3
SCORE_FILES = 2
SCORE_COMMANDS = 1
SCORE_TEXT = 1
SCORE_MULTI_TERM_BONUS = 2  # Per additional term matched


def _find_first_matching_turn(file_path: str, matched_terms: set) -> str:
    """Find the first user turn containing any matched term. Returns @N format."""
    try:
        entries = parse_jsonl_file(file_path)
        user_turn = 0
        for entry in entries:
            if entry.get('type') == 'user' and entry.get('message'):
                content = extract_text_content(entry['message'].get('content', ''))
                if content:
                    user_turn += 1
                    content_lower = content.lower()
                    for term in matched_terms:
                        if term in content_lower:
                            # Truncate content for display
                            snippet = content[:50] + '...' if len(content) > 50 else content
                            return f"@{user_turn} {snippet}"
            elif entry.get('type') == 'assistant' and entry.get('message'):
                # Also check assistant messages
                parts = []
                for item in entry['message'].get('content', []):
                    if isinstance(item, dict) and item.get('type') == 'text':
                        parts.append(item.get('text', ''))
                content = ' '.join(parts)
                if content:
                    content_lower = content.lower()
                    for term in matched_terms:
                        if term in content_lower:
                            snippet = content[:50] + '...' if len(content) > 50 else content
                            return f"@{user_turn} {snippet}"
        return None
    except (ValueError, AttributeError, TypeError):
        return None


def search(query, limit=5, skip=0, project=None, after=None, before=None, recent=False):
    """
    Search sessions by keyword. Binary scoring per category + multi-term bonus + recency.

    Scoring uses constants defined at module level.
    Recency: today +2, this week +1
    Use skip to paginate (e.g., skip=5 to get results 6-10).
    Use recent=True to sort by recency instead of relevance score.
    """
    ensure_cache_fresh()
    load_notes()

    after_dt = parse_timestamp(after) if after else None
    before_dt = parse_timestamp(before) if before else None

    query_terms = query.lower().split()
    query_stems = stem_query(query)
    results = []
    cache = get_cache()

    for session_id, data in cache.items():
        if project and project not in data.get('project', ''):
            continue

        conv_dt = parse_timestamp(data.get('timestamp', ''))
        if after_dt and conv_dt and conv_dt < after_dt:
            continue
        if before_dt and conv_dt and conv_dt > before_dt:
            continue

        score = 0
        match_source = []
        matched_terms = set()  # Track which query terms were found across all categories

        # Work items (binary) - unified todos + episode titles
        work_items = data.get('work_items', [])
        work_items_lower = ' '.join(work_items).lower()
        work_matched = False
        for t in query_terms:
            if t in work_items_lower:
                matched_terms.add(t)
                work_matched = True
        if work_matched:
            score += SCORE_WORK_ITEMS
            match_source.append('todos')

        # Notes (binary)
        notes = get_notes_for_session(session_id)
        notes_lower = ' '.join(notes).lower()
        notes_matched = False
        for t in query_terms:
            if t in notes_lower:
                matched_terms.add(t)
                notes_matched = True
        if notes_matched:
            score += SCORE_NOTES
            match_source.append('notes')

        # Files (binary)
        files_lower = ' '.join(data.get('files_touched', [])).lower()
        files_matched = False
        for t in query_terms:
            if t in files_lower:
                matched_terms.add(t)
                files_matched = True
        if files_matched:
            score += SCORE_FILES
            match_source.append('files')

        # Commands (binary)
        commands_lower = ' '.join(data.get('commands_run', [])).lower()
        commands_matched = False
        for t in query_terms:
            if t in commands_lower:
                matched_terms.add(t)
                commands_matched = True
        if commands_matched:
            score += SCORE_COMMANDS
            match_source.append('commands')

        # Text (binary) - searches full index including assistant responses
        term_counts = data.get('term_counts', data.get('user_term_counts', {}))
        text_matched = False
        for stem in query_stems:
            if stem in term_counts:
                text_matched = True
                # Find which original term this stem came from
                for t in query_terms:
                    if stem in stem_query(t):
                        matched_terms.add(t)
        if text_matched:
            score += SCORE_TEXT
            match_source.append('text')

        if score == 0:
            continue

        # Multi-term bonus: rewards sessions matching multiple query terms
        if len(matched_terms) > 1:
            score += (len(matched_terms) - 1) * SCORE_MULTI_TERM_BONUS

        # Recency boost: today +2, this week +1
        score += recency_boost(data.get('timestamp'))

        completed = data['final_todos'].get('completed', [])
        if completed:
            summary = ', '.join(completed[:3])
        else:
            arc = data.get('user_message_arc', [])
            turns = data.get('user_message_count', 0)
            if len(arc) == 2:
                summary = f"[{turns}t] {arc[0][:60]}... → {arc[1][:60]}"
            elif len(arc) == 1:
                summary = f"[{turns}t] {arc[0][:100]}"
            else:
                summary = data.get('first_message', '')[:100]

        # Find first match location: episode (:N) or turn (@X)
        first_match = None
        episodes = data.get('episodes', [])

        # First check episode titles
        for i, ep in enumerate(episodes):
            title_lower = ep.get('title', '').lower()
            for term in matched_terms:
                if term in title_lower:
                    first_match = f":{i+1} {ep['title']}"
                    break
            if first_match:
                break

        # If no episode match, find first turn with match
        if not first_match and text_matched:
            file_path = data.get('file_path')
            if file_path and os.path.exists(file_path):
                first_match = _find_first_matching_turn(file_path, matched_terms)

        result = {
            'sessionId': session_id,
            'score': score,
            'matchSource': match_source,
            'summary': summary,
            'project': short_project(data.get('project', '')),
            'when': short_timestamp(data.get('mtime', 0)),
            '_ts': data.get('mtime', 0),
            'turns': data.get('user_message_count', 0),
        }
        if first_match:
            result['firstMatch'] = first_match
        results.append(result)

    # Sort by recency only (--recent) or by score then recency
    if recent:
        results.sort(key=lambda x: x['_ts'] or '', reverse=True)
    else:
        results.sort(key=lambda x: (x['score'], x['_ts'] or ''), reverse=True)

    for r in results:
        del r['_ts']

    total = len(results)
    shown = results[skip:skip + limit]

    if skip > 0:
        summary_line = f'Found {total} sessions matching "{query}". Showing {skip+1}-{skip+len(shown)}.'
    else:
        summary_line = f'Found {total} sessions matching "{query}". Showing top {len(shown)}.'

    return summary_line, {
        'results': shown,
        'totalMatches': total,
        'query': query
    }
