import pytest
from constellation import docker_util

from packit_deploy.docker_helpers import DockerClient, write_to_container


@pytest.mark.parametrize("mode", [0o644, 0o666, 0o755])
def test_write_to_container(mode):
    docker_util.ensure_image("alpine", "alpine:latest")
    with DockerClient() as cl:
        container = cl.containers.create("alpine:latest", ["stat", "-c", "%a %U", "/hello.txt"])
        try:
            write_to_container(b"Hello", container, "/hello.txt", mode=mode)
            container.start()
            container.wait()
            actual_mode, owner = container.logs().splitlines()[0].split()
            assert int(actual_mode, base=8) == mode
            assert owner == b"root"
        finally:
            container.remove()
