"""Store UTC instants and expose the deployment server's local time with offsets."""
import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder

def utc_naive(value: datetime.datetime) -> datetime.datetime:
    return value.replace(tzinfo=value.tzinfo or datetime.UTC).astimezone(datetime.UTC).replace(tzinfo=None)


def local_iso(value: datetime.datetime | str | None) -> str:
    if not value:
        return ''
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=value.tzinfo or datetime.UTC).astimezone().isoformat()


def jsonable_local(value):
    return jsonable_encoder(value, custom_encoder={datetime.datetime: local_iso})


def server_time_zone() -> str:
    """Discover the OS zone so browsers use the same calendar and DST rules."""
    configured = os.environ.get('TZ', '').lstrip(':')
    candidates = [configured]
    if not configured:
        try:
            candidates.append(Path('/etc/timezone').read_text().strip())
        except OSError:
            pass
        localtime = str(Path('/etc/localtime').resolve())
        if '/zoneinfo/' in localtime:
            candidates.append(localtime.split('/zoneinfo/', 1)[1])
    for name in candidates:
        if '/zoneinfo/' in name:
            name = name.split('/zoneinfo/', 1)[1]
        try:
            return ZoneInfo(name).key
        except (ValueError, ZoneInfoNotFoundError):
            continue
    # Some deployments only expose a fixed UTC offset rather than an IANA zone.
    offset = datetime.datetime.now().astimezone().utcoffset() or datetime.timedelta()
    minutes = int(offset.total_seconds() / 60)
    return f'{"+" if minutes >= 0 else "-"}{abs(minutes) // 60:02}:{abs(minutes) % 60:02}'
