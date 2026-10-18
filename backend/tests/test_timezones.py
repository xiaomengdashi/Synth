import datetime
import os
import time
from contextlib import contextmanager

import pytest

from app.timezones import local_iso, jsonable_local, utc_naive


@contextmanager
def server_timezone(name):
    previous = os.environ.get('TZ')
    os.environ['TZ'] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        time.tzset()


@pytest.mark.parametrize('zone,expected', [
    ('UTC', '2026-10-18T16:19:00+00:00'),
    ('Asia/Tokyo', '2026-10-19T01:19:00+09:00'),
    ('America/New_York', '2026-10-18T12:19:00-04:00'),
])
def test_serialization_uses_deployment_server_timezone(zone, expected):
    with server_timezone(zone):
        for value in [datetime.datetime(2026, 10, 18, 16, 19),
                      datetime.datetime(2026, 10, 18, 16, 19, tzinfo=datetime.UTC),
                      '2026-10-18T16:19:00Z', '2026-10-19T01:19:00+09:00']:
            assert local_iso(value) == expected
        assert jsonable_local({'created_at': datetime.datetime(2026, 10, 18, 16, 19)}) == {'created_at': expected}


def test_server_timezone_keeps_daylight_saving_offset_for_each_instant():
    with server_timezone('America/New_York'):
        assert local_iso('2026-01-15T12:00:00Z') == '2026-01-15T07:00:00-05:00'
        assert local_iso('2026-07-15T12:00:00Z') == '2026-07-15T08:00:00-04:00'


def test_database_utc_round_trip_preserves_instant():
    aware = datetime.datetime.fromisoformat('2026-10-19T01:19:00+09:00')
    saved = utc_naive(aware)
    assert saved == datetime.datetime(2026, 10, 18, 16, 19)
    assert utc_naive(saved) == saved
    assert local_iso(None) == local_iso('') == ''


@pytest.mark.parametrize('zone', ['UTC', 'Asia/Tokyo', 'America/New_York'])
def test_runtime_timezone_endpoint_uses_server_environment(zone):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.config import router
    with server_timezone(zone):
        app = FastAPI()
        app.include_router(router, prefix='/config')
        with TestClient(app) as client:
            assert client.get('/config/timezone').json() == {'timeZone': zone}
