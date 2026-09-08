// Collect metadata for one visible interactive element.
function getElementData(element, type) {
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);

    if (
        rect.width <= 0 ||
        rect.height <= 0 ||
        style.display === "none" ||
        style.visibility === "hidden"
    ) {
        return null;
    }

    return {
        type: type,
        tag: element.tagName.toLowerCase(),
        role: element.getAttribute("role") || "",
        text: (element.innerText || "").trim(),
        aria_label: element.getAttribute("aria-label") || "",
        placeholder: element.getAttribute("placeholder") || "",
        input_type: element.getAttribute("type") || "",
        name: element.getAttribute("name") || "",
        id: element.id || "",
        value: element.value || "",
        visible: true,
        enabled: !element.disabled,
        box: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height
        }
    };
}

// Collect visible interactive elements from the page.
function collectInteractiveElements() {
    const selectors = {
        button: "button",
        input: "input",
        textarea: "textarea",
        select: "select",
        link: "a"
    };

    const elements = [];

    for (const [type, selector] of Object.entries(selectors)) {
        document.querySelectorAll(selector).forEach((element) => {
            const data = getElementData(element, type);

            if (data) {
                elements.push(data);
            }
        });
    }

    return elements;
}

// Remove credential values before leaving the browser context.
function collectSafeDom() {
    const elements = collectInteractiveElements();

    return elements.map((element) => {
        const safeElement = { ...element };

        if (
            safeElement.input_type.toLowerCase() === "password"
        ) {
            safeElement.value = "[REDACTED]";
        }

        return safeElement;
    });
}

// Collect visible page text without exposing password values.
function collectSafePageText() {
    const clonedDocument =
        document.documentElement.cloneNode(true);

    clonedDocument.querySelectorAll(
        'input[type="password"], textarea[type="password"]'
    ).forEach((element) => {
        element.value = "[REDACTED]";
        element.setAttribute(
            "value",
            "[REDACTED]"
        );
    });

    return (
        clonedDocument.innerText ||
        document.body?.innerText ||
        ""
    ).trim();
}

