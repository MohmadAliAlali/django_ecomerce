from django.conf import settings


def resolve_compute_units(path: str, header_value: str | None = None) -> int:
    max_units = int(getattr(settings, 'LB_MAX_COMPUTE_UNITS', 2048))
    default_units = int(getattr(settings, 'LB_DEFAULT_COMPUTE_UNITS', 100))
    ignore_header = bool(getattr(settings, 'LB_IGNORE_CLIENT_COMPUTE_HEADER', True))

    if not ignore_header and header_value:
        try:
            parsed = float(header_value.strip())
            if parsed > 0:
                return min(max(1, round(parsed)), max_units)
        except ValueError:
            pass

    route_map = getattr(settings, 'LB_ROUTE_COMPUTE_UNITS', {})
    best = -1
    best_len = -1
    for prefix, units in route_map.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best_len = len(prefix)
            best = int(units)

    units = best if best >= 0 else default_units
    return min(max(1, units), max_units)
