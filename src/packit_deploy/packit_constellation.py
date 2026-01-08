import re
from typing import Optional

import constellation
import jinja2
from constellation import ConstellationContainer, acme, docker_util, vault

from packit_deploy import config
from packit_deploy.config import PackitConfig
from packit_deploy.docker_helpers import write_to_container

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

            for instance in cfg.instances.values():
                vault.resolve_secrets(instance, cfg.vault.client())

        containers = []
        for instance in cfg.instances.values():
            containers.append(outpack_server_container(instance))
            containers.append(packit_db_container(instance))
            containers.append(packit_api_container(instance, cfg.orderly_runner))
            containers.append(packit_container(instance))

        if cfg.proxy is not None:
            proxy = proxy_container(cfg.proxy, cfg)
            containers.append(proxy)
            if cfg.acme_config is not None:
                hostnames = [cfg.proxy.hostname] + [
                    instance_hostname(name, cfg.proxy.hostname) for name in cfg.instances.keys() if name is not None
                ]
                acme_container = acme.acme_buddy_container(
                    cfg.acme_config,
                    "acme-buddy",
                    proxy.name_external(cfg.container_prefix),
                    "packit-tls",
                    ",".join(hostnames),
                )
                containers.append(acme_container)

        if cfg.orderly_runner is not None:
            containers.append(redis_container(cfg.orderly_runner))
            containers.append(orderly_runner_api_container(cfg.orderly_runner))
            containers.append(orderly_runner_worker_containers(cfg.orderly_runner))

        self.cfg = cfg
        self.obj = constellation.Constellation(
            "packit",
            cfg.container_prefix,
            containers,
            cfg.network,
            cfg.volumes,
            data=cfg,
            vault_config=cfg.vault,
        )

    def start(self, **kwargs):
        self.obj.start(**kwargs)

    def stop(self, **kwargs):
        self.obj.stop(**kwargs)

    def status(self):
        self.obj.status()


def instance_hostname(name: Optional[str], toplevel: str):
    if name is not None:
        return f"{name}.{toplevel}"
    else:
        return toplevel


def outpack_server_container(instance: config.PackitInstance) -> ConstellationContainer:
    name = instance.outpack_server.container_name
    mounts = [constellation.ConstellationVolumeMount(instance.volume_id_outpack, "/outpack")]
    return ConstellationContainer(name, instance.outpack_server.image, mounts=mounts)


def packit_db_container(instance: config.PackitInstance) -> ConstellationContainer:
    name = instance.packit_db.container_name

    mounts = [
        constellation.ConstellationVolumeMount(instance.volume_id_packit_db, "/pgdata"),
    ]
    if instance.volume_id_packit_db_backup is not None:
        mounts.append(constellation.ConstellationVolumeMount(instance.volume_id_packit_db_backup, "/pgbackup"))

    return ConstellationContainer(
        name,
        instance.packit_db.image,
        mounts=mounts,
        configure=packit_db_configure,
    )


def packit_db_configure(container, _cfg: PackitConfig):
    print("[packit-db] Configuring DB container")
    docker_util.exec_safely(container, ["wait-for-db"])


def packit_api_container(
    instance: config.PackitInstance, runner: Optional[config.OrderlyRunner]
) -> ConstellationContainer:
    name = instance.packit_api.container_name
    return ConstellationContainer(
        name,
        instance.packit_api.image,
        environment=packit_api_get_env(instance, runner),
    )


