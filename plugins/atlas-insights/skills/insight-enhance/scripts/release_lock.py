#!/usr/bin/env python3
"""SSH-shim → archie. Forwards this invocation to archie's canonical script.
The corpus owns the implementation; hermes is a thin client. Any future change
on archie propagates automatically — zero drift."""
import os, subprocess, sys

remote_path = os.path.abspath(__file__)  # /home/anombyte path is identical on both hosts
result = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30",
     "archie", "python3", remote_path, *sys.argv[1:]],
)
sys.exit(result.returncode)
