import re

import constellation
import docker
from constellation import docker_util, vault

from packit_deploy.docker_helpers import DockerClient


class PackitConstellation:
    def __init__(self, cfg):
        # resolve secrets early so we can set these env vars from vault values
        if cfg.vault and cfg.vault.url:
            vault.resolve_secrets(cfg, cfg.vault.client())

        outpack = outpack_server_container(cfg)
        packit_db = packit_db_container(cfg)
        packit_api = packit_api_container(cfg)
        packit = packit_container(cfg)

        containers = [outpack, packit_db, packit_api, packit]

        if cfg.proxy_enabled:
            proxy = proxy_container(cfg, packit_api, packit)
            containers.append(proxy)

        if cfg.orderly_runner_enabled:
            containers.append(redis_container(cfg))
            containers.append(orderly_runner_api_container(cfg))
            containers.append(orderly_runner_worker_container(cfg))

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
    mounts = [constellation.ConstellationVolumeMount("outpack", "/outpack")]
    outpack_server = constellation.ConstellationContainer(
        name, cfg.outpack_ref, mounts=mounts, configure=outpack_server_configure
    )
    return outpack_server


def outpack_server_configure(container, cfg):
    print("[outpack] Initialising outpack repository")
    if not outpack_is_initialised(container):
        image = str(cfg.outpack_ref)
        mounts = [docker.types.Mount("/outpack", cfg.volumes["outpack"])]

        with DockerClient() as cl:
            args = ["outpack", "init", "--require-complete-tree", "--use-file-store", "/outpack"]
            cl.containers.run(image, mounts=mounts, remove=True, entrypoint=args)


def packit_db_container(cfg):
    name = cfg.containers["packit-db"]
    mounts = [constellation.ConstellationVolumeMount("packit_db", "/pgdata")]
    packit_db = constellation.ConstellationContainer(
        name, cfg.packit_db_ref, mounts=mounts, configure=packit_db_configure
    )
    return packit_db


def packit_db_configure(container, _):
    print("[packit-db] Configuring DB container")
    docker_util.exec_safely(container, ["wait-for-db"])


def packit_api_container(cfg):
    name = cfg.containers["packit-api"]
    packit_api = constellation.ConstellationContainer(name, cfg.packit_api_ref, environment=packit_api_get_env(cfg))
    return packit_api


def packit_api_get_env(cfg):
    packit_db = cfg.containers["packit-db"]
    env = {
        "PACKIT_DB_URL": f"jdbc:postgresql://{cfg.container_prefix}-{packit_db}:5432/packit?stringtype=unspecified",
        "PACKIT_DB_USER": cfg.packit_db_user,
        "PACKIT_DB_PASSWORD": cfg.packit_db_password,
        "PACKIT_OUTPACK_SERVER_URL": cfg.outpack_server_url,
        "PACKIT_AUTH_ENABLED": "true" if cfg.packit_auth_enabled else "false",
        "PACKIT_BRAND_DARK_MODE_ENABLED": "true" if cfg.brand_dark_mode_enabled else "false",
        "PACKIT_BRAND_LIGHT_MODE_ENABLED": "true" if cfg.brand_light_mode_enabled else "false",
        "PACKIT_CORS_ALLOWED_ORIGINS": cfg.packit_cors_allowed_origins,
        "PACKIT_BASE_URL": cfg.packit_base_url,
        "PACKIT_DEVICE_FLOW_EXPIRY_SECONDS": "300",
        "PACKIT_DEVICE_AUTH_URL": f"{cfg.packit_base_url}/device",
        "PACKIT_MANAGEMENT_PORT": cfg.packit_api_management_port,
    }
    if hasattr(cfg, "brand_logo_name"):
        env["PACKIT_BRAND_LOGO_NAME"] = cfg.brand_logo_name
    if hasattr(cfg, "brand_logo_alt_text"):
        env["PACKIT_BRAND_LOGO_ALT_TEXT"] = cfg.brand_logo_alt_text
    if hasattr(cfg, "brand_logo_link"):
        env["PACKIT_BRAND_LOGO_LINK"] = cfg.brand_logo_link
    if cfg.packit_auth_enabled:
        env.update(
            {
                "PACKIT_AUTH_METHOD": cfg.packit_auth_method,
                "PACKIT_JWT_EXPIRY_DAYS": cfg.packit_auth_expiry_days,
                "PACKIT_JWT_SECRET": cfg.packit_auth_jwt_secret,
            }
        )
        if cfg.packit_auth_method == "github":
            env.update(
                {
                    "PACKIT_GITHUB_CLIENT_ID": cfg.packit_auth_github_client_id,
                    "PACKIT_GITHUB_CLIENT_SECRET": cfg.packit_auth_github_client_secret,
                    "PACKIT_AUTH_REDIRECT_URL": cfg.packit_auth_oauth2_redirect_url,
                    "PACKIT_API_ROOT": cfg.packit_auth_oauth2_redirect_packit_api_root,
                    "PACKIT_AUTH_GITHUB_ORG": cfg.packit_auth_github_api_org,
                    "PACKIT_AUTH_GITHUB_TEAM": cfg.packit_auth_github_api_team,
                }
            )
    if cfg.orderly_runner_enabled:
        env["PACKIT_ORDERLY_RUNNER_URL"] = cfg.orderly_runner_api_url
        env["PACKIT_ORDERLY_RUNNER_REPOSITORY_URL"] = cfg.orderly_runner_git_url
        if cfg.orderly_runner_git_ssh_key:
            env["PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY"] = cfg.orderly_runner_git_ssh_key
        # Mantra is going to tidy this up; it should always be the
        # same as PACKIT_OUTPACK_SERVER_URL but differs because of
        # automatic variable creation in the Kotlin framework.
        env["PACKIT_ORDERLY_RUNNER_LOCATION_URL"] = cfg.outpack_server_url

    return env


