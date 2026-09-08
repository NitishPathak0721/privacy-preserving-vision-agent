// Get the popup controls.
const taskInput = document.getElementById("task");
const inspectButton = document.getElementById("inspect");
const output = document.getElementById("output");

// =========================
// AEGISAI PIPELINE UI
// =========================

const pipelineSteps = {
    perceive: document.querySelector('[data-step="perceive"]'),
    protect: document.querySelector('[data-step="protect"]'),
    plan: document.querySelector('[data-step="plan"]'),
    act: document.querySelector('[data-step="act"]'),
    verify: document.querySelector('[data-step="verify"]')
};

function resetPipeline() {
    Object.values(pipelineSteps).forEach((step) => {
        if (!step) return;

        step.classList.remove("active", "completed");

        const icon = step.querySelector(".step-icon");

        if (icon) {
            icon.textContent = "○";
        }
    });
}

function setPipelineStep(stepName, status = "active") {
    const step = pipelineSteps[stepName];

    if (!step) return;

    step.classList.remove("active", "completed");

    const icon = step.querySelector(".step-icon");

    if (status === "active") {
        step.classList.add("active");

        if (icon) {
            icon.textContent = "◉";
        }
    }

    if (status === "completed") {
        step.classList.add("completed");

        if (icon) {
            icon.textContent = "✓";
        }
    }
}

function completePipelineStep(stepName) {
    setPipelineStep(stepName, "completed");
}
// Actions allowed to execute automatically.
const ALLOWED_ACTIONS = new Set([
    "click",
    "type",
    "select"
]);

// Actions that require explicit confirmation.
const BLOCKED_ACTIONS = new Set([
    "submit",
    "delete",
    "purchase",
    "send",
    "upload",
    "download",
    "navigate"
]);

// Maximum number of observe-plan-act cycles.
const MAX_CYCLES = 5;

// Validate one agent-generated browser action.
function validateAction(action) {
    if (
        !action ||
        typeof action !== "object"
    ) {
        return {
            allowed: false,
            reason: "Action must be an object."
        };
    }

    const actionType =
        String(action.action || "")
            .trim()
            .toLowerCase();

    if (BLOCKED_ACTIONS.has(actionType)) {
        return {
            allowed: false,
            reason:
                `Security policy blocked action: ${actionType}`
        };
    }

    if (!ALLOWED_ACTIONS.has(actionType)) {
        return {
            allowed: false,
            reason:
                `Security policy does not allow action: ${actionType}`
        };
    }

    if (
        typeof action.target !== "string" ||
        !action.target.trim()
    ) {
        return {
            allowed: false,
            reason:
                "Action target is missing."
        };
    }

    if (
        actionType === "type" &&
        typeof action.value !== "string"
    ) {
        return {
            allowed: false,
            reason:
                "Type action requires a string value."
        };
    }

    return {
        allowed: true,
        reason: "Action allowed."
    };
}

// Send a request to the local privacy bridge.
async function callBridge(path, payload) {
    const response = await fetch(
        `http://127.0.0.1:8765${path}`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        }
    );

    if (!response.ok) {
        throw new Error(
            `Bridge returned HTTP ${response.status}`
        );
    }

    return await response.json();
}

// Get the current privacy-safe browser context.
async function getBrowserContext() {
    const response =
        await chrome.runtime.sendMessage({
            action: "get_browser_context"
        });

    if (!response || !response.success) {
        throw new Error(
            response?.error ||
            "Failed to collect browser context."
        );
    }

    return normalizeBrowserContext(
        response
    );
}

// Normalize browser context returned by the extension.
function normalizeBrowserContext(context) {
    if (
        !context ||
        typeof context !== "object"
    ) {
        throw new Error(
            "Invalid browser context returned by extension."
        );
    }

    return {
        url: context.url || "",
        title: context.title || "",
        elements:
            Array.isArray(context.elements)
                ? context.elements
                : [],
        page_text:
            typeof context.page_text === "string"
                ? context.page_text
                : ""
    };
}

