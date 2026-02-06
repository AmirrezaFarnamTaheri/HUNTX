import argparse
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="MergeBot CLI")

    # Global arguments
    # Use distinct dest to avoid collision with subparser defaults
    parser.add_argument("--config", "-c", dest="global_config", help="Path to config file")
    parser.add_argument("--data-dir", help="Path to data directory")
    parser.add_argument("--db-path", help="Path to state database")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline")
    # Also allow config in subcommand for backward compatibility
    run_parser.add_argument("--config", "-c", dest="run_config", help="Path to config file")

    args = parser.parse_args()

    # Handle global environment setup
    if args.data_dir:
        os.environ["MERGEBOT_DATA_DIR"] = args.data_dir
    if args.db_path:
        os.environ["MERGEBOT_STATE_DB_PATH"] = args.db_path

    if args.command == "run":
        # Resolve config from either location
        config_path = args.global_config or args.run_config

        if not config_path:
            parser.error("the following arguments are required: --config/-c")

        # Delay import to allow env vars to take effect
        from .commands.run import run_command
        run_command(config_path)

if __name__ == "__main__":
    main()
