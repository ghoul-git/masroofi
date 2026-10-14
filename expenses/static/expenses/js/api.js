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

    // Currencies with 3 minor-unit digits (ISO 4217); the Jordanian dinar has 1000 fils.
    const THREE_DECIMAL_CURRENCIES = new Set(["JOD", "KWD", "BHD", "OMR", "IQD", "LYD", "TND"]);

    // "12.5" + "JOD" -> "12.500", "12.5" + "USD" -> "12.50". Amounts arrive as decimal strings.
    function formatAmount(value, currency) {
        const number = Number(value);
        if (value === null || value === "" || Number.isNaN(number)) return "";
        const digits = THREE_DECIMAL_CURRENCIES.has(String(currency).toUpperCase()) ? 3 : 2;
        return number.toFixed(digits);
    }

    // Highlight a field in amber with a message under it, e.g. "Please check this date".
    // The highlight goes away as soon as the user changes the value.
    function flagField(input, message) {
        const wrapper = input.closest(".field") || input.parentElement;
        let note = wrapper.querySelector(".field-warning");
        if (!note) {
            note = document.createElement("p");
            note.className = "field-warning";
            wrapper.appendChild(note);
        }
        note.textContent = message;
        note.hidden = false;
        input.classList.add("needs-check");
        input.addEventListener("input", () => clearFlag(input), { once: true });
    }

    function clearFlag(input) {
        input.classList.remove("needs-check");
        const note = (input.closest(".field") || input.parentElement).querySelector(".field-warning");
        if (note) note.hidden = true;
    }

    window.Masroofi = { apiFetch, ApiError, showErrors, categoryOptions, formatAmount, flagField, clearFlag };
})();
