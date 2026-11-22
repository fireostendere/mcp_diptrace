from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("diptrace-mcp")
except PackageNotFoundError:
    __version__ = "2.0.0"

__all__ = ["__version__"]
