"""
Data extraction from Claude Code conversation files.
"""

import os
import sys
import json
from typing import List, Dict, Any, Set

from stemmer import stem_text, stem_text_with_counts


def parse_jsonl_file(file_path: str) -> List[dict]:
    """Parse a JSONL file and return raw entries"""
    entries = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
    return entries


def extract_text_content(content: Any) -> str:
    """Extract text content from various message content formats"""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return " ".join(text_parts)

    return ""


def extract_activity_signals(entries: List[dict]) -> Dict[str, List[str]]:
    """
    Extract activity signals from tool calls:
    - Files touched (Read, Write, Edit)
    - Commands run (Bash)
    - URLs fetched (WebFetch)
    """
    files_touched: Set[str] = set()
    commands_run: Set[str] = set()
    urls_fetched: Set[str] = set()

    for entry in entries:
        if entry.get('type') != 'assistant' or not entry.get('message'):
            continue

        for content_item in entry['message'].get('content', []):
            if not isinstance(content_item, dict) or content_item.get('type') != 'tool_use':
                continue

            tool_name = content_item.get('name', '')
            tool_input = content_item.get('input', {})

            if tool_name in ['Read', 'Write', 'Edit']:
                file_path = tool_input.get('file_path', '')
                if file_path:
                    files_touched.add(os.path.basename(file_path))
                    files_touched.add(file_path)

            if tool_name == 'Bash':
                command = tool_input.get('command', '')
                if command:
                    cmd_short = command.split()[0] if command.split() else ''
                    if cmd_short:
                        commands_run.add(cmd_short)
                    commands_run.add(command[:100])

            if tool_name == 'WebFetch':
                url = tool_input.get('url', '')
                if url:
                    urls_fetched.add(url)

    return {
        'files_touched': list(files_touched),
        'commands_run': list(commands_run),
        'urls_fetched': list(urls_fetched)
    }


def is_local_command_noise(content: str) -> bool:
    """Check if content is system-generated noise to skip entirely."""
    if not content:
        return False
    # System disclaimer about local commands - skip these
    if content.startswith('Caveat: The messages below were generated'):
        return True
    return False


def clean_local_command(content: str) -> str:
    """Transform local command XML into readable format."""
    import re

    # <command-name>/context</command-name> → [/context]
    if '<command-name>' in content:
        match = re.search(r'<command-name>([^<]+)</command-name>', content)
        if match:
            return f"[{match.group(1)}]"

    # <local-command-stdout>...</local-command-stdout> → [command output]
    if '<local-command-stdout>' in content:
        return '[command output]'

    return content


def extract_user_text(entries: List[dict]) -> str:
    """Extract text content from user messages only"""
    text_parts = []

    for entry in entries:
        if entry.get('type') == 'user' and entry.get('message'):
            content = extract_text_content(entry['message'].get('content', ''))
            if content and not is_local_command_noise(content):
                content = clean_local_command(content)
                text_parts.append(content)

    return ' '.join(text_parts)


def extract_full_text(entries: List[dict]) -> str:
    """Extract all text content from a conversation for full-text search"""
    text_parts = []

    for entry in entries:
        if entry.get('type') == 'user' and entry.get('message'):
            content = extract_text_content(entry['message'].get('content', ''))
            if content and not is_local_command_noise(content):
                content = clean_local_command(content)
                text_parts.append(content)

        elif entry.get('type') == 'assistant' and entry.get('message'):
            for item in entry['message'].get('content', []):
                if isinstance(item, dict) and item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))

    return ' '.join(text_parts)


def normalize_task(task: Dict) -> Dict:
    """
    Normalize Task tools (TaskCreate/TaskUpdate) to TodoWrite format.

    TodoWrite format:  { content, status, activeForm, priority }
    Task format:       { subject, description, status, activeForm, owner, metadata }

    Returns unified format with content = subject + truncated description.
    """
    # Already in TodoWrite format
    if 'content' in task:
        return task

    # Convert from Task format
    subject = task.get('subject', '')
    description = task.get('description', '')

    # Combine subject + truncated description for searchability
    if description:
        desc_truncated = description[:100] + '...' if len(description) > 100 else description
        content = f"{subject}: {desc_truncated}"
    else:
        content = subject

    return {
        'content': content,
        'status': task.get('status', 'pending'),
        'activeForm': task.get('activeForm', ''),
        'priority': task.get('priority', ''),
        'id': task.get('id', ''),
        # Preserve original fields for richer data
        'subject': subject,
        'description': description[:200] if description else '',
        'owner': task.get('owner', ''),
    }


def calculate_episodes(todo_snapshots: List[Dict]) -> List[Dict]:
    """
    Calculate episode breaks based on when todos were completed.
    Each completed todo marks the end of a phase of work.
    """
    if not todo_snapshots:
        return []

    episodes = []
    completed_todos = set()
    prev_message_idx = 0

    for snapshot in todo_snapshots:
        for todo in snapshot['todos']:
            todo_content = todo.get('content', '')
            if (todo.get('status') == 'completed' and
                todo_content and
                todo_content not in completed_todos):

                episodes.append({
                    'title': todo_content,
                    'message_range': (prev_message_idx, snapshot['message_index']),
                    'completed_at': snapshot['message_index'],
                    'message_count': snapshot['message_index'] - prev_message_idx
                })

                completed_todos.add(todo_content)
                prev_message_idx = snapshot['message_index']

    return episodes


