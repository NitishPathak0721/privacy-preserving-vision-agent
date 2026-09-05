import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agent.privacy.firewall import inspect_page
from agent.privacy.sanitizer import (
    sanitize_page,
    sanitize_page_text,
)


HOST = "127.0.0.1"
PORT = 8765
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen2.5vl:3b"


# Send a JSON HTTP response.
def send_json_response(handler, status_code, payload):
    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8",
    )
    handler.send_header(
        "Access-Control-Allow-Origin",
        "*",
    )
    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type",
    )
    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, OPTIONS",
    )
    handler.send_header(
        "Content-Length",
        str(len(body)),
    )
    handler.end_headers()
    handler.wfile.write(body)


# Read a JSON request body.
def read_json_body(handler):
    content_length = int(
        handler.headers.get(
            "Content-Length",
            "0",
        )
    )

    raw_body = handler.rfile.read(
        content_length
    )

    return json.loads(
        raw_body.decode("utf-8")
    )


# Check whether the configured Ollama model exists.
def check_ollama():
    try:
        request = Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
        )

        with urlopen(
            request,
            timeout=5,
        ) as response:
            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        models = data.get(
            "models",
            [],
        )

        for model in models:
            if model.get("name") == OLLAMA_MODEL:
                return True

        return False

    except Exception:
        return False


# Normalize browser context.
def normalize_context(payload):
    elements = payload.get(
        "elements",
        [],
    )

    if not isinstance(
        elements,
        list,
    ):
        elements = []

    normalized_elements = []

    for element in elements:
        if not isinstance(
            element,
            dict,
        ):
            continue

        normalized_elements.append(
            {
                "tag": element.get(
                    "tag",
                    "",
                ),
                "text": element.get(
                    "text",
                    "",
                ),
                "aria_label": element.get(
                    "aria_label",
                    "",
                ),
                "placeholder": element.get(
                    "placeholder",
                    "",
                ),
                "name": element.get(
                    "name",
                    "",
                ),
                "id": element.get(
                    "id",
                    "",
                ),
                "input_type": element.get(
                    "input_type",
                    "",
                ),
                "value": element.get(
                    "value",
                    "",
                ),
                "enabled": element.get(
                    "enabled",
                    True,
                ),
                "box": element.get(
                    "box",
                    None,
                ),
            }
        )

    page_text = payload.get(
        "page_text",
        "",
    )

    if not isinstance(
        page_text,
        str,
    ):
        page_text = ""

    return {
        "url": str(
            payload.get(
                "url",
                "",
            )
        ),
        "title": str(
            payload.get(
                "title",
                "",
            )
        ),
        "elements": normalized_elements,
        "page_text": page_text,
    }


# Sanitize browser context before model access.
def sanitize_context(payload):
    context = normalize_context(
        payload
    )

    elements = context[
        "elements"
    ]

    page_text = context[
        "page_text"
    ]

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

    pii_findings = [
        finding
        for finding in findings
        if finding.get("category") == "pii"
        or finding.get("type")
        in {
            "email",
            "phone",
            "credit_card",
            "aadhaar",
            "pan",
        }
    ]

    credential_findings = [
        finding
        for finding in findings
        if finding.get("category")
        == "credential"
        or finding.get("type")
        == "credential"
    ]

    finding_types = []

    for finding in findings:
        finding_type = finding.get(
            "type"
        )

        if finding_type:
            finding_types.append(
                finding_type
            )

    return {
        "context": {
            "url": context["url"],
            "title": context["title"],
            "elements": sanitized_elements,
            "page_text": sanitized_text,
        },
        "privacy": {
            "findings": len(findings),
            "pii_findings": len(
                pii_findings
            ),
            "credential_findings": len(
                credential_findings
            ),
            "types": list(
                dict.fromkeys(
                    finding_types
                )
            ),
        },
    }


