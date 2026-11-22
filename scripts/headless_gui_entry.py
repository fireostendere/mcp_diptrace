# ruff: noqa: I001

import sys


def _main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"native-cam", "native-cad-worker"}:
        dispatch = sys.argv.pop(1)
        if dispatch == "native-cam":
            from diptrace_mcp.native_cam_export import main
        else:
            from diptrace_mcp.native_cad import main
        return main()

    if len(sys.argv) > 1 and sys.argv[1] in {"schematic-acceptance", "xml-export"}:
        dispatch = sys.argv.pop(1)
        if dispatch == "schematic-acceptance":
            from diptrace_mcp.schematic_native_acceptance import main
        else:
            from diptrace_mcp.native_xml_export import main
        return main()

    if len(sys.argv) > 1 and sys.argv[1] == "cinematic":
        from diptrace_mcp.cinematic_recording import headless_main

        return headless_main(sys.argv[2:])

    if len(sys.argv) > 1 and sys.argv[1] == "pcb-acceptance":
        from diptrace_mcp.pcb_native_acceptance import main

        return main(sys.argv[2:])

    from diptrace_mcp.headless_gui import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_main())
