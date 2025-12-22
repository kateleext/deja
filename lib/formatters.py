"""
Shared formatting utilities for Déjà commands.
"""

from datetime import datetime, timezone, timedelta


def omit_empty(d: dict) -> dict:
    """Remove keys with empty values ([], {}, '', None) from dict."""
    return {k: v for k, v in d.items() if v not in ([], {}, '', None, 0) and v is not False or k == 'success'}


def short_project(project_name):
    """Shorten project name for display"""
    if not project_name:
        return ""
    # -Users-kate-Projects-foo -> foo
    parts = project_name.split('-')
    return parts[-1] if parts else project_name


def short_timestamp(ts):
    """Format timestamp for display: 'Dec 11' or '2d ago' for recent.
    Accepts Unix timestamp (float/int) or ISO string."""
    if not ts:
        return ""
    try:
        # Handle Unix timestamp (mtime)
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            # Handle ISO string
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
    except (ValueError, AttributeError, TypeError):
        return ""


def recency_boost(timestamp):
    """Boost recent sessions: today +2, this week +1, older +0"""
    if not timestamp:
        return 0
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
    except (ValueError, AttributeError, TypeError):
        return 0
