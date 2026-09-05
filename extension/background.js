// Send a message to the active tab.
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

// Forward extension requests to the active browser tab.
chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
        if (
            message.action !== "get_page_context" &&
            message.action !== "execute_action"
        ) {
            return false;
        }

        chrome.tabs.query(
            {
                active: true,
                currentWindow: true
            },
            (tabs) => {
                const tab = tabs[0];

                if (!tab || !tab.id) {
                    sendResponse({
                        success: false,
                        error: "No active tab."
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
                            action: "execute_action",
                            browserAction:
                                message.browserAction
                        },
                        sendResponse
                    );
                }
            }
        );

        return true;
    }
);