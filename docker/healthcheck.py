import os
import sys
from urllib.error import URLError
from urllib.request import urlopen

url = f"http://127.0.0.1:{os.getenv('PORT', '8000')}/health/"

try:
    with urlopen(url, timeout=3) as response:
        if response.status != 200:
            raise RuntimeError(f"health endpoint returned HTTP {response.status}")
except (OSError, RuntimeError, URLError) as exc:
    print(f"Healthcheck failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
