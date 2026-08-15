# ruff: noqa: I001

import sys


def _main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "cinematic":
        from diptrace_mcp.cinematic_recording import headless_main

        return headless_main(sys.argv[2:])

    from diptrace_mcp.headless_gui import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_main())
