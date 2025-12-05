import os.path
from io import BytesIO
from tarfile import TarFile, TarInfo

import docker
from docker.models.containers import Container


# There is an annoyance with docker and the requests library, where
# when the http handle is reclaimed a warning is printed.  It makes
# the test log almost impossible to read.
#
# https://github.com/kennethreitz/requests/issues/1882#issuecomment-52281285
# https://github.com/kennethreitz/requests/issues/3912
#
# This little helper can be used with python's with statement as
#
#      with DockerClient() as cl:
#        cl.containers...
#
# and will close *most* unused handles on exit.  It's easier to look
# at than endless try/finally blocks everywhere.
class DockerClient:
    def __enter__(self):
        self.client = docker.client.from_env()
        return self.client

    def __exit__(self, t, value, traceback):
        pass


# This is pretty similar to constellation's string_into_container except it
# correctly sets ownership and mode of the file.
#
# string_into_container creates the tar file by writing the files to disk and
# adding them to the tarball. As a result, the file inherits the UID of the
# packit-deploy process, which is definitely wrong.
#
# It does not require executing anything in the container, meaning it works in
# a preconfigure callback, unlike executing `chmod` in the container to fix
# them.
#
# TODO: move this into constellation
def write_to_container(data: bytes, container: Container, path: str, *, mode: int = 0o644):
    buffer = BytesIO()
    with TarFile(fileobj=buffer, mode="w") as tar:
        info = TarInfo(name=os.path.basename(path))
        info.mode = mode
        info.size = len(data)
        tar.addfile(info, BytesIO(data))

    container.put_archive(os.path.dirname(path), buffer.getvalue())
