import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from text_to_sql_agent import OpenAICompatiblePlanner


class _Handler(BaseHTTPRequestHandler):
    request_body = None

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).request_body = json.loads(self.rfile.read(length))
        payload = {
            "choices": [
                {"message": {"content": "```sql\nSELECT name FROM products ORDER BY name\n```"}}
            ]
        }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class OpenAICompatiblePlannerTests(unittest.TestCase):
    def test_sends_schema_and_returns_clean_sql(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            planner = OpenAICompatiblePlanner(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_key="test-key",
                model="test-model",
            )
            sql = planner.generate("List products", "CREATE TABLE products (name TEXT)")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

        self.assertEqual("SELECT name FROM products ORDER BY name", sql)
        request = _Handler.request_body
        self.assertEqual("test-model", request["model"])
        prompt = request["messages"][1]["content"]
        self.assertIn("List products", prompt)
        self.assertIn("CREATE TABLE products", prompt)


if __name__ == "__main__":
    unittest.main()
