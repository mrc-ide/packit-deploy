import re

import constellation
import docker
import jinja2
from constellation import ConstellationContainer, acme, docker_util, vault

from packit_deploy import config
from packit_deploy.config import PackitConfig
from packit_deploy.docker_helpers import DockerClient

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.PackageLoader("packit_deploy"),
    undefined=jinja2.StrictUndefined,
    autoescape=False,  # noqa: S701, we only template from config values, not user inputs
)


class PackitConstellation:
    def __init__(self, cfg: PackitConfig):
        # resolve secrets early so we can set these env vars from vault values
        if cfg.vault and cfg.vault.url:
            vault.resolve_secrets(cfg, cfg.vault.client())
            if cfg.acme_config is not None:  # pragma: no cover
                vault.resolve_secrets(cfg.acme_config, cfg.vault.client())

        outpack = outpack_server_container(cfg)
        packit_db = packit_db_container(cfg)
        packit_api = packit_api_container(cfg)
        packit = packit_container(cfg)

        containers = [outpack, packit_db, packit_api, packit]

        if cfg.proxy is not None:
            proxy = proxy_container(cfg, cfg.proxy, packit_api, packit)
            containers.append(proxy)
            if cfg.acme_config is not None:
                acme_container = acme.acme_buddy_container(
                    cfg.acme_config,
                    "acme-buddy",
                    proxy.name_external(cfg.container_prefix),
                    "packit-tls",
                    cfg.proxy.hostname,
                )
                containers.append(acme_container)

        if cfg.orderly_runner is not None:
            containers.append(redis_container(cfg))
            containers.append(orderly_runner_api_container(cfg, cfg.orderly_runner))
            containers.append(orderly_runner_worker_containers(cfg, cfg.orderly_runner))

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


def outpack_server_container(cfg: PackitConfig) -> ConstellationContainer:
    name = cfg.containers["outpack-server"]
    mounts = [constellation.ConstellationVolumeMount("outpack", "/outpack")]
    return ConstellationContainer(
        name,
        cfg.outpack_ref,
        mounts=mounts,
        configure=outpack_server_configure,
    )


def outpack_server_configure(container, cfg: PackitConfig):
    print("[outpack] Initialising outpack repository")
    if not outpack_is_initialised(container):
        image = str(cfg.outpack_ref)
        mounts = [docker.types.Mount("/outpack", cfg.volumes["outpack"])]

        with DockerClient() as cl:
            args = ["outpack", "init", "--require-complete-tree", "--use-file-store", "/outpack"]
            cl.containers.run(image, mounts=mounts, remove=True, entrypoint=args)


def packit_db_container(cfg: PackitConfig) -> ConstellationContainer:
    name = cfg.containers["packit-db"]
    mounts = [
        constellation.ConstellationVolumeMount("packit_db", "/pgdata"),
        constellation.ConstellationVolumeMount("packit_db_backup", "/pgbackup"),
    ]
    return ConstellationContainer(
        name,
        cfg.packit_db.image,
        mounts=mounts,
        configure=packit_db_configure,
    )


def packit_db_configure(container, _cfg: PackitConfig):
    print("[packit-db] Configuring DB container")
    docker_util.exec_safely(container, ["wait-for-db"])


def packit_api_container(cfg: PackitConfig) -> ConstellationContainer:
    name = cfg.containers["packit-api"]
    return ConstellationContainer(
        name,
        cfg.packit_api.image,
        environment=packit_api_get_env(cfg),
    )


