"""Entrypoint for `python -m waylura_content_tools`."""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
