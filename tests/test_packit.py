from packit_deploy.config import PackitConfig
from packit_deploy.packit_constellation import packit_api_get_env


def test_environment_with_no_runner_contains_no_envvars():
    cfg = PackitConfig("config/noproxy")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert "PACKIT_ORDERLY_RUNNER_URL" not in env
    assert "PACKIT_ORDERLY_RUNNER_REPOSITORY_URL" not in env
    assert "PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY" not in env
    assert "PACKIT_ORDERLY_RUNNER_LOCATION_URL" not in env


def test_environment_with_public_runner_contains_url():
    cfg = PackitConfig("config/runner")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert env["PACKIT_ORDERLY_RUNNER_URL"] == "http://orderly-runner-api:8001"
    assert env["PACKIT_ORDERLY_RUNNER_REPOSITORY_URL"] == "https://github.com/reside-ic/orderly2-example.git"
    assert "PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY" not in env
    assert env["PACKIT_ORDERLY_RUNNER_LOCATION_URL"] == "http://outpack-server:8000"


def test_environment_with_private_runner_contains_url_and_key():
    cfg = PackitConfig("config/runner-private")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert env["PACKIT_ORDERLY_RUNNER_URL"] == "http://orderly-runner-api:8001"
    assert env["PACKIT_ORDERLY_RUNNER_REPOSITORY_URL"] == "git@github.com:reside-ic/orderly2-example-private.git"
    assert isinstance(env["PACKIT_ORDERLY_RUNNER_REPOSITORY_SSH_KEY"], str)
    assert env["PACKIT_ORDERLY_RUNNER_LOCATION_URL"] == "http://outpack-server:8000"


def test_default_cors_origins():
    cfg = PackitConfig("config/basicauth")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert env["PACKIT_CORS_ALLOWED_ORIGINS"] == "http://localhost*,https://localhost*"


def test_can_provide_cors_origins():
    cfg = PackitConfig("config/complete")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert env["PACKIT_CORS_ALLOWED_ORIGINS"] == "https://packit.example.com"


def test_can_set_auth_configuration():
    cfg = PackitConfig("config/noproxy")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert env["PACKIT_DEVICE_FLOW_EXPIRY_SECONDS"] == "300"
    assert env["PACKIT_DEVICE_AUTH_URL"] == "https://example.com/packit/device"


def test_can_set_base_url():
    cfg = PackitConfig("config/noproxy")
    env = packit_api_get_env(cfg.instances[None], cfg.orderly_runner)
    assert env["PACKIT_BASE_URL"] == "https://example.com/packit"
