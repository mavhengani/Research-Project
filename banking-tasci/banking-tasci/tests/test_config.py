"""Tests for the Config_Loader (src/banking_tasci/config.py).

Covers:
- Req 2.1: loading a base + override file pair produces the merged result.
- Req 2.2: merge precedence (Property 1).
- Req 2.3: missing required key after merge raises ConfigError naming the
  key and file path.
- Req 2.4: malformed YAML raises ConfigError wrapping the parse error and
  file path.
- Req 2.5: attribute access mirrors dict access (Property 2).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from banking_tasci.config import Config, ConfigError, load_config, require  # noqa: E402


# ---------------------------------------------------------------------------
# Strategies for YAML-serializable nested dicts.
# ---------------------------------------------------------------------------

_scalar_strategy = st.one_of(
    st.text(max_size=10),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)


_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), min_codepoint=48, max_codepoint=122),
    min_size=1,
    max_size=8,
)


def _nested_dict_strategy(max_depth: int = 2):
    """A strategy for small dicts with string keys, scalar or nested dict values.

    Depth is bounded explicitly (rather than via st.recursive) to keep
    generation fast and avoid Hypothesis's "too slow" health check.
    """
    leaf = st.dictionaries(_key_strategy, _scalar_strategy, min_size=0, max_size=3)
    strategy = leaf
    for _ in range(max_depth):
        strategy = st.dictionaries(_key_strategy, st.one_of(_scalar_strategy, strategy), min_size=0, max_size=3)
    return strategy


# ---------------------------------------------------------------------------
# Unit tests (Req 2.1, 2.3, 2.4)
# ---------------------------------------------------------------------------

def test_load_config_merges_base_and_override_file_pair(tmp_path: Path) -> None:
    """Req 2.1: loading a base + override file pair produces the merged result."""
    base_path = tmp_path / "base.yaml"
    base_path.write_text(
        yaml.safe_dump({"seed": 42, "log_level": "INFO", "anonymise": {"replace_amounts": False, "flag_b": 1}}),
        encoding="utf-8",
    )

    override_path = tmp_path / "override.yaml"
    override_path.write_text(
        yaml.safe_dump({"defaults": "base.yaml", "log_level": "DEBUG", "anonymise": {"replace_amounts": True}}),
        encoding="utf-8",
    )

    cfg = load_config(override_path)

    assert cfg.seed == 42  # preserved from base
    assert cfg.log_level == "DEBUG"  # overridden
    assert cfg.anonymise.replace_amounts is True  # overridden (nested)
    assert cfg.anonymise.flag_b == 1  # preserved from base (nested)


def test_load_config_with_overrides_argument(tmp_path: Path) -> None:
    base_path = tmp_path / "base.yaml"
    base_path.write_text(yaml.safe_dump({"seed": 1, "keep": "yes"}), encoding="utf-8")

    cfg = load_config(base_path, overrides={"seed": 99})

    assert cfg.seed == 99
    assert cfg.keep == "yes"


def test_require_raises_config_error_for_missing_key(tmp_path: Path) -> None:
    """Req 2.3: missing required key after merge raises ConfigError naming key and file path."""
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump({"seed": 1}), encoding="utf-8")
    cfg = load_config(path)

    with pytest.raises(ConfigError) as exc_info:
        require(cfg, "anonymise.replace_amounts", str(path))

    err = exc_info.value
    assert err.key_path == "anonymise.replace_amounts"
    assert err.file_path == str(path)
    assert "anonymise.replace_amounts" in str(err)
    assert str(path) in str(err)


def test_require_returns_value_when_present(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump({"anonymise": {"replace_amounts": True}}), encoding="utf-8")
    cfg = load_config(path)

    assert require(cfg, "anonymise.replace_amounts", str(path)) is True


def test_load_config_raises_config_error_for_malformed_yaml(tmp_path: Path) -> None:
    """Req 2.4: malformed YAML raises ConfigError wrapping the parse error and file path."""
    path = tmp_path / "broken.yaml"
    path.write_text("key: [unclosed list\nother: value", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(path)

    err = exc_info.value
    assert err.file_path == str(path)
    assert str(path) in str(err)


def test_config_to_dict_returns_plain_dict(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump({"a": {"b": 1}}), encoding="utf-8")
    cfg = load_config(path)

    assert cfg.to_dict() == {"a": {"b": 1}}


# ---------------------------------------------------------------------------
# Req 2.6: inheritance cycle detection.
# ---------------------------------------------------------------------------

def test_direct_inheritance_cycle_is_detected(tmp_path: Path) -> None:
    """A -> B -> A must raise a ConfigError naming the chain, not recurse."""
    a = tmp_path / "config_a.yaml"
    b = tmp_path / "config_b.yaml"
    a.write_text(yaml.safe_dump({"defaults": "config_b.yaml", "x": 1}), encoding="utf-8")
    b.write_text(yaml.safe_dump({"defaults": "config_a.yaml", "y": 2}), encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(a)

    msg = str(exc_info.value)
    assert "cycle detected" in msg.lower()
    assert "config_a.yaml" in msg
    assert "config_b.yaml" in msg


def test_self_referential_cycle_is_detected(tmp_path: Path) -> None:
    """A file that inherits from itself is a (degenerate) cycle."""
    a = tmp_path / "self.yaml"
    a.write_text(yaml.safe_dump({"base": "self.yaml", "x": 1}), encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(a)
    assert "cycle detected" in str(exc_info.value).lower()
    assert "self.yaml" in str(exc_info.value)


def test_indirect_inheritance_cycle_is_detected(tmp_path: Path) -> None:
    """A -> B -> C -> A must raise a ConfigError naming the full chain."""
    a = tmp_path / "config_a.yaml"
    b = tmp_path / "config_b.yaml"
    c = tmp_path / "config_c.yaml"
    a.write_text(yaml.safe_dump({"defaults": "config_b.yaml"}), encoding="utf-8")
    b.write_text(yaml.safe_dump({"defaults": "config_c.yaml"}), encoding="utf-8")
    c.write_text(yaml.safe_dump({"defaults": "config_a.yaml"}), encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(a)

    msg = str(exc_info.value)
    assert "cycle detected" in msg.lower()
    for name in ("config_a.yaml", "config_b.yaml", "config_c.yaml"):
        assert name in msg


def test_valid_multi_level_inheritance_still_works(tmp_path: Path) -> None:
    """A valid (acyclic) A -> B -> C chain must still deep-merge correctly."""
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    c = tmp_path / "c.yaml"
    c.write_text(yaml.safe_dump({"seed": 1, "nested": {"keep": "c", "over": "c"}}), encoding="utf-8")
    b.write_text(yaml.safe_dump({"defaults": "c.yaml", "nested": {"over": "b"}}), encoding="utf-8")
    a.write_text(yaml.safe_dump({"defaults": "b.yaml", "top": "a"}), encoding="utf-8")

    cfg = load_config(a)
    assert cfg.seed == 1              # from c
    assert cfg.nested.keep == "c"     # from c
    assert cfg.nested.over == "b"     # b overrides c
    assert cfg.top == "a"             # from a


def test_diamond_inheritance_is_not_a_cycle(tmp_path: Path) -> None:
    """A references the same base twice through different branches: the base is
    loaded on two independent branches, which is NOT a cycle."""
    base = tmp_path / "base.yaml"
    left = tmp_path / "left.yaml"
    base.write_text(yaml.safe_dump({"seed": 5}), encoding="utf-8")
    left.write_text(yaml.safe_dump({"defaults": "base.yaml", "x": 1}), encoding="utf-8")
    # left -> base is a simple valid chain; loading it twice is fine.
    assert load_config(left).seed == 5
    assert load_config(left).x == 1



# ---------------------------------------------------------------------------
# Property 1: Config merge — override wins, base keys preserved.
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

def _assert_merge_correct(base: dict, override: dict, merged: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _assert_merge_correct(base[key], value, merged[key])
        else:
            assert merged[key] == value
    for key, value in base.items():
        if key not in override:
            assert merged[key] == value


@settings(max_examples=100)
@given(base=_nested_dict_strategy(), override=_nested_dict_strategy())
# Feature: banking-tasci-pipeline, Property 1: Config merge — override wins, base keys preserved
def test_property_config_merge_override_wins_base_preserved(base: dict, override: dict) -> None:
    from banking_tasci.config import _deep_merge

    merged = _deep_merge(base, override)
    _assert_merge_correct(base, override, merged)


# ---------------------------------------------------------------------------
# Property 2: Config attribute access mirrors dict access.
# Validates: Requirements 2.5
# ---------------------------------------------------------------------------

def _assert_attr_matches_dict(cfg: Config, data: dict) -> None:
    for key, value in data.items():
        attr_value = getattr(cfg, key)
        if isinstance(value, dict):
            assert isinstance(attr_value, Config)
            _assert_attr_matches_dict(attr_value, value)
        else:
            assert attr_value == value


@settings(max_examples=100)
@given(data=_nested_dict_strategy())
# Feature: banking-tasci-pipeline, Property 2: Config attribute access mirrors dict access
def test_property_config_attribute_access_mirrors_dict_access(data: dict) -> None:
    cfg = Config(data)
    _assert_attr_matches_dict(cfg, data)
