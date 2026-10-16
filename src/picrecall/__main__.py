"""`python -m picrecall` 入口（与 console script `picrecall` 同一实现）。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