// Capture the current privacy-safe browser state.
function collectPageState() {
    return {
        url: window.location.href,
        title: document.title,
        elements: collectSafeDom(),
        page_text: collectSafePageText()
    };
}
// Find a visible interactive element using exact or descriptive targets.
function findTarget(target) {
    const normalizedTarget =
        String(target || "").trim();

    if (!normalizedTarget) {
        return null;
    }

    const elements = Array.from(
        document.querySelectorAll(
            "button, input, textarea, select, a"
        )
    );

    const targetLower =
        normalizedTarget.toLowerCase();

    // Resolve select/dropdown targets.
    if (
        /\b(dropdown|drop-down|select|selector|menu)\b/i.test(
            targetLower
        )
    ) {
        const selectCandidates =
            elements.filter(
                (element) =>
                    element.tagName.toLowerCase() === "select"
            );

        const cleanedTarget =
            targetLower
                .replace(
                    /\b(dropdown|drop-down|select|selector|menu)\b/gi,
                    " "
                )
                .replace(
                    /[^a-z0-9]+/g,
                    " "
                )
                .trim();

        const targetWords =
            cleanedTarget
                .split(/\s+/)
                .filter(Boolean);

        const matches =
            selectCandidates.filter((element) => {
                const label =
                    element.labels?.length
                        ? Array.from(element.labels)
                              .map(
                                  (item) =>
                                      item.innerText || ""
                              )
                              .join(" ")
                        : "";

                const values = [
                    element.getAttribute("name") || "",
                    element.id || "",
                    element.getAttribute("aria-label") || "",
                    element.getAttribute("placeholder") || "",
                    label,
                    element.innerText || ""
                ]
                    .join(" ")
                    .toLowerCase()
                    .replace(
                        /[^a-z0-9]+/g,
                        " "
                    );

                return (
                    targetWords.length > 0 &&
                    targetWords.every(
                        (word) =>
                            values.includes(word)
                    )
                );
            });

        if (matches.length === 1) {
            return matches[0];
        }

        // Direct fallback for a single visible select.
        if (
            selectCandidates.length === 1 &&
            (
                cleanedTarget === "" ||
                targetWords.length > 0
            )
        ) {
            const element =
                selectCandidates[0];

            const label =
                element.labels?.length
                    ? Array.from(element.labels)
                          .map(
                              (item) =>
                                  item.innerText || ""
                          )
                          .join(" ")
                    : "";

            const values = [
                element.getAttribute("name") || "",
                element.id || "",
                element.getAttribute("aria-label") || "",
                label,
                element.innerText || ""
            ]
                .join(" ")
                .toLowerCase();

            if (
                targetWords.some(
                    (word) =>
                        values.includes(word)
                )
            ) {
                return element;
            }
        }
    }

    // Prefer editable fields for type actions described as fields.
    const fieldWords =
        /\b(field|input|textbox|text box)\b/i.test(
            normalizedTarget
        );

    if (fieldWords) {
        const fieldCandidates =
            elements.filter((element) =>
                element.matches(
                    "input:not([type='password']), textarea"
                )
            );

        const targetWords =
            normalizedTarget
                .toLowerCase()
                .replace(
                    /\b(field|input|textbox|text box)\b/g,
                    ""
                )
                .trim();

        if (targetWords) {
            const semanticMatches =
                fieldCandidates.filter((element) => {
                    const values = [
                        element.getAttribute("name") || "",
                        element.id || "",
                        element.getAttribute("placeholder") || "",
                        element.getAttribute("aria-label") || ""
                    ];

                    return values.some((value) =>
                        value
                            .toLowerCase()
                            .includes(targetWords)
                    );
                });

            if (semanticMatches.length === 1) {
                return semanticMatches[0];
            }
        }
    }

    // Exact semantic match.
    const exactMatches =
        elements.filter((element) => {
            const values = [
                element.innerText || "",
                element.getAttribute("aria-label") || "",
                element.getAttribute("placeholder") || "",
                element.getAttribute("name") || "",
                element.id || ""
            ];

            return values.some(
                (value) =>
                    value.trim().toLowerCase() ===
                    targetLower
            );
        });

    if (exactMatches.length === 1) {
        return exactMatches[0];
    }

    // Match "button with text 'Search'".
    const textMatch =
        normalizedTarget.match(
            /^(?:button|input|textarea|select|link)\s+with\s+text\s+['"](.+)['"]$/i
        );

    if (textMatch) {
        const expectedText =
            textMatch[1].trim();

        const textMatches =
            elements.filter((element) => {
                const text =
                    (element.innerText || "").trim();

                return text === expectedText;
            });

        if (textMatches.length === 1) {
            return textMatches[0];
        }
    }

    // Match "button Search".
    const simpleMatch =
        normalizedTarget.match(
            /^(?:button|input|textarea|select|link)\s+(.+)$/i
        );

    if (simpleMatch) {
        const expectedText =
            simpleMatch[1].trim();

        const simpleMatches =
            elements.filter((element) => {
                const text =
                    (element.innerText || "").trim();

                return text === expectedText;
            });

        if (simpleMatches.length === 1) {
            return simpleMatches[0];
        }
    }

    return null;
}
// Verify that a type action changed the target value.
function verifyTypeAction(target, expectedValue) {
    if (!target) {
        return {
            success: false,
            error:
                "Target disappeared after typing."
        };
    }

    if (target.value !== expectedValue) {
        return {
            success: false,
            error:
                `Verification failed. Expected "${expectedValue}" ` +
                `but found "${target.value}".`
        };
    }

    return {
        success: true,
        verified_value:
            target.value
    };
}

// Wait briefly for browser state updates.
function waitForPageUpdate() {
    return new Promise((resolve) => {
        setTimeout(resolve, 150);
    });
}

// Verify a click by comparing state before and after the click.
async function verifyClickAction(beforeState) {
    await waitForPageUpdate();

    const afterState =
        collectPageState();

    const urlChanged =
        beforeState.url !==
        afterState.url;

    const pageChanged =
        beforeState.page_text !==
        afterState.page_text;

    const elementsChanged =
        JSON.stringify(
            beforeState.elements
        ) !==
        JSON.stringify(
            afterState.elements
        );

    const actualStateChanged =
        urlChanged ||
        pageChanged ||
        elementsChanged;

    return {
        success:
            actualStateChanged,
        url_changed:
            urlChanged,
        page_changed:
            pageChanged,
        elements_changed:
            elementsChanged,
        actual_state_changed:
            actualStateChanged,
        before_url:
            beforeState.url,
        after_url:
            afterState.url
    };
}

// Execute one validated browser action.
async function executeAction(action) {
    if (
        !action ||
        typeof action !== "object"
    ) {
        return {
            success: false,
            error:
                "Action must be an object."
        };
    }

    const actionType =
        action.action;

    if (
        actionType !== "click" &&
        actionType !== "type" &&
        actionType !== "select"
    ) {
        return {
            success: false,
            error:
                `Unsupported action: ${actionType}`
        };
    }

    const target =
        findTarget(action.target);

    if (!target) {
        return {
            success: false,
            error:
                `Could not uniquely resolve target: ${action.target}`
        };
    }

    if (target.disabled) {
        return {
            success: false,
            error:
                `Target is disabled: ${action.target}`
        };
    }

    if (actionType === "select") {
        if (
            typeof action.value !== "string"
        ) {
            return {
                success: false,
                error:
                    "Select action requires a string value."
            };
        }

        if (!target.matches("select")) {
            return {
                success: false,
                error:
                    "Select action requires a select element."
            };
        }

        const options =
            Array.from(target.options);

        const requestedValue =
            action.value.trim().toLowerCase();

        const option =
            options.find((item) =>
                item.text.trim().toLowerCase() ===
                requestedValue
            ) ||
            options.find((item) =>
                item.value.trim().toLowerCase() ===
                requestedValue
            );

        if (!option) {
            return {
                success: false,
                error:
                    `Could not find select option: ${action.value}`
            };
        }

        const beforeValue =
            target.value;

        target.value =
            option.value;

        target.dispatchEvent(
            new Event(
                "input",
                {
                    bubbles: true
                }
            )
        );

        target.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles: true
                }
            )
        );

        const verified =
            target.value === option.value;

        return {
            success: verified,
            action: "select",
            target: action.target,
            verification: {
                success: verified,
                before_value: beforeValue,
                selected_value: option.value,
                selected_text: option.text
            },
            post_action_state:
                collectPageState()
        };
    }

    if (actionType === "type") {
        if (
            typeof action.value !== "string"
        ) {
            return {
                success: false,
                error:
                    "Type action requires a string value."
            };
        }

        if (
            target.matches(
                'input[type="password"]'
            )
        ) {
            return {
                success: false,
                error:
                    "Typing into credential fields is blocked."
            };
        }

        if (
            !target.matches("input, textarea")
        ) {
            return {
                success: false,
                error:
                    "Typing is only allowed into input or textarea fields."
            };
        }
        target.focus();

        target.value =
            action.value;

        target.dispatchEvent(
            new Event(
                "input",
                {
                    bubbles: true
                }
            )
        );

        target.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles: true
                }
            )
        );

        const verification =
            verifyTypeAction(
                target,
                action.value
            );

        const postState =
            collectPageState();

        return {
            success:
                verification.success,
            action: "type",
            target:
                action.target,
            verification:
                verification,
            post_action_state:
                postState
        };
    }

    const beforeState =
        collectPageState();

    target.click();

    const verification =
        await verifyClickAction(
            beforeState
        );

    const postState =
        collectPageState();

    return {
        success:
            verification.success,
        action: "click",
        target:
            action.target,
        verification:
            verification,
        post_action_state:
            postState
    };
}

