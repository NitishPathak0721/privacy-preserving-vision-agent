// Get the popup controls.
const button = document.getElementById("inspect");
const output = document.getElementById("output");

// Send browser context through the local privacy firewall.
button.addEventListener("click", async () => {
    output.textContent = "Inspecting...";

    try {
        const browserContext = await chrome.runtime.sendMessage({
            action: "get_page_context"
        });

        if (!browserContext || !browserContext.success) {
            output.textContent = JSON.stringify(
                browserContext,
                null,
                2
            );
            return;
        }

        const firewallResponse = await fetch(
            "http://127.0.0.1:8765/inspect",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    url: browserContext.url,
                    title: browserContext.title,
                    elements: browserContext.elements,
                    page_text: ""
                })
            }
        );

        const result = await firewallResponse.json();

        output.textContent = JSON.stringify(
            result,
            null,
            2
        );
    } catch (error) {
        output.textContent = JSON.stringify(
            {
                success: false,
                error: error.message
            },
            null,
            2
        );
    }
});