// Send a message to a specific browser tab.
function sendMessageToTab(
    tabId,
    message,
    sendResponse,
    allowInjection = true
) {
    chrome.tabs.sendMessage(
        tabId,
        message,
        async (response) => {
            if (!chrome.runtime.lastError) {
                sendResponse(
                    response || {
                        success: false,
                        error:
                            "No response from content script."
                    }
                );

                return;
            }

            if (!allowInjection) {
                sendResponse({
                    success: false,
                    error:
                        chrome.runtime.lastError.message
                });

                return;
            }

            try {
                await chrome.scripting.executeScript({
                    target: {
                        tabId: tabId
                    },
                    files: ["content.js"]
                });
            } catch (error) {
                sendResponse({
                    success: false,
                    error:
                        "Could not inject content script: " +
                        error.message
                });

                return;
            }

            chrome.tabs.sendMessage(
                tabId,
                message,
                (retryResponse) => {
                    if (chrome.runtime.lastError) {
                        sendResponse({
                            success: false,
                            error:
                                chrome.runtime.lastError.message
                        });

                        return;
                    }

                    sendResponse(
                        retryResponse || {
                            success: false,
                            error:
                                "No response from content script after injection."
                        }
                    );
                }
            );
        }
    );
}

// Find a usable browser tab.
async function getActiveBrowserTab() {
    const windows = await chrome.windows.getAll({
        populate: true
    });

    const browserWindows = windows.filter(
        (window) =>
            window.type === "normal" &&
            Array.isArray(window.tabs)
    );

    if (browserWindows.length === 0) {
        return null;
    }

    const focusedWindow = browserWindows.find(
        (window) => window.focused
    );

    const targetWindow =
        focusedWindow || browserWindows[0];

    // Prefer the active tab only when it has a real page URL.
    const activeUsableTab =
        targetWindow.tabs.find(
            (tab) =>
                tab.active &&
                typeof tab.url === "string" &&
                tab.url.length > 0 &&
                !tab.url.startsWith("chrome://") &&
                !tab.url.startsWith("chrome-extension://") &&
                !tab.url.startsWith("devtools://")
        );

    if (activeUsableTab) {
        return activeUsableTab;
    }

    // Fall back to any usable page tab in the focused window.
    const usableTab =
        targetWindow.tabs.find(
            (tab) =>
                typeof tab.url === "string" &&
                tab.url.length > 0 &&
                !tab.url.startsWith("chrome://") &&
                !tab.url.startsWith("chrome-extension://") &&
                !tab.url.startsWith("devtools://")
        );

    if (usableTab) {
        return usableTab;
    }

    // Last fallback: search every normal browser window.
    for (const window of browserWindows) {
        const tab = window.tabs.find(
            (candidate) =>
                typeof candidate.url === "string" &&
                candidate.url.length > 0 &&
                !candidate.url.startsWith("chrome://") &&
                !candidate.url.startsWith("chrome-extension://") &&
                !candidate.url.startsWith("devtools://")
        );

        if (tab) {
            return tab;
        }
    }

    return null;
}

// Forward extension requests to the active browser tab.
chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
        if (
            message.action !== "get_page_context" &&
            message.action !== "execute_action"
        ) {
            return false;
        }

        getActiveBrowserTab()
            .then((tab) => {
                if (!tab || !tab.id) {
                    sendResponse({
                        success: false,
                        error:
                            "No usable browser tab."
                    });

                    return;
                }

                if (
                    message.action ===
                    "get_page_context"
                ) {
                    sendMessageToTab(
                        tab.id,
                        {
                            action: "collect_dom"
                        },
                        sendResponse
                    );

                    return;
                }

                if (
                    message.action ===
                    "execute_action"
                ) {
                    if (
                        !message.browserAction ||
                        typeof message.browserAction !==
                            "object"
                    ) {
                        sendResponse({
                            success: false,
                            error:
                                "Missing browser action."
                        });

                        return;
                    }

                    sendMessageToTab(
                        tab.id,
                        {
                            action:
                                "execute_action",
                            browserAction:
                                message.browserAction
                        },
                        sendResponse
                    );
                }
            })
            .catch((error) => {
                sendResponse({
                    success: false,
                    error:
                        "Could not determine browser tab: " +
                        error.message
                });
            });

        return true;
    }
);