import constellation
from constellation import docker_util


def packit_constellation(cfg):
    outpack = outpack_server_container(cfg)
    packit_db = packit_db_container(cfg)
    packit_api = packit_api_container(cfg)
    packit = packit_container(cfg)

    containers = [outpack, packit_db, packit_api, packit]

    if cfg.proxy_enabled:
        print("Proxy not yet enabled. Ignoring proxy configuration.")

    obj = constellation.Constellation("packit", cfg.container_prefix,
                                      containers, cfg.network, cfg.volumes,
                                      data=cfg)
    return obj


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
    url = "jdbc:postgresql://{}-{}:5432/packit?stringtype=unspecified"
    opts = {
        "db.url": url.format(cfg.container_prefix, packit_db),
        "db.user": "packituser",
        "db.password": "changeme",
        "outpack.server.url": f"http://{cfg.container_prefix}-{outpack}:8000",
    }
    txt = "".join([f"{k}={v}\n" for k, v in opts.items()])
    docker_util.string_into_container(txt, container, "/etc/packit/config.properties")


def packit_container(cfg):
    name = cfg.containers["packit"]
    packit = constellation.ConstellationContainer(name, cfg.packit_ref)
    return packit