// Run the synthetic banking login flow.
async function demoLogin() {
    const passwordInput =
        document.querySelector('input[type="password"]');

    const inputs =
        Array.from(
            document.querySelectorAll(
                'input:not([type="password"])'
            )
        );

    const usernameInput =
        inputs.find((input) => {
            const text = [
                input.name,
                input.id,
                input.placeholder,
                input.getAttribute("aria-label")
            ]
                .filter(Boolean)
                .join(" ")
                .toLowerCase();

            return (
                text.includes("user") ||
                text.includes("customer") ||
                text.includes("account") ||
                text.includes("login") ||
                text.includes("id")
            );
        }) || inputs[0];

    if (!usernameInput || !passwordInput) {
        return {
            success: false,
            error:
                "Demo login fields could not be identified."
        };
    }

    const setValue = (element, value) => {
        const setter =
            Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype,
                "value"
            )?.set;

        if (setter) {
            setter.call(element, value);
        } else {
            element.value = value;
        }

        element.dispatchEvent(
            new Event("input", {
                bubbles: true
            })
        );

        element.dispatchEvent(
            new Event("change", {
                bubbles: true
            })
        );
    };

    setValue(
        usernameInput,
        "DEMO_USER_4821"
    );

    setValue(
        passwordInput,
        "Demo@4821"
    );

    const buttons =
        Array.from(
            document.querySelectorAll(
                'button, input[type="submit"]'
            )
        );

    const loginButton =
        buttons.find((button) => {
            const text = (
                button.innerText ||
                button.value ||
                button.getAttribute("aria-label") ||
                ""
            )
                .trim()
                .toLowerCase();

            return (
                text.includes("login") ||
                text.includes("sign in") ||
                text.includes("log in")
            );
        });

    if (!loginButton) {
        return {
            success: false,
            error:
                "Demo login button could not be identified."
        };
    }

    loginButton.click();

    return {
        success: true,
        action: "demo_login",
        target: "Login"
    };
}