# Build the strict local-agent system prompt.
def build_system_prompt():
    return """
You are a local privacy-preserving browser agent.

You receive ONLY privacy-sanitized browser context.

Your job is to complete the user's browser task using the minimum number of safe actions.

Return ONLY valid JSON.

NEVER return coordinates.
NEVER return x/y positions.
NEVER return mouse positions.
NEVER return screenshots.
NEVER return markdown.
NEVER return prose outside JSON.

The ONLY valid response schema is:

{
  "status": "ready",
  "reason": "short explanation",
  "actions": [
    {
      "action": "click",
      "target": "exact visible target"
    }
  ]
}

For typing:

{
  "status": "ready",
  "reason": "short explanation",
  "actions": [
    {
      "action": "type",
      "target": "exact visible input",
      "value": "exact value explicitly provided by the user"
    }
  ]
}

If the task is already complete:

{
  "status": "completed",
  "reason": "short explanation",
  "actions": []
}

If the task cannot safely be completed:

{
  "status": "blocked",
  "reason": "short explanation",
  "actions": []
}

Allowed browser actions are ONLY:

1. click
2. type

Click actions MUST contain:
- action
- target

Click actions MUST NOT contain:
- value
- coordinate
- x
- y

Type actions MUST contain:
- action
- target
- value

Type actions MUST NOT contain:
- coordinate
- x
- y

Security rules:

1. Inspect the CURRENT browser state before deciding anything.
2. Use only information present in the sanitized context.
3. Never invent personal information.
4. Never invent a value that the user did not provide.
5. Never type into password or credential fields.
6. Never type [EMAIL].
7. Never type [PHONE].
8. Never type [CREDIT_CARD].
9. Never type [AADHAAR].
10. Never type [PAN].
11. Never type [REDACTED].
12. Sanitized values are unavailable private information.
13. The existence of a button does not mean it should be clicked.
14. Prefer the exact visible button text as the click target.
15. Prefer the exact visible placeholder, name, ID, or label as a type target.
16. Use the minimum number of actions.
17. Do not repeat an action when its result is already visible.
18. Only return completed when the CURRENT browser state proves completion.
19. If required user information is missing, return blocked.
20. Never use coordinate-based browser control.
21. Never output an action not supported by the schema.
22. Return JSON only.

Example:

User task:
Click the Search button.

Current page:
A visible button has text "Search".

Correct response:

{
  "status": "ready",
  "reason": "The Search button is visible and can be clicked.",
  "actions": [
    {
      "action": "click",
      "target": "Search"
    }
  ]
}

Incorrect response:

{
  "action": "click",
  "coordinate": [100, 100]
}

The incorrect response is NEVER allowed.

If the model is uncertain about the target, use the visible target text from the sanitized DOM instead of coordinates.
""".strip()


# Build the model user prompt.
def build_user_prompt(
    task,
    context,
):
    elements_json = json.dumps(
        context["elements"],
        ensure_ascii=False,
        indent=2,
    )

    return f"""
User task:
{task}

Current sanitized browser URL:
{context["url"]}

Current page title:
{context["title"]}

Current sanitized interactive elements:
{elements_json}

Current sanitized visible page text:
{context["page_text"]}

Determine the minimum safe action required.

IMPORTANT:

Return ONLY one JSON object.

The response MUST contain:
status
reason
actions

The status MUST be one of:
ready
completed
blocked

Every action MUST use only:
click
type

For click:
target is required.
value is forbidden.

For type:
target is required.
value is required.

Coordinates are forbidden.

If you cannot identify a safe visible target, return:

{{
  "status": "blocked",
  "reason": "A safe visible target could not be identified.",
  "actions": []
}}
""".strip()


# Extract the first JSON object from model output.
def extract_json_object(raw_text):
    if not isinstance(
        raw_text,
        str,
    ):
        return None

    text = raw_text.strip()

    # Remove accidental markdown fences.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()

    for index, character in enumerate(text):
        if character != "{":
            continue

        try:
            value, _ = decoder.raw_decode(
                text[index:]
            )

            if isinstance(
                value,
                dict,
            ):
                return value

        except json.JSONDecodeError:
            continue

    return None


