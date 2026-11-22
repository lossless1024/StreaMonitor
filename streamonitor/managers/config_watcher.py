"""
config_watcher.py – Hot-reload watcher for config.json.

Polls config.json every POLL_INTERVAL seconds and synchronises the
in-memory ``streamers`` list with whatever the file currently contains.
This lets the user edit config.json with any text editor while the bot
is running, and the changes take effect automatically:

  * New entry added       → bot thread is started
  * Entry removed         → bot thread is stopped and removed
  * "running" false→true  → bot resumes monitoring
  * "running" true→false  → bot pauses monitoring

No external dependencies — only stdlib ``os``, ``json``, and
``time``.  All sync logic goes through the existing ``Manager``
command methods (``do_add``, ``do_remove``, ``do_start``,
``do_stop``) so behaviour is identical to using the CLI or web UI.
"""

import json
import os
import time

import streamonitor.config as config_module
import streamonitor.log as log
from streamonitor.bot import Bot
from streamonitor.manager import Manager


class ConfigWatcherManager(Manager):
    """Watches config.json for external edits and keeps streamers in sync."""

    # Seconds between file-stat polls.  5 s is a good balance between
    # responsiveness and I/O cost.
    POLL_INTERVAL = 5

    def __init__(self, streamers, favorites_only=False):
        super().__init__(streamers)
        self.daemon = True
        self.logger = log.Logger("config-watcher").get_logger()
        self.favorites_only = favorites_only
        self._last_mtime: float | None = None
        self._last_size: int | None = None
        self._last_favorites_mtime: float | None = None
        self._last_favorites_size: int | None = None

    # ------------------------------------------------------------------
    # File monitoring helpers
    # ------------------------------------------------------------------

    def _stat(self) -> tuple:
        """Return (mtime, size) of config.json, or (None, None) if missing."""
        try:
            s = os.stat(config_module.config_loc)
            return s.st_mtime, s.st_size
        except FileNotFoundError:
            return None, None

    def _favorites_stat(self) -> tuple:
        try:
            s = os.stat(config_module.favorites_loc)
            return s.st_mtime, s.st_size
        except FileNotFoundError:
            return None, None

    def _favorites_file_changed(self) -> bool:
        mtime, size = self._favorites_stat()
        changed = (
            mtime != self._last_favorites_mtime
            or size != self._last_favorites_size
        )
        if changed:
            self._last_favorites_mtime = mtime
            self._last_favorites_size = size
        return changed

    def _file_changed(self) -> bool:
        """Return True if the file's mtime or size differs from the last check,
        and update the internal baseline."""
        mtime, size = self._stat()
        changed = (mtime != self._last_mtime or size != self._last_size)
        if changed:
            self._last_mtime = mtime
            self._last_size = size
        return changed

    def _safe_load(self):
        """Read and parse config.json without calling sys.exit on error.

        Returns the parsed list, or None if the file is unreadable or
        contains invalid JSON (e.g. a partial write still in progress).
        """
        try:
            with open(config_module.config_loc, "r") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return None
        except (ValueError, json.JSONDecodeError):
            self.logger.warning(
                "config-watcher: config.json is not valid JSON yet "
                "(partial write?), skipping this cycle"
            )
            return None
        except Exception as exc:
            self.logger.warning(f"config-watcher: could not read config.json: {exc}")
            return None

    # ------------------------------------------------------------------
    # Key helpers — both are case-insensitive
    # ------------------------------------------------------------------

    @staticmethod
    def _mem_key(streamer) -> tuple:
        return (streamer.username.lower(), streamer.site.lower())

    @staticmethod
    def _disk_key(entry: dict) -> tuple:
        return (entry["username"].lower(), entry["site"].lower())

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------

    def _sync(self, disk_entries: list) -> None:
        """Diff disk state vs. in-memory state and apply the minimum changes."""

        # Snapshot current in-memory list (avoid mutation issues mid-loop)
        mem_map = {self._mem_key(s): s for s in list(self.streamers)}

        # Build disk map; first occurrence wins (guard against duplicates)
        disk_map: dict = {}
        for entry in disk_entries:
            if "username" not in entry or "site" not in entry:
                continue  # malformed entry – skip silently
            key = self._disk_key(entry)
            if key not in disk_map:
                disk_map[key] = entry

        # 1. New entries on disk → add ----------------------------------------
        for key, entry in disk_map.items():
            if key in mem_map:
                continue
            username, site = entry["username"], entry["site"]
            if not Bot.str2site(site):
                self.logger.warning(
                    f"config-watcher: unknown site '{site}' for '{username}', skipping"
                )
                continue
            try:
                result = self.do_add(None, username, site)
                self.logger.info(f"config-watcher: added {site}/{username}: {result}")
                # Respect 'running' field: do_add always starts the bot,
                # so stop it immediately if the entry says running=False.
                if not entry.get("running", True):
                    new_s = self.getStreamer(username, site)
                    if new_s:
                        self.do_stop(new_s, username, site)
            except Exception as exc:
                self.logger.error(
                    f"config-watcher: error adding {site}/{username}: {exc}"
                )

        # 2. Entries removed from disk → remove ----------------------------------
        for key, streamer in list(mem_map.items()):
            if key not in disk_map:
                try:
                    result = self.do_remove(
                        streamer, streamer.username, streamer.site
                    )
                    self.logger.info(
                        f"config-watcher: removed {streamer.site}/{streamer.username}: {result}"
                    )
                except Exception as exc:
                    self.logger.error(
                        f"config-watcher: error removing "
                        f"{streamer.site}/{streamer.username}: {exc}"
                    )

        # 3. 'running' field toggled (existing entries only) ----------------------
        for key, entry in disk_map.items():
            if key not in mem_map:
                continue  # already processed as new entry above
            streamer = mem_map[key]
            disk_running = entry.get("running", True)
            if disk_running and not streamer.running:
                result = self.do_start(streamer, streamer.username, streamer.site)
                self.logger.info(
                    f"config-watcher: started {streamer.site}/{streamer.username}: {result}"
                )
            elif not disk_running and streamer.running:
                result = self.do_stop(streamer, streamer.username, streamer.site)
                self.logger.info(
                    f"config-watcher: stopped {streamer.site}/{streamer.username}: {result}"
                )

    def _sync_favorites(self) -> None:
        if (
            os.path.exists(config_module.favorites_loc)
            and config_module.load_favorites_config() is None
        ):
            return
        favorite_entries = config_module.load_favorite_streamers()
        target = {
            (
                entry["username"].lower(),
                entry["site"].lower(),
            ): entry
            for entry in favorite_entries
        }
        mem_map = {
            self._mem_key(streamer): streamer
            for streamer in list(self.streamers)
        }

        for key, entry in target.items():
            if key in mem_map:
                continue
            try:
                result = self.do_add(None, entry["username"], entry["site"])
                self.logger.info(
                    f"config-watcher: added favorite {entry['site']}/{entry['username']}: {result}"
                )
                added = self.getStreamer(entry["username"], entry["site"])
                if added and not entry.get("running", True):
                    self.do_stop(added, entry["username"], entry["site"])
            except Exception as exc:
                self.logger.error(
                    f"config-watcher: error adding favorite "
                    f"{entry['site']}/{entry['username']}: {exc}"
                )

        for key, streamer in list(mem_map.items()):
            if key in target:
                continue
            try:
                result = self.do_remove(
                    streamer,
                    streamer.username,
                    streamer.site,
                )
                self.logger.info(
                    f"config-watcher: removed favorite "
                    f"{streamer.site}/{streamer.username}: {result}"
                )
            except Exception as exc:
                self.logger.error(
                    f"config-watcher: error removing favorite "
                    f"{streamer.site}/{streamer.username}: {exc}"
                )

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:  # pragma: no cover
        # Seed the baseline so we do NOT trigger on the very first poll
        # (the file on disk already reflects the in-memory state loaded
        # at startup).
        self._last_mtime, self._last_size = self._stat()
        self._last_favorites_mtime, self._last_favorites_size = self._favorites_stat()
        self.logger.info(
            f"config-watcher: watching '{config_module.config_loc}' "
            f"every {self.POLL_INTERVAL}s"
        )
        while True:
            time.sleep(self.POLL_INTERVAL)
            config_changed = self._file_changed()
            favorites_changed = self._favorites_file_changed()
            if not config_changed and not favorites_changed:
                continue
            entries = self._safe_load() if config_changed else None
            if config_changed and entries is None:
                # File missing or mid-write; update baseline anyway so we
                # re-check on the NEXT mtime change, not every poll.
                self._last_mtime, self._last_size = self._stat()
            elif config_changed:
                self.logger.debug("config-watcher: config change detected, syncing…")
                config_module.sync_favorites_config(entries)
                if self.favorites_only:
                    self._sync_favorites()
                else:
                    self._sync(entries)

            if favorites_changed:
                self.logger.debug("config-watcher: favorites change detected, syncing…")
                config_module.sync_favorites_config()
                if self.favorites_only:
                    self._sync_favorites()