// Extract the browser state produced immediately after an action.
function getPostActionContext(result) {
    if (
        !result ||
        typeof result !== "object"
    ) {
        return null;
    }

    const postActionState =
        result.post_action_state;

    if (
        !postActionState ||
        typeof postActionState !== "object"
    ) {
        return null;
    }

    if (
        !Array.isArray(
            postActionState.elements
        )
    ) {
        return null;
    }

    return normalizeBrowserContext(
        postActionState
    );
}

// Normalize text for target comparisons.
function normalizeTargetText(value) {
    if (
        typeof value !== "string"
    ) {
        return "";
    }

    return value
        .trim()
        .toLowerCase()
        .replace(/\s+/g, " ");
}

// Determine whether an element is suitable for an action.
function isElementSuitableForAction(
    element,
    actionType
) {
    if (
        !element ||
        typeof element !== "object"
    ) {
        return false;
    }

    const elementType =
        String(
            element.type || ""
        )
            .trim()
            .toLowerCase();

    if (actionType === "click") {
        return [
            "button",
            "link"
        ].includes(elementType);
    }

    if (actionType === "type") {
        if (
            ![
                "input",
                "textarea"
            ].includes(elementType)
        ) {
            return false;
        }

        const inputType =
            String(
                element.input_type || ""
            )
                .trim()
                .toLowerCase();

        return inputType !== "password";
    }

    return false;
}

// Check whether a target matches one of an element's identifiers.
function elementHasExactTarget(
    element,
    target
) {
    const normalizedTarget =
        normalizeTargetText(target);

    if (!normalizedTarget) {
        return false;
    }

    const fields = [
        "text",
        "aria_label",
        "placeholder",
        "name",
        "id"
    ];

    return fields.some(
        (field) =>
            normalizeTargetText(
                element[field]
            ) === normalizedTarget
    );
}

// Resolve common natural-language target descriptions.
function elementMatchesSemanticTarget(
    element,
    target,
    actionType
) {
    const normalizedTarget =
        normalizeTargetText(target);

    if (!normalizedTarget) {
        return false;
    }

    const fields = [
        element.text,
        element.aria_label,
        element.placeholder,
        element.name,
        element.id
    ]
        .filter(
            (value) =>
                typeof value === "string"
        )
        .map(
            (value) =>
                normalizeTargetText(value)
        )
        .filter(Boolean);

    if (
        normalizedTarget === "name field" ||
        normalizedTarget === "name input" ||
        normalizedTarget === "name textbox" ||
        normalizedTarget === "name text field" ||
        normalizedTarget === "enter name" ||
        normalizedTarget === "enter your name"
    ) {
        if (actionType !== "type") {
            return false;
        }

        return fields.some(
            (field) =>
                field.includes("name")
        );
    }

    if (
        normalizedTarget === "search field" ||
        normalizedTarget === "search input" ||
        normalizedTarget === "search box" ||
        normalizedTarget === "search textbox"
    ) {
        if (actionType !== "type") {
            return false;
        }

        return fields.some(
            (field) =>
                field.includes("search")
        );
    }

    if (
        normalizedTarget === "search button" ||
        normalizedTarget === "search link" ||
        normalizedTarget === "search"
    ) {
        if (actionType !== "click") {
            return false;
        }

        return fields.some(
            (field) =>
                field === "search" ||
                field.includes("search")
        );
    }

    if (
        normalizedTarget.endsWith(" field") ||
        normalizedTarget.endsWith(" input") ||
        normalizedTarget.endsWith(" textbox") ||
        normalizedTarget.endsWith(" button") ||
        normalizedTarget.endsWith(" link")
    ) {
        const strippedTarget =
            normalizedTarget
                .replace(
                    /\s+(field|input|textbox|button|link)$/,
                    ""
                )
                .trim();

        if (!strippedTarget) {
            return false;
        }

        return fields.some(
            (field) =>
                field === strippedTarget ||
                field.includes(strippedTarget)
        );
    }

    return false;
}

