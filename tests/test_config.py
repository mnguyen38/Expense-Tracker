"""Tests for config loading and the generated config file."""

import pytest

from expense_tracker.config import DEFAULT_CATEGORIES, DEFAULT_MODEL, Config, load_config


@pytest.fixture(autouse=True)
def no_env_overrides(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    monkeypatch.chdir(__import__("tempfile").gettempdir())


def test_defaults_without_config_file(tmp_path):
    config = load_config(tmp_path)
    assert config.model == DEFAULT_MODEL
    assert config.categories == DEFAULT_CATEGORIES
    assert config.db_path == tmp_path / "ledger.db"


def test_written_config_round_trips(tmp_path):
    original = Config(home=tmp_path, statement_close_day=11, alert_threshold=500, currency_symbol="£")
    original.categories = {"Food & Drink": 'meals, "coffee"', "Rent": "", "Misc": "other"}
    original.write()

    loaded = load_config(tmp_path)
    assert loaded.statement_close_day == 11
    assert loaded.alert_threshold == 500
    assert loaded.currency_symbol == "£"
    assert loaded.categories == original.categories


def test_misc_is_always_available(tmp_path):
    (tmp_path / "config.toml").write_text('[categories]\nFood = "meals"\n', encoding="utf-8")
    assert list(load_config(tmp_path).categories) == ["Food", "Misc"]


def test_environment_overrides_file(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text('model = "claude-haiku-4-5"\n', encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")
    assert load_config(tmp_path).model == "claude-opus-5"


def test_rejects_invalid_close_day(tmp_path):
    (tmp_path / "config.toml").write_text("statement_close_day = 40\n", encoding="utf-8")
    with pytest.raises(ValueError, match="1-31"):
        load_config(tmp_path)
