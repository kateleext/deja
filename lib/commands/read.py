"""
Read command implementation for Déjà.
Handles message reading and navigation within sessions.
"""

import os

from cache import ensure_cache_fresh, get_cache
from extraction import parse_jsonl_file, extract_text_content, is_local_command_noise, clean_local_command
from notes import load_notes
from formatters import short_project, short_timestamp
from commands.shared import resolve_session_id


# Message display constants
TRUNCATE_LENGTH = 500  # Characters to show in truncated assistant messages
CONTEXT_TURNS = 2  # Number of turns to show before/after target turn
DEFAULT_MESSAGE_LIMIT = 50  # Default number of messages to show when displaying all


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


def read(session_id, episode=None, turn=None, message=None, start=None, end=None, last=None, expand=0, full=False):
    """
    Read messages from a session.

    By default truncates long assistant messages. Use full=True for untruncated.
    Use message=N to fetch a single message at index N (always full).
    Use last=N to show the last N messages instead of first N.
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
                    'when': short_timestamp(data.get('timestamp', '')),
                    'project': short_project(data.get('project', '')),
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
                # Skip system caveats, transform local commands to readable format
                if content and not is_local_command_noise(content):
                    content = clean_local_command(content)
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
    episode_list = data.get('episodes', [])
    navigation_mode = None
    actual_start = 0
    actual_end = total_messages
    episode_title = None

    if episode is not None:
        navigation_mode = 'episode'
        if episode < 1 or episode > len(episode_list):
            if not episode_list:
                # No episodes - suggest turn-based navigation
                return f"No episodes in this session", {
                    'error': f'This session has no episodes. Use @N for turn-based navigation (e.g., deja {session_id[:8]}@1)',
                    'success': False,
                    'hint': 'turn',
                    'turns': user_turn_count
                }
            episode_titles = [f"{i+1}: {e['title']}" for i, e in enumerate(episode_list)]
            return f"Episode {episode} not found", {
                'error': f'Episode {episode} not found. Available: {episode_titles}',
                'success': False
            }
        ep = episode_list[episode - 1]
        episode_title = ep['title']
        actual_start = ep['message_range'][0]
        actual_end = ep['message_range'][1]

    elif turn is not None:
        navigation_mode = 'turn'
        if turn < 1 or turn > user_turn_count:
            return f"Turn {turn} out of range", {
                'error': f'Turn {turn} out of range. Session has {user_turn_count} turns.',
                'success': False
            }
        target_start_turn = max(1, turn - CONTEXT_TURNS)
        target_end_turn = min(user_turn_count, turn + CONTEXT_TURNS)

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

    elif last is not None:
        navigation_mode = 'last'
        actual_start = max(0, total_messages - last)
        actual_end = total_messages

    else:
        navigation_mode = 'all'
        actual_end = min(DEFAULT_MESSAGE_LIMIT, total_messages)

    actual_start = max(0, actual_start - expand)
    actual_end = min(total_messages, actual_end + expand)

    selected_messages = messages[actual_start:actual_end]

    # Build summary line
    if episode is not None:
        summary_line = f"Episode {episode}: {episode_title} · {len(selected_messages)} messages"
    elif last is not None:
        summary_line = f"Last {len(selected_messages)} messages of {total_messages}"
    else:
        summary_line = f"Messages {actual_start}-{actual_end} of {total_messages}"

    return summary_line, {
        'success': True,
        'sessionId': session_id,
        'range': (actual_start, actual_end),
        'messages': selected_messages
    }
