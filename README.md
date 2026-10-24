# Text-to-SQL Agent

A dependency-free Python/SQLite agent that turns natural-language questions into SQL, shows the generated query, and executes it through a read-only database connection.

## Why this design is efficient

- Sends only the database schema and current question to the planner.
- Uses deterministic `temperature: 0` for OpenAI-compatible models.
- Fetches at most the configured row limit instead of materializing every row.
- Runs locally without credentials using a deterministic demo planner.
- Keeps SQL planning behind a small protocol, so the model provider can be swapped.

## Quick start

Requires Python 3.11+.

```bash
python -m text_to_sql_agent init --db demo.db
python -m text_to_sql_agent ask --db demo.db "Which products generated the most revenue?"
python -m text_to_sql_agent schema --db demo.db
```

Install the command globally or in a virtual environment:

```bash
python -m pip install -e .
text-to-sql init --db demo.db
text-to-sql ask --db demo.db "Which products generated the most revenue?"
```

## Use an OpenAI-compatible model

Set these environment variables (OpenAI, Azure proxy, Ollama gateway, vLLM, or another compatible `/chat/completions` endpoint):

```bash
export TEXT2SQL_BASE_URL="https://your-host/v1"
export TEXT2SQL_API_KEY="..."
export TEXT2SQL_MODEL="your-model"
python -m text_to_sql_agent ask --planner openai --db your.db "Revenue by month"
```

The live model path is implemented but requires your endpoint and credentials; the bundled tests use a local HTTP server and make no paid API calls.

## Safety boundaries

1. The model receives schema DDL, not table contents.
2. Only one statement beginning with `SELECT` or `WITH` is accepted.
3. The SQLite database is opened with `mode=ro` for execution.
4. Results are capped by `--limit` (default: 100 rows).
5. SQL is always printed so a caller can add a human-approval step.

This is a read-only analytics agent, not a database administration agent. For production, also use a database account restricted to approved views, add query timeouts/cost controls, redact sensitive schema names, and log approvals.

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite covers the offline end-to-end flow, CLI execution, write rejection, multi-statement rejection, and the OpenAI-compatible HTTP contract.
