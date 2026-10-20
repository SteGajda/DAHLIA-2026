"""Frozen defaults are public config, source mode and overrides stay usable."""

import json
import sys

from dahlia.core.desktop_runtime import configure_desktop_runtime


def test_source_mode_does_not_set_cloud_defaults(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.delenv('DAHLIA_API_URL', raising=False)
    monkeypatch.delenv('DAHLIA_API_TIMEOUT', raising=False)
    configure_desktop_runtime()
    import os
    assert 'DAHLIA_API_URL' not in os.environ
    assert 'DAHLIA_API_TIMEOUT' not in os.environ


def test_frozen_defaults_and_explicit_overrides(tmp_path, monkeypatch):
    root = tmp_path / 'bundle'
    root.mkdir()
    (root / 'dahlia_build.json').write_text(json.dumps({
        'api_url': 'https://api.example.com', 'api_timeout': 120,
    }))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(root), raising=False)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'state'))
    monkeypatch.delenv('DAHLIA_API_URL', raising=False)
    monkeypatch.delenv('DAHLIA_API_TIMEOUT', raising=False)
    configure_desktop_runtime()
    import os
    assert os.environ['DAHLIA_API_URL'] == 'https://api.example.com'
    assert os.environ['DAHLIA_API_TIMEOUT'] == '120'
    monkeypatch.setenv('DAHLIA_API_URL', 'http://127.0.0.1:8000')
    configure_desktop_runtime()
    assert os.environ['DAHLIA_API_URL'] == 'http://127.0.0.1:8000'


def test_windowed_mode_has_writable_streams(tmp_path, monkeypatch):
    (tmp_path / 'dahlia_build.json').write_text(json.dumps({
        'api_url': 'https://api.example.com', 'api_timeout': 120,
    }))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    monkeypatch.setenv('APPDATA', str(tmp_path))
    # Restore the environment at fixture teardown after setdefault writes.
    monkeypatch.setenv('DAHLIA_API_URL', 'https://api.example.com')
    monkeypatch.setenv('DAHLIA_API_TIMEOUT', '120')
    configure_desktop_runtime()
    streams = sys.stdout, sys.stderr
    try:
        sys.stderr.write('windowed diagnostic\n')
        sys.stderr.flush()
        assert 'windowed diagnostic' in (tmp_path / 'DAHLIA/logs/desktop.log').read_text()
    finally:
        for stream in streams:
            stream.close()
