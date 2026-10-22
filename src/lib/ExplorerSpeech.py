"""Short, expiring Explorer warnings. Never supersedes another eligible reply."""
from .Event import PluginEvent, GameEvent, StatusEvent


def departure_warning(events, enabled):
    warnings = []
    for event in events:
        if isinstance(event, PluginEvent):
            data = event.plugin_event_content
            if (event.plugin_event_name == 'TARSExplorerTarget' and isinstance(data, dict)
                    and data.get('callout_kind') == 'unfinished_target'
                    and data.get('warning_trigger') == 'FsdHyperdriveCharging'):
                warnings.append(event)
            else:
                return None
        elif event.kind in ('user', 'user_speaking', 'tool', 'quest', 'projected', 'external'):
            return None
        else:
            data = event.content if isinstance(event, GameEvent) else event.status if isinstance(event, StatusEvent) else {}
            if data.get('event') in enabled and data.get('event') != 'FsdCharging':
                return None
    return warnings[0] if warnings else None


def warning_text(event):
    targets = event.plugin_event_content.get('targets') or []
    if not targets:
        return ''
    target = targets[0]
    body = target.get('body')
    unfinished = target.get('unfinished') or []
    if not isinstance(body, str) or not unfinished:
        return ''
    task = ('biological sampling' if any('biology not fully sampled' in task for task in unfinished)
            else 'DSS mapping')
    return f"Commander, body {body} still has unfinished {task}. We're about to leave it behind."
