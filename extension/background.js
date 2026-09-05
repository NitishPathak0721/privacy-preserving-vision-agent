// Forward page-context requests to the active tab.
chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
        if (message.action !== "get_page_context") {
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

                chrome.tabs.sendMessage(
                    tab.id,
                    {
                        action: "collect_dom"
                    },
                    (response) => {
                        if (chrome.runtime.lastError) {
                            sendResponse({
                                success: false,
                                error: chrome.runtime.lastError.message
                            });
                            return;
                        }

                        sendResponse(
                            response || {
                                success: false,
                                error: "No response from content script."
                            }
                        );
                    }
                );
            }
        );

        return true;
    }
);