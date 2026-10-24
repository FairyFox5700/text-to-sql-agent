import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from text_to_sql_agent import (
    TextToSQLAgent,
    UnsafeQueryError,
    create_demo_database,
)


class FixedPlanner:
    def __init__(self, sql: str):
        self.sql = sql

    def generate(self, question: str, schema: str) -> str:
        return self.sql


class AgentEndToEndTests(unittest.TestCase):
    def test_revenue_question_returns_ranked_products(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "shop.db"
            create_demo_database(database)
            agent = TextToSQLAgent(database)

            result = agent.ask("Which products generated the most revenue?")

            self.assertIn("SELECT", result.sql.upper())
            self.assertEqual(["product", "revenue"], result.columns)
            self.assertEqual("Mechanical Keyboard", result.rows[0][0])
            self.assertGreater(result.rows[0][1], result.rows[1][1])

    def test_write_query_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "shop.db"
            create_demo_database(database)
            agent = TextToSQLAgent(database, planner=FixedPlanner("DROP TABLE products"))

            with self.assertRaisesRegex(UnsafeQueryError, "read-only"):
                agent.ask("Delete all products")

            with closing(sqlite3.connect(database)) as connection:
                count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            self.assertEqual(3, count)

    def test_multiple_statements_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "shop.db"
            create_demo_database(database)
            agent = TextToSQLAgent(
                database,
                planner=FixedPlanner("SELECT * FROM products; DROP TABLE products"),
            )

            with self.assertRaisesRegex(UnsafeQueryError, "single"):
                agent.ask("Show and then delete products")

    def test_cli_initializes_database_and_answers_question(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "shop.db"
            init = subprocess.run(
                [sys.executable, "-m", "text_to_sql_agent", "init", "--db", str(database)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, init.returncode, init.stderr)

            ask = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "text_to_sql_agent",
                    "ask",
                    "--db",
                    str(database),
                    "Which products generated the most revenue?",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, ask.returncode, ask.stderr)
            self.assertIn("Mechanical Keyboard", ask.stdout)
            self.assertIn("SQL:", ask.stdout)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.db"

            with self.assertRaisesRegex(FileNotFoundError, "Database not found"):
                TextToSQLAgent(database)

            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
