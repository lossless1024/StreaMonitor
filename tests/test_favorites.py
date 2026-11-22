import json

from streamonitor import config
from streamonitor.manager import Manager


def test_sync_favorites_creates_copy_and_preserves_existing(tmp_path, monkeypatch):
    base = tmp_path / "config.json"
    favorites = tmp_path / "config.favorites.json"
    base_entries = [
        {"username": "model1", "site": "Chaturbate", "running": True},
        {"username": "model2", "site": "StripChat", "running": False},
    ]
    base.write_text(json.dumps(base_entries))
    favorites.write_text(json.dumps([
        {"username": "model1", "site": "Chaturbate", "favorite": True},
    ]))
    monkeypatch.setattr(config, "config_loc", str(base))
    monkeypatch.setattr(config, "favorites_loc", str(favorites))

    result = config.sync_favorites_config(base_entries)

    assert result[0]["favorite"] is True
    assert result[1]["favorite"] is False
    assert json.loads(favorites.read_text()) == result


def test_sync_favorites_removes_models_deleted_from_config(tmp_path, monkeypatch):
    base = tmp_path / "config.json"
    favorites = tmp_path / "config.favorites.json"
    base_entries = [{"username": "model1", "site": "Chaturbate", "running": True}]
    base.write_text(json.dumps(base_entries))
    favorites.write_text(json.dumps([
        {"username": "model1", "site": "Chaturbate", "favorite": True},
        {"username": "deleted", "site": "StripChat", "favorite": True},
    ]))
    monkeypatch.setattr(config, "favorites_loc", str(favorites))

    result = config.sync_favorites_config(base_entries)

    assert [entry["username"] for entry in result] == ["model1"]
    assert result[0]["favorite"] is True


def test_set_favorite_does_not_modify_config(tmp_path, monkeypatch):
    base = tmp_path / "config.json"
    favorites = tmp_path / "config.favorites.json"
    base_entries = [{"username": "model1", "site": "Chaturbate", "running": True}]
    base.write_text(json.dumps(base_entries))
    favorites.write_text("[]")
    monkeypatch.setattr(config, "config_loc", str(base))
    monkeypatch.setattr(config, "favorites_loc", str(favorites))

    assert config.set_favorite("model1", "Chaturbate", True) is True
    assert json.loads(base.read_text()) == base_entries
    assert json.loads(favorites.read_text())[0]["favorite"] is True


def test_load_favorite_streamers_filters_by_copy(tmp_path, monkeypatch):
    base = tmp_path / "config.json"
    favorites = tmp_path / "config.favorites.json"
    base_entries = [
        {"username": "model1", "site": "Chaturbate", "running": True},
        {"username": "model2", "site": "StripChat", "running": True},
    ]
    base.write_text(json.dumps(base_entries))
    favorites.write_text(json.dumps([
        dict(base_entries[0], favorite=True),
        dict(base_entries[1], favorite=False),
    ]))
    monkeypatch.setattr(config, "config_loc", str(base))
    monkeypatch.setattr(config, "favorites_loc", str(favorites))

    result = config.load_favorite_streamers()

    assert [entry["username"] for entry in result] == ["model1"]


def test_save_config_is_ignored_in_favorites_mode(monkeypatch):
    config.favorites_only = True
    manager = object.__new__(Manager)
    called = []
    monkeypatch.setattr(config, "saveStreamers", lambda streamers: called.append(streamers))

    manager.saveConfig()

    assert called == []
    config.favorites_only = False


def test_missing_favorites_file_is_created(tmp_path, monkeypatch):
    base = tmp_path / "config.json"
    favorites = tmp_path / "config.favorites.json"
    base_entries = [{"username": "model1", "site": "Chaturbate", "running": True}]
    base.write_text(json.dumps(base_entries))
    monkeypatch.setattr(config, "config_loc", str(base))
    monkeypatch.setattr(config, "favorites_loc", str(favorites))

    result = config.ensure_favorites_config(base_entries)

    assert favorites.exists()
    assert result[0]["favorite"] is False


def test_invalid_favorites_file_is_not_overwritten(tmp_path, monkeypatch):
    base = tmp_path / "config.json"
    favorites = tmp_path / "config.favorites.json"
    base_entries = [{"username": "model1", "site": "Chaturbate", "running": True}]
    base.write_text(json.dumps(base_entries))
    favorites.write_text("{partial")
    monkeypatch.setattr(config, "config_loc", str(base))
    monkeypatch.setattr(config, "favorites_loc", str(favorites))

    result = config.sync_favorites_config(base_entries)

    assert favorites.read_text() == "{partial"
    assert result[0]["username"] == "model1"
    assert result[0]["favorite"] is False


def test_fav_list_command(monkeypatch):
    manager = object.__new__(Manager)
    monkeypatch.setattr(
        config,
        "load_favorites_config",
        lambda: [
            {"username": "model1", "site": "Chaturbate", "favorite": True},
            {"username": "model2", "site": "StripChat", "favorite": False},
        ],
    )

    result = manager.do_fav(None, "list", "")

    assert result == "Chaturbate/model1"
