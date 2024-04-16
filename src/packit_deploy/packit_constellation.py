import constellation
import docker
from constellation import docker_util, vault

from packit_deploy.docker_helpers import DockerClient


class PackitConstellation:
    def __init__(self, cfg):
        outpack = outpack_server_container(cfg)
        packit_db = packit_db_container(cfg)
        packit_api = packit_api_container(cfg)
        packit = packit_container(cfg)

        containers = [outpack, packit_db, packit_api, packit]

        if cfg.proxy_enabled:
            proxy = proxy_container(cfg, packit_api, packit)
            containers.append(proxy)

        self.cfg = cfg
        self.obj = constellation.Constellation(
            "packit", cfg.container_prefix, containers, cfg.network, cfg.volumes, data=cfg, vault_config=cfg.vault
        )

    def start(self, **kwargs):
        self.obj.start(**kwargs)

    def stop(self, **kwargs):
        self.obj.stop(**kwargs)

    def status(self):
        self.obj.status()


def outpack_is_initialised(container):
    res = container.exec_run(["test", "-f", "/outpack/.outpack/config.json"])
    return res[0] == 0


def outpack_server_container(cfg):
    name = cfg.containers["outpack-server"]
    mounts = [constellation.ConstellationMount("outpack", "/outpack")]
    outpack_server = constellation.ConstellationContainer(
        name, cfg.outpack_ref, mounts=mounts, configure=outpack_server_configure
    )
    return outpack_server


def outpack_server_configure(container, cfg):
    if cfg.ssh:
        outpack_ssh_configure(container, cfg)
    if cfg.outpack_source_url is not None:
        if outpack_is_initialised(container):
            print("[outpack] outpack volume already contains data - not initialising")
        else:
            outpack_init_clone(container, cfg)


def outpack_ssh_configure(container, cfg):
    print("[outpack] Configuring ssh")
    path_private = "/root/.ssh/id_rsa"
    path_public = "/root/.ssh/id_rsa.pub"
    path_known_hosts = "/root/.ssh/known_hosts"
    docker_util.exec_safely(container, ["mkdir", "-p", "/root/.ssh"])
    docker_util.string_into_container(cfg.ssh_private, container, path_private)
    docker_util.string_into_container(cfg.ssh_public, container, path_public)
    docker_util.exec_safely(container, ["chmod", "600", path_private])
    hosts = docker_util.exec_safely(container, ["ssh-keyscan", "github.com"])
    docker_util.string_into_container(hosts[1].decode("UTF-8"), container, path_known_hosts)


def outpack_init_clone(container, cfg):
    print("[orderly] Initialising orderly by cloning")
    # TODO: revert this branch pin to:
    args = ["git", "clone", cfg.outpack_source_url, "/outpack"]

    docker_util.exec_safely(container, args)
    # usually cloning a source repo will not ensure outpack is initialised
    # so here, check that outpack config exists, and if not, initialise
    if not outpack_is_initialised(container):
        image = str(cfg.outpack_ref)
        mounts = [docker.types.Mount("/outpack", cfg.volumes["outpack"])]

        with DockerClient() as cl:
            args = ["outpack", "init", "--require-complete-tree", "--use-file-store", "/outpack"]
            cl.containers.run(image, mounts=mounts, remove=True, entrypoint=args)


def packit_db_container(cfg):
    name = cfg.containers["packit-db"]
    packit_db = constellation.ConstellationContainer(name, cfg.packit_db_ref, configure=packit_db_configure)
    return packit_db


def packit_db_configure(container, _):
    print("[packit-db] Configuring DB container")
    docker_util.exec_safely(container, ["wait-for-db"])
    docker_util.exec_safely(
        container, ["psql", "-U", "packituser", "-d", "packit", "-a", "-f", "/packit-schema/schema.sql"]
    )


