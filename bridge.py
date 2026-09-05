# Privacy-preserving local browser-agent bridge.

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


# Bridge configuration.
HOST = "127.0.0.1"
PORT = 8765

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen2.5vl:3b"

MAX_PAGE_TEXT_LENGTH = 12000

ALLOWED_BROWSER_HOSTS = {
    "localhost",
    "127.0.0.1",
}


# Return a JSON HTTP response.
def json_response(
    handler,
    status_code,
    payload,
):
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
        "Content-Length",
        str(len(body)),
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

    if content_length <= 0:
        return {}

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
                response.read().decode("utf-8")
            )

        models = data.get(
            "models",
            [],
        )

        return any(
            model.get("name") == OLLAMA_MODEL
            for model in models
        )

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

    page_text = payload.get(
        "page_text",
        "",
    )

    if not isinstance(
        page_text,
        str,
    ):
        page_text = ""

    if len(page_text) > MAX_PAGE_TEXT_LENGTH:
        page_text = page_text[
            :MAX_PAGE_TEXT_LENGTH
        ]

    return {
        "url": payload.get(
            "url",
            "",
        ),
        "title": payload.get(
            "title",
            "",
        ),
        "elements": elements,
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
        if finding.get("type")
        != "credential"
    ]

    credential_findings = [
        finding
        for finding in findings
        if finding.get("type")
        == "credential"
    ]

    finding_types = sorted(
        {
            finding.get("type")
            for finding in findings
            if finding.get("type")
        }
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
            "types": finding_types,
        },
    }