# Validate and normalize the model response.
def validate_model_plan(plan):
    if not isinstance(
        plan,
        dict,
    ):
        return {
            "status": "blocked",
            "reason":
                "The local model returned an invalid response.",
            "actions": [],
        }

    status = plan.get(
        "status",
        "",
    )

    reason = plan.get(
        "reason",
        "",
    )

    actions = plan.get(
        "actions",
        [],
    )

    # Reject legacy coordinate-based model output.
    if (
        "coordinate" in plan
        or "coordinates" in plan
        or "x" in plan
        or "y" in plan
    ):
        return {
            "status": "blocked",
            "reason":
                "The local model returned an unsafe coordinate-based action.",
            "actions": [],
        }

    if status not in {
        "ready",
        "completed",
        "blocked",
    }:
        return {
            "status": "blocked",
            "reason":
                "The local model returned an unsupported status.",
            "actions": [],
        }

    if not isinstance(
        reason,
        str,
    ):
        reason = ""

    if not isinstance(
        actions,
        list,
    ):
        return {
            "status": "blocked",
            "reason":
                "The local model returned invalid actions.",
            "actions": [],
        }

    normalized_actions = []

    for action in actions:
        if not isinstance(
            action,
            dict,
        ):
            return {
                "status": "blocked",
                "reason":
                    "The local model returned an invalid action.",
                "actions": [],
            }

        action_type = action.get(
            "action",
            "",
        )

        target = action.get(
            "target",
            "",
        )

        if action_type not in {
            "click",
            "type",
        }:
            return {
                "status": "blocked",
                "reason":
                    "The local model returned an unsupported browser action.",
                "actions": [],
            }

        if not isinstance(
            target,
            str,
        ) or not target.strip():
            return {
                "status": "blocked",
                "reason":
                    "The local model returned an action without a target.",
                "actions": [],
            }

        if (
            "coordinate" in action
            or "coordinates" in action
            or "x" in action
            or "y" in action
        ):
            return {
                "status": "blocked",
                "reason":
                    "Coordinate-based browser actions are forbidden.",
                "actions": [],
            }

        normalized_action = {
            "action": action_type,
            "target": target.strip(),
        }

        if action_type == "type":
            value = action.get(
                "value"
            )

            if not isinstance(
                value,
                str,
            ):
                return {
                    "status": "blocked",
                    "reason":
                        "The type action does not contain a valid value.",
                    "actions": [],
                }

            if value in {
                "[EMAIL]",
                "[PHONE]",
                "[CREDIT_CARD]",
                "[AADHAAR]",
                "[PAN]",
                "[REDACTED]",
            }:
                return {
                    "status": "blocked",
                    "reason":
                        "The model attempted to type sanitized private information.",
                    "actions": [],
                }

            normalized_action[
                "value"
            ] = value

        elif "value" in action:
            return {
                "status": "blocked",
                "reason":
                    "Click actions cannot contain a value.",
                "actions": [],
            }

        normalized_actions.append(
            normalized_action
        )

    if status == "completed":
        if normalized_actions:
            return {
                "status": "blocked",
                "reason":
                    "A completed response cannot contain browser actions.",
                "actions": [],
            }

    if status == "blocked":
        return {
            "status": "blocked",
            "reason":
                reason
                or "The local agent blocked the task.",
            "actions": [],
        }

    return {
        "status": "ready",
        "reason": reason,
        "actions": normalized_actions,
    }


# Call the local Ollama model.
def call_ollama(
    system_message,
    user_message,
):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_message,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0,
        },
        "format": "json",
    }

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        OLLAMA_URL,
        data=body,
        headers={
            "Content-Type":
                "application/json",
        },
        method="POST",
    )

    with urlopen(
        request,
        timeout=120,
    ) as response:
        raw = response.read().decode(
            "utf-8"
        )

    data = json.loads(raw)

    message = data.get(
        "message",
        {},
    )

    if not isinstance(
        message,
        dict,
    ):
        message = {}

    return message.get(
        "content",
        "",
    )


# Detect tasks that require user-specific information.
def extract_missing_user_information(task):
    if not isinstance(
        task,
        str,
    ):
        return ""

    patterns = [
        (
            r"\bmy\s+name\b",
            "your name",
        ),
        (
            r"\bmy\s+email\b",
            "your email",
        ),
        (
            r"\bmy\s+phone\b",
            "your phone number",
        ),
        (
            r"\bmy\s+address\b",
            "your address",
        ),
        (
            r"\bmy\s+password\b",
            "your password",
        ),
        (
            r"\bmy\s+credit\s+card\b",
            "your credit card information",
        ),
    ]

    for pattern, description in patterns:
        if re.search(
            pattern,
            task,
            re.IGNORECASE,
        ):
            return description

    return ""


