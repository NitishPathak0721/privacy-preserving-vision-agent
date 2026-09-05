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
                field === "name" ||
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

    const allElements =
        Array.isArray(
            browserContext.elements
        )
            ? browserContext.elements
            : [];

    const elements =
        allElements.filter(
            (element) =>
                isElementSuitableForAction(
                    element,
                    actionType
                )
        );

    // Prefer deterministic field identifiers for common type targets.
    if (
        actionType === "type" &&
        [
            "name field",
            "name input",
            "name textbox",
            "name text field",
            "enter name",
            "enter your name"
        ].includes(
            normalizeTargetText(target)
        )
    ) {
        const nameMatches =
            elements.filter(
                (element) => {
                    const id =
                        normalizeTargetText(
                            element.id
                        );

                    const name =
                        normalizeTargetText(
                            element.name
                        );

                    const placeholder =
                        normalizeTargetText(
                            element.placeholder
                        );

                    const ariaLabel =
                        normalizeTargetText(
                            element.aria_label
                        );

                    return (
                        id === "name" ||
                        name === "name" ||
                        placeholder === "enter your name" ||
                        ariaLabel === "name"
                    );
                }
            );

        if (nameMatches.length === 1) {
            const element =
                nameMatches[0];

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
    }

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

// Sanitize PII before displaying results.
function sanitizeDisplayedText(
    value
) {
    if (
        typeof value !== "string"
    ) {
        return value;
    }

    return value
        .replace(
            /\b[A-Z]{5}\d{4}[A-Z]\b/gi,
            "[PAN]"
        )
        .replace(
            /\b\d{4}\s?\d{4}\s?\d{4}\b/g,
            "[AADHAAR]"
        )
        .replace(
            /\b(?:\d[ -]?){13,19}\b/g,
            "[CREDIT_CARD]"
        )
        .replace(
            /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
            "[EMAIL]"
        )
        .replace(
            /(?:\+91[\s-]?)?[6-9]\d{9}\b/g,
            "[PHONE]"
        );
}

// Recursively sanitize values before displaying them.
function sanitizeDisplayedValue(
    value
) {
    if (
        typeof value === "string"
    ) {
        return sanitizeDisplayedText(
            value
        );
    }

    if (
        Array.isArray(value)
    ) {
        return value.map(
            (item) =>
                sanitizeDisplayedValue(
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
            const [
                key,
                item
            ] of Object.entries(value)
        ) {
            if (
                key === "value" &&
                typeof item === "string"
            ) {
                sanitized[key] =
                    item.includes("[REDACTED]")
                        ? "[REDACTED]"
                        : sanitizeDisplayedText(
                            item
                        );
            } else {
                sanitized[key] =
                    sanitizeDisplayedValue(
                        item
                    );
            }
        }

        return sanitized;
    }

    return value;
}

// Display the final result safely.
function showResult(
    result
) {
    const safeResult =
        sanitizeDisplayedValue(
            result
        );

    output.textContent =
        JSON.stringify(
            safeResult,
            null,
            2
        );
}

// Update agent status.
function setStatus(
    status,
    type = "idle"
) {
    const statusText =
        document.getElementById(
            "status-text"
        );

    const statusDot =
        document.getElementById(
            "status-dot"
        );

    if (statusText) {
        statusText.textContent =
            status;
    }

    if (statusDot) {
        statusDot.className =
            `status-dot ${type}`;
    }
}

// Run the autonomous observe-plan-act loop.
async function runAgentLoop(
    task
) {
    let browserContext =
        await getBrowserContext();

    const cycles = [];

    for (
        let cycle = 1;
        cycle <= MAX_CYCLES;
        cycle++
    ) {
        setStatus(
            `Cycle ${cycle}: inspecting browser`,
            "running"
        );

        browserContext =
            await getBrowserContext();

        const agentResult =
            await callBridge(
                "/agent",
                {
                    task: task,
                    url: browserContext.url,
                    title: browserContext.title,
                    elements: browserContext.elements,
                    page_text: browserContext.page_text || ""
                }
            );

        const plan =
            agentResult?.agent?.response ||
            agentResult?.plan ||
            agentResult?.response ||
            agentResult;

        const cycleRecord = {
            cycle: cycle,
            privacy:
                plan.privacy || {},
            agent: {
                model:
                    plan.model ||
                    "qwen2.5vl:3b",
                response:
                    plan.plan ||
                    plan.response ||
                    plan
            },
            actions: []
        };

        cycles.push(
            cycleRecord
        );

        if (
            plan.status ===
            "requires_user_input"
        ) {
            setStatus(
                `User input required: ${
                    plan.missing_information ||
                    "required information"
                }`,
                "warning"
            );

            return {
                success: false,
                status:
                    "requires_user_input",
                reason:
                    plan.reason ||
                    "The task requires information that only the user can provide.",
                missing_information:
                    plan.missing_information ||
                    "",
                cycles: cycles
            };
        }

        if (
            plan.status ===
            "blocked"
        ) {
            setStatus(
                "Action blocked by security policy",
                "error"
            );

            return {
                success: false,
                status: "blocked",
                reason:
                    plan.reason ||
                    "The action was blocked.",
                cycles: cycles
            };
        }

        if (
            plan.status ===
            "completed"
        ) {
            setStatus(
                "Task completed",
                "success"
            );

            return {
                success: true,
                status: "completed",
                reason:
                    plan.reason ||
                    "Task completed successfully.",
                cycles: cycles
            };
        }

        if (
            plan.status !== "ready"
        ) {
            setStatus(
                "Agent not ready",
                "error"
            );

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
            setStatus(
                "No executable action",
                "error"
            );

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

                setStatus(
                    "Action blocked",
                    "error"
                );

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

            setStatus(
                `Cycle ${cycle}: executing ${action.action} on ${action.target}`,
                "running"
            );

            try {
                const result =
                    await executeBrowserAction(
                        action
                    );

                actionRecord.result =
                    result;

                if (!result.success) {
                    setStatus(
                        "Action failed",
                        "error"
                    );

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

                const verification =
                    result.verification;

                if (
                    verification &&
                    verification.success === false
                ) {
                    setStatus(
                        "Action verification failed",
                        "error"
                    );

                    return {
                        success: false,
                        status:
                            "verification_failed",
                        cycles: cycles
                    };
                }

                if (
                    verification &&
                    verification.success === true
                ) {
                    actionRecord.result =
                        result;
                }

                const refreshedContext =
                    await getBrowserContext();

                browserContext =
                    refreshedContext;

                // Continue explicit type-then-click tasks after successful typing.
                const sequenceMatch =
                    task.match(
                        /^type\s+(.+?)\s+into\s+(.+?)\s+and\s+then\s+click\s+(.+)$/i
                    );

                if (
                    sequenceMatch &&
                    action.action === "type"
                ) {
                    const clickTarget =
                        sequenceMatch[3].trim();

                    const clickAction = {
                        action: "click",
                        target: clickTarget
                    };

                    const canonicalClickAction =
                        canonicalizeActionTarget(
                            clickAction,
                            browserContext
                        );

                    const clickPolicy =
                        validateAction(
                            canonicalClickAction
                        );

                    const clickRecord = {
                        action:
                            canonicalClickAction,
                        policy:
                            clickPolicy
                    };

                    cycleRecord.actions.push(
                        clickRecord
                    );

                    if (!clickPolicy.allowed) {
                        clickRecord.result = {
                            success: false,
                            error:
                                clickPolicy.reason
                        };

                        setStatus(
                            "Action blocked",
                            "error"
                        );

                        return {
                            success: false,
                            status: "blocked",
                            cycles: cycles
                        };
                    }

                    setStatus(
                        `Cycle ${cycle}: executing click on ${canonicalClickAction.target}`,
                        "running"
                    );

                    const clickResult =
                        await executeBrowserAction(
                            canonicalClickAction
                        );

                    clickRecord.result =
                        clickResult;

                    if (!clickResult.success) {
                        setStatus(
                            "Action failed",
                            "error"
                        );

                        return {
                            success: false,
                            status:
                                "execution_failed",
                            cycles: cycles
                        };
                    }

                    const clickPostActionContext =
                        getPostActionContext(
                            clickResult
                        );

                    if (
                        clickPostActionContext
                    ) {
                        browserContext =
                            clickPostActionContext;
                    } else {
                        browserContext =
                            await getBrowserContext();
                    }

                    const clickVerification =
                        clickResult.verification;

                    if (
                        clickVerification &&
                        clickVerification.success === false
                    ) {
                        setStatus(
                            "Action verification failed",
                            "error"
                        );

                        return {
                            success: false,
                            status:
                                "verification_failed",
                            cycles: cycles
                        };
                    }

                    const finalContext =
                        await getBrowserContext();

                    browserContext =
                        finalContext;

                    if (
                        finalContext.page_text
                            .toLowerCase()
                            .includes(
                                "search completed successfully"
                            )
                    ) {
                        setStatus(
                            "Task completed",
                            "success"
                        );

                        return {
                            success: true,
                            status: "completed",
                            reason:
                                "The requested type-and-click sequence completed successfully.",
                            cycles: cycles
                        };
                    }

                    if (
                        clickVerification &&
                        clickVerification.success === true
                    ) {
                        setStatus(
                            "Task completed",
                            "success"
                        );

                        return {
                            success: true,
                            status: "completed",
                            reason:
                                "The requested type-and-click sequence was executed successfully.",
                            cycles: cycles
                        };
                    }
                }

                if (
                    action.action === "click" &&
                    refreshedContext.page_text
                        .toLowerCase()
                        .includes(
                            "completed successfully"
                        )
                ) {
                    setStatus(
                        "Task completed",
                        "success"
                    );

                    return {
                        success: true,
                        status: "completed",
                        reason:
                            "The requested final click was executed successfully.",
                        cycles: cycles
                    };
                }

                if (
                    refreshedContext.page_text
                        .toLowerCase()
                        .includes(
                            "search completed successfully"
                        )
                ) {
                    setStatus(
                        "Task completed",
                        "success"
                    );

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

                setStatus(
                    "Action failed",
                    "error"
                );

                return {
                    success: false,
                    status:
                        "execution_failed",
                    cycles: cycles
                };
            }
        }

        setStatus(
            `Cycle ${cycle}: state updated`,
            "running"
        );

        await new Promise(
            (resolve) =>
                setTimeout(
                    resolve,
                    200
                )
        );
    }

    setStatus(
        "Maximum cycles reached",
        "error"
    );

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

            setStatus(
                "Enter a browser task",
                "warning"
            );

            return;
        }

        inspectButton.disabled = true;

        setStatus(
            "Starting autonomous agent...",
            "running"
        );

        output.textContent =
            "Starting autonomous agent...";

        try {
            const result =
                await runAgentLoop(
                    task
                );

            showResult(result);
        } catch (error) {
            setStatus(
                "Action failed",
                "error"
            );

            showResult({
                success: false,
                status:
                    "execution_failed",
                error:
                    error.message
            });
        } finally {
            inspectButton.disabled = false;
        }
    }
);