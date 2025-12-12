"""
Command implementations for Déjà.
Each command returns a tuple: (summary_line, data_dict)
"""

import os
import glob as glob_module

from config import CLAUDE_PROJECTS_PATH
from cache import ensure_cache_fresh, get_cache, parse_timestamp
from extraction import parse_jsonl_file, extract_text_content
from stemmer import stem_query
from notes import load_notes, get_notes_for_session, add_note_to_session


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


def recent(limit=5, skip=0, project=None, after=None, before=None):
    """List recent sessions - JSON format. Use skip for pagination."""
    ensure_cache_fresh()
    load_notes()

    after_dt = parse_timestamp(after) if after else None
    before_dt = parse_timestamp(before) if before else None

    cache = get_cache()

    # Count totals
    total_sessions = len(cache)
    projects = set()
    for data in cache.values():
        proj = data.get('project', '')
        if proj:
            projects.add(_short_project(proj))

    # Filter and sort
    conversations = []
    for session_id, data in cache.items():
        if project and project not in data.get('project', ''):
            continue

        conv_dt = parse_timestamp(data.get('timestamp', ''))
        if after_dt and conv_dt and conv_dt < after_dt:
            continue
        if before_dt and conv_dt and conv_dt > before_dt:
            continue

        completed = data['final_todos'].get('completed', [])
        pending = data['final_todos'].get('pending', [])
        in_progress = data['final_todos'].get('in_progress', [])
        notes = get_notes_for_session(session_id)

        if completed:
            summary = ', '.join(completed[:3])
        else:
            arc = data.get('user_message_arc', [])
            user_turn_count = data.get('user_message_count', 0)
            if len(arc) == 1:
                summary = f"[1 turn] {arc[0]}"
            elif len(arc) == 2:
                summary = f"[{user_turn_count} turns] {arc[0][:60]}... → {arc[1][:60]}"
            else:
                summary = data.get('first_message', 'No content')[:120]

        work_done = data.get('files_touched', [])[:5] + data.get('commands_run', [])[:3]

        conversations.append({
            'sessionId': session_id,
            'project': _short_project(data.get('project', '')),
            'when': _short_timestamp(data.get('timestamp', '')),
            '_ts': data.get('timestamp', ''),
            'summary': summary,
            'completed': completed,
            'inProgress': in_progress,
            'pending': pending,
            'turns': data.get('user_message_count', 0),
            'hasChapters': len(data.get('chapters', [])) > 0,
            'workDone': work_done[:8],
            'hasNotes': len(notes) > 0
        })

    conversations.sort(key=lambda x: x['_ts'] or '', reverse=True)

    for c in conversations:
        del c['_ts']

    sessions = conversations[skip:skip + limit]

    # Build helpful summary line
    if skip > 0:
        summary_line = f"{total_sessions} conversations across {len(projects)} projects. Showing {skip+1}-{skip+len(sessions)}."
    else:
        summary_line = f"{total_sessions} conversations across {len(projects)} projects. Showing {len(sessions)} most recent."

    return summary_line, {'sessions': sessions}


def _recency_boost(timestamp):
    """Boost recent sessions: today +2, this week +1, older +0"""
    if not timestamp:
        return 0
    from datetime import datetime, timezone, timedelta
    try:
        ts = timestamp.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        age = now - dt
        if age < timedelta(hours=24):
            return 2
        elif age < timedelta(days=7):
            return 1
        return 0
    except:
        return 0


