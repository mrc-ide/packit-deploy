import pytest

from src.packit_deploy.config import PackitConfig


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

    assert cfg.outpack_demo is True
    assert cfg.outpack_source_url is None
    assert cfg.proxy_enabled is False
    assert cfg.protect_data is False

    assert cfg.packit_db_user == "packituser"
    assert cfg.packit_db_password == "changeme"


def test_config_proxy_disabled():
    options = {"proxy": {"enabled": False}}
    cfg = PackitConfig("config/basic", options=options)
    assert cfg.proxy_enabled is False


def test_config_proxy():
    cfg = PackitConfig("config/basic")
    assert cfg.proxy_enabled
    assert cfg.proxy_ssl_self_signed
    assert "proxy" in cfg.containers
    assert str(cfg.images["proxy"]) == "mrcide/packit-proxy:mrc-4319"
    assert cfg.proxy_hostname == "localhost"
    assert cfg.proxy_port_http == 80
    assert cfg.proxy_port_https == 443

    cfg = PackitConfig("config/complete")
    assert cfg.proxy_enabled
    assert not cfg.proxy_ssl_self_signed
    assert cfg.proxy_ssl_certificate == "cert"
    assert cfg.proxy_ssl_key == "keyval"


def test_outpack_initial_source():
    options = {"outpack": {"initial": {"source": "wrong"}}}
    with pytest.raises(Exception) as err:
        PackitConfig("config/noproxy", options=options)
    assert str(err.value) == "Unknown outpack initial source. Valid values are 'demo' and 'clone'"

    options = {"outpack": {"initial": {"source": "clone", "url": "whatever"}}}
    cfg = PackitConfig("config/noproxy", options=options)
    assert cfg.outpack_demo is False
    assert cfg.outpack_source_url == "whatever"

    cfg = PackitConfig("config/nodemo")
    assert cfg.outpack_demo is False
    assert cfg.outpack_source_url is None
