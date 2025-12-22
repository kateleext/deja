"""
Listing commands for Déjà: recent sessions and episode overview.
"""

from cache import ensure_cache_fresh, get_cache, parse_timestamp
from notes import load_notes, get_notes_for_session
from formatters import omit_empty, short_project, short_timestamp
from commands.shared import resolve_session_id


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
            projects.add(short_project(proj))

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

        session_data = {
            'sessionId': session_id,
            'project': short_project(data.get('project', '')),
            'when': short_timestamp(data.get('mtime', 0)),
            '_ts': data.get('mtime', 0),
            'summary': summary,
            'turns': data.get('user_message_count', 0),
        }
        # Only include if non-empty
        if completed:
            session_data['completed'] = completed
        if in_progress:
            session_data['inProgress'] = in_progress
        if pending:
            session_data['pending'] = pending
        if len(data.get('episodes', [])) > 0:
            session_data['hasEpisodes'] = True
        if work_done:
            session_data['workDone'] = work_done[:8]
        if notes:
            session_data['hasNotes'] = True
        conversations.append(session_data)

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


def episodes(session_id):
    """Show episodes/overview for a session - JSON format"""
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
                    'when': short_timestamp(data.get('timestamp', '')),
                    'project': short_project(data.get('project', '')),
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
    episode_list = data.get('episodes', [])
    pending = data['final_todos'].get('pending', [])
    in_progress = data['final_todos'].get('in_progress', [])
    completed = data['final_todos'].get('completed', [])

    # Build summary line
    parts = [f"Session {session_id}"]
    parts.append(f"{data.get('user_message_count', 0)} turns")
    parts.append(short_project(data.get('project', '')))
    parts.append(short_timestamp(data.get('timestamp', '')))
    summary_line = " · ".join(parts)

    # Combine files and commands into workDone
    work_done = data.get('files_touched', [])[:10] + data.get('commands_run', [])[:5]

    return summary_line, omit_empty({
        'success': True,
        'sessionId': session_id,
        'project': short_project(data.get('project', '')),
        'when': short_timestamp(data.get('mtime', 0)),
        'episodes': episode_list,
        'completed': completed,
        'inProgress': in_progress,
        'pending': pending,
        'notes': notes,
        'workDone': work_done[:15],
        'turns': data.get('user_message_count', 0)
    })