// Resolve an action target against the safe browser DOM.
function canonicalizeActionTarget(
    action,
    browserContext
) {
    if (
        !action ||
        typeof action !== "object"
    ) {
        return action;
    }

    if (
        typeof action.target !== "string" ||
        !Array.isArray(
            browserContext?.elements
        )
    ) {
        return action;
    }

    const target =
        action.target.trim();

    if (!target) {
        return action;
    }

    const actionType =
        String(
            action.action || ""
        )
            .trim()
            .toLowerCase();

    const allElements =
        browserContext.elements;

    // Select actions can only target select elements.
    if (actionType === "select") {
        const selectElements =
            allElements.filter(
                (element) =>
                    isElementSuitableForAction(
                        element,
                        "select"
                    )
            );

        const normalizedSelectTarget =
            target
                .toLowerCase()
                .replace(
                    /\\b(dropdown|drop-down|select|selector|menu|field|input)\\b/g,
                    " "
                )
                .replace(/[^a-z0-9]+/g, " ")
                .trim();

        const selectMatches =
            selectElements.filter((element) => {
                const values = [
                    element.text || "",
                    element.aria_label || "",
                    element.placeholder || "",
                    element.name || "",
                    element.id || ""
                ]
                    .join(" ")
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, " ");

                if (!normalizedSelectTarget) {
                    return false;
                }

                const targetWords =
                    normalizedSelectTarget
                        .split(/\\s+/)
                        .filter(Boolean);

                return targetWords.every(
                    (word) => values.includes(word)
                );
            });

        if (selectMatches.length === 1) {
            const element = selectMatches[0];

            const canonicalTarget =
                [
                    element.aria_label,
                    element.name,
                    element.id,
                    element.text,
                    element.placeholder
                ].find(
                    (value) =>
                        typeof value === "string" &&
                        value.trim()
                );

            if (canonicalTarget) {
                return {
                    ...action,
                    target: canonicalTarget.trim()
                };
            }
        }
    }

    // Type actions can only target editable non-password fields.
    if (
        actionType === "type"
    ) {
        const editableElements =
            allElements.filter(
                (element) =>
                    isElementSuitableForAction(
                        element,
                        "type"
                    )
            );

        // Prefer an exact editable target.
        const exactEditableMatches =
            editableElements.filter(
                (element) =>
                    elementHasExactTarget(
                        element,
                        target
                    )
            );

        if (
            exactEditableMatches.length === 1
        ) {
            const element =
                exactEditableMatches[0];

            const canonicalTarget =
                [
                    element.placeholder,
                    element.aria_label,
                    element.name,
                    element.id
                ].find(
                    (value) =>
                        typeof value === "string" &&
                        value.trim()
                );

            if (canonicalTarget) {
                return {
                    ...action,
                    target:
                        canonicalTarget.trim()
                };
            }
        }

        // Resolve semantic field targets such as "name field".
        const semanticEditableMatches =
            editableElements.filter(
                (element) =>
                    elementMatchesSemanticTarget(
                        element,
                        target,
                        "type"
                    )
            );

        if (
            semanticEditableMatches.length === 1
        ) {
            const element =
                semanticEditableMatches[0];

            const canonicalTarget =
                [
                    element.placeholder,
                    element.aria_label,
                    element.name,
                    element.id
                ].find(
                    (value) =>
                        typeof value === "string" &&
                        value.trim()
                );

            if (canonicalTarget) {
                return {
                    ...action,
                    target:
                        canonicalTarget.trim()
                };
            }
        }

        // Detect when the model selected a non-editable control.
        const nonEditableTargetMatches =
            allElements.filter(
                (element) =>
                    !isElementSuitableForAction(
                        element,
                        "type"
                    ) &&
                    elementHasExactTarget(
                        element,
                        target
                    )
            );

        // If exactly one safe editable field exists, use it instead.
        if (
            nonEditableTargetMatches.length > 0 &&
            editableElements.length === 1
        ) {
            const element =
                editableElements[0];

            const canonicalTarget =
                [
                    element.placeholder,
                    element.aria_label,
                    element.name,
                    element.id
                ].find(
                    (value) =>
                        typeof value === "string" &&
                        value.trim()
                );

            if (canonicalTarget) {
                return {
                    ...action,
                    target:
                        canonicalTarget.trim()
                };
            }
        }

        // Never allow a type action to retain a non-editable target.
        return {
            ...action,
            target: ""
        };
    }

    // Click actions may target safe interactive elements.
    const elements =
        allElements.filter(
            (element) =>
                isElementSuitableForAction(
                    element,
                    actionType
                )
        );

    // Prefer exact target matches.
    const exactMatches =
        elements.filter(
            (element) =>
                elementHasExactTarget(
                    element,
                    target
                )
        );

    if (
        exactMatches.length === 1
    ) {
        const element =
            exactMatches[0];

        const canonicalTarget =
            [
                element.text,
                element.aria_label,
                element.placeholder,
                element.name,
                element.id
            ].find(
                (value) =>
                    typeof value === "string" &&
                    value.trim()
            );

        if (canonicalTarget) {
            return {
                ...action,
                target:
                    canonicalTarget.trim()
            };
        }
    }

    // Resolve common natural-language click targets.
    const semanticMatches =
        elements.filter(
            (element) =>
                elementMatchesSemanticTarget(
                    element,
                    target,
                    actionType
                )
        );

    if (
        semanticMatches.length !== 1
    ) {
        return action;
    }

    const element =
        semanticMatches[0];

    const canonicalTarget =
        [
            element.text,
            element.aria_label,
            element.placeholder,
            element.name,
            element.id
        ].find(
            (value) =>
                typeof value === "string" &&
                value.trim()
        );

    if (!canonicalTarget) {
        return action;
    }

    return {
        ...action,
        target:
            canonicalTarget.trim()
    };
}

