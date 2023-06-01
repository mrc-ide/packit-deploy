import json
import ssl
import urllib
from datetime import time
from unittest import mock

import docker
from constellation import docker_util

from src.packit_deploy import cli
from src.packit_deploy.config import PackitConfig


def test_start_and_stop():
    path = "config/noproxy"
    try:
        res = cli.main(["start", path, "--pull"])
        assert res

        cl = docker.client.from_env()
        containers = cl.containers.list()
        print(containers)
        assert len(containers) == 4
        cfg = PackitConfig(path)
        assert docker_util.network_exists(cfg.network)
        assert docker_util.volume_exists(cfg.volumes["outpack"])
        assert docker_util.container_exists("packit-outpack-server")
        assert docker_util.container_exists("packit-packit-api")
        assert docker_util.container_exists("packit-packit-db")
        assert docker_util.container_exists("packit-packit")

        api = cfg.get_container("packit-api")
        api_config = docker_util.string_from_container(api, "/etc/packit/config.properties").split("\n")

        assert "outpack.server=http://orderly-web-orderly:8321" in api_config

        # Trivial check that the proxy container works too:
        proxy = cfg.get_container("proxy")
        ports = proxy.attrs["HostConfig"]["PortBindings"]
        assert set(ports.keys()) == {"443/tcp", "80/tcp"}
        dat = json.loads(http_get("http://localhost/api/"))
        assert dat["status"] == "success"
        dat = json.loads(http_get("https://localhost/api/"))
        assert dat["status"] == "success"

        # Bring the whole lot down:
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


# Because we wait for a go signal to come up, we might not be able to
# make the request right away:
def http_get(url, retries=5, poll=0.5):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for _i in range(retries):
        try:
            r = urllib.request.urlopen(url, context=ctx)
            return r.read().decode("UTF-8")
        except (urllib.error.URLError, ConnectionResetError) as e:
            print("sleeping...")
            time.sleep(poll)
            error = e
    raise error