# Build the browser-agent system prompt.
def build_system_prompt():
    return """
You are a local privacy-preserving browser agent.

You receive ONLY privacy-sanitized browser context.

Your job is to complete the user's browser task using the minimum number of safe actions.

Return ONLY valid JSON.

The JSON must have exactly this structure:

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
  "action": "type",
  "target": "exact visible input",
  "value": "value explicitly requested by the user"
}

If the task is already completed:

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

Allowed browser actions are only:

- click
- type

Critical rules:

1. Inspect the CURRENT browser state before deciding anything.

2. Never assume an input contains a value unless the CURRENT browser context explicitly shows that value.

3. Never invent personal information.

4. Never invent a value that the user did not provide.

5. Never type into a credential or password field.

6. If the user explicitly requests typing a value into a field and the current field does NOT contain that value, the task is NOT completed.

7. If the requested value is missing from the required field, return the required type action.

8. Only return "completed" when the current browser state provides evidence that the requested task is already complete.

9. The existence of a button does not mean the button should be clicked.

10. Do not repeat an action when the current browser state already shows that its result occurred.

11. If a page explicitly shows that the requested operation succeeded, return "completed".

12. Do not expose or reproduce sanitized PII.

13. If required user information is missing, return "blocked" instead of guessing.

14. Prefer the smallest number of actions.

Example:

User task:
Type Shivansh into the name field and click Search.

Current state:
Name field is empty.

Correct response:

{
  "status": "ready",
  "reason": "The name field is empty and must be populated before searching.",
  "actions": [
    {
      "action": "type",
      "target": "name field",
      "value": "Shivansh"
    }
  ]
}

After the name field contains Shivansh and the search has not yet happened:

{
  "status": "ready",
  "reason": "The name is populated and the search still needs to be performed.",
  "actions": [
    {
      "action": "click",
      "target": "Search"
    }
  ]
}

After the page explicitly shows that the search succeeded:

{
  "status": "completed",
  "reason": "The requested search completed successfully.",
  "actions": []
}

Never return markdown.
Never return explanations outside JSON.
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
If the task requires typing a specific value, compare that requirement against the CURRENT input value.

Do not say the task is completed merely because the task value was mentioned in the user request.

Only return "completed" when the CURRENT browser state proves completion.
""".strip()


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
        "format": "json",
        "options": {
            "temperature": 0,
        },
    }

    body = json.dumps(
        payload
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

    data = json.loads(
        raw
    )

    message = data.get(
        "message",
        {},
    )

    content = message.get(
        "content",
        "",
    )

    return {
        "content": content,
        "raw": data,
    }


# Extract JSON from model output.
def parse_model_json(content):
    if not content:
        raise ValueError(
            "Model returned empty content."
        )

    try:
        return json.loads(
            content
        )
    except json.JSONDecodeError:
        pass

    match = re.search(
        r"\{.*\}",
        content,
        re.DOTALL,
    )

    if not match:
        raise ValueError(
            "Model response did not contain valid JSON."
        )

    return json.loads(
        match.group(0)
    )


# Normalize the model plan.
def validate_plan(plan):
    if not isinstance(
        plan,
        dict,
    ):
        return {
            "status": "blocked",
            "reason":
                "Model plan was not an object.",
            "actions": [],
        }

    status = plan.get(
        "status"
    )

    if status not in {
        "ready",
        "completed",
        "blocked",
    }:
        status = "blocked"

    reason = plan.get(
        "reason",
        "",
    )

    if not isinstance(
        reason,
        str,
    ):
        reason = ""

    actions = plan.get(
        "actions",
        [],
    )

    if not isinstance(
        actions,
        list,
    ):
        actions = []

    normalized_actions = []

    for action in actions:
        if not isinstance(
            action,
            dict,
        ):
            continue

        action_type = action.get(
            "action"
        )

        target = action.get(
            "target"
        )

        if not isinstance(
            action_type,
            str,
        ):
            continue

        if not isinstance(
            target,
            str,
        ):
            continue

        normalized = {
            "action":
                action_type.strip().lower(),
            "target":
                target.strip(),
        }

        if normalized[
            "action"
        ] == "type":
            value = action.get(
                "value"
            )

            if not isinstance(
                value,
                str,
            ):
                continue

            normalized[
                "value"
            ] = value

        normalized_actions.append(
            normalized
        )

    if status in {
        "completed",
        "blocked",
    }:
        normalized_actions = []

    return {
        "status": status,
        "reason": reason,
        "actions":
            normalized_actions,
    }


# Normalize text for comparisons.
def normalize_text(value):
    if not isinstance(
        value,
        str,
    ):
        return ""

    return " ".join(
        value.strip().lower().split()
    )


# Find an interactive element matching a natural-language target.
def find_matching_element(
    elements,
    target,
):
    target_normalized = normalize_text(target)

    if not target_normalized:
        return None

    exact_fields = [
        "text",
        "aria_label",
        "placeholder",
        "name",
        "id",
    ]

    for element in elements:
        for field in exact_fields:
            value = normalize_text(
                element.get(field)
            )

            if value == target_normalized:
                return element

    for element in elements:
        candidates = []

        for field in exact_fields:
            value = normalize_text(
                element.get(field)
            )

            if value:
                candidates.append(
                    value
                )

        combined = " ".join(
            candidates
        )

        if (
            target_normalized in combined
            or combined in target_normalized
        ):
            return element

    target_without_field = re.sub(
        r"\b(field|input|textbox)\b",
        "",
        target_normalized,
    ).strip()

    if target_without_field:
        for element in elements:
            candidates = []

            for field in exact_fields:
                value = normalize_text(
                    element.get(field)
                )

                if value:
                    candidates.append(
                        value
                    )

            combined = " ".join(
                candidates
            )

            if target_without_field in combined:
                return element

    return None

# Return the safest exact target identifier for an interactive element.
def canonicalize_action_target(
    element,
    fallback_target,
):
    if not isinstance(
        element,
        dict,
    ):
        return fallback_target

    for field in [
        "aria_label",
        "placeholder",
        "name",
        "id",
        "text",
    ]:
        value = element.get(
            field,
            "",
        )

        if isinstance(
            value,
            str,
        ) and value.strip():
            return value.strip()

    return fallback_target

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
            r"\bmy\s+number\b",
            "your number",
        ),
        (
            r"\bmy\s+address\b",
            "your address",
        ),
        (
            r"\bmy\s+username\b",
            "your username",
        ),
        (
            r"\bmy\s+password\b",
            "your password",
        ),
        (
            r"\bmy\s+date\s+of\s+birth\b",
            "your date of birth",
        ),
        (
            r"\bmy\s+dob\b",
            "your date of birth",
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
            r"""
            \btype\s+
            (?P<value>.+?)
            \s+
            (?:into|in)\s+
            (?:the\s+)?
            (?P<target>.+?)
            (?=
                \s+(?:and|then)\s+
                (?:click|press|select)\b
                |
                \s*$
            )
            """,
            re.IGNORECASE |
            re.VERBOSE,
        ),
    ]

    for pattern in patterns:
        for match in pattern.finditer(
            task
        ):
            value = match.group(
                "value"
            ).strip()

            target = match.group(
                "target"
            ).strip()

            if (
                value.startswith('"')
                and value.endswith('"')
            ):
                value = value[1:-1]

            if (
                value.startswith("'")
                and value.endswith("'")
            ):
                value = value[1:-1]

            if value and target:
                requirements.append(
                    {
                        "value": value,
                        "target": target,
                    }
                )

    return requirements


