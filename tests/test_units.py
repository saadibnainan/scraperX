"""Unit tests for the browser-independent modules."""

import os

import pandas as pd
import pytest

from scraperx.config import Config, _as_bool, _as_int, _as_list
from scraperx.rotators import ProxyRotator, UserAgentRotator, _parse_proxy
from scraperx.exporter import DataExporter


# --- config parsing --------------------------------------------------------
def test_as_bool():
    assert _as_bool("true", False) is True
    assert _as_bool("NO", True) is False
    assert _as_bool("", True) is True          # empty -> default
    assert _as_bool("garbage", False) is False  # unknown -> default


def test_as_int_and_list():
    assert _as_int("7", 0) == 7
    assert _as_int("x", 3) == 3
    assert _as_list("a, b\nc,,d") == ["a", "b", "c", "d"]
    assert _as_list("") == []


def test_config_overrides_ignore_none():
    cfg = Config.from_env(target_url="https://x.test", crawl_depth=None)
    assert cfg.target_url == "https://x.test"
    assert cfg.crawl_depth == 1  # unchanged default, None ignored


def test_config_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        Config.from_env(max_retries=-1)


def test_config_redacts_secrets():
    cfg = Config.from_env(proxy_url="http://u:p@host:8080",
                          proxy_username="u", proxy_password="p")
    red = cfg.redacted()
    assert red["proxy_password"] == "***"
    assert red["proxy_url"] == "***"


# --- proxy parsing / rotation ----------------------------------------------
def test_parse_proxy_embedded_creds():
    p = _parse_proxy("http://user:pass@host:8080")
    assert p == {"server": "http://host:8080", "username": "user", "password": "pass"}


def test_parse_proxy_no_scheme():
    p = _parse_proxy("host:3128")
    assert p["server"] == "http://host:3128"


def test_proxy_rotator_round_robin():
    r = ProxyRotator([{"server": "http://a"}, {"server": "http://b"}])
    seq = [r.next()["server"] for _ in range(4)]
    assert seq == ["http://a", "http://b", "http://a", "http://b"]


def test_proxy_rotator_empty_returns_none():
    r = ProxyRotator([])
    assert r.next() is None
    assert r.enabled is False


def test_ua_rotator_falls_back_to_builtin():
    r = UserAgentRotator([])
    ua = r.next()
    assert isinstance(ua, str) and "Mozilla" in ua


def test_ua_rotator_uses_supplied_pool():
    r = UserAgentRotator(["UA-1", "UA-2"])
    assert [r.next() for _ in range(3)] == ["UA-1", "UA-2", "UA-1"]


# --- exporter --------------------------------------------------------------
def test_exporter_writes_csv(tmp_path):
    out = tmp_path / "sub" / "results.csv"
    exp = DataExporter(str(out))
    exp.extend([
        {"source_url": "u1", "text": "hello", "record_type": "element"},
        {"source_url": "u2", "text": "world", "record_type": "link", "href": "h"},
    ])
    path = exp.export()
    assert os.path.exists(path)
    df = pd.read_csv(path)
    assert len(df) == 2
    # preferred columns come first
    assert list(df.columns)[0] == "source_url"


def test_exporter_append(tmp_path):
    out = tmp_path / "a.csv"
    exp = DataExporter(str(out))
    exp.export([{"source_url": "u1"}])
    exp.export([{"source_url": "u2"}], append=True)
    df = pd.read_csv(out)
    assert len(df) == 2


def test_exporter_empty(tmp_path):
    out = tmp_path / "empty.csv"
    exp = DataExporter(str(out))
    path = exp.export([])
    assert os.path.exists(path)
