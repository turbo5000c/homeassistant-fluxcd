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
from collections.abc import Iterable, Sequence

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

# Directories searched when the kubeconfig path is left empty.  The Home
# Assistant config directory is added on top of these at runtime, see
# async_get_search_dirs().
DEFAULT_SEARCH_DIRS: tuple[str, ...] = (
    "~/.kube",
    "~",
    "/config/.kube",
    "/config",
    "/root/.kube",
)


class KubeconfigNotFound(Exception):
    """Raised when no readable kubeconfig file can be located."""


def get_search_dirs(config_dir: str | None = None) -> list[str]:
    """Return the directories to search for a kubeconfig file.

    ``config_dir`` is the Home Assistant configuration directory (``/config``
    on container/OS installs, ``~/.homeassistant`` on core installs).  It is
    searched first, both directly and via a ``.kube`` subdirectory, so a
    kubeconfig placed next to ``configuration.yaml`` is found automatically.
    """
    dirs: list[str] = []
    if config_dir:
        dirs.extend([os.path.join(config_dir, ".kube"), config_dir])
    dirs.extend(DEFAULT_SEARCH_DIRS)

    # Preserve order while dropping duplicates (e.g. a container install where
    # config_dir is already /config).
    seen: set[str] = set()
    unique_dirs: list[str] = []
    for directory in dirs:
        if directory and directory not in seen:
            seen.add(directory)
            unique_dirs.append(directory)
    return unique_dirs


def expand_path(path: str) -> str:
    """Expand ``~`` and environment variables in a user supplied path."""
    return os.path.expanduser(os.path.expandvars(path.strip()))


def _find_in_dir(directory: str) -> str | None:
    """Return the first known kubeconfig file name inside ``directory``."""
    for candidate_dir in (directory, os.path.join(directory, ".kube")):
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


def _env_kubeconfig_entries() -> list[str]:
    """Return the path entries from the KUBECONFIG environment variable."""
    env_value = os.environ.get("KUBECONFIG", "")
    return [entry for entry in env_value.split(os.pathsep) if entry.strip()]


def _candidate_paths(search_dirs: Iterable[str]) -> list[str]:
    """Return every path to probe when no kubeconfig path is configured."""
    candidates = _env_kubeconfig_entries()
    for directory in search_dirs:
        candidates.extend(
            os.path.join(directory, filename) for filename in KUBECONFIG_FILENAMES
        )
    return candidates


def resolve_kubeconfig_path(
    configured_path: str | None = None,
    search_dirs: Sequence[str] | None = None,
) -> str | None:
    """Resolve the kubeconfig location, or return None when there is none.

    When ``configured_path`` is set it is expanded and may point at a file, a
    directory, or an ``os.pathsep`` separated list of either (the same syntax
    the ``KUBECONFIG`` environment variable uses).  Entries that do not exist
    are skipped, matching kubectl behavior.

    When ``configured_path`` is empty the ``KUBECONFIG`` environment variable
    and then ``search_dirs`` are probed for a file named ``config``,
    ``kubeconfig``, ``kubeconfig.yaml``, or ``kubeconfig.yml``.

    This performs blocking file system calls — run it in the executor.
    """
    if configured_path and configured_path.strip():
        resolved: list[str] = []
        for entry in configured_path.split(os.pathsep):
            if not entry.strip():
                continue
            match = resolve_path_entry(entry)
            if match:
                resolved.append(match)
            else:
                _LOGGER.warning(
                    "Configured kubeconfig path does not exist, skipping: %s", entry
                )
        if resolved:
            return os.pathsep.join(resolved)
        return None

    for candidate in _candidate_paths(
        search_dirs if search_dirs is not None else get_search_dirs()
    ):
        match = resolve_path_entry(candidate)
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