# Extract an explicit click target from the user task.
def extract_click_target(task):
    if not isinstance(
        task,
        str,
    ):
        return ""

    patterns = [
        re.compile(
            r"\b(?:and|then)\s+click\s+(?:the\s+)?(.+?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*click\s+(?:the\s+)?(.+?)\s*$",
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
            r"\s+(?:button|link)\s*$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()

        if target:
            return target

    return ""


# Enforce explicit task requirements against the current browser state.
def enforce_type_requirements(
    task,
    context,
    plan,
):
    requirements = extract_type_requirements(
        task
    )

    if not requirements:
        return plan

    elements = context.get(
        "elements",
        [],
    )

    all_requirements_satisfied = True

    for requirement in requirements:
        expected_value = requirement[
            "value"
        ]

        target = requirement[
            "target"
        ]

        element = find_matching_element(
            elements,
            target,
        )

        if element is None:
            all_requirements_satisfied = False
            continue

        actual_value = element.get(
            "value",
            "",
        )

        if not isinstance(
            actual_value,
            str,
        ):
            actual_value = ""

        if actual_value != expected_value:
            all_requirements_satisfied = False

            return {
                "status": "ready",
                "reason":
                    "The required input value is not present in the current browser state.",
                "actions": [
                    {
                        "action": "type",
                        "target": target,
                        "value": expected_value,
                    }
                ],
            }

    if all_requirements_satisfied:
        click_target = extract_click_target(
            task
        )

        if click_target:
            click_element = find_matching_element(
                elements,
                click_target,
            )

            if click_element is not None:
                element_type = click_element.get(
                    "type",
                    "",
                )

                if element_type in {
                    "button",
                    "link",
                }:
                    actual_target = canonicalize_action_target(
                        click_element,
                        click_target,
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

    missing_information = extract_missing_user_information(
        task
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
                        "requires_user_input",
                    "reason":
                        "The task requires information that only the user can provide.",
                    "missing_information":
                        missing_information,
                    "actions": [],
                },
            },
        }

    if not check_ollama():
        return {
            "success": False,
            "error":
                f"Local Ollama model '{OLLAMA_MODEL}' is unavailable.",
            "privacy":
                sanitized["privacy"],
        }

    system_message = build_system_prompt()

    user_message = build_user_prompt(
        task,
        sanitized["context"],
    )

    try:
        model_result = call_ollama(
            system_message,
            user_message,
        )

        parsed = parse_model_json(
            model_result["content"]
        )

        plan = validate_plan(
            parsed
        )

        plan = enforce_type_requirements(
            task,
            sanitized["context"],
            plan,
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
                    model_result["content"],
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
            },
            "error":
                str(error),
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

    # Handle CORS preflight.
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

    # Handle GET requests.
    def do_GET(self):
        parsed_url = urlparse(
            self.path
        )

        if parsed_url.path == "/health":
            ollama_available = check_ollama()

            json_response(
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

        json_response(
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

        except Exception as error:
            json_response(
                self,
                400,
                {
                    "success": False,
                    "error":
                        f"Invalid JSON: {error}",
                },
            )

            return

        try:
            if parsed_url.path == "/inspect":
                result = handle_inspect(
                    payload
                )

                json_response(
                    self,
                    200,
                    result,
                )

                return

            if parsed_url.path == "/agent":
                result = handle_agent(
                    payload
                )

                json_response(
                    self,
                    200,
                    result,
                )

                return

            json_response(
                self,
                404,
                {
                    "success": False,
                    "error":
                        "Not found.",
                },
            )

        except Exception as error:
            json_response(
                self,
                500,
                {
                    "success": False,
                    "error":
                        str(error),
                },
            )


# Start the bridge server.
def main():
    server = HTTPServer(
        (HOST, PORT),
        PrivacyBridgeHandler,
    )

    print(
        f"Privacy bridge running at "
        f"http://{HOST}:{PORT}"
    )

    print(
        f"Local Ollama model: "
        f"{OLLAMA_MODEL}"
    )

    server.serve_forever()


if __name__ == "__main__":
    main()