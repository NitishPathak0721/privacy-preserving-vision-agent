// Render the actual transaction result stored by the agent.

function renderResult(data) {
    const container =
        document.getElementById("transactions");

    container.textContent = "";

    if (
        !data ||
        !data.demoResult ||
        !data.demoResult.success
    ) {
        const message =
            document.createElement("div");

        message.className = "empty";

        message.textContent =
            data?.demoResult?.error ||
            "No completed agent result available.";

        container.appendChild(message);

        return;
    }

    const transactions =
        Array.isArray(
            data.demoResult.transactions
        )
            ? data.demoResult.transactions
            : [];

    if (transactions.length === 0) {
        const message =
            document.createElement("div");

        message.className = "empty";

        message.textContent =
            "No transactions were returned.";

        container.appendChild(message);

        return;
    }

    transactions
        .slice(0, 3)
        .forEach((transaction) => {
            const card =
                document.createElement("div");

            card.className =
                "transaction";

            if (Array.isArray(transaction)) {
                transaction.forEach((value) => {
                    const line =
                        document.createElement("div");

                    line.className =
                        "transaction-line";

                    line.textContent =
                        String(value);

                    card.appendChild(line);
                });
            } else {
                const line =
                    document.createElement("div");

                line.className =
                    "transaction-line";

                line.textContent =
                    String(transaction);

                card.appendChild(line);
            }

            container.appendChild(card);
        });
}

chrome.storage.local
    .get(["demoResult"])
    .then(renderResult);
