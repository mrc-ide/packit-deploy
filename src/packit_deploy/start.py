from config import build_config
from packit_constellation import packit_constellation


def start(path, extra=None, options=None, pull_images=False):
    cfg = build_config(path, extra, options)
    obj = packit_constellation(cfg)

    try:
        obj.start(pull_images=pull_images)

        return True
    except Exception:
        notifier.post("*Failed* deploy to {} :bomb:".format(cfg.web_url))
        raise


def config_save(cfg):
    print("Persisting configuration")
    cfg.save()
