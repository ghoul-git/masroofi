(function () {
    const { apiFetch, showErrors, categoryOptions } = window.Masroofi;
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
            cellInput("number", item.quantity ?? "1", { className: "item-quantity", min: "0", step: "0.01" }),
            cellInput("number", item.price, { className: "item-price", min: "0", step: "0.01" })
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
        itemsBody.appendChild(row);
        updateNoItems();
    }

    function fillReviewForm(result) {
        const extracted = result.extracted;
        receiptId = result.receipt.id;

        field("store-name").value = extracted.store_name || "";
        field("date").value = extracted.date || "";
        field("total").value = extracted.total ?? "";
        field("currency").value = extracted.currency || "JOD";
        categoryOptions(field("category"), categories, extracted.category);
        field("raw-text").textContent = result.receipt.raw_text || "(no text was read)";
        field("failed-notice").hidden = result.receipt.status !== "failed";

        itemsBody.replaceChildren();
        (extracted.items || []).forEach(addItemRow);
        updateNoItems();
        showErrors(reviewErrors, []);

        uploadForm.closest(".card").hidden = true;
        reviewForm.hidden = false;
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
        try {
            const result = await apiFetch("/api/receipts/", { method: "POST", body });
            document.getElementById("usage").textContent = result.usage.label;
            fillReviewForm(result);
        } catch (error) {
            showErrors(uploadErrors, error.messages || [String(error)]);
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
            await apiFetch(`/api/receipts/${receiptId}/confirm/`, { method: "POST", json: collectReviewData() });
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
