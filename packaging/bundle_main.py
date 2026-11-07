"""Entry point of the .mcpb bundle: Claude Desktop runs `uv run --directory <bundle> --frozen --no-dev bundle_main.py`;
uv installs Python + the locked dependencies (incl. this package from src/) on first start."""

import os

os.environ.setdefault("SCHNIPPO_BUNDLE", "1")

from schnippo.server import main  # noqa: E402

main()
