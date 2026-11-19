"""One-off for release ep5-20261119T021135Z (same rule as the fixed installer): make the parents that
service users traverse 0755. Changes directory modes only; file modes (*.env 0600) are untouched."""
import json
from pathlib import Path
paths = ["/usr/local/libexec", "/var/log/pedidos360", "/etc/pedidos360", "/etc/pedidos360/tls", "/opt/pedidos360"]
before = {p: oct(Path(p).stat().st_mode & 0o777) for p in paths}
for p in paths:
    Path(p).chmod(0o755)
print(json.dumps({"before": before, "after": {p: oct(Path(p).stat().st_mode & 0o777) for p in paths},
                  "envFiles": {str(f): oct(f.stat().st_mode & 0o777) for f in sorted(Path("/etc/pedidos360").glob("*.env"))}}))
