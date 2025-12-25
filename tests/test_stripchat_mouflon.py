import json
from pathlib import Path

import pytest

# Import the class under test
from streamonitor.sites.stripchat import StripChat


def setup_stripchat(tmp_path: Path):
    """
    Reset shared class state between tests and point cache to a temp file.
    """
    StripChat._mouflon_keys = {}
    StripChat._cached_keys = None
    StripChat._mouflon_cache_filename = str(tmp_path / "mouflon_cache.json")


def test_none_js_data_returns_none(tmp_path):
    setup_stripchat(tmp_path)
    StripChat._doppio_js_data = None
    assert StripChat.getMouflonDecKey("any") is None


def test_bytes_js_data_decoded_and_match(tmp_path):
    setup_stripchat(tmp_path)
    # bytes payload that decodes to a simple key:value pair
    StripChat._doppio_js_data = b'"abc:decoded_value" some other content'
    res = StripChat.getMouflonDecKey("abc")
    assert res == "decoded_value"
    # ensure the cache file was written and contains the key
    with open(StripChat._mouflon_cache_filename, "r") as f:
        data = json.load(f)
    assert data.get("abc") == "decoded_value"


def test_str_js_data_escape_pkey(tmp_path):
    setup_stripchat(tmp_path)
    # pkey contains regex-special characters
    pkey = r'a.b*c+?^$'
    StripChat._doppio_js_data = f'"{pkey}:val123"'
    res = StripChat.getMouflonDecKey(pkey)
    assert res == "val123"


def test_no_match_returns_none(tmp_path):
    setup_stripchat(tmp_path)
    StripChat._doppio_js_data = '"foo:bar"'
    assert StripChat.getMouflonDecKey("nonexistent") is None
