"""Kubeconfig discovery helpers for the FluxCD integration.

Home Assistant users store their kubeconfig in a handful of different places
depending on how HA is installed, and they commonly type a path containing
``~`` (for example ``~/.kube/config``).  A bare ``os.path.isfile()`` check
rejects such a path because ``~`` is only meaningful to a shell, so this module
normalizes user input and falls back to searching the usual locations.

Everything here performs blocking file system calls — always run it in the
executor, never on the event loop.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

_LOGGER = logging.getLogger(__name__)

# File names a kubeconfig is commonly saved under.  ``config`` is the kubectl
# default (``~/.kube/config``); the rest cover people who drop the file into
# the Home Assistant config directory as ``kubeconfig``.
KUBECONFIG_FILENAMES: tuple[str, ...] = (
    "config",
    "kubeconfig",
    "kubeconfig.yaml",
    "kubeconfig.yml",
)

# Directories searched when the kubeconfig path is left empty.  Each one is
# probed via its ``.kube`` subdirectory first and then directly, so listing
# ``~`` also covers ``~/.kube``.  The Home Assistant config directory is added
# in front of these at runtime, see get_search_dirs().
DEFAULT_SEARCH_DIRS: tuple[str, ...] = (
    "~",
    "/config",
    "/root",
)


class KubeconfigNotFound(Exception):
    """Raised when no readable kubeconfig file can be located."""


def get_search_dirs(config_dir: str | None = None) -> list[str]:
    """Return the directories to search for a kubeconfig file.

    ``config_dir`` is the Home Assistant configuration directory (``/config``
    on container/OS installs, ``~/.homeassistant`` on core installs).  It is
    searched first so a kubeconfig placed next to ``configuration.yaml`` is
    found automatically.
    """
    dirs: list[str] = [config_dir] if config_dir else []
    dirs.extend(DEFAULT_SEARCH_DIRS)

    # Preserve order while dropping duplicates (e.g. a container install where
    # config_dir is already /config, possibly with a trailing separator).
    seen: set[str] = set()
    unique_dirs: list[str] = []
    for directory in dirs:
        if not directory:
            continue
        key = os.path.normpath(directory)
        if key not in seen:
            seen.add(key)
            unique_dirs.append(directory)
    return unique_dirs


def get_search_dirs_for_hass(hass) -> list[str]:
    """Return the search directories for a Home Assistant instance.

    Only reads attributes, so it is safe to call on the event loop.  Keeping
    this in one place stops the config flow and the API client from disagreeing
    about where a kubeconfig may live.
    """
    config_dir = getattr(getattr(hass, "config", None), "config_dir", None)
    return get_search_dirs(config_dir if isinstance(config_dir, str) else None)


def expand_path(path: str) -> str:
    """Expand ``~`` and environment variables in a user supplied path."""
    return os.path.expanduser(os.path.expandvars(path.strip()))


def _find_in_dir(directory: str) -> str | None:
    """Return the first known kubeconfig file name inside ``directory``.

    A ``.kube`` subdirectory is checked first so the kubectl default
    (``~/.kube/config``) wins over a stray ``~/kubeconfig``.
    """
    for candidate_dir in (os.path.join(directory, ".kube"), directory):
        if not os.path.isdir(candidate_dir):
            continue
        for filename in KUBECONFIG_FILENAMES:
            candidate = os.path.join(candidate_dir, filename)
            if os.path.isfile(candidate):
                return candidate
    return None


def resolve_path_entry(path: str) -> str | None:
    """Resolve a single user supplied path to an existing kubeconfig file.

    Accepts a file path (with ``~``/``$VAR`` expansion) or a directory, in
    which case the directory — and a ``.kube`` subdirectory of it — is searched
    for a known kubeconfig file name.  Returns None when nothing was found.
    """
    expanded = expand_path(path)
    if not expanded:
        return None
    if os.path.isfile(expanded):
        return expanded
    return _find_in_dir(expanded)


def _resolve_path_list(paths: str, *, warn_missing: bool) -> str | None:
    """Resolve an ``os.pathsep`` separated list to the entries that exist.

    Missing entries are skipped rather than failing the whole list, which is
    how kubectl treats ``KUBECONFIG``.  Returns the surviving entries joined
    back together so they are merged downstream, or None if none exist.
    """
    resolved: list[str] = []
    for entry in paths.split(os.pathsep):
        if not entry.strip():
            continue
        match = resolve_path_entry(entry)
        if match:
            resolved.append(match)
        elif warn_missing:
            _LOGGER.warning(
                "Configured kubeconfig path does not exist, skipping: %s", entry
            )
        else:
            _LOGGER.debug("Kubeconfig path does not exist, skipping: %s", entry)
    return os.pathsep.join(resolved) if resolved else None


def resolve_kubeconfig_path(
    configured_path: str | None = None,
    search_dirs: Sequence[str] | None = None,
) -> str | None:
    """Resolve the kubeconfig location, or return None when there is none.

    When ``configured_path`` is set it is expanded and may point at a file, a
    directory, or an ``os.pathsep`` separated list of either (the same syntax
    the ``KUBECONFIG`` environment variable uses).

    When ``configured_path`` is empty the ``KUBECONFIG`` environment variable
    is used if it names any existing file — all of its entries, so a split
    cluster/credentials setup still merges — and otherwise ``search_dirs`` are
    probed for a file named ``config``, ``kubeconfig``, ``kubeconfig.yaml``, or
    ``kubeconfig.yml``.

    This performs blocking file system calls — run it in the executor.
    """
    if configured_path and configured_path.strip():
        return _resolve_path_list(configured_path, warn_missing=True)

    from_env = _resolve_path_list(
        os.environ.get("KUBECONFIG", ""), warn_missing=False
    )
    if from_env:
        _LOGGER.debug("Using kubeconfig from the KUBECONFIG variable: %s", from_env)
        return from_env

    for directory in search_dirs if search_dirs is not None else get_search_dirs():
        match = _find_in_dir(expand_path(directory))
        if match:
            _LOGGER.debug("Using auto-discovered kubeconfig file: %s", match)
            return match

    return None


def require_kubeconfig_path(
    configured_path: str | None = None,
    search_dirs: Sequence[str] | None = None,
) -> str:
    """Resolve the kubeconfig location or raise KubeconfigNotFound.

    This performs blocking file system calls — run it in the executor.
    """
    resolved = resolve_kubeconfig_path(configured_path, search_dirs)
    if resolved:
        return resolved

    if configured_path and configured_path.strip():
        raise KubeconfigNotFound(
            f"No kubeconfig file found at '{configured_path}'. Enter the full path "
            "to the file (for example /config/kubeconfig) or leave the field empty "
            "to search the default locations."
        )
    searched = search_dirs if search_dirs is not None else get_search_dirs()
    raise KubeconfigNotFound(
        "No kubeconfig file found. Searched the KUBECONFIG environment variable "
        f"and these directories: {', '.join(searched)}. Copy your kubeconfig to "
        "one of them or enter its full path."
    )