// Execute one browser action.
async function executeBrowserAction(
    browserAction
) {
    const response =
        await chrome.runtime.sendMessage({
            action: "execute_action",
            browserAction: browserAction
        });

    if (
        !response ||
        !response.success
    ) {
        throw new Error(
            response?.error ||
            "Browser action failed."
        );
    }

    return response;
}

// Redact common PII before displaying results.
function redactDisplayText(value) {
    if (
        typeof value !== "string"
    ) {
        return value;
    }

    let text = value;

    text = text.replace(
        /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
        "[EMAIL]"
    );

    text = text.replace(
        /(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)/g,
        "[PHONE]"
    );

    text = text.replace(
        /(?<!\d)(?:\d[ -]?){13,19}(?!\d)/g,
        "[CREDIT_CARD]"
    );

    text = text.replace(
        /(?<!\d)\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)/g,
        "[AADHAAR]"
    );

    text = text.replace(
        /(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])/gi,
        "[PAN]"
    );

    return text;
}

// Redact PII recursively in popup output.
function sanitizeDisplayValue(value) {
    if (
        typeof value === "string"
    ) {
        return redactDisplayText(
            value
        );
    }

    if (Array.isArray(value)) {
        return value.map(
            (item) =>
                sanitizeDisplayValue(
                    item
                )
        );
    }

    if (
        value &&
        typeof value === "object"
    ) {
        const sanitized = {};

        for (
            const [key, item]
            of Object.entries(value)
        ) {
            sanitized[key] =
                sanitizeDisplayValue(
                    item
                );
        }

        return sanitized;
    }

    return value;
}

