"""A small, secure-by-default text-to-SQL agent for SQLite."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[tuple[object, ...]]


class SQLPlanner(Protocol):
    def generate(self, question: str, schema: str) -> str: ...


class UnsafeQueryError(ValueError):
    """Raised when generated SQL violates the read-only policy."""


def _has_multiple_statements(sql: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote:
            if character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == ";" and sql[index + 1 :].strip():
            return True
        index += 1
    return False


def validate_sql(sql: str) -> str:
    candidate = sql.strip()
    if not candidate:
        raise UnsafeQueryError("Generated SQL is empty")
    if _has_multiple_statements(candidate):
        raise UnsafeQueryError("Only a single SQL statement is allowed")
    first_token = candidate.split(None, 1)[0].upper()
    if first_token not in {"SELECT", "WITH"}:
        raise UnsafeQueryError("Only read-only SELECT queries are allowed")
    return candidate


class OpenAICompatiblePlanner:
    """Planner for OpenAI-compatible chat-completions endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ):
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, question: str, schema: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You translate data questions into one read-only SQLite SELECT statement. "
                        "Use only the supplied schema. Never use INSERT, UPDATE, DELETE, DROP, "
                        "ALTER, ATTACH, PRAGMA, or multiple statements. Return SQL only."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Schema:\n{schema}\n\nQuestion:\n{question}",
                },
            ],
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
            content = data["choices"][0]["message"]["content"].strip()
        except (HTTPError, URLError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Planner request failed: {error}") from error
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return content.strip()


class RuleBasedPlanner:
    """Deterministic offline planner used by the bundled demo."""

    def generate(self, question: str, schema: str) -> str:
        normalized = question.casefold()
        if "revenue" in normalized and ("product" in normalized or "products" in normalized):
            return """
                SELECT p.name AS product,
                       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
                FROM order_items AS oi
                JOIN products AS p ON p.id = oi.product_id
                GROUP BY p.id, p.name
                ORDER BY revenue DESC
            """
        raise ValueError(
            "The offline planner does not recognize that question. "
            "Configure an OpenAI-compatible planner or try a demo question."
        )


class TextToSQLAgent:
    def __init__(self, database: str | Path, planner: SQLPlanner | None = None, row_limit: int = 100):
        self.database = Path(database)
        if not self.database.is_file():
            raise FileNotFoundError(f"Database not found: {self.database}")
        self.planner = planner or RuleBasedPlanner()
        self.row_limit = row_limit

    def schema(self) -> str:
        with closing(sqlite3.connect(self.database)) as connection:
            rows = connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return "\n".join(row[0] for row in rows if row[0])

    def ask(self, question: str) -> QueryResult:
        sql = validate_sql(self.planner.generate(question, self.schema()))
        with closing(sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)) as connection:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(self.row_limit)
            columns = [column[0] for column in cursor.description or []]
        return QueryResult(sql=sql, columns=columns, rows=rows)


def create_demo_database(path: str | Path) -> Path:
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            """
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, ordered_at TEXT NOT NULL, status TEXT NOT NULL);
            CREATE TABLE order_items (
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL
            );
            INSERT INTO products VALUES
                (1, 'Mechanical Keyboard', 'Accessories'),
                (2, 'USB-C Dock', 'Accessories'),
                (3, '27-inch Monitor', 'Displays');
            INSERT INTO orders VALUES
                (1, '2026-01-10', 'completed'),
                (2, '2026-02-14', 'completed'),
                (3, '2026-03-02', 'completed');
            INSERT INTO order_items VALUES
                (1, 1, 3, 120.00),
                (1, 2, 1, 180.00),
                (2, 1, 2, 120.00),
                (2, 3, 1, 299.00),
                (3, 2, 2, 180.00);
            """
        )
    return database


__all__ = [
    "OpenAICompatiblePlanner",
    "QueryResult",
    "RuleBasedPlanner",
    "SQLPlanner",
    "TextToSQLAgent",
    "UnsafeQueryError",
    "create_demo_database",
    "validate_sql",
]
