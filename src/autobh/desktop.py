"""Private loopback server owned by the macOS app window."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .gui import make_server
from .appearance import read_appearance


def main(arguments=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--watch-parent", action="store_true")
    args = parser.parse_args(arguments)
    root = Path(os.environ.get("AUTOBH_HOME", str(Path.home() / ".autobh"))).expanduser().resolve()
    with make_server(root, port=0, demo=args.demo) as server:
        # A private ephemeral port avoids conflicting with an existing CLI GUI.
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}", "appearance": "system" if args.demo else read_appearance(root)}), flush=True)
        if args.watch_parent:
            def parent_closed():
                sys.stdin.buffer.read()
                server.shutdown()
            threading.Thread(target=parent_closed, daemon=True).start()
        def terminate(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
