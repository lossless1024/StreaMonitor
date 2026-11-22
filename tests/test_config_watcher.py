"""
Tests for ConfigWatcherManager (_sync logic and file monitoring helpers).

The thread's run() method is excluded from automated tests (marked
pragma: no cover) because it blocks forever; we test the synchronisation
logic directly by calling _sync() and the file-monitoring helpers
(_file_changed, _safe_load) with mocked OS calls.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import streamonitor.managers.config_watcher as cw_module
from streamonitor.managers.config_watcher import ConfigWatcherManager


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _streamer(username, site, running=True):
    s = MagicMock()
    s.username = username
    s.site = site
    s.running = running
    return s


def _watcher(streamers=None):
    """Build a ConfigWatcherManager without calling __init__ or Thread."""
    w = ConfigWatcherManager.__new__(ConfigWatcherManager)
    w.streamers = streamers if streamers is not None else []
    w.logger = MagicMock()
    w._last_mtime = None
    w._last_size = None
    return w


# ---------------------------------------------------------------------------
# _sync – no-op when disk and memory match
# ---------------------------------------------------------------------------

class TestSyncNoOp:
    def test_identical_state_no_calls(self):
        s = _streamer("model1", "Chaturbate", running=True)
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()
        w.do_start = MagicMock()
        w.do_stop = MagicMock()

        w._sync([{"username": "model1", "site": "Chaturbate", "running": True}])

        w.do_add.assert_not_called()
        w.do_remove.assert_not_called()
        w.do_start.assert_not_called()
        w.do_stop.assert_not_called()

    def test_empty_disk_empty_memory_no_calls(self):
        w = _watcher([])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()

        w._sync([])

        w.do_add.assert_not_called()
        w.do_remove.assert_not_called()


# ---------------------------------------------------------------------------
# _sync – new entry on disk
# ---------------------------------------------------------------------------

class TestSyncAddition:
    def test_new_entry_calls_do_add(self):
        w = _watcher([])
        w.do_add = MagicMock(return_value="Added")
        w.do_stop = MagicMock()
        w.getStreamer = MagicMock(return_value=None)

        with patch.object(cw_module.Bot, "str2site", return_value=MagicMock()):
            w._sync([{"username": "newmodel", "site": "Chaturbate", "running": True}])

        w.do_add.assert_called_once_with(None, "newmodel", "Chaturbate")
        w.do_stop.assert_not_called()

    def test_new_entry_running_false_stops_after_add(self):
        """When a new entry has running=False, the bot should be added then stopped."""
        new_s = _streamer("newmodel", "Chaturbate", running=True)
        w = _watcher([])
        w.do_add = MagicMock(return_value="Added")
        w.do_stop = MagicMock(return_value="OK")
        w.getStreamer = MagicMock(return_value=new_s)

        with patch.object(cw_module.Bot, "str2site", return_value=MagicMock()):
            w._sync([{"username": "newmodel", "site": "Chaturbate", "running": False}])

        w.do_add.assert_called_once()
        w.do_stop.assert_called_once_with(new_s, "newmodel", "Chaturbate")

    def test_unknown_site_skips_add(self):
        w = _watcher([])
        w.do_add = MagicMock()

        with patch.object(cw_module.Bot, "str2site", return_value=None):
            w._sync([{"username": "model1", "site": "GhostSite", "running": True}])

        w.do_add.assert_not_called()
        w.logger.warning.assert_called()

    def test_malformed_entry_missing_site_skipped(self):
        w = _watcher([])
        w.do_add = MagicMock()

        w._sync([{"username": "model1"}])  # no 'site' key

        w.do_add.assert_not_called()

    def test_malformed_entry_missing_username_skipped(self):
        w = _watcher([])
        w.do_add = MagicMock()

        w._sync([{"site": "Chaturbate"}])  # no 'username' key

        w.do_add.assert_not_called()

    def test_duplicate_entries_on_disk_first_wins(self):
        """Duplicate (username, site) on disk: only the first is processed."""
        w = _watcher([])
        add_calls = []
        w.do_add = MagicMock(side_effect=lambda *a: add_calls.append(a) or "Added")
        w.do_stop = MagicMock()
        w.getStreamer = MagicMock(return_value=None)

        with patch.object(cw_module.Bot, "str2site", return_value=MagicMock()):
            w._sync([
                {"username": "model1", "site": "Chaturbate", "running": True},
                {"username": "model1", "site": "Chaturbate", "running": True},  # dup
            ])

        assert len(add_calls) == 1


# ---------------------------------------------------------------------------
# _sync – entry removed from disk
# ---------------------------------------------------------------------------

class TestSyncRemoval:
    def test_removed_entry_calls_do_remove(self):
        s = _streamer("oldmodel", "Chaturbate")
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock(return_value="OK")
        w.do_start = MagicMock()
        w.do_stop = MagicMock()

        w._sync([])  # empty disk

        w.do_remove.assert_called_once_with(s, "oldmodel", "Chaturbate")

    def test_multiple_removals(self):
        s1 = _streamer("model1", "Chaturbate")
        s2 = _streamer("model2", "Chaturbate")
        w = _watcher([s1, s2])
        w.do_remove = MagicMock(return_value="OK")
        w.do_add = MagicMock()
        w.do_start = MagicMock()
        w.do_stop = MagicMock()

        w._sync([])

        assert w.do_remove.call_count == 2


# ---------------------------------------------------------------------------
# _sync – 'running' field toggled for existing entries
# ---------------------------------------------------------------------------

class TestSyncRunningToggle:
    def test_running_true_to_false_stops(self):
        s = _streamer("model1", "Chaturbate", running=True)
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()
        w.do_start = MagicMock()
        w.do_stop = MagicMock(return_value="OK")

        w._sync([{"username": "model1", "site": "Chaturbate", "running": False}])

        w.do_stop.assert_called_once_with(s, "model1", "Chaturbate")
        w.do_start.assert_not_called()

    def test_running_false_to_true_starts(self):
        s = _streamer("model1", "Chaturbate", running=False)
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()
        w.do_start = MagicMock(return_value="OK")
        w.do_stop = MagicMock()

        w._sync([{"username": "model1", "site": "Chaturbate", "running": True}])

        w.do_start.assert_called_once_with(s, "model1", "Chaturbate")
        w.do_stop.assert_not_called()

    def test_already_running_no_start(self):
        s = _streamer("model1", "Chaturbate", running=True)
        w = _watcher([s])
        w.do_start = MagicMock()
        w.do_stop = MagicMock()
        w.do_add = MagicMock()
        w.do_remove = MagicMock()

        w._sync([{"username": "model1", "site": "Chaturbate", "running": True}])

        w.do_start.assert_not_called()
        w.do_stop.assert_not_called()

    def test_already_stopped_no_stop(self):
        s = _streamer("model1", "Chaturbate", running=False)
        w = _watcher([s])
        w.do_start = MagicMock()
        w.do_stop = MagicMock()
        w.do_add = MagicMock()
        w.do_remove = MagicMock()

        w._sync([{"username": "model1", "site": "Chaturbate", "running": False}])

        w.do_start.assert_not_called()
        w.do_stop.assert_not_called()

    def test_missing_running_field_defaults_to_true(self):
        """Entry without 'running' key → treated as running=True."""
        s = _streamer("model1", "Chaturbate", running=False)
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()
        w.do_start = MagicMock(return_value="OK")
        w.do_stop = MagicMock()

        w._sync([{"username": "model1", "site": "Chaturbate"}])  # no 'running'

        w.do_start.assert_called_once()


# ---------------------------------------------------------------------------
# _sync – case-insensitive matching
# ---------------------------------------------------------------------------

class TestSyncCaseInsensitive:
    def test_username_case_insensitive(self):
        s = _streamer("ModelOne", "Chaturbate", running=True)
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()
        w.do_start = MagicMock()
        w.do_stop = MagicMock()

        # Disk uses different casing
        w._sync([{"username": "modelone", "site": "chaturbate", "running": True}])

        w.do_add.assert_not_called()
        w.do_remove.assert_not_called()

    def test_site_case_insensitive(self):
        s = _streamer("model1", "CHATURBATE", running=True)
        w = _watcher([s])
        w.do_add = MagicMock()
        w.do_remove = MagicMock()
        w.do_start = MagicMock()
        w.do_stop = MagicMock()

        w._sync([{"username": "model1", "site": "Chaturbate", "running": True}])

        w.do_add.assert_not_called()
        w.do_remove.assert_not_called()


# ---------------------------------------------------------------------------
# File monitoring helpers
# ---------------------------------------------------------------------------

class TestFileChanged:
    def test_changed_mtime(self):
        w = _watcher()
        w._last_mtime = 1000.0
        w._last_size = 500

        with patch.object(cw_module.os, "stat") as mock_stat:
            mock_stat.return_value = SimpleNamespace(st_mtime=2000.0, st_size=500)
            assert w._file_changed() is True

        assert w._last_mtime == 2000.0

    def test_changed_size(self):
        w = _watcher()
        w._last_mtime = 1000.0
        w._last_size = 500

        with patch.object(cw_module.os, "stat") as mock_stat:
            mock_stat.return_value = SimpleNamespace(st_mtime=1000.0, st_size=600)
            assert w._file_changed() is True

    def test_unchanged(self):
        w = _watcher()
        w._last_mtime = 1000.0
        w._last_size = 500

        with patch.object(cw_module.os, "stat") as mock_stat:
            mock_stat.return_value = SimpleNamespace(st_mtime=1000.0, st_size=500)
            assert w._file_changed() is False

    def test_file_not_found_returns_none_tuple(self):
        w = _watcher()
        w._last_mtime = None
        w._last_size = None

        with patch.object(cw_module.os, "stat", side_effect=FileNotFoundError):
            mtime, size = w._stat()

        assert mtime is None
        assert size is None


class TestSafeLoad:
    def test_valid_json_returns_list(self, tmp_path):
        config_file = tmp_path / "config.json"
        data = [{"username": "model1", "site": "CB", "running": True}]
        config_file.write_text(json.dumps(data))

        w = _watcher()
        with patch.object(cw_module.config_module, "config_loc", str(config_file)):
            result = w._safe_load()

        assert result == data

    def test_invalid_json_returns_none(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{this is not valid json")

        w = _watcher()
        with patch.object(cw_module.config_module, "config_loc", str(config_file)):
            result = w._safe_load()

        assert result is None
        w.logger.warning.assert_called()

    def test_file_not_found_returns_none(self, tmp_path):
        w = _watcher()
        with patch.object(cw_module.config_module, "config_loc",
                          str(tmp_path / "nonexistent.json")):
            result = w._safe_load()

        assert result is None

    def test_empty_array_valid(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("[]")

        w = _watcher()
        with patch.object(cw_module.config_module, "config_loc", str(config_file)):
            result = w._safe_load()

        assert result == []
