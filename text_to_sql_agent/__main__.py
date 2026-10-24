from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import OpenAICompatiblePlanner, TextToSQLAgent, create_demo_database


def _format_table(columns: list[str], rows: list[tuple[object, ...]]) -> str:
    values = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in values:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    header = " | ".join(column.ljust(width) for column, width in zip(columns, widths))
    separator = "-+-".join("-" * width for width in widths)
    body = [" | ".join(value.ljust(width) for value, width in zip(row, widths)) for row in values]
    return "\n".join([header, separator, *body])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secure text-to-SQL agent for SQLite")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create the e-commerce demo database")
    init.add_argument("--db", type=Path, default=Path("demo.db"))

    ask = commands.add_parser("ask", help="Ask a natural-language data question")
    ask.add_argument("--db", type=Path, default=Path("demo.db"))
    ask.add_argument("--limit", type=int, default=100)
    ask.add_argument(
        "--planner",
        choices=("offline", "openai"),
        default="offline",
        help="Use deterministic demo rules or an OpenAI-compatible endpoint",
    )
    ask.add_argument("question")

    schema = commands.add_parser("schema", help="Show the schema provided to the planner")
    schema.add_argument("--db", type=Path, default=Path("demo.db"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            create_demo_database(args.db)
            print(f"Created demo database: {args.db}")
            return 0

        planner = None
        if args.command == "ask" and args.planner == "openai":
            required = {
                "TEXT2SQL_BASE_URL": os.getenv("TEXT2SQL_BASE_URL"),
                "TEXT2SQL_API_KEY": os.getenv("TEXT2SQL_API_KEY"),
                "TEXT2SQL_MODEL": os.getenv("TEXT2SQL_MODEL"),
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"Missing environment variables: {', '.join(missing)}")
            planner = OpenAICompatiblePlanner(
                base_url=required["TEXT2SQL_BASE_URL"],
                api_key=required["TEXT2SQL_API_KEY"],
                model=required["TEXT2SQL_MODEL"],
            )
        agent = TextToSQLAgent(
            args.db,
            planner=planner,
            row_limit=getattr(args, "limit", 100),
        )
        if args.command == "schema":
            print(agent.schema())
            return 0

        result = agent.ask(args.question)
        print(f"SQL:\n{result.sql}\n")
        print(_format_table(result.columns, result.rows))
        print(f"\nRows: {len(result.rows)}")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