def packit_api_get_env(instance: config.PackitInstance, runner: Optional[config.OrderlyRunner]) -> dict[str, str]:
    env: dict[str, str] = {
        "PACKIT_DB_URL": instance.packit_db.jdbc_url,
        "PACKIT_DB_USER": instance.packit_db.user,
        "PACKIT_DB_PASSWORD": instance.packit_db.password,
        "PACKIT_OUTPACK_SERVER_URL": instance.outpack_server_url,
        "PACKIT_AUTH_ENABLED": "true" if instance.packit_api.auth is not None else "false",
        "PACKIT_BRAND_DARK_MODE_ENABLED": "true" if instance.brand.dark_mode_enabled else "false",
        "PACKIT_BRAND_LIGHT_MODE_ENABLED": "true" if instance.brand.light_mode_enabled else "false",
        "PACKIT_CORS_ALLOWED_ORIGINS": instance.packit_api.cors_allowed_origins,
        "PACKIT_BASE_URL": instance.packit_api.base_url,
        "PACKIT_DEVICE_FLOW_EXPIRY_SECONDS": "300",
        "PACKIT_DEVICE_AUTH_URL": f"{instance.packit_api.base_url.rstrip('/')}/device",
        "PACKIT_MANAGEMENT_PORT": str(instance.packit_api.management_port),
        "PACKIT_DEFAULT_ROLES": instance.packit_api.default_roles,
    }

    if instance.brand.logo is not None:
        env["PACKIT_BRAND_LOGO_NAME"] = instance.brand.logo.name
    if instance.brand.logo_alt_text is not None:
        env["PACKIT_BRAND_LOGO_ALT_TEXT"] = instance.brand.logo_alt_text
    if instance.brand.logo_link is not None:
        env["PACKIT_BRAND_LOGO_LINK"] = instance.brand.logo_link

    if instance.packit_api.auth is not None:
        env.update(
            {
                "PACKIT_AUTH_METHOD": instance.packit_api.auth.method,
                "PACKIT_JWT_EXPIRY_DAYS": str(instance.packit_api.auth.expiry_days),
                "PACKIT_JWT_SECRET": instance.packit_api.auth.jwt_secret,
            }
        )
        if instance.packit_api.auth.github is not None:
            github = instance.packit_api.auth.github
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

    if instance.packit_api.runner_git_url is not None:
        if runner is None:
            msg = "Runner is configured on the API but not available"
            raise Exception(msg)

        env["PACKIT_ORDERLY_RUNNER_URL"] = runner.api_url
        env["PACKIT_ORDERLY_RUNNER_REPOSITORY_URL"] = instance.packit_api.runner_git_url
        if instance.packit_api.runner_git_ssh_key is not None:
            env["PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY"] = instance.packit_api.runner_git_ssh_key
        env["PACKIT_ORDERLY_RUNNER_LOCATION_URL"] = instance.outpack_server_url

    return env


def packit_container(instance: config.PackitInstance):
    name = instance.packit_app.container_name
    mounts = []

    if instance.brand.logo is not None:
        logo_in_container = f"{config.APP_HTML_ROOT}/img/{instance.brand.logo.name}"
        mounts.append(constellation.ConstellationBindMount(str(instance.brand.logo), logo_in_container, read_only=True))

    if instance.brand.favicon is not None:
        favicon_in_container = f"{config.APP_HTML_ROOT}/{instance.brand.favicon.name}"
        mounts.append(
            constellation.ConstellationBindMount(str(instance.brand.favicon), favicon_in_container, read_only=True)
        )

    return ConstellationContainer(
        name,
        instance.packit_app.image,
        mounts=mounts,
        configure=lambda c, cfg: packit_configure(c, cfg, instance),
    )


def packit_configure(container, _cfg: PackitConfig, instance: config.PackitInstance):
    print("[instance] Configuring Packit container")
    if instance.brand.name is not None:
        # We configure the title tag of the index.html file here, rather than updating it dynamically with JS,
        # since using JS results in the page title visibly changing a number of seconds after the initial page load.
        substitute_file_content(
            container, f"{config.APP_HTML_ROOT}/index.html", r"(?<=<title>).*?(?=</title>)", instance.brand.name
        )
    if instance.brand.favicon is not None:
        substitute_file_content(
            container, f"{config.APP_HTML_ROOT}/index.html", r"favicon\.ico", instance.brand.favicon.name
        )

    new_css = ""
    if instance.brand.theme_light is not None:
        new_css += (
            ":root {\n"
            f"  --custom-accent: {instance.brand.theme_light.accent};\n"
            f"  --custom-accent-foreground: {instance.brand.theme_light.foreground};\n"
            "}\n"
        )
    if instance.brand.theme_dark is not None:
        new_css += (
            ".dark {\n"
            f"  --custom-accent: {instance.brand.theme_dark.accent};\n"
            f"  --custom-accent-foreground: {instance.brand.theme_dark.foreground};\n"
            "}\n"
        )
    overwrite_file(container, f"{config.APP_HTML_ROOT}/css/custom.css", new_css)


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


