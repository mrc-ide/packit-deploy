from unittest import mock

import docker
import pytest
import vault_dev
from constellation import docker_util

from src.packit_deploy import cli
from src.packit_deploy.config import PackitConfig
from src.packit_deploy.docker_helpers import DockerClient


def test_start_and_stop():
    path = "config/noproxy"
    try:
        # Start
        res = cli.main(["start", path, "--pull"])
        assert res

        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 4
        cfg = PackitConfig(path)
        assert docker_util.network_exists(cfg.network)
        assert docker_util.volume_exists(cfg.volumes["outpack"])
        assert docker_util.container_exists("packit-outpack-server")
        assert docker_util.container_exists("packit-packit-api")
        assert docker_util.container_exists("packit-packit-db")
        assert docker_util.container_exists("packit-packit")

        # Stop
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])
            containers = cl.containers.list()
            assert len(containers) == 0
            assert not docker_util.network_exists(cfg.network)
            assert not docker_util.volume_exists(cfg.volumes["outpack"])
            assert not docker_util.container_exists("packit-packit-api")
            assert not docker_util.container_exists("packit-packit-db")
            assert not docker_util.container_exists("packit-packit")
            assert not docker_util.container_exists("packit-outpack-server")
    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


def test_status():
    res = cli.main(["status", "config/noproxy"])
    assert res


def test_proxy_not_allowed():
    with pytest.raises(Exception) as err:
        cli.main(["start", "config/basic", "--option=proxy.enabled=true"])
    assert str(err.value) == "Proxy not yet supported. Ignoring proxy configuration."


def test_api_configured():
    path = "config/noproxy"
    try:
        cli.main(["start", path, "--pull"])
        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 4
        cfg = PackitConfig(path)

        api = cfg.get_container("packit-api")
        api_config = docker_util.string_from_container(api, "/etc/packit/config.properties").split("\n")

        assert "db.url=jdbc:postgresql://packit-packit-db:5432/packit?stringtype=unspecified" in api_config
        assert "db.user=packituser" in api_config
        assert "db.password=changeme" in api_config
        assert "outpack.server.url=http://packit-outpack-server:8000" in api_config

    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


def test_outpack_cloning_unsupported():
    path = "config/noproxy"
    try:
        with pytest.raises(Exception) as err:
            cli.main(["start", path, "--option=outpack.initial.url=whatever", "--option=outpack.initial.source=clone"])
        assert str(err.value) == "Outpack source cloning not yet supported. Setup outpack volume manually or use demo."
    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


def test_outpack_already_initialised():
    path = "config/noproxy"
    outpack_vol = docker.types.Mount("/outpack", "outpack_volume")
    with DockerClient() as cl:
        cl.containers.run("ubuntu", remove=True, mounts=[outpack_vol], command=["mkdir", "/outpack/.outpack"])
        cl.containers.run(
            "ubuntu", remove=True, mounts=[outpack_vol], command=["touch", "/outpack/.outpack/config.json"]
        )
        cl.containers.run("ubuntu", remove=True, mounts=[outpack_vol], command=["mkdir", "/outpack/.outpack/test.txt"])
    try:
        cli.main(["start", path])
    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


def test_vault():
    path = "config/complete"
    try:
        with vault_dev.server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            cl = cfg.vault.client()
            cl.write("secret/db/user", value="us3r")
            cl.write("secret/db/password", value="p@ssword")

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            api = cfg.get_container("packit-api")
            api_config = docker_util.string_from_container(api, "/etc/packit/config.properties").split("\n")

            assert "db.user=us3r" in api_config
            assert "db.password=p@ssword" in api_config

    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])
