// Get the popup controls.
const button = document.getElementById("inspect");
const output = document.getElementById("output");

// Request the current page context.
button.addEventListener("click", async () => {
    output.textContent = "Inspecting...";

    try {
        const response = await chrome.runtime.sendMessage({
            action: "get_page_context"
        });

        output.textContent = JSON.stringify(
            response,
            null,
            2
        );
    } catch (error) {
        output.textContent = error.message;
    }
});