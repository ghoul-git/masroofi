(function () {
    const { apiFetch, showErrors, categoryOptions, flagField, clearFlag, labelCells } = window.Masroofi;
    const categories = JSON.parse(document.getElementById("categories-data").textContent);

    const uploadForm = document.getElementById("upload-form");
    const uploadButton = document.getElementById("upload-button");
    const uploadErrors = document.getElementById("upload-errors");
    const loading = document.getElementById("loading");

    const reviewForm = document.getElementById("review-form");
    const reviewErrors = document.getElementById("review-errors");
    const saveButton = document.getElementById("save-button");
    const itemsBody = document.getElementById("items-body");
    const noItems = document.getElementById("no-items");
    const saved = document.getElementById("saved");

    const field = (id) => document.getElementById(id);
    let receiptId = null;

    // The worker reads the receipt in the background; the page asks for the result every 2 seconds.
    const POLL_INTERVAL_MS = 2000;
    const POLL_TIMEOUT_MS = 3 * 60 * 1000;
    const MAX_POLL_ERRORS = 5; // in a row; a single failed request (e.g. a mobile network blip) is retried
    const READY = new Set(["extracted", "failed", "confirmed"]);

    const MESSAGES = {
        failed: "We couldn't read this receipt automatically. Please fill in the fields yourself.",
        slow: "Reading this receipt is taking longer than usual. Please fill in the fields yourself.",
        error: "We couldn't get the result for this receipt. Please fill in the fields yourself.",
    };

    function setLoading(isLoading) {
        loading.hidden = !isLoading;
        uploadButton.disabled = isLoading;
        field("receipt-image").disabled = isLoading;
    }

    function updateNoItems() {
        noItems.hidden = itemsBody.children.length > 0;
    }

    function cellInput(type, value, attributes = {}) {
        const td = document.createElement("td");
        const input = document.createElement("input");
        input.type = type;
        input.value = value ?? "";
        Object.assign(input, attributes);
        td.appendChild(input);
        return td;
    }

    function addItemRow(item = {}) {
        const row = document.createElement("tr");
        row.append(
            cellInput("text", item.name, { className: "item-name", maxLength: 200, placeholder: "Item name" }),
            cellInput("number", item.quantity ?? "1", { className: "item-quantity", min: "0", step: "0.001" }),
            cellInput("number", item.price, { className: "item-price", min: "0", step: "0.001" })
        );
        const removeCell = document.createElement("td");
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "button button-secondary button-small";
        remove.textContent = "Remove";
        remove.addEventListener("click", () => {
            row.remove();
            updateNoItems();
        });
        removeCell.appendChild(remove);
        row.appendChild(removeCell);
        itemsBody.appendChild(labelCells(itemsBody.closest("table"), row));
        updateNoItems();
    }

    // receipt is the GET /api/receipts/<id>/ result, or null when there is no result to show.
    // notice explains why the fields are empty, if they are.
    function fillReviewForm(receipt, notice) {
        const extracted = (receipt && receipt.extracted) || {};
        if (!notice && receipt && receipt.status === "failed") notice = MESSAGES.failed;

        field("store-name").value = extracted.store_name || "";
        field("date").value = extracted.date || "";
        field("total").value = extracted.total ?? "";
        field("currency").value = extracted.currency || "JOD";
        categoryOptions(field("category"), categories, extracted.category);
        field("raw-text").textContent = (receipt && receipt.raw_text) || "(no text was read)";
        field("failed-notice").textContent = notice || "";
        field("failed-notice").hidden = !notice;

        itemsBody.replaceChildren();
        (extracted.items || []).forEach(addItemRow);
        updateNoItems();
        showErrors(reviewErrors, []);

        uploadForm.closest(".card").hidden = true;
        reviewForm.hidden = false;
        // Fields the server flagged for a second look, e.g. a date a year ago or a payment platform as store.
        const flagged = { store_name: field("store-name"), date: field("date") };
        Object.values(flagged).forEach(clearFlag);
        for (const [name, message] of Object.entries((receipt && receipt.warnings) || {})) {
            if (flagged[name]) flagField(flagged[name], message);
        }
        field("store-name").focus();
    }

    function collectReviewData() {
        const items = [...itemsBody.querySelectorAll("tr")].map((row) => ({
            name: row.querySelector(".item-name").value.trim(),
            quantity: row.querySelector(".item-quantity").value,
            price: row.querySelector(".item-price").value,
        }));
        return {
            store_name: field("store-name").value.trim(),
            date: field("date").value,
            total: field("total").value,
            currency: field("currency").value.trim().toUpperCase(),
            category: field("category").value || null,
            items,
        };
    }

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    // Poll until the worker has finished. Resolves to the receipt, or null after POLL_TIMEOUT_MS.
    async function waitForResult(id) {
        const deadline = Date.now() + POLL_TIMEOUT_MS;
        let errors = 0;
        while (Date.now() < deadline) {
            await sleep(POLL_INTERVAL_MS);
            try {
                const receipt = await apiFetch(`/api/receipts/${id}/`);
                errors = 0;
                if (READY.has(receipt.status)) return receipt;
            } catch (error) {
                errors += 1;
                if (error.status === 404 || errors >= MAX_POLL_ERRORS) throw error;
            }
        }
        return null;
    }

    uploadForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const file = field("receipt-image").files[0];
        if (!file) {
            showErrors(uploadErrors, ["Choose an image first."]);
            return;
        }

        const body = new FormData();
        body.append("image", file);
        showErrors(uploadErrors, []);
        setLoading(true);
        let queued;
        try {
            queued = await apiFetch("/api/receipts/", { method: "POST", body });
        } catch (error) {
            // Not uploaded (invalid image, limit reached, no connection): stay on the upload form.
            showErrors(uploadErrors, error.messages || [String(error)]);
            setLoading(false);
            return;
        }

        receiptId = queued.id;
        document.getElementById("usage").textContent = queued.usage.label;
        try {
            const receipt = await waitForResult(queued.id);
            fillReviewForm(receipt, receipt ? null : MESSAGES.slow);
        } catch (error) {
            // The receipt was saved, so it can still be confirmed with the fields filled in by hand.
            fillReviewForm(null, MESSAGES.error);
        } finally {
            setLoading(false);
        }
    });

    document.getElementById("add-item").addEventListener("click", () => {
        addItemRow();
        itemsBody.lastElementChild.querySelector(".item-name").focus();
    });

    document.getElementById("start-over").addEventListener("click", () => {
        window.location.reload();
    });

    reviewForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        showErrors(reviewErrors, []);
        saveButton.disabled = true;
        saveButton.textContent = "Saving...";
        try {
            const expense = await apiFetch(`/api/receipts/${receiptId}/confirm/`, { method: "POST", json: collectReviewData() });
            // Saved either way; remind the user of anything that still looks unusual.
            showErrors(document.getElementById("saved-warnings"), Object.values(expense.warnings || {}));
            reviewForm.hidden = true;
            saved.hidden = false;
        } catch (error) {
            showErrors(reviewErrors, error.messages || [String(error)]);
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = "Save";
        }
    });
})();