def packit_api_container(cfg):
    name = cfg.containers["packit-api"]
    outpack = cfg.containers["outpack-server"]
    packit_db = cfg.containers["packit-db"]
    env = {
        "DB_URL": f"jdbc:postgresql://{cfg.container_prefix}-{packit_db}:5432/packit?stringtype=unspecified",
        "DB_USER": cfg.packit_db_user,
        "DB_PASSWORD": cfg.packit_db_password,
        "OUTPACK_SERVER_URL": f"http://{cfg.container_prefix}-{outpack}:8000",
        "AUTH_ENABLED": "true" if cfg.packit_auth_enabled else "false",
    }
    if cfg.packit_auth_enabled:
        if cfg.vault and cfg.vault.url:
            # resolve secrets early so we can set these env vars from vault values
            vault.resolve_secrets(cfg, cfg.vault.client())
        env.update(
            {
                "AUTH_METHOD": cfg.packit_auth_method,
                "JWT_EXPIRY_DAYS": cfg.packit_auth_expiry_days,
                "AUTH_GITHUB_ORG": cfg.packit_auth_github_api_org,
                "AUTH_GITHUB_TEAM": cfg.packit_auth_github_api_team,
                "JWT_SECRET": cfg.packit_auth_jwt_secret,
                "AUTH_REDIRECT_URL": cfg.packit_auth_oauth2_redirect_url,
                "GITHUB_CLIENT_ID": cfg.packit_auth_github_client_id,
                "GITHUB_CLIENT_SECRET": cfg.packit_auth_github_client_secret,
                "PACKIT_API_ROOT": cfg.packit_auth_oauth2_redirect_packit_api_root,
            }
        )
    packit_api = constellation.ConstellationContainer(name, cfg.packit_api_ref, environment=env)
    return packit_api


def packit_api_configure(container, cfg):
    print("[packit-api] Configuring API container")
    outpack = cfg.containers["outpack-server"]
    packit_db = cfg.containers["packit-db"]
    opts = {
        "db.url": f"jdbc:postgresql://{cfg.container_prefix}-{packit_db}:5432/packit?stringtype=unspecified",
        "db.user": cfg.packit_db_user,
        "db.password": cfg.packit_db_password,
        "outpack.server.url": f"http://{cfg.container_prefix}-{outpack}:8000",
        "auth.enabled": "true" if cfg.packit_auth_enabled else "false",
    }
    if cfg.packit_auth_enabled:
        opts["auth.enableGithubLogin"] = "true" if cfg.packit_auth_enable_github_login else "false"
        opts["auth.expiryDays"] = cfg.packit_auth_expiry_days
        opts["auth.githubAPIOrg"] = cfg.packit_auth_github_api_org
        opts["auth.githubAPITeam"] = cfg.packit_auth_github_api_team
        opts["auth.jwt.secret"] = cfg.packit_auth_jwt_secret
        opts["auth.oauth2.redirect.url"] = cfg.packit_auth_oauth2_redirect_url

    txt = "".join([f"{k}={v}\n" for k, v in opts.items()])
    docker_util.string_into_container(txt, container, "/etc/packit/config.properties")


def packit_container(cfg):
    name = cfg.containers["packit"]
    packit = constellation.ConstellationContainer(name, cfg.packit_ref)
    return packit


def proxy_container(cfg, packit_api=None, packit=None):
    proxy_name = cfg.containers["proxy"]
    packit_api_addr = f"{packit_api.name_external(cfg.container_prefix)}:8080"
    packit_addr = packit.name_external(cfg.container_prefix)
    proxy_args = [cfg.proxy_hostname, str(cfg.proxy_port_http), str(cfg.proxy_port_https), packit_api_addr, packit_addr]
    proxy_mounts = [constellation.ConstellationMount("proxy_logs", "/var/log/nginx")]
    proxy_ports = [cfg.proxy_port_http, cfg.proxy_port_https]
    proxy = constellation.ConstellationContainer(
        proxy_name, cfg.proxy_ref, ports=proxy_ports, args=proxy_args, mounts=proxy_mounts, configure=proxy_configure
    )
    return proxy


def proxy_configure(container, cfg):
    print("[proxy] Configuring proxy container")
    if cfg.proxy_ssl_self_signed:
        print("[proxy] Generating self-signed certificates for proxy")
        docker_util.exec_safely(container, ["self-signed-certificate", "/run/proxy"])
    else:
        print("[proxy] Copying ssl certificate and key into proxy")
        docker_util.string_into_container(cfg.proxy_ssl_certificate, container, "/run/proxy/certificate.pem")
        docker_util.string_into_container(cfg.proxy_ssl_key, container, "/run/proxy/key.pem")