# Extract explicit type requirements from the user task.
def extract_type_requirements(task):
    if not isinstance(
        task,
        str,
    ):
        return []

    requirements = []

    patterns = [
        re.compile(
            r"\btype\s+(?P<value>.+?)\s+into\s+(?P<target>.+?)(?:\s+and\s+then\s+click\s+.+)?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"\benter\s+(?P<value>.+?)\s+into\s+(?P<target>.+?)(?:\s+and\s+then\s+click\s+.+)?$",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bfill\s+(?P<target>.+?)\s+with\s+(?P<value>.+?)(?:\s+and\s+then\s+click\s+.+)?$",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(task)

        if not match:
            continue

        value = match.group(
            "value"
        ).strip()

        target = match.group(
            "target"
        ).strip()

        target = re.sub(
            r"\s+and\s+then\s+click\s+.+$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()

        if value and target:
            requirements.append(
                {
                    "value": value,
                    "target": target,
                }
            )

    return requirements


# Find an element matching a target description.
def find_matching_element(
    elements,
    target,
):
    if not isinstance(
        target,
        str,
    ):
        return None

    target_normalized = target.strip().lower()

    if not target_normalized:
        return None

    for element in elements:
        if not isinstance(
            element,
            dict,
        ):
            continue

        candidates = [
            element.get("text", ""),
            element.get("aria_label", ""),
            element.get("placeholder", ""),
            element.get("name", ""),
            element.get("id", ""),
        ]

        for candidate in candidates:
            if (
                isinstance(
                    candidate,
                    str,
                )
                and candidate.strip().lower()
                == target_normalized
            ):
                return element

    for element in elements:
        if not isinstance(
            element,
            dict,
        ):
            continue

        candidates = [
            element.get("text", ""),
            element.get("aria_label", ""),
            element.get("placeholder", ""),
            element.get("name", ""),
            element.get("id", ""),
        ]

        for candidate in candidates:
            if not isinstance(
                candidate,
                str,
            ):
                continue

            if (
                target_normalized
                in candidate.strip().lower()
                or candidate.strip().lower()
                in target_normalized
            ):
                return element

    return None


# Extract an explicit click target from the user task.
def extract_click_target(task):
    if not isinstance(
        task,
        str,
    ):
        return ""

    patterns = [
        re.compile(
            r"\bclick\s+(?:the\s+)?(.+?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:and|then)\s+click\s+(?:the\s+)?(.+?)\s*$",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(task)

        if not match:
            continue

        target = match.group(
            1
        ).strip()

        target = re.sub(
            r"^(?:button|link|field|input)\s+(?:with\s+text\s+)?",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()

        if target:
            return target

    return ""


# Enforce explicit type requirements against the current browser state.
def enforce_type_requirements(
    task,
    context,
    plan,
):
    requirements = extract_type_requirements(
        task
    )

    if not requirements:
        click_target = extract_click_target(
            task
        )

        if click_target:
            element = find_matching_element(
                context.get(
                    "elements",
                    [],
                ),
                click_target,
            )

            if element:
                actual_target = (
                    element.get("text")
                    or element.get(
                        "aria_label"
                    )
                    or element.get(
                        "placeholder"
                    )
                    or element.get("name")
                    or element.get("id")
                    or click_target
                )

                return {
                    "status": "ready",
                    "reason":
                        "The requested visible target is available.",
                    "actions": [
                        {
                            "action": "click",
                            "target": actual_target,
                        }
                    ],
                }

        return plan

    elements = context.get(
        "elements",
        [],
    )

    for requirement in requirements:
        expected_value = requirement[
            "value"
        ]

        target_description = requirement[
            "target"
        ]

        element = find_matching_element(
            elements,
            target_description,
        )

        if not element:
            return {
                "status": "blocked",
                "reason":
                    "The required input field could not be identified safely.",
                "actions": [],
            }

        input_type = str(
            element.get(
                "input_type",
                "",
            )
        ).lower()

        if input_type == "password":
            return {
                "status": "blocked",
                "reason":
                    "Typing into credential fields is blocked.",
                "actions": [],
            }

        current_value = element.get(
            "value",
            "",
        )

        if not isinstance(
            current_value,
            str,
        ):
            current_value = ""

        if current_value == expected_value:
            click_target = extract_click_target(
                task
            )

            if click_target:
                click_element = find_matching_element(
                    elements,
                    click_target,
                )

                if click_element:
                    actual_target = (
                        click_element.get("text")
                        or click_element.get(
                            "aria_label"
                        )
                        or click_element.get(
                            "placeholder"
                        )
                        or click_element.get("name")
                        or click_element.get("id")
                        or click_target
                    )

                    return {
                        "status": "ready",
                        "reason":
                            "The required input is already populated and the requested click is the next required action.",
                        "actions": [
                            {
                                "action": "click",
                                "target": actual_target,
                            }
                        ],
                    }

            return {
                "status": "completed",
                "reason":
                    "The requested input value is already present in the current browser state.",
                "actions": [],
            }

        actual_target = (
            element.get("placeholder")
            or element.get("aria_label")
            or element.get("name")
            or element.get("id")
            or element.get("text")
            or target_description
        )

        return {
            "status": "ready",
            "reason":
                "The requested value is not yet present in the required input.",
            "actions": [
                {
                    "action": "type",
                    "target": actual_target,
                    "value": expected_value,
                }
            ],
        }

    return plan


# Process privacy inspection.
def handle_inspect(payload):
    sanitized = sanitize_context(
        payload
    )

    return {
        "success": True,
        "privacy":
            sanitized["privacy"],
        "context":
            sanitized["context"],
    }


# Process the local-agent endpoint.
def handle_agent(payload):
    task = payload.get(
        "task",
        "",
    )

    if not isinstance(
        task,
        str,
    ) or not task.strip():
        return {
            "success": False,
            "error":
                "Task is required.",
        }

    sanitized = sanitize_context(
        payload
    )

    missing_information = (
        extract_missing_user_information(
            task
        )
    )

    if missing_information:
        return {
            "success": True,
            "privacy":
                sanitized["privacy"],
            "agent": {
                "model":
                    OLLAMA_MODEL,
                "response": {
                    "status":
                        "blocked",
                    "reason":
                        "The task requires information that only the user can provide.",
                    "actions": [],
                },
            },
        }

    if not check_ollama():
        return {
            "success": False,
            "error":
                "Configured Ollama model is unavailable.",
            "model":
                OLLAMA_MODEL,
        }

    system_message = (
        build_system_prompt()
    )

    user_message = build_user_prompt(
        task,
        sanitized["context"],
    )

    try:
        raw_response = call_ollama(
            system_message,
            user_message,
        )

        parsed_response = (
            extract_json_object(
                raw_response
            )
        )

        plan = validate_model_plan(
            parsed_response
        )

        plan = enforce_type_requirements(
            task,
            sanitized["context"],
            plan,
        )

        plan = validate_model_plan(
            plan
        )

        return {
            "success": True,
            "privacy":
                sanitized["privacy"],
            "agent": {
                "model":
                    OLLAMA_MODEL,
                "response":
                    plan,
                "raw_response":
                    raw_response,
            },
        }

    except Exception as error:
        return {
            "success": False,
            "privacy":
                sanitized["privacy"],
            "agent": {
                "model":
                    OLLAMA_MODEL,
                "response": {
                    "status":
                        "blocked",
                    "reason":
                        "The local agent failed to produce a safe action plan.",
                    "actions": [],
                },
                "error":
                    str(error),
            },
        }


# HTTP request handler.
class PrivacyBridgeHandler(
    BaseHTTPRequestHandler
):
    # Silence default HTTP logging.
    def log_message(
        self,
        format_string,
        *args,
    ):
        return

    # Handle OPTIONS requests.
    def do_OPTIONS(self):
        send_json_response(
            self,
            204,
            {},
        )

    # Handle GET requests.
    def do_GET(self):
        parsed_url = urlparse(
            self.path
        )

        if parsed_url.path == "/health":
            ollama_available = (
                check_ollama()
            )

            send_json_response(
                self,
                200,
                {
                    "success": True,
                    "service":
                        "privacy-bridge",
                    "privacy_firewall":
                        "active",
                    "ollama":
                        ollama_available,
                    "model":
                        OLLAMA_MODEL,
                },
            )

            return

        send_json_response(
            self,
            404,
            {
                "success": False,
                "error":
                    "Not found.",
            },
        )

    # Handle POST requests.
    def do_POST(self):
        parsed_url = urlparse(
            self.path
        )

        try:
            payload = read_json_body(
                self
            )

        except json.JSONDecodeError:
            send_json_response(
                self,
                400,
                {
                    "success": False,
                    "error":
                        "Invalid JSON.",
                },
            )

            return

        except Exception as error:
            send_json_response(
                self,
                400,
                {
                    "success": False,
                    "error":
                        str(error),
                },
            )

            return

        try:
            if parsed_url.path == "/inspect":
                result = handle_inspect(
                    payload
                )

                send_json_response(
                    self,
                    200,
                    result,
                )

                return

            if parsed_url.path == "/agent":
                result = handle_agent(
                    payload
                )

                send_json_response(
                    self,
                    200,
                    result
                )

                return

            send_json_response(
                self,
                404,
                {
                    "success": False,
                    "error":
                        "Not found.",
                },
            )

        except Exception as error:
            send_json_response(
                self,
                500,
                {
                    "success": False,
                    "error":
                        str(error),
                },
            )


# Start the privacy bridge.
def main():
    server = HTTPServer(
        (
            HOST,
            PORT,
        ),
        PrivacyBridgeHandler,
    )

    print(
        "Privacy bridge running at "
        f"http://{HOST}:{PORT}"
    )

    print(
        "Local Ollama model: "
        f"{OLLAMA_MODEL}"
    )

    server.serve_forever()


if __name__ == "__main__":
    main()