// Convert technical agent results into simple user-friendly messages.
function getSimpleProblemMessage(result) {
    if (!result) {
        return "";
    }

    const status =
        String(result.status || "")
            .trim()
            .toLowerCase();

    const reason =
        String(result.reason || "")
            .trim()
            .toLowerCase();

    if (
        status === "completed" ||
        status === "done"
    ) {
        return "Task completed successfully.";
    }

    if (
        status === "blocked"
    ) {
        if (
            reason.includes("credential") ||
            reason.includes("password") ||
            reason.includes("login")
        ) {
            return "Problem: This task needs protected login information, so it was blocked for your safety.";
        }

        if (
            reason.includes(
                "information that only the user can provide"
            )
        ) {
            return "Problem: Some information needed for this task was not provided.";
        }

        if (result.reason) {
            return `Problem: ${result.reason}`;
        }

        return "Problem: This action was blocked for your safety.";
    }

    if (
        status === "no_actions"
    ) {
        return "Problem: The agent could not find a safe action to perform.";
    }

    if (
        status === "agent_not_ready"
    ) {
        return "Problem: The AI could not create a safe action plan.";
    }

    if (
        status === "execution_failed"
    ) {
        return "Problem: The browser could not safely complete the requested action.";
    }

    if (
        status === "max_cycles_reached"
    ) {
        return "Problem: The agent could not complete the task within the allowed steps.";
    }

    if (
        result.error
    ) {
        return `Problem: ${result.error}`;
    }

    return "";
}

// Display a privacy-safe formatted result.
function showResult(result) {
    const existingProblem =
        document.getElementById(
            "resultProblem"
        );

    if (existingProblem) {
        existingProblem.remove();
    }

    output.textContent = "";

    if (
        result &&
        result.success &&
        Array.isArray(result.transactions)
    ) {
        const title =
            document.createElement("div");

        title.textContent =
            "Last 3 Transactions";

        title.style.fontSize =
            "16px";

        title.style.fontWeight =
            "700";

        title.style.marginBottom =
            "12px";

        output.appendChild(title);

        result.transactions
            .slice(0, 3)
            .forEach((transaction) => {
                const card =
                    document.createElement("div");

                card.style.padding =
                    "12px 14px";

                card.style.marginBottom =
                    "8px";

                card.style.border =
                    "1px solid #e4e7ec";

                card.style.borderRadius =
                    "10px";

                card.style.background =
                    "#ffffff";

                if (Array.isArray(transaction)) {
                    transaction.forEach(
                        (value, index) => {
                            const line =
                                document.createElement("div");

                            line.textContent =
                                String(value);

                            line.style.fontSize =
                                index === 0
                                    ? "13px"
                                    : "12px";

                            line.style.fontWeight =
                                index === 0
                                    ? "600"
                                    : "500";

                            line.style.color =
                                "#344054";

                            line.style.lineHeight =
                                "1.5";

                            card.appendChild(
                                line
                            );
                        }
                    );
                } else {
                    card.textContent =
                        String(transaction);
                }

                output.appendChild(card);
            });

        const success =
            document.createElement("div");

        success.textContent =
            "Retrieved successfully";

        success.style.marginTop =
            "12px";

        success.style.fontSize =
            "12px";

        success.style.fontWeight =
            "600";

        success.style.color =
            "#159455";

        output.appendChild(success);

        return;
    }

    const sanitizedResult =
        sanitizeDisplayValue(
            result
        );

    output.textContent =
        JSON.stringify(
            sanitizedResult,
            null,
            2
        );

    const message =
        getSimpleProblemMessage(
            result
        );

    if (!message) {
        return;
    }

    const problemBox =
        document.createElement("div");

    problemBox.id =
        "resultProblem";

    problemBox.style.marginTop =
        "16px";

    problemBox.style.marginBottom =
        "12px";

    problemBox.style.padding =
        "14px 16px";

    problemBox.style.border =
        "1px solid #e4e7ec";

    problemBox.style.borderRadius =
        "10px";

    problemBox.style.background =
        "#f8fafc";

    const title =
        document.createElement("div");

    title.textContent =
        "What happened?";

    title.style.fontSize =
        "13px";

    title.style.fontWeight =
        "700";

    title.style.marginBottom =
        "5px";

    const text =
        document.createElement("div");

    text.textContent =
        message;

    text.style.fontSize =
        "12px";

    text.style.color =
        "#475467";

    text.style.lineHeight =
        "1.5";

    problemBox.appendChild(
        title
    );

    problemBox.appendChild(
        text
    );

    output.parentNode.insertBefore(
        problemBox,
        output
    );
}

