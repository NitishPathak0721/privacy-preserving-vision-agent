// Get the popup controls.
const taskInput = document.getElementById("task");
const inspectButton = document.getElementById("inspect");
const output = document.getElementById("output");

// Actions allowed to execute automatically.
const ALLOWED_ACTIONS = new Set([
    "click",
    "type"
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
            action: "get_page_context"
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
        return [
            "input",
            "textarea"
        ].includes(elementType);
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

// Resolve the safest canonical target from the current browser context.
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

    const elements =
        browserContext.elements.filter(
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

    if (exactMatches.length === 1) {
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

    // Resolve common natural-language targets.
    const semanticMatches =
        elements.filter(
            (element) =>
                elementMatchesSemanticTarget(
                    element,
                    target,
                    actionType
                )
        );

    if (semanticMatches.length !== 1) {
        return action;
    }

    const element =
        semanticMatches[0];

    const canonicalTarget =
        [
            element.placeholder,
            element.aria_label,
            element.text,
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

// Display a privacy-safe formatted result.
function showResult(result) {
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
    const cycles = [];

    let browserContext =
        await getBrowserContext();

    for (
        let cycle = 1;
        cycle <= MAX_CYCLES;
        cycle++
    ) {
        output.textContent =
            `Cycle ${cycle}: planning...`;

        const agentResult =
            await getAgentPlan(
                task,
                browserContext
            );

        if (!agentResult.success) {
            return {
                success: false,
                cycles: cycles,
                error:
                    agentResult.error ||
                    "Agent planning failed."
            };
        }

        const agent =
            agentResult.agent;

        const plan =
            agent?.response;

        if (!plan) {
            return {
                success: false,
                cycles: cycles,
                error:
                    "Agent returned no plan."
            };
        }

        const cycleRecord = {
            cycle: cycle,
            privacy:
                agentResult.privacy,
            agent: {
                model:
                    agent.model,
                response:
                    plan
            },
            actions: []
        };

        cycles.push(
            cycleRecord
        );

        if (
            plan.status === "completed" ||
            plan.status === "done"
        ) {
            return {
                success: true,
                status: "completed",
                cycles: cycles
            };
        }

        if (
            plan.status !== "ready"
        ) {
            return {
                success: false,
                status:
                    "agent_not_ready",
                cycles: cycles
            };
        }

        const actions =
            Array.isArray(plan.actions)
                ? plan.actions
                : [];

        if (
            actions.length === 0
        ) {
            return {
                success: false,
                status:
                    "no_actions",
                cycles: cycles
            };
        }

        for (
            let actionIndex = 0;
            actionIndex < actions.length;
            actionIndex++
        ) {
            const originalAction =
                actions[actionIndex];

            // Resolve model-generated natural-language targets against the safe DOM.
            const action =
                canonicalizeActionTarget(
                    originalAction,
                    browserContext
                );

            const policy =
                validateAction(action);

            const actionRecord = {
                action: action,
                policy: policy
            };

            cycleRecord.actions.push(
                actionRecord
            );

            if (!policy.allowed) {
                actionRecord.result = {
                    success: false,
                    error:
                        policy.reason
                };

                return {
                    success: false,
                    status: "blocked",
                    cycles: cycles,
                    security: {
                        status: "blocked",
                        reason:
                            policy.reason
                    }
                };
            }

            output.textContent =
                `Cycle ${cycle}: executing ${action.action} on ${action.target}...`;

            try {
                const result =
                    await executeBrowserAction(
                        action
                    );

                actionRecord.result =
                    result;

                if (!result.success) {
                    return {
                        success: false,
                        status:
                            "execution_failed",
                        cycles: cycles
                    };
                }

                const postActionContext =
                    getPostActionContext(
                        result
                    );

                if (
                    postActionContext
                ) {
                    browserContext =
                        postActionContext;
                } else {
                    browserContext =
                        await getBrowserContext();
                }

                const isLastAction =
                    actionIndex ===
                    actions.length - 1;

                // Complete the task when the final requested click succeeds.
                if (
                    isLastAction &&
                    isFinalClickAction(
                        task,
                        action
                    )
                ) {
                    return {
                        success: true,
                        status: "completed",
                        reason:
                            "The requested final click was executed successfully.",
                        cycles: cycles
                    };
                }

                // Complete when the page explicitly reports success.
                if (
                    pageShowsSuccess(
                        browserContext
                    )
                ) {
                    return {
                        success: true,
                        status: "completed",
                        reason:
                            "The browser page explicitly reports successful completion.",
                        cycles: cycles
                    };
                }
            } catch (error) {
                actionRecord.result = {
                    success: false,
                    error:
                        error.message
                };

                return {
                    success: false,
                    status:
                        "execution_failed",
                    cycles: cycles
                };
            }
        }

        output.textContent =
            `Cycle ${cycle}: state updated.`;

        await new Promise(
            (resolve) =>
                setTimeout(
                    resolve,
                    200
                )
        );
    }

    return {
        success: false,
        status:
            "max_cycles_reached",
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
                error:
                    error.message
            });
        }
    }
);