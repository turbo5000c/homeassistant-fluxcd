"""Tests for kubeconfig path resolution and discovery."""

from __future__ import annotations

import os

import pytest
from fluxcd_k8s.kubeconfig import (
    DEFAULT_SEARCH_DIRS,
    KubeconfigNotFound,
    expand_path,
    get_search_dirs,
    require_kubeconfig_path,
    resolve_kubeconfig_path,
    resolve_path_entry,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep the host's real kubeconfig out of every test."""
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()


def _write_kubeconfig(path):
    """Create a placeholder kubeconfig file at path (parents included)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("apiVersion: v1\nkind: Config\n")
    return str(path)


class TestExpandPath:
    def test_expands_home_shortcut(self, tmp_path):
        assert expand_path("~/.kube/config") == str(tmp_path / "home" / ".kube" / "config")

    def test_expands_environment_variable(self, monkeypatch):
        monkeypatch.setenv("MY_KUBE_DIR", "/opt/kube")
        assert expand_path("$MY_KUBE_DIR/config") == "/opt/kube/config"

    def test_strips_surrounding_whitespace(self):
        assert expand_path("  /config/kubeconfig  ") == "/config/kubeconfig"


class TestResolvePathEntry:
    def test_resolves_tilde_path_to_real_file(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_path_entry("~/.kube/config") == expected

    def test_resolves_directory_to_contained_config(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_path_entry(str(tmp_path / "home" / ".kube")) == expected

    def test_resolves_directory_to_contained_kubeconfig(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "kubeconfig")
        assert resolve_path_entry(str(tmp_path)) == expected

    def test_resolves_directory_via_dot_kube_subdirectory(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / ".kube" / "config")
        assert resolve_path_entry(str(tmp_path)) == expected

    def test_returns_none_for_missing_path(self, tmp_path):
        assert resolve_path_entry(str(tmp_path / "missing")) is None

    def test_returns_none_for_empty_path(self):
        assert resolve_path_entry("   ") is None


class TestResolveKubeconfigPath:
    def test_configured_file_wins(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "custom" / "my-kubeconfig")
        assert resolve_kubeconfig_path(expected, [str(tmp_path)]) == expected

    def test_configured_tilde_path_is_expanded(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_kubeconfig_path("~/.kube/config", []) == expected

    def test_missing_configured_path_returns_none(self, tmp_path):
        assert resolve_kubeconfig_path(str(tmp_path / "nope"), []) is None

    def test_multiple_configured_paths_are_joined(self, tmp_path):
        first = _write_kubeconfig(tmp_path / "a" / "kubeconfig")
        second = _write_kubeconfig(tmp_path / "b" / "kubeconfig")
        combined = os.pathsep.join([first, second])
        assert resolve_kubeconfig_path(combined, []) == combined

    def test_missing_entry_in_list_is_skipped(self, tmp_path):
        existing = _write_kubeconfig(tmp_path / "a" / "kubeconfig")
        combined = os.pathsep.join([str(tmp_path / "gone"), existing])
        assert resolve_kubeconfig_path(combined, []) == existing

    def test_empty_path_finds_home_kube_config(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_kubeconfig_path("", get_search_dirs()) == expected

    def test_empty_path_finds_config_dir_kubeconfig(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "ha-config" / "kubeconfig")
        search_dirs = get_search_dirs(str(tmp_path / "ha-config"))
        assert resolve_kubeconfig_path("", search_dirs) == expected

    def test_empty_path_finds_config_dir_dot_kube_config(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "ha-config" / ".kube" / "config")
        search_dirs = get_search_dirs(str(tmp_path / "ha-config"))
        assert resolve_kubeconfig_path("", search_dirs) == expected

    def test_empty_path_honors_kubeconfig_env_var(self, tmp_path, monkeypatch):
        expected = _write_kubeconfig(tmp_path / "env" / "kubeconfig")
        monkeypatch.setenv("KUBECONFIG", expected)
        # A home kubeconfig also exists; KUBECONFIG must take precedence.
        _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_kubeconfig_path("", get_search_dirs()) == expected

    def test_returns_none_when_nothing_exists(self, tmp_path):
        assert resolve_kubeconfig_path("", [str(tmp_path / "nowhere")]) is None


class TestGetSearchDirs:
    def test_config_dir_is_searched_first(self):
        dirs = get_search_dirs("/config")
        assert dirs[0] == os.path.join("/config", ".kube")
        assert dirs[1] == "/config"

    def test_defaults_are_included(self):
        dirs = get_search_dirs("/config")
        for default_dir in DEFAULT_SEARCH_DIRS:
            assert default_dir in dirs

    def test_duplicates_are_removed(self):
        dirs = get_search_dirs("/config")
        assert len(dirs) == len(set(dirs))

    def test_without_config_dir_returns_defaults(self):
        assert get_search_dirs() == list(DEFAULT_SEARCH_DIRS)


class TestRequireKubeconfigPath:
    def test_returns_resolved_path(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert require_kubeconfig_path("~/.kube/config", []) == expected

    def test_error_mentions_the_configured_path(self, tmp_path):
        missing = str(tmp_path / "nope" / "kubeconfig")
        with pytest.raises(KubeconfigNotFound, match="nope"):
            require_kubeconfig_path(missing, [])

    def test_error_lists_searched_directories(self, tmp_path):
        with pytest.raises(KubeconfigNotFound, match="/config"):
            require_kubeconfig_path("", ["/config", "~/.kube"])