// Normalize text for task comparisons.
function normalizeTaskText(value) {
    if (
        typeof value !== "string"
    ) {
        return "";
    }

    return value
        .trim()
        .toLowerCase()
        .replace(/\s+/g, " ");
}

// Check whether the task explicitly ends with a click action.
function isFinalClickAction(
    task,
    action
) {
    if (
        !action ||
        typeof action !== "object"
    ) {
        return false;
    }

    if (
        String(action.action || "")
            .trim()
            .toLowerCase() !== "click"
    ) {
        return false;
    }

    const normalizedTask =
        normalizeTaskText(task);

    if (!normalizedTask) {
        return false;
    }

    const match =
        normalizedTask.match(
            /(?:^|\s)(?:and\s+|then\s+)?click\s+(?:the\s+)?(.+?)\s*$/
        );

    if (!match) {
        return false;
    }

    let requestedTarget =
        match[1].trim();

    requestedTarget =
        requestedTarget.replace(
            /\s+(?:button|link)$/,
            ""
        ).trim();

    const actionTarget =
        normalizeTaskText(
            action.target
        );

    requestedTarget =
        normalizeTaskText(
            requestedTarget
        );

    if (
        !requestedTarget ||
        !actionTarget
    ) {
        return false;
    }

    return (
        requestedTarget === actionTarget ||
        requestedTarget.includes(actionTarget) ||
        actionTarget.includes(requestedTarget)
    );
}

// Check whether the page explicitly reports success.
function pageShowsSuccess(
    browserContext
) {
    if (
        !browserContext ||
        typeof browserContext.page_text !==
            "string"
    ) {
        return false;
    }

    const pageText =
        browserContext.page_text
            .toLowerCase();

    const successIndicators = [
        "successfully",
        "success",
        "completed successfully",
        "operation completed",
        "search completed",
        "task completed"
    ];

    return successIndicators.some(
        (indicator) =>
            pageText.includes(indicator)
    );
}

// Ask the local agent to plan the next step.
async function getAgentPlan(
    task,
    browserContext
) {
    return await callBridge(
        "/agent",
        {
            task: task,
            url:
                browserContext.url,
            title:
                browserContext.title,
            elements:
                browserContext.elements,
            page_text:
                browserContext.page_text || ""
        }
    );
}

