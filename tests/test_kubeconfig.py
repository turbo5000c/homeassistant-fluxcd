"""Tests for kubeconfig path resolution and discovery."""

from __future__ import annotations

import os
import types

import pytest
from fluxcd_k8s import kubeconfig as kc
from fluxcd_k8s.kubeconfig import (
    KubeconfigNotFound,
    expand_path,
    get_search_dirs,
    get_search_dirs_for_hass,
    require_kubeconfig_path,
    resolve_kubeconfig_path,
    resolve_path_entry,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep the host's real kubeconfig out of every test.

    DEFAULT_SEARCH_DIRS holds absolute paths (/config, /root) that exist on the
    machines this integration targets, so it is redirected at the temporary
    home as well — otherwise a host kubeconfig would decide the result.
    """
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setattr(kc, "DEFAULT_SEARCH_DIRS", ("~",))


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

    def test_kubeconfig_env_var_keeps_every_existing_entry(
        self, tmp_path, monkeypatch
    ):
        """A split cluster/credentials KUBECONFIG must still be merged."""
        first = _write_kubeconfig(tmp_path / "env" / "cluster.yaml")
        second = _write_kubeconfig(tmp_path / "env" / "user.yaml")
        monkeypatch.setenv("KUBECONFIG", os.pathsep.join([first, second]))
        assert resolve_kubeconfig_path("", get_search_dirs()) == os.pathsep.join(
            [first, second]
        )

    def test_kubeconfig_env_var_skips_missing_entries(self, tmp_path, monkeypatch):
        existing = _write_kubeconfig(tmp_path / "env" / "cluster.yaml")
        monkeypatch.setenv(
            "KUBECONFIG", os.pathsep.join([str(tmp_path / "gone.yaml"), existing])
        )
        assert resolve_kubeconfig_path("", get_search_dirs()) == existing

    def test_empty_kubeconfig_env_var_falls_back_to_search_dirs(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("KUBECONFIG", str(tmp_path / "does-not-exist"))
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_kubeconfig_path("", get_search_dirs()) == expected

    def test_directory_named_config_does_not_shadow_a_real_file(self, tmp_path):
        """A `config/` directory must not outrank a `kubeconfig` file beside it."""
        _write_kubeconfig(tmp_path / "search" / "config" / "kubeconfig")
        expected = _write_kubeconfig(tmp_path / "search" / "kubeconfig")
        assert resolve_kubeconfig_path("", [str(tmp_path / "search")]) == expected

    def test_dot_kube_wins_over_a_loose_file_in_the_same_dir(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "search" / ".kube" / "config")
        _write_kubeconfig(tmp_path / "search" / "kubeconfig")
        assert resolve_kubeconfig_path("", [str(tmp_path / "search")]) == expected

    def test_search_dirs_are_expanded(self, tmp_path):
        expected = _write_kubeconfig(tmp_path / "home" / ".kube" / "config")
        assert resolve_kubeconfig_path("", ["~"]) == expected

    def test_returns_none_when_nothing_exists(self, tmp_path):
        assert resolve_kubeconfig_path("", [str(tmp_path / "nowhere")]) is None


class TestGetSearchDirs:
    def test_config_dir_is_searched_first(self):
        assert get_search_dirs("/config")[0] == "/config"

    def test_defaults_are_included(self):
        dirs = get_search_dirs("/somewhere/else")
        for default_dir in kc.DEFAULT_SEARCH_DIRS:
            assert default_dir in dirs

    def test_duplicates_are_removed(self, monkeypatch):
        monkeypatch.setattr(kc, "DEFAULT_SEARCH_DIRS", ("~", "/config", "/root"))
        assert get_search_dirs("/config/") == ["/config/", "~", "/root"]

    def test_without_config_dir_returns_defaults(self):
        assert get_search_dirs() == list(kc.DEFAULT_SEARCH_DIRS)


class TestGetSearchDirsForHass:
    def test_uses_the_home_assistant_config_dir(self):
        hass = types.SimpleNamespace(config=types.SimpleNamespace(config_dir="/ha"))
        assert get_search_dirs_for_hass(hass)[0] == "/ha"

    def test_ignores_a_non_string_config_dir(self):
        hass = types.SimpleNamespace(config=types.SimpleNamespace(config_dir=object()))
        assert get_search_dirs_for_hass(hass) == list(kc.DEFAULT_SEARCH_DIRS)

    def test_tolerates_a_hass_without_config(self):
        assert get_search_dirs_for_hass(object()) == list(kc.DEFAULT_SEARCH_DIRS)


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

    def test_missing_tilde_path_shows_what_it_expanded_to(self, tmp_path):
        """The error must reveal the resolved path, not just echo the raw input.

        This is what makes 'doesn't work on HA OS' self-diagnosable: on HA OS,
        Supervised, and Container installs '~' silently resolves to a path
        inside the Home Assistant container (typically /root) rather than
        anywhere reachable by Samba/SSH/File Editor, so the raw path alone
        gives no clue why it failed.
        """
        with pytest.raises(KubeconfigNotFound) as exc_info:
            require_kubeconfig_path("~/.kube/config", [])

        message = str(exc_info.value)
        assert "~/.kube/config" in message
        assert os.path.expanduser("~/.kube/config") in message
        assert "resolved to" in message

    def test_missing_tilde_path_names_the_container_reachability_gotcha(self):
        with pytest.raises(KubeconfigNotFound, match="Home Assistant container"):
            require_kubeconfig_path("~/.kube/config", [])
        with pytest.raises(KubeconfigNotFound, match="/config/kubeconfig"):
            require_kubeconfig_path("~/.kube/config", [])

    def test_missing_absolute_path_has_no_tilde_specific_guidance(self, tmp_path):
        """A plain missing absolute path is a typo, not the HA-OS container gotcha."""
        missing = str(tmp_path / "typo" / "kubeconfig")
        with pytest.raises(KubeconfigNotFound) as exc_info:
            require_kubeconfig_path(missing, [])

        message = str(exc_info.value)
        assert "Home Assistant container" not in message
        assert "resolved to" not in message  # nothing to expand, so nothing to show
        assert "Enter the full path" in message

    def test_missing_env_var_path_expands_without_tilde_guidance(
        self, tmp_path, monkeypatch
    ):
        """$VAR expansion should be shown, but isn't the '~' container gotcha."""
        monkeypatch.setenv("MY_KUBE_DIR", str(tmp_path / "opt"))
        with pytest.raises(KubeconfigNotFound) as exc_info:
            require_kubeconfig_path("$MY_KUBE_DIR/kubeconfig", [])

        message = str(exc_info.value)
        assert str(tmp_path / "opt" / "kubeconfig") in message
        assert "resolved to" in message
        assert "Home Assistant container" not in message