def search(query, limit=5, skip=0, project=None, after=None, before=None):
    """
    Search sessions by keyword. Binary scoring per category + recency boost.

    Score: todos +3, notes +3, files +2, commands +1, text +1, today +2, this week +1
    Each category only counts once (binary), then sorted by score desc, recency desc.
    Use skip to paginate (e.g., skip=5 to get results 6-10).
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

        # Work items: +3 (binary) - unified todos + chapter titles
        work_items = data.get('work_items', [])
        if any(any(t in item.lower() for t in query_terms) for item in work_items):
            score += 3
            match_source.append('todos')

        # Notes: +3 (binary)
        notes = get_notes_for_session(session_id)
        if any(any(t in note.lower() for t in query_terms) for note in notes):
            score += 3
            match_source.append('notes')

        # Files: +2 (binary)
        if any(any(t in f.lower() for t in query_terms) for f in data.get('files_touched', [])):
            score += 2
            match_source.append('files')

        # Commands: +1 (binary)
        if any(any(t in cmd.lower() for t in query_terms) for cmd in data.get('commands_run', [])):
            score += 1
            match_source.append('commands')

        # Text: +1 (binary) - searches full index including assistant responses
        term_counts = data.get('term_counts', data.get('user_term_counts', {}))
        if any(stem in term_counts for stem in query_stems):
            score += 1
            match_source.append('text')

        if score == 0:
            continue

        # Recency boost: today +2, this week +1
        score += _recency_boost(data.get('timestamp'))

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

        results.append({
            'sessionId': session_id,
            'score': score,
            'matchSource': match_source,
            'summary': summary,
            'project': _short_project(data.get('project', '')),
            'when': _short_timestamp(data.get('timestamp', '')),
            '_ts': data.get('timestamp', ''),
            'turns': data.get('user_message_count', 0),
        })

    # Sort by score (desc), then recency (desc)
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


def chapters(session_id):
    """Show chapters/overview for a session - JSON format"""
    ensure_cache_fresh()
    load_notes()

    cache = get_cache()

    # Resolve partial ID
    full_id, error_or_matches = resolve_session_id(session_id, cache)
    if not full_id:
        # Check if it's a list of matches
        if isinstance(error_or_matches, list):
            # Return matching sessions as JSON
            sorted_matches = sorted(
                error_or_matches,
                key=lambda sid: cache[sid].get('timestamp', ''),
                reverse=True
            )[:10]
            matches_info = []
            for sid in sorted_matches:
                data = cache[sid]
                completed = data['final_todos'].get('completed', [])
                matches_info.append({
                    'sessionId': sid,
                    'when': _short_timestamp(data.get('timestamp', '')),
                    'project': _short_project(data.get('project', '')),
                    'summary': completed[0][:60] if completed else data.get('first_message', '')[:60]
                })
            return f'{len(error_or_matches)} sessions match "{session_id}". Be more specific or use full ID.', {
                'success': False,
                'matches': matches_info,
                'total': len(error_or_matches)
            }
        else:
            return f"Session not found: {session_id}", {
                'error': error_or_matches,
                'success': False
            }
    session_id = full_id

    data = cache[session_id]
    notes = get_notes_for_session(session_id)
    chapter_list = data.get('chapters', [])
    pending = data['final_todos'].get('pending', [])
    in_progress = data['final_todos'].get('in_progress', [])
    completed = data['final_todos'].get('completed', [])

    # Build summary line
    parts = [f"Session {session_id}"]
    parts.append(f"{data.get('user_message_count', 0)} turns")
    parts.append(_short_project(data.get('project', '')))
    parts.append(_short_timestamp(data.get('timestamp', '')))
    summary_line = " · ".join(parts)

    # Combine files and commands into workDone
    work_done = data.get('files_touched', [])[:10] + data.get('commands_run', [])[:5]

    return summary_line, {
        'success': True,
        'sessionId': session_id,
        'project': _short_project(data.get('project', '')),
        'when': _short_timestamp(data.get('timestamp', '')),
        'chapters': chapter_list,
        'completed': completed,
        'inProgress': in_progress,
        'pending': pending,
        'notes': notes,
        'workDone': work_done[:15],
        'turns': data.get('user_message_count', 0)
    }


def _get_tool_detail(tool_name: str, tool_input: dict) -> str:
    """Extract key detail from tool call for display."""
    if tool_name in ['Read', 'Write', 'Edit']:
        path = tool_input.get('file_path', '')
        return path.split('/')[-1] if path else ''
    elif tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        return cmd[:50] + '...' if len(cmd) > 50 else cmd
    elif tool_name in ['Grep', 'Glob']:
        return tool_input.get('pattern', '')
    elif tool_name == 'WebFetch':
        url = tool_input.get('url', '')
        if '://' in url:
            url = url.split('://')[1]
        return url.split('/')[0]
    elif tool_name == 'Task':
        return tool_input.get('description', '')
    elif tool_name == 'TodoWrite':
        todos = tool_input.get('todos', [])
        return f"{len(todos)} items"
    return ''


def read(session_id, chapter=None, turn=None, message=None, start=None, end=None, expand=0, full=False):
    """
    Read messages from a session.

    By default truncates long assistant messages. Use full=True for untruncated.
    Use message=N to fetch a single message at index N (always full).
    """
    ensure_cache_fresh()
    load_notes()

    cache = get_cache()

    # Resolve partial ID
    full_id, error_or_matches = resolve_session_id(session_id, cache)
    if not full_id:
        # Check if it's a list of matches
        if isinstance(error_or_matches, list):
            # Return matches for display
            matches_info = []
            sorted_matches = sorted(
                error_or_matches,
                key=lambda sid: cache[sid].get('timestamp', ''),
                reverse=True
            )[:10]
            for sid in sorted_matches:
                data = cache[sid]
                completed = data['final_todos'].get('completed', [])
                matches_info.append({
                    'sessionId': sid,
                    'when': _short_timestamp(data.get('timestamp', '')),
                    'project': _short_project(data.get('project', '')),
                    'summary': completed[0][:40] if completed else data.get('first_message', '')[:40]
                })
            return f'{len(error_or_matches)} sessions match "{session_id}"', {
                'success': False,
                'matches': matches_info,
                'total': len(error_or_matches)
            }
        else:
            return f"Session not found: {session_id}", {
                'error': error_or_matches,
                'success': False
            }
    session_id = full_id

    data = cache[session_id]
    file_path = data.get('file_path')

    if not file_path or not os.path.exists(file_path):
        return "Session file not found on disk", {
            'error': 'Session file not found on disk.',
            'success': False
        }

    entries = parse_jsonl_file(file_path)
    all_messages = []
    msg_index = 0
    user_turn_count = 0

    for entry in entries:
        if entry.get('type') in ['user', 'assistant']:
            msg_index += 1

            if entry.get('type') == 'user' and entry.get('message'):
                content = extract_text_content(entry['message'].get('content', ''))
                if content:  # Only count non-empty user messages as turns
                    user_turn_count += 1
                    all_messages.append({
                        'role': 'user',
                        'content': content,
                        'timestamp': entry.get('timestamp', ''),
                        'index': msg_index,
                        'userTurn': user_turn_count
                    })
            elif entry.get('type') == 'assistant' and entry.get('message'):
                parts = []
                for item in entry['message'].get('content', []):
                    if isinstance(item, dict):
                        if item.get('type') == 'text':
                            parts.append(item.get('text', ''))
                        elif item.get('type') == 'tool_use':
                            tool_name = item.get('name', 'unknown')
                            tool_input = item.get('input', {})
                            tool_detail = _get_tool_detail(tool_name, tool_input)
                            if tool_detail:
                                parts.append(f"[{tool_name}: {tool_detail}]")
                            else:
                                parts.append(f"[{tool_name}]")

                content = '\n'.join(parts)
                all_messages.append({
                    'role': 'assistant',
                    'content': content,
                    'timestamp': entry.get('timestamp', ''),
                    'index': msg_index,
                    'userTurn': user_turn_count
                })

    # Single message fetch - always full
    if message is not None:
        msg = next((m for m in all_messages if m['index'] == message), None)
        if not msg:
            return f"Message {message} not found", {
                'error': f'Message {message} not found. Session has {len(all_messages)} messages.',
                'success': False
            }
        return f"Message {message}", {
            'success': True,
            'sessionId': session_id,
            'navigationMode': 'message',
            'message': msg
        }

    # Truncate assistant messages unless full=True
    TRUNCATE_LENGTH = 500
    messages = []
    for m in all_messages:
        if m['role'] == 'assistant' and not full and len(m['content']) > TRUNCATE_LENGTH:
            messages.append({
                **m,
                'content': m['content'][:TRUNCATE_LENGTH] + '...',
                'truncated': True
            })
        else:
            messages.append(m)

    total_messages = len(messages)
    chapter_list = data.get('chapters', [])
    navigation_mode = None
    actual_start = 0
    actual_end = total_messages
    chapter_title = None

    if chapter is not None:
        navigation_mode = 'chapter'
        if chapter < 1 or chapter > len(chapter_list):
            chapter_titles = [f"{i+1}: {c['title']}" for i, c in enumerate(chapter_list)]
            return f"Chapter {chapter} not found", {
                'error': f'Chapter {chapter} not found. Available: {chapter_titles}',
                'success': False
            }
        ch = chapter_list[chapter - 1]
        chapter_title = ch['title']
        actual_start = ch['message_range'][0]
        actual_end = ch['message_range'][1]

    elif turn is not None:
        navigation_mode = 'turn'
        if turn < 1 or turn > user_turn_count:
            return f"Turn {turn} out of range", {
                'error': f'Turn {turn} out of range. Session has {user_turn_count} turns.',
                'success': False
            }
        context_turns = 2
        target_start_turn = max(1, turn - context_turns)
        target_end_turn = min(user_turn_count, turn + context_turns)

        selected = [msg for msg in messages
                   if target_start_turn <= msg.get('userTurn', 0) <= target_end_turn]

        summary_line = f"Turn {turn} of {user_turn_count} (showing context)"
        return summary_line, {
            'success': True,
            'sessionId': session_id,
            'turn': turn,
            'messages': selected
        }

    elif start is not None and end is not None:
        navigation_mode = 'range'
        actual_start = max(0, start)
        actual_end = min(total_messages, end)

    else:
        navigation_mode = 'all'
        actual_end = min(50, total_messages)

    actual_start = max(0, actual_start - expand)
    actual_end = min(total_messages, actual_end + expand)

    selected_messages = messages[actual_start:actual_end]

    # Build summary line
    if chapter is not None:
        summary_line = f"Chapter {chapter}: {chapter_title} · {len(selected_messages)} messages"
    else:
        summary_line = f"Messages {actual_start}-{actual_end} of {total_messages}"

    return summary_line, {
        'success': True,
        'sessionId': session_id,
        'range': (actual_start, actual_end),
        'messages': selected_messages
    }


def note(session_id, note_text):
    """Add a note to a session"""
    total = add_note_to_session(session_id, note_text)

    summary_line = f"Added note to {session_id[:8]} ({total} total notes)"
    return summary_line, {
        'success': True,
        'sessionId': session_id,
        'note': note_text,
        'totalNotes': total
    }


def projects():
    """List available projects"""
    project_dirs = [d for d in glob_module.glob(os.path.join(CLAUDE_PROJECTS_PATH, "*"))
                   if os.path.isdir(d)]
    project_list = [os.path.basename(d) for d in project_dirs]

    summary_line = f"{len(project_list)} projects"
    return summary_line, {'projects': project_list}


def _short_project(project_name):
    """Shorten project name for display"""
    if not project_name:
        return ""
    # -Users-kate-Projects-foo -> foo
    parts = project_name.split('-')
    return parts[-1] if parts else project_name


def _short_timestamp(ts):
    """Format timestamp for display: 'Dec 11' or '2d ago' for recent"""
    if not ts:
        return ""
    from datetime import datetime, timezone
    try:
        ts = ts.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = now - dt

        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                return "now"
            return f"{hours}h ago"
        elif diff.days == 1:
            return "yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            return dt.strftime("%b %d")
    except:
        return ""
