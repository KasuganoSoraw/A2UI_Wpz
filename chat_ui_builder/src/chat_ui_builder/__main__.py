from __future__ import annotations

import uvicorn

from chat_ui_builder.api.app import app
from chat_ui_builder.core.settings import settings


def main() -> None:
  uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
  main()
