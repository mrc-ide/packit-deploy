# https://stackoverflow.com/a/35394239
import vault_dev


def pytest_sessionstart(session):  # noqa: ARG001
    vault_dev.ensure_installed()
