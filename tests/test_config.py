import os
import unittest

from src.packit_deploy.config import PackitConfig

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

    assert len(cfg.images) == 4
    assert str(cfg.images["outpack-server"]) == "mrcide/outpack_server:main"
    assert str(cfg.images["packit"]) == "mrcide/packit:main"
    assert str(cfg.images["packit-db"]) == "mrcide/packit-db:main"
    assert str(cfg.images["packit-api"]) == "mrcide/packit-api:main"

    assert cfg.proxy_enabled is False
    assert cfg.protect_data is False

    assert cfg.packit_db_user == "packituser"
    assert cfg.packit_db_password == "changeme"


def test_config_proxy_disabled():
    options = {"proxy": {"enabled": False}}
    cfg = PackitConfig("config/novault", options=options)
    assert cfg.proxy_enabled is False


def test_config_proxy():
    cfg = PackitConfig("config/novault")
    assert cfg.proxy_enabled
    assert cfg.proxy_ssl_self_signed
    assert "proxy" in cfg.containers
    assert str(cfg.images["proxy"]) == "mrcide/packit-proxy:main"
    assert cfg.proxy_hostname == "localhost"
    assert cfg.proxy_port_http == 80
    assert cfg.proxy_port_https == 443

    cfg = PackitConfig("config/complete")
    assert cfg.proxy_enabled
    assert not cfg.proxy_ssl_self_signed
    assert cfg.proxy_ssl_certificate == "VAULT:secret/cert:value"
    assert cfg.proxy_ssl_key == "VAULT:secret/key:value"


def test_github_auth():
    cfg = PackitConfig("config/githubauth")
    assert cfg.packit_auth_enabled is True
    assert cfg.packit_auth_method == "github"
    assert cfg.packit_auth_expiry_days == 1
    assert cfg.packit_auth_github_api_org == "mrc-ide"
    assert cfg.packit_auth_github_api_team == "packit"
    assert cfg.packit_auth_github_client_id == "VAULT:secret/packit/githubauth/auth/githubclient:id"
    assert cfg.packit_auth_github_client_secret == "VAULT:secret/packit/githubauth/auth/githubclient:secret"
    assert cfg.packit_auth_jwt_secret == "VAULT:secret/packit/githubauth/auth/jwt:secret"
    assert cfg.packit_auth_oauth2_redirect_packit_api_root == "https://localhost/api"
    assert cfg.packit_auth_oauth2_redirect_url == "https://localhost/redirect"


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

    assert cfg.brand_name == "My Packit Instance"
    assert cfg.brand_logo_alt_text == "My Packit Instance logo"
    assert cfg.brand_logo_path == os.path.abspath(
        os.path.join(packit_deploy_project_root_dir, "config/complete/examplelogo.webp")
    )
    assert cfg.brand_logo_name == "examplelogo.webp"
    undefined_attributes = [
        "brand_logo_link",
        "brand_favicon_path",
        "brand_accent_light",
        "brand_accent_foreground_light",
        "brand_accent_dark",
        "brand_accent_foreground_dark",
    ]
    for attr in undefined_attributes:
        with unittest.TestCase().assertRaises(AttributeError):
            _ = getattr(cfg, attr)


def test_custom_branding_unprovided_dark_colors_fall_back_to_light_colors():
    options = {
        "brand": {
            "css": {"dark": None},
        }
    }
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.brand_accent_light == "hsl(0 100% 50%)"
    assert cfg.brand_accent_foreground_light == "hsl(123 100% 50%)"
    assert cfg.brand_accent_dark == cfg.brand_accent_light
    assert cfg.brand_accent_foreground_dark == cfg.brand_accent_foreground_light


def test_custom_branding_with_complete_branding_config():
    cfg = PackitConfig("config/complete")

    assert cfg.brand_logo_alt_text == "My logo"
    assert cfg.brand_logo_link == "https://www.google.com/"
    assert cfg.brand_favicon_path == os.path.abspath(
        os.path.join(packit_deploy_project_root_dir, "config/complete/examplefavicon.ico")
    )
    assert cfg.brand_favicon_name == "examplefavicon.ico"
    assert cfg.brand_accent_light == "hsl(0 100% 50%)"
    assert cfg.brand_accent_foreground_light == "hsl(123 100% 50%)"
    assert cfg.brand_accent_dark == "hsl(30 100% 50%)"
    assert cfg.brand_accent_foreground_dark == "hsl(322, 50%, 87%)"


def test_workers_can_be_enabled():
    cfg = PackitConfig("config/complete")
    assert cfg.images

    assert cfg.orderly_runner_enabled
    assert cfg.orderly_runner_ref.repo == "mrcide"
    assert cfg.orderly_runner_ref.name == "orderly.runner"
    assert cfg.orderly_runner_ref.tag == "main"
    assert cfg.orderly_runner_workers == 1

    assert len(cfg.images) == 7
    assert str(cfg.images["orderly-runner"]) == "mrcide/orderly.runner:main"
    assert str(cfg.images["redis"]) == "library/redis:8.0"

    assert cfg.orderly_runner_env == {"FOO": "bar"}


def test_workers_can_be_omitted():
    cfg = PackitConfig("config/noproxy")
    assert not cfg.orderly_runner_enabled


def test_can_use_private_urls_for_git():
    cfg = PackitConfig("config/runner-private")
    assert cfg.orderly_runner_git_url == "git@github.com:reside-ic/orderly2-example-private.git"
    assert type(cfg.orderly_runner_git_ssh_key) is str
