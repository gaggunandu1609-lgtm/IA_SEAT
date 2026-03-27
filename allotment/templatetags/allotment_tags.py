from django import template

register = template.Library()

@register.filter
def get_at_index(list_obj, index):
    try:
        return list_obj[int(index)]
    except (IndexError, TypeError, ValueError):
        return None

@register.filter
def get_room_for_session(session_rooms, session_key):
    """
    session_rooms: dict with (date, session_label) tuples as keys
    session_key: a string "date__session" passed from template
    Returns the room number or empty string.
    """
    try:
        if not session_rooms or not session_key:
            return ""
        # session_key format: "2026-02-16__Morning"
        date_str, session_label = session_key.split("__", 1)
        import datetime
        d = datetime.date.fromisoformat(date_str)
        return session_rooms.get((d, session_label), "")
    except Exception:
        return ""