def packit_api_get_env(cfg: PackitConfig) -> dict[str, str]:
    packit_db = cfg.containers["packit-db"]
    env: dict[str, str] = {
        "PACKIT_DB_URL": f"jdbc:postgresql://{cfg.container_prefix}-{packit_db}:5432/packit?stringtype=unspecified",
        "PACKIT_DB_USER": cfg.packit_db.user,
        "PACKIT_DB_PASSWORD": cfg.packit_db.password,
        "PACKIT_OUTPACK_SERVER_URL": cfg.outpack_server_url,
        "PACKIT_AUTH_ENABLED": "true" if cfg.packit_api.auth is not None else "false",
        "PACKIT_BRAND_DARK_MODE_ENABLED": "true" if cfg.brand.dark_mode_enabled else "false",
        "PACKIT_BRAND_LIGHT_MODE_ENABLED": "true" if cfg.brand.light_mode_enabled else "false",
        "PACKIT_CORS_ALLOWED_ORIGINS": cfg.packit_api.cors_allowed_origins,
        "PACKIT_BASE_URL": cfg.packit_api.base_url,
        "PACKIT_DEVICE_FLOW_EXPIRY_SECONDS": "300",
        "PACKIT_DEVICE_AUTH_URL": f"{cfg.packit_api.base_url}/device",
        "PACKIT_MANAGEMENT_PORT": str(cfg.packit_api.management_port),
    }

    if cfg.brand.logo is not None:
        env["PACKIT_BRAND_LOGO_NAME"] = cfg.brand.logo.name
    if cfg.brand.logo_alt_text is not None:
        env["PACKIT_BRAND_LOGO_ALT_TEXT"] = cfg.brand.logo_alt_text
    if cfg.brand.logo_link is not None:
        env["PACKIT_BRAND_LOGO_LINK"] = cfg.brand.logo_link

    if cfg.packit_api.auth is not None:
        env.update(
            {
                "PACKIT_AUTH_METHOD": cfg.packit_api.auth.method,
                "PACKIT_JWT_EXPIRY_DAYS": str(cfg.packit_api.auth.expiry_days),
                "PACKIT_JWT_SECRET": cfg.packit_api.auth.jwt_secret,
            }
        )
        if cfg.packit_api.auth.github is not None:
            github = cfg.packit_api.auth.github
            env.update(
                {
                    "PACKIT_GITHUB_CLIENT_ID": github.client_id,
                    "PACKIT_GITHUB_CLIENT_SECRET": github.client_secret,
                    "PACKIT_AUTH_REDIRECT_URL": github.oauth2_redirect_url,
                    "PACKIT_API_ROOT": github.oauth2_redirect_packit_api_root,
                    "PACKIT_AUTH_GITHUB_ORG": github.org,
                    "PACKIT_AUTH_GITHUB_TEAM": github.team,
                }
            )

    if cfg.packit_api.runner_git_url is not None:
        env["PACKIT_ORDERLY_RUNNER_URL"] = cfg.orderly_runner_api_url
        env["PACKIT_ORDERLY_RUNNER_REPOSITORY_URL"] = cfg.packit_api.runner_git_url
        if cfg.packit_api.runner_git_ssh_key is not None:
            env["PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY"] = cfg.packit_api.runner_git_ssh_key
        env["PACKIT_ORDERLY_RUNNER_LOCATION_URL"] = cfg.outpack_server_url

    return env


def packit_container(cfg: PackitConfig):
    mounts = []

    if cfg.brand.logo is not None:
        logo_in_container = f"{cfg.app_html_root}/img/{cfg.brand.logo.name}"
        mounts.append(constellation.ConstellationBindMount(str(cfg.brand.logo), logo_in_container, read_only=True))

    if cfg.brand.favicon is not None:
        favicon_in_container = f"{cfg.app_html_root}/{cfg.brand.favicon.name}"
        mounts.append(
            constellation.ConstellationBindMount(str(cfg.brand.favicon), favicon_in_container, read_only=True)
        )

    return ConstellationContainer(
        cfg.containers["packit"],
        cfg.packit_ref,
        mounts=mounts,
        configure=packit_configure,
    )


