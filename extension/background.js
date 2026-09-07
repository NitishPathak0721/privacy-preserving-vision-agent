// Background service worker for the privacy-preserving browser agent.

const BRIDGE_URL = "http://127.0.0.1:8765";
const DEMO_URL = "https://sih-2026-demo-clone.vercel.app/login";

let demoRunning = false;

// Find a usable browser tab.
async function getActiveBrowserTab() {
    const windows = await chrome.windows.getAll({
        populate: true
    });

    for (const window of windows) {
        if (window.type !== "normal") {
            continue;
        }

        const activeTab = (window.tabs || []).find(
            (tab) =>
                tab.active &&
                tab.url &&
                /^https?:\/\//i.test(tab.url)
        );

        if (activeTab) {
            return activeTab;
        }
    }

    for (const window of windows) {
        if (window.type !== "normal") {
            continue;
        }

        const demoTab = (window.tabs || []).find(
            (tab) =>
                tab.url &&
                tab.url.startsWith(DEMO_URL)
        );

        if (demoTab) {
            return demoTab;
        }
    }

    return await chrome.tabs.create({
        url: DEMO_URL,
        active: true
    });
}

// Inject content script if necessary and send a message.
async function sendMessageToTab(tabId, message, sendResponse) {
    try {
        let response;

        try {
            response = await chrome.tabs.sendMessage(
                tabId,
                message
            );
        } catch (firstError) {
            await chrome.scripting.executeScript({
                target: {
                    tabId: tabId
                },
                files: ["content.js"]
            });

            await new Promise((resolve) =>
                setTimeout(resolve, 200)
            );

            response = await chrome.tabs.sendMessage(
                tabId,
                message
            );
        }

        sendResponse(response);
    } catch (error) {
        sendResponse({
            success: false,
            error:
                error?.message ||
                "Failed to communicate with browser tab."
        });
    }
}

// Wait until a tab finishes loading.
function waitForTabComplete(tabId, timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
        let finished = false;

        const cleanup = () => {
            chrome.tabs.onUpdated.removeListener(listener);
            clearTimeout(timeout);
        };

        const finish = () => {
            if (finished) {
                return;
            }

            finished = true;
            cleanup();
            resolve();
        };

        const listener = (updatedTabId, changeInfo) => {
            if (
                updatedTabId === tabId &&
                changeInfo.status === "complete"
            ) {
                finish();
            }
        };

        const timeout = setTimeout(() => {
            if (finished) {
                return;
            }

            finished = true;
            cleanup();
            reject(new Error("Browser page load timed out."));
        }, timeoutMs);

        chrome.tabs.onUpdated.addListener(listener);

        chrome.tabs.get(tabId)
            .then((tab) => {
                if (tab.status === "complete") {
                    finish();
                }
            })
            .catch(() => {});
    });
}

// Execute a browser action.
async function executeBrowserAction(tabId, browserAction) {
    if (!browserAction || typeof browserAction !== "object") {
        return {
            success: false,
            error: "Missing browser action."
        };
    }

    const actionType = String(
        browserAction.action || ""
    ).toLowerCase();

    if (actionType === "navigate") {
        const targetUrl = String(
            browserAction.target || ""
        ).trim();

        if (!/^https?:\/\//i.test(targetUrl)) {
            return {
                success: false,
                error: "Invalid navigation URL."
            };
        }

        await chrome.tabs.update(tabId, {
            url: targetUrl,
            active: true
        });

        return {
            success: true,
            action: browserAction,
            verification: {
                success: true,
                page_changed: true
            }
        };
    }

    return await new Promise((resolve) => {
        sendMessageToTab(
            tabId,
            {
                action: "execute_action",
                browserAction: browserAction
            },
            resolve
        );
    });
}