def extract_conversation_data(jsonl_file: str) -> Dict[str, Any]:
    """
    Parse JSONL file and extract structured data:
    - Todo snapshots and episodes
    - Activity signals (files, commands, URLs)
    - Full text for search (stemmed)
    - Metadata
    """
    entries = parse_jsonl_file(jsonl_file)

    todo_snapshots = []
    message_index = 0
    session_id = None
    timestamp = None
    user_messages = []

    for entry in entries:
        if 'sessionId' in entry and not session_id:
            session_id = entry['sessionId']

        if entry.get('type') == 'user' and entry.get('message'):
            msg_content = extract_text_content(entry['message'].get('content', ''))
            if msg_content:
                user_messages.append(msg_content[:200])
                if not timestamp:
                    timestamp = entry.get('timestamp')

        if entry.get('type') in ['user', 'assistant']:
            message_index += 1

        if entry.get('type') == 'assistant' and entry.get('message'):
            for content_item in entry['message'].get('content', []):
                if not isinstance(content_item, dict) or content_item.get('type') != 'tool_use':
                    continue

                tool_name = content_item.get('name', '')
                tool_input = content_item.get('input', {})

                # Legacy TodoWrite - replaces entire todo list
                if tool_name == 'TodoWrite':
                    todos = tool_input.get('todos', [])
                    todo_snapshots.append({
                        'message_index': message_index,
                        'timestamp': entry.get('timestamp'),
                        'todos': [normalize_task(t) for t in todos]
                    })

                # New TaskCreate - adds a single task
                elif tool_name == 'TaskCreate':
                    task = normalize_task(tool_input)
                    # Assign sequential ID if not present
                    if todo_snapshots:
                        existing = todo_snapshots[-1]['todos'].copy()
                        next_id = str(len(existing) + 1)
                    else:
                        existing = []
                        next_id = '1'
                    if not task.get('id'):
                        task['id'] = next_id
                    existing.append(task)
                    todo_snapshots.append({
                        'message_index': message_index,
                        'timestamp': entry.get('timestamp'),
                        'todos': existing
                    })

                # New TaskUpdate - modifies task status
                elif tool_name == 'TaskUpdate':
                    task_id = tool_input.get('taskId', '')
                    new_status = tool_input.get('status')
                    if todo_snapshots and task_id and new_status:
                        updated = []
                        for t in todo_snapshots[-1]['todos']:
                            t_copy = t.copy()
                            if t_copy.get('id') == task_id:
                                t_copy['status'] = new_status
                            updated.append(t_copy)
                        todo_snapshots.append({
                            'message_index': message_index,
                            'timestamp': entry.get('timestamp'),
                            'todos': updated
                        })

        # Also check for OpenCode todos in user messages (created via interface)
        if entry.get('type') == 'user' and entry.get('todos'):
            todos = entry.get('todos', [])
            if todos:  # Only add if todos array is not empty
                todo_snapshots.append({
                    'message_index': message_index,
                    'timestamp': entry.get('timestamp'),
                    'todos': [normalize_task(t) for t in todos]
                })

    # Calculate final state and episodes
    final_todos = {'completed': [], 'in_progress': [], 'pending': []}
    episodes = []

    if todo_snapshots:
        for todo in todo_snapshots[-1]['todos']:
            status = todo.get('status', 'pending')
            content = todo.get('content', '')
            if content:
                final_todos[status].append(content)

        episodes = calculate_episodes(todo_snapshots)

    # Unified work items: final todos + episode titles (for sessions that cleared todos)
    episode_titles = [ep.get('title', '') for ep in episodes if ep.get('title')]
    work_items = list(set(
        final_todos['completed'] + final_todos['in_progress'] + final_todos['pending'] + episode_titles
    ))

    # Collect task descriptions for search (from new Task format)
    task_descriptions = []
    if todo_snapshots:
        for todo in todo_snapshots[-1]['todos']:
            desc = todo.get('description', '')
            if desc:
                task_descriptions.append(desc)

    # User message arc (first + last)
    user_message_arc = []
    if len(user_messages) > 0:
        user_message_arc.append(user_messages[0])
        if len(user_messages) > 1:
            user_message_arc.append(user_messages[-1])

    # Extract signals and text
    activity = extract_activity_signals(entries)

    # Build one searchable index from everything
    all_searchable_text = ' '.join([
        extract_full_text(entries),  # user + assistant messages
        ' '.join(work_items),
        ' '.join(task_descriptions),  # task descriptions for search
        ' '.join(activity['files_touched']),
        ' '.join(activity['commands_run']),
    ])
    term_counts = stem_text_with_counts(all_searchable_text)

    return {
        'session_id': session_id or 'unknown',
        'project': os.path.basename(os.path.dirname(jsonl_file)),
        'first_message': user_messages[0] if user_messages else 'No message',
        'user_message_arc': user_message_arc,
        'user_message_count': len(user_messages),
        'timestamp': timestamp or '',
        'todo_snapshots': todo_snapshots,
        'final_todos': final_todos,
        'work_items': work_items,  # unified: todos + episode titles
        'episodes': episodes,
        'message_count': message_index,
        'files_touched': activity['files_touched'],
        'commands_run': activity['commands_run'],
        'urls_fetched': activity['urls_fetched'],
        'term_counts': term_counts,
    }
