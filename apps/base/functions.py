def get_user_display(user):
    """Return a human-readable label for a user instance."""
    if not user:
        return None
    name = getattr(user, "get_full_name", lambda: None)()
    return name if name else getattr(user, "email", str(user))


def extract_nested_fields(field_list):
    """
    Split a list of dotted/dunder field names into a dict.

    Example:
        ["name", "department__name", "department__code"]
        -> {"name": [], "department": ["name", "code"]}
    """
    field_map = {}
    for field in field_list:
        if "__" in field:
            root, rest = field.split("__", 1)
            field_map.setdefault(root, []).append(rest)
        else:
            field_map.setdefault(field, [])
    return field_map