// Run the deterministic live banking demo in the background.
async function runBankDemo(task) {
    if (demoRunning) {
        return {
            success: false,
            status: "busy",
            error: "A demo task is already running."
        };
    }

    demoRunning = true;

    await chrome.storage.local.set({
        demoResult: null,
        demoStatus: "running",
        demoTask: task || ""
    });

    try {
        let tab = await getActiveBrowserTab();

        if (!tab || !tab.id) {
            throw new Error("No usable browser tab.");
        }

        const tabId = tab.id;

        await chrome.tabs.update(tabId, {
            url: DEMO_URL,
            active: true
        });

        await waitForTabComplete(tabId, 20000);

        await new Promise((resolve) =>
            setTimeout(resolve, 1500)
        );

        // Perform the synthetic demo login directly in the page.
        const loginResult =
            await chrome.scripting.executeScript({
                target: {
                    tabId: tabId
                },
                func: () => {
                    const inputs =
                        Array.from(
                            document.querySelectorAll("input")
                        );

                    const passwordInput =
                        inputs.find(
                            (input) =>
                                input.type === "password"
                        );

                    const customerInput =
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
                                input.type !== "password" &&
                                (
                                    text.includes("customer") ||
                                    text.includes("user") ||
                                    text.includes("login") ||
                                    text.includes("account") ||
                                    text.includes("id")
                                )
                            );
                        }) ||
                        inputs.find(
                            (input) =>
                                input.type !== "password"
                        );

                    if (
                        !customerInput ||
                        !passwordInput
                    ) {
                        return {
                            success: false,
                            error:
                                "Login fields not found."
                        };
                    }

                    const setInputValue = (
                        input,
                        value
                    ) => {
                        const setter =
                            Object.getOwnPropertyDescriptor(
                                HTMLInputElement.prototype,
                                "value"
                            )?.set;

                        if (setter) {
                            setter.call(input, value);
                        } else {
                            input.value = value;
                        }

                        input.dispatchEvent(
                            new Event("input", {
                                bubbles: true
                            })
                        );

                        input.dispatchEvent(
                            new Event("change", {
                                bubbles: true
                            })
                        );
                    };

                    setInputValue(
                        customerInput,
                        "1234567890"
                    );

                    setInputValue(
                        passwordInput,
                        "Demo@4821"
                    );

                    const buttons =
                        Array.from(
                            document.querySelectorAll(
                                "button, input[type='submit']"
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
                                text === "login" ||
                                text === "log in" ||
                                text === "sign in" ||
                                text.includes("login")
                            );
                        });

                    if (!loginButton) {
                        return {
                            success: false,
                            error:
                                "Login button not found."
                        };
                    }

                    loginButton.click();

                    return {
                        success: true
                    };
                }
            });

        const login =
            loginResult?.[0]?.result;

        if (!login || !login.success) {
            throw new Error(
                login?.error ||
                "Demo login failed."
            );
        }

        await new Promise((resolve) =>
            setTimeout(resolve, 1800)
        );

        // Open transactions and extract the latest three rows.
        const transactionResult =
            await chrome.scripting.executeScript({
                target: {
                    tabId: tabId
                },
                func: () => {
                    const controls =
                        Array.from(
                            document.querySelectorAll(
                                "a, button"
                            )
                        );

                    const transactionControl =
                        controls.find((element) => {
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
                    }

                    return {
                        success: true
                    };
                }
            });

        const transactionOpen =
            transactionResult?.[0]?.result;

        if (
            !transactionOpen ||
            !transactionOpen.success
        ) {
            throw new Error(
                "Could not open transaction history."
            );
        }

        await new Promise((resolve) =>
            setTimeout(resolve, 1200)
        );

        const extractionResult =
            await chrome.scripting.executeScript({
                target: {
                    tabId: tabId
                },
                func: () => {
                    const rows =
                        Array.from(
                            document.querySelectorAll(
                                "table tbody tr"
                            )
                        );

                    let transactions =
                        rows
                            .map((row) =>
                                Array.from(
                                    row.querySelectorAll("td")
                                )
                                    .map((cell) =>
                                        cell.innerText.trim()
                                    )
                                    .filter(Boolean)
                            )
                            .filter(
                                (cells) =>
                                    cells.length > 0
                            )
                            .slice(0, 3);

                    if (
                        transactions.length === 0
                    ) {
                        const text =
                            document.body.innerText || "";

                        const lines =
                            text
                                .split("\n")
                                .map((line) =>
                                    line.trim()
                                )
                                .filter(Boolean);

                        const transactionLines =
                            lines.filter((line) =>
                                /₹|INR|Amazon|Salary|Food|Uber|Electricity|Grocery|Recharge|Movie|Restaurant/i.test(
                                    line
                                )
                            );

                        transactions =
                            transactionLines
                                .slice(0, 3)
                                .map((line) => [line]);
                    }

                    return {
                        success:
                            transactions.length > 0,
                        transactions:
                            transactions
                    };
                }
            });

        const extracted =
            extractionResult?.[0]?.result;

        if (
            !extracted ||
            !extracted.success
        ) {
            throw new Error(
                "Transaction history could not be extracted."
            );
        }

        const result = {
            success: true,
            status: "completed",
            task: task || "",
            transactions:
                extracted.transactions,
            message:
                "The last 3 transactions were retrieved successfully."
        };

        await chrome.storage.local.set({
            demoResult: result,
            demoStatus: "completed"
        });

        await chrome.tabs.create({
            url: chrome.runtime.getURL("result.html"),
            active: true
        });

        return result;
    } catch (error) {
        const result = {
            success: false,
            status: "error",
            error:
                error?.message ||
                "Demo execution failed."
        };

        await chrome.storage.local.set({
            demoResult: result,
            demoStatus: "error"
        });

        return result;
    } finally {
        demoRunning = false;
    }
}

