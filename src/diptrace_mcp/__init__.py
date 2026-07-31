from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("diptrace-mcp")
except PackageNotFoundError:
    __version__ = "0.1.0"

from ._live_path_compat import install as _install_live_path_compat

_install_live_path_compat()
del _install_live_path_compat

__all__ = ["__version__"]