// Open transaction history and extract the latest three transactions.
async function demoTransactions() {
    await new Promise((resolve) =>
        setTimeout(resolve, 500)
    );

    const links =
        Array.from(
            document.querySelectorAll(
                'a, button'
            )
        );

    const transactionControl =
        links.find((element) => {
            const text = (
                element.innerText ||
                element.textContent ||
                element.getAttribute("aria-label") ||
                ""
            )
                .trim()
                .toLowerCase();

            return (
                text.includes("transaction") ||
                text.includes("history")
            );
        });

    if (transactionControl) {
        transactionControl.click();

        await new Promise((resolve) =>
            setTimeout(resolve, 800)
        );
    }

    const rows =
        Array.from(
            document.querySelectorAll(
                "table tbody tr"
            )
        );

    let transactions = rows
        .map((row) => {
            const cells =
                Array.from(
                    row.querySelectorAll("td")
                )
                    .map((cell) =>
                        cell.innerText.trim()
                    )
                    .filter(Boolean);

            return cells;
        })
        .filter(
            (cells) => cells.length > 0
        )
        .slice(0, 3);

    if (transactions.length === 0) {
        const cards =
            Array.from(
                document.querySelectorAll(
                    '[class*="transaction"], [class*="Transaction"]'
                )
            );

        transactions = cards
            .map((card) =>
                card.innerText
                    .trim()
                    .split("\n")
                    .map((line) => line.trim())
                    .filter(Boolean)
            )
            .filter(
                (lines) => lines.length > 0
            )
            .slice(0, 3);
    }

    if (transactions.length === 0) {
        return {
            success: false,
            error:
                "Transaction history could not be identified."
        };
    }

    return {
        success: true,
        action: "demo_transactions",
        transactions: transactions
    };
}

// Handle DOM collection and browser action requests.
chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
        if (
            message.action ===
            "collect_dom"
        ) {
            try {
                sendResponse({
                    success: true,
                    ...collectPageState()
                });
            } catch (error) {
                sendResponse({
                    success: false,
                    error:
                        error.message
                });
            }

            return true;
        }

        if (
            message.action ===
            "execute_action"
        ) {
            executeAction(
                message.browserAction
            )
                .then((result) => {
                    sendResponse(result);
                })
                .catch((error) => {
                    sendResponse({
                        success: false,
                        error:
                            error.message
                    });
                });

            return true;
        }

        return false;
    }
);

// Confirm that the content script is loaded.
console.log(
    "Privacy Browser Agent content script loaded:",
    window.location.href
);