// Handle extension messages.
chrome.runtime.onMessage.addListener(
    (message, sender, sendResponse) => {
        if (!message || typeof message !== "object") {
            return false;
        }

        if (message.action === "get_active_tab") {
            getActiveBrowserTab()
                .then((tab) => {
                    sendResponse({
                        success: true,
                        tab: tab
                    });
                })
                .catch((error) => {
                    sendResponse({
                        success: false,
                        error:
                            error?.message ||
                            "No usable browser tab."
                    });
                });

            return true;
        }

        if (message.action === "get_browser_context") {
            getActiveBrowserTab()
                .then(async (tab) => {
                    if (!tab || !tab.id) {
                        throw new Error(
                            "No usable browser tab."
                        );
                    }

                    const response = await new Promise((resolve) => {
                        sendMessageToTab(
                            tab.id,
                            {
                                action: "collect_dom"
                            },
                            resolve
                        );
                    });

                    if (!response || response.success === false) {
                        throw new Error(
                            response?.error ||
                            "Content script could not collect browser context."
                        );
                    }

                    sendResponse({
                        success: true,
                        tab: tab,
                        context: response
                    });
                })
                .catch((error) => {
                    sendResponse({
                        success: false,
                        error:
                            error?.message ||
                            "Could not collect browser context."
                    });
                });

            return true;
        }

        if (message.action === "execute_action") {
            getActiveBrowserTab()
                .then(async (tab) => {
                    if (!tab || !tab.id) {
                        throw new Error(
                            "No usable browser tab."
                        );
                    }

                    const result =
                        await executeBrowserAction(
                            tab.id,
                            message.browserAction
                        );

                    sendResponse(result);
                })
                .catch((error) => {
                    sendResponse({
                        success: false,
                        error:
                            error?.message ||
                            "Browser action failed."
                    });
                });

            return true;
        }

        if (message.action === "run_demo_task") {
            runBankDemo(message.task || "")
                .then(sendResponse)
                .catch((error) => {
                    sendResponse({
                        success: false,
                        status: "error",
                        error:
                            error?.message ||
                            "Demo task failed."
                    });
                });

            return true;
        }

        if (message.action === "get_demo_result") {
            chrome.storage.local.get(
                [
                    "demoResult",
                    "demoStatus",
                    "demoTask"
                ]
            ).then((data) => {
                sendResponse({
                    success: true,
                    result: data.demoResult || null,
                    status: data.demoStatus || "idle",
                    task: data.demoTask || ""
                });
            });

            return true;
        }

        return false;
    }
);