def proxy_container(proxy: config.Proxy, cfg: PackitConfig):
    name = proxy.container_name
    mounts = [constellation.ConstellationVolumeMount("proxy_logs", "/var/log/nginx")]
    if cfg.acme_config is not None:
        mounts.append(constellation.ConstellationVolumeMount("packit-tls", "/run/proxy"))
    ports = [proxy.port_http, proxy.port_https]
    if proxy.port_metrics is not None:
        ports.append(proxy.port_metrics)
    return ConstellationContainer(
        name,
        image=proxy.image,
        ports=ports,
        mounts=mounts,
        preconfigure=lambda container, cfg: proxy_preconfigure(container, cfg, proxy),
        configure=proxy_configure,
    )


def proxy_preconfigure(container: ConstellationContainer, cfg: PackitConfig, proxy: config.Proxy):
    print("[proxy] Preconfiguring proxy container")

    instances = [
        {
            "hostname": instance_hostname(name, proxy.hostname),
            "outpack_server_url": instance.outpack_server_url,
            "packit_app_url": instance.packit_app_url,
            "packit_api_url": instance.packit_api_url,
            "packit_api_management_url": instance.packit_api_management_url,
            "name": instance.brand.name or name,
        }
        for name, instance in cfg.instances.items()
    ]

    if None not in instances:
        index = JINJA_ENVIRONMENT.get_template("index.html.j2").render(instances=instances)
        write_to_container(index.encode("utf-8"), container, "/usr/share/nginx/html/index.html")
        index_hostname = proxy.hostname
    else:
        index_hostname = None

    nginx_conf = JINJA_ENVIRONMENT.get_template("nginx.conf.j2").render(
        instances=instances,
        port_http=proxy.port_http,
        port_https=proxy.port_https,
        port_metrics=proxy.port_metrics,
        index_hostname=index_hostname,
    )
    write_to_container(nginx_conf.encode("utf-8"), container, "/etc/nginx/conf.d/default.conf")


def proxy_configure(container: ConstellationContainer, cfg: PackitConfig):
    print("[proxy] Configuring proxy container")
    if cfg.acme_config is None:
        print("[proxy] Generating self-signed certificates for proxy")
        docker_util.exec_safely(container, ["self-signed-certificate", "/run/proxy"])


def redis_container(runner: config.OrderlyRunner) -> ConstellationContainer:
    name = runner.redis.container_name
    image = str(runner.redis.image)
    return ConstellationContainer(
        name,
        image,
        configure=redis_configure,
    )


def redis_configure(container, _cfg: PackitConfig):
    print("[redis] Waiting for redis to come up")
    write_to_container(WAIT_FOR_REDIS, container, "/wait_for_redis", mode=0o755)
    docker_util.exec_safely(container, ["/wait_for_redis"])


def orderly_runner_api_container(runner: config.OrderlyRunner):
    name = runner.api.container_name
    image = str(runner.api.image)
    env = orderly_runner_env(runner)
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


def orderly_runner_worker_containers(runner: config.OrderlyRunner):
    name = runner.worker.container_name
    image = str(runner.worker.image)
    count = runner.worker_count
    env = orderly_runner_env(runner)
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


def orderly_runner_env(runner: config.OrderlyRunner):
    return {
        "REDIS_URL": runner.redis_url,
        "ORDERLY_RUNNER_QUEUE_ID": "orderly.runner.queue",
        **runner.env,
    }


# Small script to wait for redis to come up
WAIT_FOR_REDIS = b"""#!/usr/bin/env bash
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
