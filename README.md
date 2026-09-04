<div align="center">

# Privacy-Preserving Vision Browser Agent

### A local AI browser agent designed to understand webpages without unnecessarily exposing sensitive information.

Perceive · Protect · Plan · Act · Verify

<br>

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](#)
[![Playwright](https://img.shields.io/badge/Browser-Playwright-orange)](#)
[![Ollama](https://img.shields.io/badge/AI-Ollama-black)](#)
[![Qwen2.5-VL](https://img.shields.io/badge/Vision-Qwen2.5--VL-green)](#)
[![Privacy](https://img.shields.io/badge/Privacy-Local-red)](#)

<br>

**A privacy-first browser agent that places a local privacy firewall between the browser and AI reasoning.**

</div>

---

## Problem

AI browser agents need access to webpage context to understand and interact with websites.

That context can contain highly sensitive information such as:

- Personal information
- Email addresses
- Phone numbers
- Passwords and credentials
- Payment information
- Sensitive content rendered directly on the webpage

A conventional browser-agent pipeline can expose large amounts of webpage data to an AI model simply because the model needs enough context to perform a task.

The challenge is therefore:

> **How can an AI agent interact with webpages while minimizing the sensitive information exposed to its reasoning model?**

---

## Our Solution

We introduce a **local privacy firewall** between the browser and the AI agent.

Instead of directly sending raw webpage information to the model, the system first performs local perception and privacy analysis.

```text
User Goal
    │
    ▼
Browser
    │
    ├── DOM
    └── Screenshot
          │
          ▼
   Local Perception
          │
          ▼
   Privacy Firewall
          │
     ┌────┴────┐
     │         │
    PII   Credentials
     │         │
     └────┬────┘
          │
    Visual Redaction
          │
          ▼
 Privacy-Safe Context
          │
          ▼
     Local AI Agent
          │
          ▼
     Action Planning
          │
          ▼
       Browser
          │
          ▼
     Verification
````

The key principle is **data minimization**:

> The AI receives the information required for the task, rather than unrestricted access to the raw webpage.

---

# Key Features

### Local Privacy Firewall

Sensitive webpage information is detected and filtered locally before reaching the AI planner.

### PII Detection

The system detects sensitive information such as:

* Email addresses
* Phone numbers
* Credit card numbers

Detected values are replaced with privacy-safe representations.

```text
john@example.com
        ↓
     [EMAIL]
```

### Credential Protection

Credential-related fields are identified using DOM properties such as:

* Password input types
* Field names
* IDs
* Placeholders
* ARIA labels
* Authentication-related keywords

Sensitive credential values are not exposed to the AI planner.

### Visual Privacy Redaction

Privacy protection is not limited to the DOM.

Sensitive information can also appear directly inside rendered webpage pixels.

The system therefore uses local OCR to identify sensitive text regions and applies visual redaction before the screenshot is passed to the vision model.

```text
Raw Screenshot
      │
      ▼
    Local OCR
      │
      ▼
Sensitive Region Detection
      │
      ▼
    Redaction
      │
      ▼
Safe Screenshot
```

### Local Vision AI

The agent uses a local vision-language model through Ollama.

This allows webpage reasoning to happen locally instead of requiring webpage screenshots or DOM context to be sent to an external AI service.

### Action Validation

AI-generated actions are validated against the current webpage state before execution.

The agent does not blindly execute arbitrary model output.

### Action Verification

After executing an action, the agent verifies that the webpage actually changed as expected.

```text
Plan
 ↓
Validate
 ↓
Execute
 ↓
Verify
 ↓
Re-perceive
```

This creates a closed-loop browser-agent architecture rather than simple one-shot automation.

---

# Tech Stack

| Component          | Technology                 |
| ------------------ | -------------------------- |
| Language           | Python                     |
| Browser Automation | Playwright                 |
| Browser            | Chromium                   |
| Vision Model       | Qwen2.5-VL 3B              |
| Local AI Runtime   | Ollama                     |
| OCR                | Tesseract                  |
| Image Processing   | Pillow                     |
| DOM Perception     | Playwright DOM APIs        |
| Privacy Detection  | Local Regex + DOM Analysis |
| Visual Redaction   | Pillow                     |
| Architecture       | Local / Privacy-first      |

---

# Project Structure

```text
privacy-preserving-vision-agent/
│
├── agent/
│   ├── perception/
│   │   └── dom.py
│   │
│   ├── privacy/
│   │   ├── credentials.py
│   │   ├── pii.py
│   │   ├── firewall.py
│   │   ├── sanitizer.py
│   │   └── visual.py
│   │
│   ├── security/
│   │   └── policy.py
│   │
│   └── planner.py
│
├── tests/
│   ├── test_browser.py
│   ├── test_ollama.py
│   ├── visual_test.py
│   └── test_privacy.py
│
├── tools/
│   ├── browser_agent.py
│   ├── browser_ocr.py
│   └── ocr_coordinates.py
│
├── demo/
│   └── test_page.html
│
├── autonomous_agent.py
├── legacy_agent.py
└── README.md
```

---

# Demo / Current Prototype

The current prototype demonstrates an end-to-end privacy-preserving browser-agent workflow.

A test webpage contains multiple types of sensitive information alongside interactive UI elements.

The agent first perceives the webpage:

```text
DOM + Screenshot
```

The local privacy firewall detects sensitive information:

```text
Credential
Email
Phone
Credit Card
```

The AI-facing context is then sanitized so that the planner receives the usable interface without unnecessary sensitive values.

For example:

```text
BUTTON  Search
BUTTON  Login
INPUT   Enter your name
INPUT   Enter password
```

The agent can then execute a user-specified task such as:

```text
type "Shivansh" into Enter your name and click Search
```

The deterministic task controller maintains the required sequence:

```text
1. TYPE "Shivansh" → Enter your name
2. CLICK → Search
```

Each action is validated and verified before the next step.

```text
User Task
    ↓
Privacy-Safe Perception
    ↓
Local Vision Model
    ↓
Action Validation
    ↓
Browser Execution
    ↓
Action Verification
    ↓
Task Completion
```

The current prototype successfully demonstrates the complete loop:

**Perceive → Protect → Plan → Act → Verify**

---

<div align="center">

### Privacy-Preserving Vision Browser Agent

**Local AI · Browser Automation · Privacy Firewall · Visual Perception**

</div>
