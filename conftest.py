import vault_dev


# https://stackoverflow.com/a/35394239
def pytest_sessionstart(_):
    vault_dev.ensure_installed()
