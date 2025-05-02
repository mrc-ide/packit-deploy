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

    assert cfg.outpack_source_url is not None
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


def test_outpack_initial_source():
    cfg = PackitConfig("config/complete")
    assert cfg.outpack_source_url == "https://github.com/reside-ic/orderly3-example.git"

    cfg = PackitConfig("config/nodemo")
    assert cfg.outpack_source_url is None


def test_ssh():
    cfg = PackitConfig("config/complete")
    assert cfg.ssh_public == "VAULT:secret/ssh:public"
    assert cfg.ssh_private == "VAULT:secret/ssh:private"
    assert cfg.ssh

    cfg = PackitConfig("config/novault")
    assert not cfg.ssh


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


def test_custom_branding_without_optional_branding_config():
    options = {
        "brand": {
            "logo_link": None,
            "logo_alt_text": None,
            "favicon_path": None,
        }
    }
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.branding_enabled is True
    assert cfg.brand_name == "My Packit Instance"
    assert cfg.brand_logo_path == os.path.abspath(
        os.path.join(packit_deploy_project_root_dir, "config/complete/examplelogo.webp")
    )
    assert cfg.brand_logo_name == "examplelogo.webp"
    with unittest.TestCase().assertRaises(AttributeError):
        _ = cfg.brand_logo_link
    with unittest.TestCase().assertRaises(AttributeError):
        _ = cfg.brand_logo_alt_text
    with unittest.TestCase().assertRaises(AttributeError):
        _ = cfg.brand_favicon_path
    with unittest.TestCase().assertRaises(AttributeError):
        _ = cfg.brand_favicon_name


def test_custom_branding_with_optional_branding_config():
    cfg = PackitConfig("config/complete")

    assert cfg.branding_enabled is True
    assert cfg.brand_logo_alt_text == "My logo"
    assert cfg.brand_logo_link == "https://www.google.com/"
    assert cfg.brand_favicon_path == os.path.abspath(
        os.path.join(packit_deploy_project_root_dir, "config/complete/favicon.ico")
    )
    assert cfg.brand_favicon_name == "favicon.ico"


def test_custom_branding_requires_proxy():
    options = {"proxy": {"enabled": False}}
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.branding_enabled is False


def test_custom_branding_requires_brand_name():
    options = {"brand": {"name": None}}
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.branding_enabled is False


def test_custom_branding_requires_logo():
    options = {"brand": {"logo_path": None}}
    cfg = PackitConfig("config/complete", options=options)

    assert cfg.branding_enabled is False