def packit_configure(container, cfg: PackitConfig):
    print("[packit] Configuring Packit container")
    if cfg.brand.name is not None:
        # We configure the title tag of the index.html file here, rather than updating it dynamically with JS,
        # since using JS results in the page title visibly changing a number of seconds after the initial page load.
        substitute_file_content(
            container, f"{cfg.app_html_root}/index.html", r"(?<=<title>).*?(?=</title>)", cfg.brand.name
        )
    if cfg.brand.favicon is not None:
        substitute_file_content(container, f"{cfg.app_html_root}/index.html", r"favicon\.ico", cfg.brand.favicon.name)

    new_css = ""
    if cfg.brand.theme_light is not None:
        new_css += (
            ":root {\n"
            f"  --custom-accent: {cfg.brand.theme_light.accent};\n"
            f"  --custom-accent-foreground: {cfg.brand.theme_light.foreground};\n"
            "}\n"
        )
    if cfg.brand.theme_dark is not None:
        new_css += (
            ".dark {\n"
            f"  --custom-accent: {cfg.brand.theme_dark.accent};\n"
            f"  --custom-accent-foreground: {cfg.brand.theme_dark.foreground};\n"
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


def proxy_container(
    cfg: PackitConfig,
    proxy: config.Proxy,
    packit_api: ConstellationContainer,
    packit: ConstellationContainer,
):
    name = cfg.containers["proxy"]
    mounts = [constellation.ConstellationVolumeMount("proxy_logs", "/var/log/nginx")]
    if cfg.acme_config is not None:
        mounts.append(constellation.ConstellationVolumeMount("packit-tls", "/run/proxy"))
    ports = [proxy.port_http, proxy.port_https]
    return ConstellationContainer(
        name,
        image=proxy.image,
        ports=ports,
        mounts=mounts,
        preconfigure=lambda container, cfg: proxy_preconfigure(container, cfg, proxy, packit_api, packit),
        configure=proxy_configure,
    )


def proxy_nginx_conf(
    cfg: PackitConfig, proxy: config.Proxy, packit_api: ConstellationContainer, packit: ConstellationContainer
):
    packit_api_addr = f"{packit_api.name_external(cfg.container_prefix)}:8080"
    packit_app_addr = packit.name_external(cfg.container_prefix)

    template = JINJA_ENVIRONMENT.get_template("nginx.conf.j2")
    return template.render(
        upstream_api=packit_api_addr,
        upstream_app=packit_app_addr,
        hostname=proxy.hostname,
        port_http=proxy.port_http,
        port_https=proxy.port_https,
    )


def proxy_preconfigure(
    container: ConstellationContainer,
    cfg: PackitConfig,
    proxy: config.Proxy,
    packit_api: ConstellationContainer,
    packit: ConstellationContainer,
):
    print("[proxy] Preconfiguring proxy container")
    nginx_conf = proxy_nginx_conf(cfg, proxy, packit_api, packit)
    docker_util.string_into_container(nginx_conf, container, "/etc/nginx/conf.d/default.conf")


def proxy_configure(container: ConstellationContainer, cfg: PackitConfig):
    print("[proxy] Configuring proxy container")
    if cfg.acme_config is None:
        print("[proxy] Generating self-signed certificates for proxy")
        docker_util.exec_safely(container, ["self-signed-certificate", "/run/proxy"])


def redis_container(cfg: PackitConfig) -> ConstellationContainer:
    name = cfg.containers["redis"]
    image = str(cfg.redis_image)
    return ConstellationContainer(
        name,
        image,
        configure=redis_configure,
    )


def redis_configure(container, _cfg: PackitConfig):
    print("[redis] Waiting for redis to come up")
    docker_util.string_into_container(WAIT_FOR_REDIS, container, "/wait_for_redis")
    docker_util.exec_safely(container, ["bash", "/wait_for_redis"])


def orderly_runner_api_container(cfg: PackitConfig, runner: config.OrderlyRunner):
    name = cfg.containers["orderly-runner-api"]
    image = str(runner.image)
    env = orderly_runner_env(cfg, runner)
    entrypoint = "/usr/local/bin/orderly.runner.server"
    args = ["/data"]
    mounts = [
        constellation.ConstellationVolumeMount("orderly_library", "/library"),
        constellation.ConstellationVolumeMount("orderly_logs", "/logs"),
    ]
    return ConstellationContainer(
        name,
        image,
        environment=env,
        entrypoint=entrypoint,
        args=args,
        mounts=mounts,
    )


def orderly_runner_worker_containers(cfg: PackitConfig, runner: config.OrderlyRunner):
    name = cfg.containers["orderly-runner-worker"]
    image = str(runner.image)
    count = runner.workers
    env = orderly_runner_env(cfg, runner)
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


def orderly_runner_env(cfg: PackitConfig, runner: config.OrderlyRunner):
    return {
        "REDIS_URL": cfg.redis_url,
        "ORDERLY_RUNNER_QUEUE_ID": "orderly.runner.queue",
        **runner.env,
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
