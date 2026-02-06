import argparse
import sys
from .commands.run import run_command

def main():
    parser = argparse.ArgumentParser(description="MergeBot CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline")
    run_parser.add_argument("--config", "-c", required=True, help="Path to config file")

    args = parser.parse_args()

    if args.command == "run":
        run_command(args.config)

if __name__ == "__main__":
    main()
