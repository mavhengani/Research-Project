"""Configuration loading for the banking-tasci project.

Loads YAML configuration files from `configs/`, supporting a `defaults`/
`base` top-level key that references another YAML file (resolved relative
to the referencing file's directory) to deep-merge as a base configuration,
with the referencing file's own keys taking precedence.

Requirements:
- 2.1: load configuration values from YAML files under configs/
- 2.2: merge a referenced base configuration, override file wins
- 2.3: raise an explicit exception naming a missing required key + file path
- 2.4: raise an explicit exception naming the file path + underlying parse error
- 2.5: expose loaded configuration as an attribute-accessible object
- 2.6: detect inheritance cycles (A -> B -> A) and raise a ConfigError whose
  message names the full chain of files involved, instead of recursing until
  the interpreter's recursion limit is hit.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Union

import yaml

PathLike = Union[str, Path]

# Top-level keys used to reference a base configuration file to merge under
# this file's own keys. Checked in this order; only the first one found is
# treated as the base reference (and both are stripped from the merged
# result, since they are directives, not real config values).
_BASE_REFERENCE_KEYS = ("defaults", "base")

# Attribute names that resolve via normal Python attribute lookup (instance/
# class attributes) rather than falling through to Config.__getattr__.
# Config keys colliding with these names remain accessible via dict-style
# access (`cfg["to_dict"]`) but not via attribute access.
_RESERVED_ATTRS = frozenset({"_data", "to_dict"})

_MISSING = object()


class ConfigError(Exception):
    """Raised for a missing required config key or unparsable YAML content.

    Carries `file_path` (and `key_path`, when applicable) so callers can
    report exactly which file/key caused the failure (Req 2.3, 2.4).
    """

    def __init__(self, message: str, *, file_path: str | None = None, key_path: str | None = None):
        self.file_path = file_path
        self.key_path = key_path
        super().__init__(message)


class Config:
    """Recursive attribute-accessible wrapper around a merged config dict.

    Nested dicts are wrapped in `Config` lazily on access, so `cfg.a.b.c`
    mirrors `d["a"]["b"]["c"]` for any YAML-serializable nested dict
    (Req 2.5).
    """

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        # Only invoked when normal attribute lookup (instance/class
        # attributes, including `_data` and `to_dict`) does not find `name`.
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(
                f"Config has no key '{name}'"
            ) from exc
        if isinstance(value, dict):
            return Config(value)
        return value

    def __getitem__(self, name: str) -> Any:
        value = self._data[name]
        if isinstance(value, dict):
            return Config(value)
        return value

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Config):
            return self._data == other._data
        return NotImplemented

    def __repr__(self) -> str:
        return f"Config({self._data!r})"

    def to_dict(self) -> dict:
        """Return a plain (deep-copied) dict of the wrapped configuration."""
        return copy.deepcopy(self._data)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge `override` on top of `base`; override values win.

    Keys present only in `base` are preserved unchanged; keys present in
    `override` (at any nesting level) take precedence (Req 2.2).
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml_dict(path: Path) -> dict:
    """Read and parse a YAML file at `path`, returning its top-level dict.

    Raises ConfigError naming `path` if the file cannot be read, cannot be
    parsed as valid YAML, or does not contain a top-level mapping (Req 2.4).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Cannot read config file {path}: {exc}", file_path=str(path)
        ) from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Failed to parse YAML file {path}: {exc}", file_path=str(path)
        ) from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"Config file {path} must contain a top-level mapping, got {type(data).__name__}",
            file_path=str(path),
        )
    return data


def _format_cycle_chain(chain: "list[Path]", repeated: Path) -> str:
    """Render a human-readable inheritance chain ending at the file that
    closes the cycle, e.g. ``config_a.yaml -> config_b.yaml -> config_a.yaml``.

    Uses each path's file name for readability, but falls back to the full
    resolved path if two files in the chain share a name (so the message is
    never ambiguous about which files are involved).
    """
    full = chain + [repeated]
    names = [p.name for p in full]
    if len(set(names)) != len(names):
        # Name collision across directories -> show full resolved paths.
        return " -> ".join(str(p) for p in full)
    return " -> ".join(names)


def _load_merged_dict(path: Path, _chain: "list[Path] | None" = None) -> dict:
    """Load `path`, recursively resolving and merging any base reference.

    `_chain` is the list of already-resolved config paths on the current
    inheritance branch. It is used to detect inheritance cycles: if `path`
    (resolved) is already on the chain, a `ConfigError` naming the full chain
    is raised instead of recursing forever (Req 2.6).
    """
    resolved = path.resolve()
    chain = list(_chain or [])
    if resolved in chain:
        raise ConfigError(
            "Configuration inheritance cycle detected: "
            + _format_cycle_chain(chain, resolved),
            file_path=str(resolved),
        )
    chain.append(resolved)

    data = _read_yaml_dict(path)

    base_ref = None
    for key in _BASE_REFERENCE_KEYS:
        if key in data:
            base_ref = data.pop(key)
            break
    # Strip any remaining base-reference keys so they never leak into the
    # merged result (e.g. a file declaring both `defaults` and `base`).
    for key in _BASE_REFERENCE_KEYS:
        data.pop(key, None)

    if base_ref is None:
        return data

    base_path = (path.parent / base_ref).resolve()
    base_data = _load_merged_dict(base_path, chain)
    return _deep_merge(base_data, data)


def load_config(path: PathLike, overrides: dict | None = None) -> Config:
    """Load a YAML file at `path` into a `Config` object.

    If the file contains a top-level `defaults`/`base` key referencing
    another YAML file (resolved relative to `path`'s directory), that base
    configuration is loaded and deep-merged first, with this file's own
    keys applied on top (override wins). `overrides`, when given, is
    deep-merged on top of the fully-resolved file configuration with the
    same override-wins precedence.

    Raises ConfigError on unreadable/unparsable YAML (Req 2.4).
    """
    path = Path(path)
    merged = _load_merged_dict(path)
    if overrides:
        merged = _deep_merge(merged, overrides)
    return Config(merged)


def require(cfg: Config, key_path: str, file_path: str) -> Any:
    """Look up a dotted `key_path` (e.g. `"anonymise.replace_amounts"`) in `cfg`.

    Raises ConfigError naming `key_path` and `file_path` if any segment of
    the path is absent (Req 2.3).
    """
    current: Any = cfg
    for part in key_path.split("."):
        if isinstance(current, Config):
            value = getattr(current, part, _MISSING)
        elif isinstance(current, dict):
            value = current.get(part, _MISSING)
        else:
            value = _MISSING

        if value is _MISSING:
            raise ConfigError(
                f"Missing required config key '{key_path}' in {file_path}",
                file_path=file_path,
                key_path=key_path,
            )
        current = value
    return current
