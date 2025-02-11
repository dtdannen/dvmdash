from django import template
from datetime import timedelta

register = template.Library()


@register.filter
def precise_naturaldelta(seconds):
    if not isinstance(seconds, (int, float)):
        return seconds  # Return unchanged if not a number

    if seconds < 0:
        return "N/A"

    delta = timedelta(seconds=seconds)
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds or not parts:  # Always include seconds if it's the only non-zero unit
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return ", ".join(parts)
