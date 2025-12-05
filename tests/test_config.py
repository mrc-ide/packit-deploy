import os
from pathlib import Path

from constellation import BuildSpec

from packit_deploy.config import Branding, PackitConfig, Theme

packit_deploy_project_root_dir = os.path.dirname(os.path.dirname(__file__))


def test_config_no_proxy() -> None:
    cfg = PackitConfig("config/noproxy")
    instance = cfg.instances[None]

    assert cfg.network == "packit-network"
    assert cfg.volumes["outpack"] == "outpack_volume"
    assert cfg.container_prefix == "packit"

    assert instance.outpack_server.container_name == "outpack-server"
    assert instance.packit_app.container_name == "packit"
    assert instance.packit_api.container_name == "packit-api"
    assert instance.packit_db.container_name == "packit-db"

    assert str(instance.outpack_server.image) == "ghcr.io/mrc-ide/outpack_server:main"
    assert str(instance.packit_app.image) == "ghcr.io/mrc-ide/packit:main"
    assert str(instance.packit_db.image) == "ghcr.io/mrc-ide/packit-db:main"
    assert str(instance.packit_api.image) == "ghcr.io/mrc-ide/packit-api:main"

    assert cfg.proxy is None
    assert cfg.protect_data is False

    assert instance.packit_db.user == "packituser"
    assert instance.packit_db.password == "changeme"


def test_config_proxy_disabled() -> None:
    options = {"proxy": {"enabled": False}}
    cfg = PackitConfig("config/novault", options=options)
    assert cfg.proxy is None


def test_config_proxy() -> None:
    cfg = PackitConfig("config/novault")

    assert cfg.proxy is not None
    assert cfg.proxy.image == BuildSpec(os.path.join(packit_deploy_project_root_dir, "proxy"))
    assert cfg.proxy.hostname == "localhost"
    assert cfg.proxy.port_http == 80
    assert cfg.proxy.port_https == 443

    cfg = PackitConfig("config/complete")

    assert cfg.proxy is not None


def test_basic_auth() -> None:
    cfg = PackitConfig("config/basicauth")
    instance = cfg.instances[None]

    assert instance.packit_api.auth is not None
    assert instance.packit_api.auth.expiry_days == 1
    assert instance.packit_api.auth.jwt_secret == "0b4g4f8z4mdsrhoxfde2mam8f00vmt0f"
    assert instance.packit_api.auth.method == "basic"


def test_github_auth() -> None:
    cfg = PackitConfig("config/githubauth")
    instance = cfg.instances[None]

    assert instance.packit_api.auth is not None
    assert instance.packit_api.auth.expiry_days == 1
    assert instance.packit_api.auth.jwt_secret == "VAULT:secret/packit/githubauth/auth/jwt:secret"
    assert instance.packit_api.auth.method == "github"

    assert instance.packit_api.auth.github is not None
    assert instance.packit_api.auth.github.org == "mrc-ide"
    assert instance.packit_api.auth.github.team == "packit"
    assert instance.packit_api.auth.github.client_id == "VAULT:secret/packit/githubauth/auth/githubclient:id"
    assert instance.packit_api.auth.github.client_secret == "VAULT:secret/packit/githubauth/auth/githubclient:secret"
    assert instance.packit_api.auth.github.oauth2_redirect_packit_api_root == "https://localhost/api"
    assert instance.packit_api.auth.github.oauth2_redirect_url == "https://localhost/redirect"


def test_custom_branding_with_partial_branding_config() -> None:
    options = {
        "brand": {
            "logo_link": None,
            "logo_alt_text": None,
            "favicon_path": None,
            "css": None,
        }
    }
    cfg = PackitConfig("config/complete", options=options)
    brand = cfg.instances[None].brand

    assert brand == Branding(
        name="My Packit Instance",
        logo=Path(packit_deploy_project_root_dir, "config/complete/examplelogo.webp"),
        logo_link=None,
        logo_alt_text="My Packit Instance logo",
        favicon=None,
        theme_light=None,
        theme_dark=None,
    )
    assert brand.dark_mode_enabled
    assert brand.light_mode_enabled


def test_custom_branding_without_dark_colors() -> None:
    options = {
        "brand": {
            "css": {"dark": None},
        }
    }
    cfg = PackitConfig("config/complete", options=options)
    brand = cfg.instances[None].brand

    assert brand.theme_light == Theme(accent="hsl(0 100% 50%)", foreground="hsl(123 100% 50%)")
    assert brand.theme_dark is None

    assert not brand.dark_mode_enabled
    assert brand.light_mode_enabled


def test_custom_branding_without_light_colors() -> None:
    options = {
        "brand": {
            "css": {"light": None},
        }
    }
    cfg = PackitConfig("config/complete", options=options)
    brand = cfg.instances[None].brand

    assert brand.theme_dark == Theme(accent="hsl(30 100% 50%)", foreground="hsl(322 50% 87%)")
    assert brand.theme_light is None

    assert brand.dark_mode_enabled
    assert not brand.light_mode_enabled


def test_custom_branding_with_complete_branding_config() -> None:
    cfg = PackitConfig("config/complete")
    brand = cfg.instances[None].brand

    assert brand == Branding(
        name="My Packit Instance",
        logo=Path(packit_deploy_project_root_dir, "config/complete/examplelogo.webp"),
        logo_link="https://www.google.com/",
        logo_alt_text="My logo",
        theme_light=Theme(accent="hsl(0 100% 50%)", foreground="hsl(123 100% 50%)"),
        theme_dark=Theme(accent="hsl(30 100% 50%)", foreground="hsl(322 50% 87%)"),
        favicon=Path(packit_deploy_project_root_dir, "config/complete/examplefavicon.ico"),
    )
    assert brand.dark_mode_enabled
    assert brand.light_mode_enabled


def test_management_port() -> None:
    cfg = PackitConfig("config/novault")
    assert cfg.instances[None].packit_api.management_port == 8082


def test_workers_can_be_enabled() -> None:
    cfg = PackitConfig("config/complete")
    assert cfg.orderly_runner is not None
    assert cfg.orderly_runner.worker_count == 1
    assert cfg.orderly_runner.env == {"FOO": "bar"}

    assert str(cfg.orderly_runner.api.image) == "ghcr.io/mrc-ide/orderly.runner:main"
    assert str(cfg.orderly_runner.worker.image) == "ghcr.io/mrc-ide/orderly.runner:main"
    assert str(cfg.orderly_runner.redis.image) == "library/redis:8.0"


def test_workers_can_be_omitted() -> None:
    cfg = PackitConfig("config/noproxy")
    assert cfg.orderly_runner is None


def test_can_use_private_urls_for_git() -> None:
    cfg = PackitConfig("config/runner-private")
    instance = cfg.instances[None]

    assert instance.packit_api.runner_git_url == "git@github.com:reside-ic/orderly2-example-private.git"
    assert instance.packit_api.runner_git_ssh_key == "VAULT:secret/packit/testing/orderly2-example-private:private"


def test_multipackit() -> None:
    cfg = PackitConfig("config/multipackit")
    assert cfg.instances.keys() == {"foo", "bar"}

    # Can have per-instance branding
    assert cfg.instances["foo"].brand.name == "Foo"
    assert cfg.instances["bar"].brand.name == "Bar"

    # Volumes are not shared across instances
    assert cfg.volumes[cfg.instances["foo"].volume_id_outpack] == "foo_outpack_volume"
    assert cfg.volumes[cfg.instances["bar"].volume_id_outpack] == "bar_outpack_volume"
