"""Entry point for running Garava as a module: python -m garava"""

from dotenv import load_dotenv

# Load .env file if present (before importing anything else)
load_dotenv()

from garava.cli.commands import cli  # noqa: E402

if __name__ == "__main__":
    cli()