def packit_container(cfg):
    mounts = []
    cfg.app_html_root = "/usr/share/nginx/html"  # from Packit app Dockerfile

    if hasattr(cfg, "brand_logo_name"):
        logo_in_container = f"{cfg.app_html_root}/img/{cfg.brand_logo_name}"
        mounts.append(constellation.ConstellationBindMount(cfg.brand_logo_path, logo_in_container, read_only=True))

    if hasattr(cfg, "brand_favicon_name"):
        favicon_in_container = f"{cfg.app_html_root}/{cfg.brand_favicon_name}"
        mounts.append(
            constellation.ConstellationBindMount(cfg.brand_favicon_path, favicon_in_container, read_only=True)
        )

    packit = constellation.ConstellationContainer(
        cfg.containers["packit"], cfg.packit_ref, mounts=mounts, configure=packit_configure
    )
    return packit


def packit_configure(container, cfg):
    print("[packit] Configuring Packit container")
    if hasattr(cfg, "brand_name"):
        # We configure the title tag of the index.html file here, rather than updating it dynamically with JS,
        # since using JS results in the page title visibly changing a number of seconds after the initial page load.
        substitute_file_content(
            container, f"{cfg.app_html_root}/index.html", r"(?<=<title>).*?(?=</title>)", cfg.brand_name
        )
    if hasattr(cfg, "brand_favicon_name"):
        substitute_file_content(container, f"{cfg.app_html_root}/index.html", r"favicon\.ico", cfg.brand_favicon_name)
    if hasattr(cfg, "brand_accent_light") or hasattr(cfg, "brand_accent_dark"):
        new_css = ""
        if cfg.brand_light_mode_enabled and hasattr(cfg, "brand_accent_light"):
            new_css += (
                ":root {\n"
                f"  --custom-accent: {cfg.brand_accent_light};\n"
                f"  --custom-accent-foreground: {cfg.brand_accent_foreground_light};\n"
                "}\n"
            )
        if cfg.brand_dark_mode_enabled and hasattr(cfg, "brand_accent_dark"):
            new_css += (
                ".dark {\n"
                f"  --custom-accent: {cfg.brand_accent_dark};\n"
                f"  --custom-accent-foreground: {cfg.brand_accent_foreground_dark};\n"
                "}\n"
            )
        overwrite_file(container, f"{cfg.app_html_root}/css/custom.css", new_css)


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
    proxy_name = cfg.containers["proxy"]
    packit_api_addr = f"{packit_api.name_external(cfg.container_prefix)}:8080"
    packit_addr = packit.name_external(cfg.container_prefix)
    proxy_args = [cfg.proxy_hostname, str(cfg.proxy_port_http), str(cfg.proxy_port_https), packit_api_addr, packit_addr]
    proxy_mounts = [constellation.ConstellationVolumeMount("proxy_logs", "/var/log/nginx")]
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
