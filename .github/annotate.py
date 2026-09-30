"""Print the tail of a log as a GitHub Actions error annotation (readable without signing in)."""

import sys

title, log = sys.argv[1], sys.argv[2]
with open(log, encoding="utf-8", errors="replace") as f:
    tail = f.read().splitlines()[-40:]
message = "%0A".join(line.replace("%", "%25").replace("\r", "") for line in tail)
print(f"::error title={title}::{message}")
