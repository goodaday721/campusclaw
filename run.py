"""Application entry point.

Validates required environment variables before starting.
Exits with code 1 if any required variable is missing.
"""
import sys

from app.config import Config, ConfigError


def main() -> None:
    try:
        config = Config()
    except ConfigError as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        sys.exit(1)

    from app import create_app

    app = create_app(config)
    app.run(host="0.0.0.0", port=config.port, debug=False)


if __name__ == "__main__":
    main()
