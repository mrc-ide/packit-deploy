import constellation
import docker
from constellation import docker_util

from packit_deploy.docker_helpers import DockerClient


class PackitConstellation:
    def __init__(self, cfg):
        outpack = outpack_server_container(cfg)
        packit_db = packit_db_container(cfg)
        packit_api = packit_api_container(cfg)
        packit = packit_container(cfg)

        containers = [outpack, packit_db, packit_api, packit]

        if cfg.proxy_enabled:
            err = "Proxy not yet supported. Ignoring proxy configuration."
            raise Exception(err)

        self.cfg = cfg
        self.obj = constellation.Constellation(
            "packit", cfg.container_prefix, containers, cfg.network, cfg.volumes, data=cfg
        )

    def start(self, **kwargs):
        if self.cfg.outpack_source_url is not None:
            msg = "Outpack source cloning not yet supported. Setup outpack volume manually or use demo."
            raise Exception(msg)
        if self.cfg.outpack_demo:
            outpack_init(self.cfg)
        self.obj.start(**kwargs)

    def stop(self, **kwargs):
        self.obj.stop(**kwargs)

    def status(self):
        self.obj.status()


def outpack_init(cfg):
    if outpack_is_initialised(cfg):
        print("[outpack] outpack volume already contains data - not initialising")
    else:
        print("[outpack] Initialising outpack")
        image = "mrcide/outpack.orderly:main"
        mount = docker.types.Mount("/outpack", cfg.volumes["outpack"])

        with DockerClient() as cl:
            cl.containers.run(
                image, mounts=[mount], remove=True, entrypoint=["R", "-e", "outpack::outpack_init('/outpack')"]
            )


def outpack_is_initialised(cfg):
    image = "bash"
    mount = docker.types.Mount("/outpack", cfg.volumes["outpack"])

    with DockerClient() as cl:
        container = cl.containers.run(
            image, mounts=[mount], detach=True, command=["test", "-f", "/outpack/.outpack/config.json"]
        )
        result = container.wait()
        container.remove()
        return result["StatusCode"] == 0


def outpack_server_container(cfg):
    name = cfg.containers["outpack-server"]
    mounts = [constellation.ConstellationMount("outpack", "/outpack")]
    outpack_server = constellation.ConstellationContainer(name, cfg.outpack_ref, mounts=mounts)
    return outpack_server


def packit_db_container(cfg):
    name = cfg.containers["packit-db"]
    packit_db = constellation.ConstellationContainer(name, cfg.packit_db_ref, configure=packit_db_configure)
    return packit_db


def packit_db_configure(container, _):
    docker_util.exec_safely(container, ["wait-for-db"])
    docker_util.exec_safely(
        container, ["psql", "-U", "packituser", "-d", "packit", "-a", "-f", "/packit-schema/schema.sql"]
    )


def packit_api_container(cfg):
    name = cfg.containers["packit-api"]
    packit_api = constellation.ConstellationContainer(name, cfg.packit_api_ref, configure=packit_api_configure)
    return packit_api


def packit_api_configure(container, cfg):
    print("[web] Configuring Packit API container")
    outpack = cfg.containers["outpack-server"]
    packit_db = cfg.containers["packit-db"]
    opts = {
        "db.url": f"jdbc:postgresql://{cfg.container_prefix}-{packit_db}:5432/packit?stringtype=unspecified",
        "db.user": cfg.packit_db_user,
        "db.password": cfg.packit_db_password,
        "outpack.server.url": f"http://{cfg.container_prefix}-{outpack}:8000",
    }
    txt = "".join([f"{k}={v}\n" for k, v in opts.items()])
    docker_util.string_into_container(txt, container, "/etc/packit/config.properties")


def packit_container(cfg):
    name = cfg.containers["packit"]
    packit = constellation.ConstellationContainer(name, cfg.packit_ref)
    return packit
