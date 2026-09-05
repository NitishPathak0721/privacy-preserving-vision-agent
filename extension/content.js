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
    const clonedDocument = document.documentElement.cloneNode(true);

    clonedDocument.querySelectorAll(
        'input[type="password"], textarea[type="password"]'
    ).forEach((element) => {
        element.value = "[REDACTED]";
        element.setAttribute("value", "[REDACTED]");
    });

    return (
        clonedDocument.innerText ||
        document.body?.innerText ||
        ""
    ).trim();
}

// Handle DOM collection requests.
chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
        if (message.action !== "collect_dom") {
            return false;
        }

        try {
            sendResponse({
                success: true,
                url: window.location.href,
                title: document.title,
                elements: collectSafeDom(),
                page_text: collectSafePageText()
            });
        } catch (error) {
            sendResponse({
                success: false,
                error: error.message
            });
        }

        return true;
    }
);