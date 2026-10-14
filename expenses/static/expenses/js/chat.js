(function () {
    const { apiFetch, showErrors } = window.Masroofi;

    const log = document.getElementById("chat-log");
    const historyLoading = document.getElementById("history-loading");
    const empty = document.getElementById("empty");
    const thinking = document.getElementById("thinking");
    const errors = document.getElementById("chat-errors");
    const form = document.getElementById("chat-form");
    const question = document.getElementById("question");
    const sendButton = document.getElementById("send-button");

    const TOOL_LABELS = {
        get_spending_total: "spending total",
        get_spending_by_category: "spending by category",
        list_expenses: "expense list",
        get_top_expenses: "top expenses",
        compare_periods: "period comparison",
    };

    function scrollToBottom() {
        log.scrollTop = log.scrollHeight;
    }

    // meta: optional small line under the bubble, such as the tools used.
    function addMessage(role, content, meta) {
        empty.hidden = true;
        const message = document.createElement("div");
        message.className = `message ${role}`;

        const bubble = document.createElement("div");
        bubble.className = "bubble";
        bubble.dir = "auto";
        bubble.textContent = content;
        message.appendChild(bubble);

        if (meta) {
            const line = document.createElement("div");
            line.className = "meta";
            line.textContent = meta;
            message.appendChild(line);
        }

        log.appendChild(message);
        scrollToBottom();
    }

    function toolsLine(toolsUsed, responseTime) {
        const names = [...new Set(toolsUsed.map((t) => TOOL_LABELS[t.name] || t.name))];
        const tools = names.length ? `Tools used: ${names.join(", ")}` : "No tools used";
        // The response time is only known for answers given on this page, not for saved history.
        return responseTime == null ? tools : `${tools} · ${responseTime.toFixed(1)}s`;
    }

    const usageLine = document.getElementById("usage");
    const limitNotice = document.getElementById("limit-notice");
    let limitReached = form.dataset.limitReached === "true";

    function setBusy(busy) {
        thinking.hidden = !busy;
        sendButton.disabled = busy || limitReached;
        question.disabled = busy || limitReached;
        if (busy) scrollToBottom();
    }

    function updateUsage(usage) {
        usageLine.textContent = usage.label;
        limitReached = usage.limit_reached;
        limitNotice.hidden = !limitReached;
    }

    async function loadHistory() {
        try {
            const messages = await apiFetch("/api/chat/history/");
            messages.forEach((m) =>
                addMessage(m.role, m.content, m.role === "assistant" ? toolsLine(m.tools_used || [], null) : null)
            );
            empty.hidden = messages.length > 0;
        } catch (error) {
            showErrors(errors, error.messages || [String(error)]);
        } finally {
            historyLoading.remove();
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const text = question.value.trim();
        if (!text) return;

        showErrors(errors, []);
        addMessage("user", text);
        question.value = "";
        setBusy(true);
        try {
            const result = await apiFetch("/api/chat/", { method: "POST", json: { question: text } });
            addMessage("assistant", result.answer, toolsLine(result.tools_used, result.response_time));
            updateUsage(result.usage);
        } catch (error) {
            // The question was not saved, so put it back for another try.
            log.lastElementChild.remove();
            empty.hidden = log.querySelector(".message") !== null;
            question.value = text;
            showErrors(errors, error.messages || [String(error)]);
            if (error.status === 429) {
                limitReached = true;
            }
        } finally {
            setBusy(false);
            question.focus();
        }
    });

    // Enter sends, Shift+Enter adds a new line.
    question.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    setBusy(false);
    loadHistory();
})();