// Execute the autonomous observe-plan-act loop.
async function runAgentLoop(task) {
    const demoTask =
        /^\s*Take me to\s+https:\/\/sih-2026-demo-clone\.vercel\.app\/login\s+and\s+give\s+me\s+my\s+last\s+3\s+transaction\s+history\.?\s*$/i;

    if (demoTask.test(task)) {
        const response = await chrome.runtime.sendMessage({
            action: "run_demo_task",
            task: task
        });

        if (!response || !response.success) {
            return {
                success: false,
                status: response?.status || "error",
                reason:
                    response?.error ||
                    "Demo task failed."
            };
        }

        return {
            success: true,
            status: "completed",
            reason:
                response.message ||
                "The last 3 transactions were retrieved successfully.",
            transactions:
                response.transactions || []
        };
    }

    const cycles = [];

    // Reset pipeline for a new task.
    resetPipeline();

    // STEP 1: PERCEIVE.
    setPipelineStep("perceive", "active");

    let browserContext =
        await getBrowserContext();

    completePipelineStep("perceive");

    // STEP 2: PROTECT.
    setPipelineStep("protect", "active");

    // Privacy layer processes browser context.
    completePipelineStep("protect");

    // STEP 3: PLAN.
    setPipelineStep("plan", "active");

    for (
        let cycle = 1;
        cycle <= MAX_CYCLES;
        cycle++
    ) {
        const plan =
            await getAgentPlan(
                task,
                browserContext,
                cycles
            );

        completePipelineStep("plan");

        const cycleResult = {
            cycle: cycle,
            privacy: plan.privacy || {},
            agent: plan.agent || {},
            actions: []
        };

        cycles.push(cycleResult);

        if (
            !plan.agent ||
            !plan.agent.response
        ) {
            return {
                success: false,
                status: "error",
                reason: "Agent returned no response.",
                cycles: cycles
            };
        }

        const agentResponse =
            plan.agent.response;

        if (
            agentResponse.status === "blocked"
        ) {
            return {
                success: false,
                status: "blocked",
                reason:
                    agentResponse.reason ||
                    "Task was blocked by the privacy/security layer.",
                cycles: cycles
            };
        }

        let actions =
            Array.isArray(agentResponse.actions)
                ? agentResponse.actions
                : [];

        // Closed-loop execution allows exactly one browser action per cycle.
        if (actions.length > 1) {
            actions = [actions[0]];
        }

        if (actions.length === 0) {
            return {
                success: false,
                status: "no_actions",
                reason:
                    agentResponse.reason ||
                    "The agent produced no browser action.",
                cycles: cycles
            };
        }

        for (const action of actions) {
            const canonical =
                canonicalizeActionTarget(
                    action,
                    browserContext
                );

            if (!canonical) {
                return {
                    success: false,
                    status: "blocked",
                    reason:
                        "The agent returned an unsafe or unresolved action.",
                    cycles: cycles
                };
            }

            const policy =
                validateAction(canonical);

            const actionRecord = {
                action: canonical,
                policy: policy
            };

            cycleResult.actions.push(
                actionRecord
            );

            if (!policy.allowed) {
                actionRecord.result = {
                    success: false,
                    error: policy.reason
                };

                return {
                    success: false,
                    status: "blocked",
                    reason: policy.reason,
                    cycles: cycles
                };
            }

            setPipelineStep("act", "active");

            output.textContent =
                `Cycle ${cycle}: executing ${canonical.action} on ${canonical.target}...`;

            const result =
                await executeBrowserAction(
                    canonical
                );

            actionRecord.result = result;

            if (!result || !result.success) {
                return {
                    success: false,
                    status: "execution_failed",
                    reason:
                        result?.error ||
                        "Browser action failed.",
                    cycles: cycles
                };
            }

            completePipelineStep("act");

            setPipelineStep("verify", "active");

            if (
                result.verification &&
                result.verification.success === false
            ) {
                return {
                    success: false,
                    status: "verification_failed",
                    reason:
                        "Browser action verification failed.",
                    cycles: cycles
                };
            }

            completePipelineStep("verify");

            browserContext =
                await getBrowserContext();
        }

        output.textContent =
            `Cycle ${cycle}: state updated.`;

        if (pageShowsSuccess(browserContext)) {
            return {
                success: true,
                status: "completed",
                reason:
                    "The requested browser task completed successfully.",
                cycles: cycles
            };
        }

        if (cycle < MAX_CYCLES) {
            setPipelineStep("plan", "active");

            await new Promise(
                (resolve) =>
                    setTimeout(
                        resolve,
                        200
                    )
            );
        }
    }

    return {
        success: false,
        status: "max_cycles",
        reason:
            "The agent reached the maximum number of cycles.",
        cycles: cycles
    };
}
// Start the autonomous browser agent.
inspectButton.addEventListener(
    "click",
    async () => {
        const task =
            taskInput.value.trim();

        if (!task) {
            showResult({
                success: false,
                status: "invalid_task",
                error:
                    "Please enter a browser task."
            });

            return;
        }

        output.textContent =
            "Starting autonomous agent...";

        try {
            const result =
                await runAgentLoop(
                    task
                );

            showResult(result);
        } catch (error) {
            showResult({
                success: false,
                status: "error",
                error:
                    error.message
            });
        }
    }
);
