import json
import ssl
import time
import urllib
from unittest import mock

import docker
import vault_dev
from constellation import docker_util

from src.packit_deploy import cli
from src.packit_deploy.config import PackitConfig
from src.packit_deploy.docker_helpers import DockerClient


def test_start_and_stop_noproxy():
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


def test_start_and_stop_proxy():
    path = "config/basic"
    try:
        res = cli.main(["start", path])
        assert res

        cl = docker.client.from_env()
        containers = cl.containers.list()
        assert len(containers) == 5
        assert docker_util.container_exists("packit-proxy")

        # Trivial check that the proxy container works:
        cfg = PackitConfig(path)
        proxy = cfg.get_container("proxy")
        ports = proxy.attrs["HostConfig"]["PortBindings"]
        assert set(ports.keys()) == {"443/tcp", "80/tcp"}
        http_get("http://localhost")
        res = http_get("http://localhost/packit/api/packets", poll=3)
        # might take some seconds for packets to appear
        retries = 1
        while len(json.loads(res)) < 1 and retries < 5:
            res = http_get("http://localhost/packit/api/packets")
            time.sleep(5)
            retries = retries + 1
        assert len(json.loads(res)) > 1
    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


def test_proxy_ssl_configured():
    path = "config/complete"
    try:
        with vault_dev.server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            cl = cfg.vault.client()
            cl.write("secret/cert", value="c3rt")
            cl.write("secret/key", value="s3cret")
            cl.write("secret/db/user", value="us3r")
            cl.write("secret/db/password", value="p@ssword")
            cl.write("secret/ssh", public="publ1c", private="private")

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            proxy = cfg.get_container("proxy")
            cert = docker_util.string_from_container(proxy, "run/proxy/certificate.pem")
            key = docker_util.string_from_container(proxy, "run/proxy/key.pem")
            assert "c3rt" in cert
            assert "s3cret" in key

    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


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


def test_uninitialised_source_repo():
    path = "config/noproxy"
    try:
        cli.main(["start", path, "--option=outpack.initial.url=https://github.com/reside-ic/reside-ic.github.io.git"])
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
        outpack = cfg.get_container("outpack-server")
        config = docker_util.string_from_container(outpack, "/outpack/.outpack/config.json")
        assert config is not None
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
            cl.write("secret/cert", value="c3rt")
            cl.write("secret/key", value="s3cret")
            cl.write("secret/db/user", value="us3r")
            cl.write("secret/db/password", value="p@ssword")
            cl.write("secret/ssh", public="publ1c", private="private")

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            api = cfg.get_container("packit-api")
            api_config = docker_util.string_from_container(api, "/etc/packit/config.properties").split("\n")

            assert "db.user=us3r" in api_config
            assert "db.password=p@ssword" in api_config

    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


def test_ssh():
    path = "config/complete"
    try:
        with vault_dev.server() as s:
            url = f"http://localhost:{s.port}"
            cfg = PackitConfig(path, options={"vault": {"addr": url, "auth": {"args": {"token": s.token}}}})
            cl = cfg.vault.client()
            cl.write("secret/cert", value="c3rt")
            cl.write("secret/key", value="s3cret")
            cl.write("secret/db/user", value="us3r")
            cl.write("secret/db/password", value="p@ssword")
            cl.write("secret/ssh", public="publ1c", private="private")

            cli.main(["start", path, f"--option=vault.addr={url}", f"--option=vault.auth.args.token={s.token}"])

            outpack_server = cfg.get_container("outpack-server")
            pub_key = docker_util.string_from_container(outpack_server, "/root/.ssh/id_rsa.pub")
            assert pub_key == "publ1c"
    finally:
        with mock.patch("src.packit_deploy.cli.prompt_yes_no") as prompt:
            prompt.return_value = True
            cli.main(["stop", path, "--kill", "--volumes", "--network"])


# Because we wait for a go signal to come up, we might not be able to
# make the request right away:
def http_get(url, retries=5, poll=1):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for _i in range(retries):
        try:
            r = urllib.request.urlopen(url, context=ctx)  # noqa: S310
            return r.read().decode("UTF-8")
        except (urllib.error.URLError, ConnectionResetError) as e:
            print("sleeping...")
            time.sleep(poll)
            error = e
    raise error
