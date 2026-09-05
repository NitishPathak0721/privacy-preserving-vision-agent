# Local bridge between the Chrome extension and the Python privacy firewall.

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import sanitize_page
from agent.privacy.sanitizer import sanitize_page_text


HOST = "127.0.0.1"
PORT = 8765


class BridgeHandler(BaseHTTPRequestHandler):
    # Disable default HTTP request logging.
    def log_message(self, format, *args):
        return

    # Return a JSON response.
    def send_json(self, status_code, payload):
        body = json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )
        self.end_headers()

        self.wfile.write(body)

    # Handle CORS preflight requests.
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )
        self.end_headers()

    # Check whether the bridge is alive.
    def do_GET(self):
        if self.path != "/health":
            self.send_json(
                404,
                {
                    "success": False,
                    "error": "Not found.",
                },
            )
            return

        self.send_json(
            200,
            {
                "success": True,
                "service": "privacy-bridge",
                "privacy_firewall": "active",
            },
        )

    # Process browser context through the local privacy firewall.
    def do_POST(self):
        if self.path != "/inspect":
            self.send_json(
                404,
                {
                    "success": False,
                    "error": "Not found.",
                },
            )
            return

        try:
            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            if content_length <= 0:
                self.send_json(
                    400,
                    {
                        "success": False,
                        "error": "Empty request body.",
                    },
                )
                return

            if content_length > 5 * 1024 * 1024:
                self.send_json(
                    413,
                    {
                        "success": False,
                        "error": "Request body too large.",
                    },
                )
                return

            raw_body = self.rfile.read(
                content_length
            )

            payload = json.loads(
                raw_body.decode("utf-8")
            )

            elements = payload.get(
                "elements",
                [],
            )

            page_text = payload.get(
                "page_text",
                "",
            )

            if not isinstance(elements, list):
                self.send_json(
                    400,
                    {
                        "success": False,
                        "error": "elements must be a list.",
                    },
                )
                return

            if not isinstance(page_text, str):
                page_text = ""

            findings = inspect_page(
                elements,
                page_text,
            )

            sanitized_elements = sanitize_page(
                elements,
                findings,
            )

            sanitized_text = sanitize_page_text(
                page_text,
                findings,
            )

            finding_types = sorted(
                {
                    finding.get("type")
                    for finding in findings
                    if finding.get("type")
                }
            )

            credential_count = sum(
                1
                for finding in findings
                if finding.get("type") == "credential"
            )

            pii_count = len(findings) - credential_count

            self.send_json(
                200,
                {
                    "success": True,
                    "privacy": {
                        "findings": len(findings),
                        "pii_findings": pii_count,
                        "credential_findings": credential_count,
                        "types": finding_types,
                    },
                    "context": {
                        "url": payload.get(
                            "url",
                            "",
                        ),
                        "title": payload.get(
                            "title",
                            "",
                        ),
                        "elements": sanitized_elements,
                        "page_text": sanitized_text,
                    },
                },
            )

        except json.JSONDecodeError:
            self.send_json(
                400,
                {
                    "success": False,
                    "error": "Invalid JSON.",
                },
            )

        except Exception as error:
            self.send_json(
                500,
                {
                    "success": False,
                    "error": str(error),
                },
            )


def main():
    server = ThreadingHTTPServer(
        (HOST, PORT),
        BridgeHandler,
    )

    print(
        f"Privacy bridge running at "
        f"http://{HOST}:{PORT}"
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()