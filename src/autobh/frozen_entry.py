"""Entry point for the distributable engine, including detached workers."""
from __future__ import annotations

import runpy
import sys


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ["--native"]:
        from autobh.runtime import NATIVE_MODULES
        if len(arguments) < 2 or arguments[1] not in NATIVE_MODULES:
            raise SystemExit("Unknown native tool")
        module = NATIVE_MODULES[arguments[1]]
        sys.argv = [module, *arguments[2:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return 0
    if arguments[:1] == ["--update-workers"]:
        from autobh.update_workers import main as update_workers_main
        return update_workers_main(arguments[1:])
    if arguments[:1] == ["--desktop-server"]:
        from autobh.desktop import main as desktop_main
        return desktop_main(arguments[1:])
    from autobh.cli import main as cli_main
    return cli_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
