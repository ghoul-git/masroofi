// Small helpers shared by the pages: CSRF token, JSON fetch, error formatting.
(function () {
    function csrfToken() {
        const cookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrftoken="));
        if (cookie) {
            return decodeURIComponent(cookie.slice("csrftoken=".length));
        }
        const input = document.querySelector("[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    // Turn a DRF error body ({field: [messages]} or {detail: "..."}) into lines of text.
    function errorMessages(body) {
        if (!body || typeof body !== "object") {
            return ["Something went wrong. Please try again."];
        }
        const messages = [];
        // The service messages already name their field ("Total must not be negative."),
        // so only the text is shown.
        for (const value of Object.values(body)) {
            for (const message of Array.isArray(value) ? value : [value]) {
                messages.push(typeof message === "string" ? message : JSON.stringify(message));
            }
        }
        return messages.length ? messages : ["Something went wrong. Please try again."];
    }

    class ApiError extends Error {
        constructor(status, messages) {
            super(messages.join(" "));
            this.status = status;
            this.messages = messages;
        }
    }

    // fetch() with the CSRF token and session cookie. Resolves to the parsed JSON
    // body (or null for 204), and rejects with an ApiError for non-2xx responses.
    async function apiFetch(url, { method = "GET", json, body } = {}) {
        const headers = { "X-CSRFToken": csrfToken(), Accept: "application/json" };
        if (json !== undefined) {
            headers["Content-Type"] = "application/json";
            body = JSON.stringify(json);
        }

        let response;
        try {
            response = await fetch(url, { method, headers, body, credentials: "same-origin" });
        } catch (networkError) {
            throw new ApiError(0, ["Could not reach the server. Check your connection and try again."]);
        }

        if (response.status === 204) {
            return null;
        }
        const data = await response.json().catch(() => null);
        if (!response.ok) {
            throw new ApiError(response.status, errorMessages(data));
        }
        return data;
    }

    function showErrors(listElement, messages) {
        listElement.replaceChildren(
            ...messages.map((message) => {
                const li = document.createElement("li");
                li.textContent = message;
                return li;
            })
        );
        listElement.hidden = messages.length === 0;
    }

    function categoryOptions(select, categories, selectedId) {
        const placeholder = new Option("Choose a category", "");
        placeholder.disabled = true;
        select.replaceChildren(placeholder, ...categories.map((c) => new Option(c.name, c.id)));
        select.value = selectedId != null ? String(selectedId) : "";
    }

    window.Masroofi = { apiFetch, ApiError, showErrors, categoryOptions };
})();
