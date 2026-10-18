"""PyInstaller 打包入口（开发时用主目录的 main.py）。"""

import sys

from longon_qte.app import main

if __name__ == "__main__":
    sys.exit(main())
