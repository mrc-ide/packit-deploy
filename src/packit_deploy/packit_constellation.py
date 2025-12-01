import re
from pathlib import PurePosixPath
from typing import TypeVar, Optional

import constellation
import docker
from constellation import docker_util, vault

from packit_deploy import schema
from packit_deploy.docker_helpers import DockerClient


T = TypeVar('T')
def unwrap(v: Optional[T]) -> T:
    if v is None:
        raise ValueError("unexpected None")
    else:
        return v

class PackitConstellation:
    def __init__(self, cfg: schema.Config):
        # resolve secrets early so we can set these env vars from vault values
        if cfg.vault and cfg.vault.addr:
            vault.resolve_secrets(cfg, cfg.vault.client())

        outpack = outpack_server_container(cfg)
        packit_db = packit_db_container(cfg)
        packit_api = packit_api_container(cfg)
        packit = packit_container(cfg)

        containers = [outpack, packit_db, packit_api, packit]

        if cfg.proxy is not None:
            proxy = proxy_container(cfg, packit_api, packit)
            containers.append(proxy)

        if cfg.orderly_runner is not None:
            containers.append(redis_container(cfg))
            containers.append(orderly_runner_api_container(cfg))
            containers.append(orderly_runner_worker_container(cfg))

        self.cfg = cfg
        self.obj = constellation.Constellation(
            "packit",
            cfg.container_prefix,
            containers,
            cfg.network,
            cfg.volumes.model_dump(exclude_none=True),
            data=cfg,
            vault_config=cfg.vault,
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


def outpack_server_container(cfg: schema.Config):
    mounts = [constellation.ConstellationVolumeMount("outpack", "/outpack")]
    outpack_server = constellation.ConstellationContainer(
        "outpack-server", cfg.outpack_ref, mounts=mounts, configure=outpack_server_configure
    )
    return outpack_server


def outpack_server_configure(container, cfg: schema.Config):
    print("[outpack] Initialising outpack repository")
    if not outpack_is_initialised(container):
        image = str(cfg.outpack_ref)
        mounts = [docker.types.Mount("/outpack", cfg.volumes.outpack)]

        with DockerClient() as cl:
            args = ["outpack", "init", "--require-complete-tree", "--use-file-store", "/outpack"]
            cl.containers.run(image, mounts=mounts, remove=True, entrypoint=args)


def packit_db_container(cfg: schema.Config):
    mounts = [
        constellation.ConstellationVolumeMount("packit_db", "/pgdata"),
        constellation.ConstellationVolumeMount("packit_db_backup", "/pgbackup"),
    ]
    packit_db = constellation.ConstellationContainer(
        "packit-db", cfg.packit_db_ref, mounts=mounts, configure=packit_db_configure
    )
    return packit_db


def packit_db_configure(container, _):
    print("[packit-db] Configuring DB container")
    docker_util.exec_safely(container, ["wait-for-db"])


def packit_api_container(cfg: schema.Config):
    packit_api = constellation.ConstellationContainer(
        "packit-api", cfg.packit_api_ref, environment=packit_api_get_env(cfg)
    )
    return packit_api


def packit_api_get_env(cfg: schema.Config):
    env : dict[str, str]= {
        "PACKIT_DB_URL": f"jdbc:postgresql://{cfg.container_prefix}-packit-db:5432/packit?stringtype=unspecified",
        "PACKIT_DB_USER": cfg.packit.db.user,
        "PACKIT_DB_PASSWORD": cfg.packit.db.password,
        "PACKIT_OUTPACK_SERVER_URL": cfg.outpack_server_url,
        "PACKIT_AUTH_ENABLED": "true" if cfg.packit.auth is not None else "false",
        "PACKIT_BRAND_DARK_MODE_ENABLED": "true" if cfg.brand.dark_mode_enabled else "false",
        "PACKIT_BRAND_LIGHT_MODE_ENABLED": "true" if cfg.brand.light_mode_enabled else "false",
        "PACKIT_CORS_ALLOWED_ORIGINS": cfg.packit.cors_allowed_origins,
        "PACKIT_BASE_URL": cfg.packit.base_url,
        "PACKIT_DEVICE_FLOW_EXPIRY_SECONDS": "300",
        "PACKIT_DEVICE_AUTH_URL": f"{cfg.packit.base_url}/device",
        "PACKIT_MANAGEMENT_PORT": str(cfg.packit.api.management_port),
    }

    if cfg.brand.logo_name is not None:
        env["PACKIT_BRAND_LOGO_NAME"] = cfg.brand.logo_name
    if cfg.brand.logo_alt_text is not None:
        env["PACKIT_BRAND_LOGO_ALT_TEXT"] = cfg.brand.logo_alt_text
    if cfg.brand.logo_link is not None:
        env["PACKIT_BRAND_LOGO_LINK"] = cfg.brand.logo_link

    if cfg.packit.auth is not None:
        env.update(
            {
                "PACKIT_AUTH_METHOD": cfg.packit.auth.auth_method,
                "PACKIT_JWT_EXPIRY_DAYS": str(cfg.packit.auth.expiry_days),
                "PACKIT_JWT_SECRET": cfg.packit.auth.jwt.secret,
            }
        )
        if cfg.packit.auth.auth_method == "github":
            env.update(
                {
                    "PACKIT_GITHUB_CLIENT_ID": unwrap(cfg.packit.auth.github_client).id,
                    "PACKIT_GITHUB_CLIENT_SECRET": unwrap(cfg.packit.auth.github_client).secret,
                    "PACKIT_AUTH_REDIRECT_URL": unwrap(cfg.packit.auth.oauth2).redirect.url,
                    "PACKIT_API_ROOT": unwrap(cfg.packit.auth.oauth2).redirect.packit_api_root,
                    "PACKIT_AUTH_GITHUB_ORG": unwrap(cfg.packit.auth.github_api_org),
                    "PACKIT_AUTH_GITHUB_TEAM": unwrap(cfg.packit.auth.github_api_team),
                }
            )

    if cfg.orderly_runner is not None:
        env["PACKIT_ORDERLY_RUNNER_URL"] = cfg.orderly_runner_api_url
        env["PACKIT_ORDERLY_RUNNER_REPOSITORY_URL"] = cfg.orderly_runner_git_url
        if cfg.orderly_runner_git_ssh_key:
            env["PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY"] = cfg.orderly_runner_git_ssh_key
        # Mantra is going to tidy this up; it should always be the
        # same as PACKIT_OUTPACK_SERVER_URL but differs because of
        # automatic variable creation in the Kotlin framework.
        env["PACKIT_ORDERLY_RUNNER_LOCATION_URL"] = cfg.outpack_server_url

    return env


def packit_container(cfg: schema.Config):
    mounts = []
    app_html_root = PurePosixPath("/usr/share/nginx/html")  # from Packit app Dockerfile

    if cfg.brand.logo_path is not None:
        logo_in_container = app_html_root / img / cfg.brand.logo_name
        mounts.append(constellation.ConstellationBindMount(cfg.brand_logo_path, logo_in_container, read_only=True))

    if cfg.brand.favicon_path is not None:
        favicon_in_container = app_html_root / img / cfg.brand.favicon_name
        mounts.append(
            constellation.ConstellationBindMount(cfg.brand.favicon_path, favicon_in_container, read_only=True)
        )

    packit = constellation.ConstellationContainer("packit", cfg.packit_ref, mounts=mounts, configure=packit_configure)
    return packit


def packit_configure(container, cfg: schema.Config):
    print("[packit] Configuring Packit container")
    if cfg.brand.name is not None:
        # We configure the title tag of the index.html file here, rather than updating it dynamically with JS,
        # since using JS results in the page title visibly changing a number of seconds after the initial page load.
        substitute_file_content(
            container, f"{cfg.app_html_root}/index.html", r"(?<=<title>).*?(?=</title>)", cfg.brand.name
        )

    if cfg.brand.favicon_name is not None:
        substitute_file_content(container, f"{cfg.app_html_root}/index.html", r"favicon\.ico", cfg.brand.favicon_name)

    css = ""
    if cfg.brand.css.light is not None:
        css += (
            ":root {\n"
            f"  --custom-accent: {cfg.brand.css.light.accent};\n"
            f"  --custom-accent-foreground: {cfg.brand.css.light.accent_foreground};\n"
            "}\n"
        )

    if cfg.brand.css.dark is not None:
        css += (
            ".dark {\n"
            f"  --custom-accent: {cfg.brand.css.dark.accent};\n"
            f"  --custom-accent-foreground: {cfg.brand.css.dark.accent_foreground};\n"
            "}\n"
        )

    if css:
        overwrite_file(container, f"{app_html_root}/css/custom.css", css)


def overwrite_file(container, path, content):
    substitute_file_content(container, path, r".*", content, flags=re.DOTALL)


def substitute_file_content(container, path, pattern, replacement, flags=0):
    prev_file_content = docker_util.string_from_container(container, path)
    new_content = re.sub(pattern, replacement, prev_file_content, flags=flags)

    backup = f"{path}.bak"
    docker_util.exec_safely(container, ["mv", path, backup])

    docker_util.string_into_container(new_content, container, path)

    # Clone permissions from the original file's backup to the new one
    docker_util.exec_safely(container, ["chown", "--reference", backup, path])
    docker_util.exec_safely(container, ["chmod", "--reference", backup, path])

    # Remove the backup file
    docker_util.exec_safely(container, ["rm", backup])


def proxy_container(cfg, packit_api=None, packit=None):
    packit_api_addr = f"{packit_api.name_external(cfg.container_prefix)}:8080"
    packit_addr = packit.name_external(cfg.container_prefix)
    proxy_args = [cfg.proxy.hostname, str(cfg.proxy.port_http), str(cfg.proxy.port_https), packit_api_addr, packit_addr]
    proxy_mounts = [constellation.ConstellationVolumeMount("proxy_logs", "/var/log/nginx")]
    proxy_ports = [cfg.proxy.port_http, cfg.proxy.port_https]
    proxy = constellation.ConstellationContainer(
        "proxy", cfg.proxy_ref, ports=proxy_ports, args=proxy_args, mounts=proxy_mounts, configure=proxy_configure
    )
    return proxy


def proxy_configure(container, cfg):
    print("[proxy] Configuring proxy container")
    if cfg.proxy.ssl is None:
        print("[proxy] Generating self-signed certificates for proxy")
        docker_util.exec_safely(container, ["self-signed-certificate", "/run/proxy"])
    else:
        print("[proxy] Copying ssl certificate and key into proxy")
        docker_util.string_into_container(cfg.proxy.ssl.certificate, container, "/run/proxy/certificate.pem")
        docker_util.string_into_container(cfg.proxy.ssl.key, container, "/run/proxy/key.pem")


def redis_container(cfg):
    name = cfg.containers["redis"]
    image = str(cfg.images["redis"])
    return constellation.ConstellationContainer(name, image, configure=redis_configure)


def redis_configure(container, _cfg):
    print("[redis] Waiting for redis to come up")
    docker_util.string_into_container(WAIT_FOR_REDIS, container, "/wait_for_redis")
    docker_util.exec_safely(container, ["bash", "/wait_for_redis"])


def orderly_runner_api_container(cfg):
    name = cfg.containers["orderly-runner-api"]
    image = str(cfg.images["orderly-runner"])
    env = orderly_runner_env(cfg)
    entrypoint = "/usr/local/bin/orderly.runner.server"
    args = ["/data"]
    mounts = [
        constellation.ConstellationVolumeMount("orderly_library", "/library"),
        constellation.ConstellationVolumeMount("orderly_logs", "/logs"),
    ]
    return constellation.ConstellationContainer(
        name,
        image,
        environment=env,
        entrypoint=entrypoint,
        args=args,
        mounts=mounts,
    )


def orderly_runner_worker_container(cfg):
    name = cfg.containers["orderly-runner-worker"]
    image = str(cfg.images["orderly-runner"])
    count = cfg.orderly_runner_workers
    env = orderly_runner_env(cfg)
    entrypoint = "/usr/local/bin/orderly.runner.worker"
    args = ["/data"]
    mounts = [
        constellation.ConstellationVolumeMount("orderly_library", "/library"),
        constellation.ConstellationVolumeMount("orderly_logs", "/logs"),
    ]
    return constellation.ConstellationService(
        name,
        image,
        count,
        environment=env,
        entrypoint=entrypoint,
        args=args,
        mounts=mounts,
    )


def orderly_runner_env(cfg):
    base = {"REDIS_URL": cfg.redis_url, "ORDERLY_RUNNER_QUEUE_ID": "orderly.runner.queue"}
    return {
        **base,
        **cfg.orderly_runner_env,
    }


# Small script to wait for redis to come up
WAIT_FOR_REDIS = """#!/usr/bin/env bash
wait_for()
{
    echo "waiting up to $TIMEOUT seconds for redis"
    start_ts=$(date +%s)
    for i in $(seq $TIMEOUT); do
        redis-cli -p 6379 ping | grep PONG
        result=$?
        if [[ $result -eq 0 ]]; then
            end_ts=$(date +%s)
            echo "redis is available after $((end_ts - start_ts)) seconds"
            break
        fi
        sleep 1
        echo "...still waiting"
    done
    return $result
}

# The variable expansion below is 20s by default, or the argument provided
# to this script
TIMEOUT="${1:-20}"
wait_for
RESULT=$?
if [[ $RESULT -ne 0 ]]; then
  echo "redis did not become available in time"
fi
exit $RESULT
"""
