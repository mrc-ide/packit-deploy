import os
from pathlib import Path

from packit_deploy.config import Branding, PackitConfig, Theme

packit_deploy_project_root_dir = os.path.dirname(os.path.dirname(__file__))


def test_config_no_proxy():
    cfg = PackitConfig("config/noproxy")
    assert cfg.network == "packit-network"
    assert cfg.volumes["outpack"] == "outpack_volume"
    assert cfg.container_prefix == "packit"

    assert len(cfg.containers) == 4
    assert cfg.containers["outpack-server"] == "outpack-server"
    assert cfg.containers["packit"] == "packit"
    assert cfg.containers["packit-api"] == "packit-api"
    assert cfg.containers["packit-db"] == "packit-db"

    assert str(cfg.outpack_ref) == "ghcr.io/mrc-ide/outpack_server:main"
    assert str(cfg.packit_ref) == "ghcr.io/mrc-ide/packit:main"
    assert str(cfg.packit_db.image) == "ghcr.io/mrc-ide/packit-db:main"
    assert str(cfg.packit_api.image) == "ghcr.io/mrc-ide/packit-api:main"

    assert cfg.proxy is None
    assert cfg.protect_data is False

    assert cfg.packit_db.user == "packituser"
    assert cfg.packit_db.password == "changeme"


def test_config_proxy_disabled():
    options = {"proxy": {"enabled": False}}
    cfg = PackitConfig("config/novault", options=options)
    assert cfg.proxy is None


def test_config_proxy():
    cfg = PackitConfig("config/novault")
    assert cfg.proxy is not None
    assert "proxy" in cfg.containers
    assert str(cfg.proxy.image) == "ghcr.io/mrc-ide/packit-proxy:main"
    assert cfg.proxy.hostname == "localhost"
    assert cfg.proxy.port_http == 80
    assert cfg.proxy.port_https == 443

    cfg = PackitConfig("config/complete")
    assert cfg.proxy is not None


def test_basic_auth():
    cfg = PackitConfig("config/basicauth")
    assert cfg.packit_api.auth is not None
    assert cfg.packit_api.auth.expiry_days == 1
    assert cfg.packit_api.auth.jwt_secret == "0b4g4f8z4mdsrhoxfde2mam8f00vmt0f"
    assert cfg.packit_api.auth.method == "basic"


def test_github_auth():
    cfg = PackitConfig("config/githubauth")
    assert cfg.packit_api.auth is not None
    assert cfg.packit_api.auth.expiry_days == 1
    assert cfg.packit_api.auth.jwt_secret == "VAULT:secret/packit/githubauth/auth/jwt:secret"
    assert cfg.packit_api.auth.method == "github"

    assert cfg.packit_api.auth.github is not None
    assert cfg.packit_api.auth.github.org == "mrc-ide"
    assert cfg.packit_api.auth.github.team == "packit"
    assert cfg.packit_api.auth.github.client_id == "VAULT:secret/packit/githubauth/auth/githubclient:id"
    assert cfg.packit_api.auth.github.client_secret == "VAULT:secret/packit/githubauth/auth/githubclient:secret"
    assert cfg.packit_api.auth.github.oauth2_redirect_packit_api_root == "https://localhost/api"
    assert cfg.packit_api.auth.github.oauth2_redirect_url == "https://localhost/redirect"


def test_custom_branding_with_partial_branding_config():
    options = {
        "brand": {
            "logo_link": None,
            "logo_alt_text": None,
            "favicon_path": None,
            "css": None,
        }
    }
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.brand == Branding(
        name="My Packit Instance",
        logo=Path(packit_deploy_project_root_dir, "config/complete/examplelogo.webp"),
        logo_link=None,
        logo_alt_text="My Packit Instance logo",
        favicon=None,
        theme_light=None,
        theme_dark=None,
    )
    assert cfg.brand.dark_mode_enabled
    assert cfg.brand.light_mode_enabled


def test_custom_branding_without_dark_colors():
    options = {
        "brand": {
            "css": {"dark": None},
        }
    }
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.brand.theme_light == Theme(accent="hsl(0 100% 50%)", foreground="hsl(123 100% 50%)")
    assert cfg.brand.theme_dark is None

    assert not cfg.brand.dark_mode_enabled
    assert cfg.brand.light_mode_enabled


def test_custom_branding_without_light_colors():
    options = {
        "brand": {
            "css": {"light": None},
        }
    }
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.brand.theme_dark == Theme(accent="hsl(30 100% 50%)", foreground="hsl(322 50% 87%)")
    assert cfg.brand.theme_light is None

    assert cfg.brand.dark_mode_enabled
    assert not cfg.brand.light_mode_enabled


def test_custom_branding_with_complete_branding_config():
    cfg = PackitConfig("config/complete")
    assert cfg.brand == Branding(
        name="My Packit Instance",
        logo=Path(packit_deploy_project_root_dir, "config/complete/examplelogo.webp"),
        logo_link="https://www.google.com/",
        logo_alt_text="My logo",
        theme_light=Theme(accent="hsl(0 100% 50%)", foreground="hsl(123 100% 50%)"),
        theme_dark=Theme(accent="hsl(30 100% 50%)", foreground="hsl(322 50% 87%)"),
        favicon=Path(packit_deploy_project_root_dir, "config/complete/examplefavicon.ico"),
    )
    assert cfg.brand.dark_mode_enabled
    assert cfg.brand.light_mode_enabled


def test_management_port():
    cfg = PackitConfig("config/novault")
    assert cfg.packit_api.management_port == 8082


def test_workers_can_be_enabled():
    cfg = PackitConfig("config/complete")
    assert cfg.orderly_runner is not None
    assert cfg.orderly_runner.image.repo == "ghcr.io/mrc-ide"
    assert cfg.orderly_runner.image.name == "orderly.runner"
    assert cfg.orderly_runner.image.tag == "main"
    assert cfg.orderly_runner.workers == 1
    assert cfg.orderly_runner.env == {"FOO": "bar"}

    assert str(cfg.orderly_runner.image) == "ghcr.io/mrc-ide/orderly.runner:main"
    assert str(cfg.redis_image) == "library/redis:8.0"


def test_workers_can_be_omitted():
    cfg = PackitConfig("config/noproxy")
    assert cfg.orderly_runner is None


def test_can_use_private_urls_for_git():
    cfg = PackitConfig("config/runner-private")
    assert cfg.packit_api.runner_git_url == "git@github.com:reside-ic/orderly2-example-private.git"
    assert cfg.packit_api.runner_git_ssh_key == "VAULT:secret/packit/testing/orderly2-example-private:private"
