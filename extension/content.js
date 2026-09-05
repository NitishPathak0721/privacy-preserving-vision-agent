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

    // Try exact matches first.
    const exactMatches = elements.filter((element) => {
        const text =
            (element.innerText || "").trim();

        const ariaLabel =
            element.getAttribute("aria-label") || "";

        const placeholder =
            element.getAttribute("placeholder") || "";

        const name =
            element.getAttribute("name") || "";

        const id =
            element.id || "";

        return [
            text,
            ariaLabel,
            placeholder,
            name,
            id
        ].some(
            (value) =>
                value === normalizedTarget
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
        actionType !== "type"
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