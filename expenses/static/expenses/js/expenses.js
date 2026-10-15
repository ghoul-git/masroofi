(function () {
    const { apiFetch, showErrors, categoryOptions, formatAmount, labelCells } = window.Masroofi;
    const categories = JSON.parse(document.getElementById("categories-data").textContent);

    const body = document.getElementById("expenses-body");
    const pageErrors = document.getElementById("page-errors");
    const pageWarnings = document.getElementById("page-warnings");
    const loading = document.getElementById("loading");
    const empty = document.getElementById("empty");
    const tableWrap = document.getElementById("table-wrap");
    const table = tableWrap.querySelector("table");
    const pagination = document.getElementById("pagination");
    const previousButton = document.getElementById("previous-page");
    const nextButton = document.getElementById("next-page");
    const pageInfo = document.getElementById("page-info");

    const PAGE_SIZE = 20; // matches ExpensePagination.page_size on the server
    let currentPage = 1;

    function cell(text, className) {
        const td = document.createElement("td");
        td.textContent = text;
        if (className) td.className = className;
        return td;
    }

    // A cell highlighted in amber, with the reason as a tooltip, when the server flagged the value.
    function flaggedCell(text, warning) {
        const td = cell(text);
        if (warning) {
            td.classList.add("needs-check");
            td.title = warning;
        }
        return td;
    }

    function button(label, className, onClick) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `button button-small ${className}`;
        b.textContent = label;
        b.addEventListener("click", onClick);
        return b;
    }

    function input(type, value, attributes = {}) {
        const td = document.createElement("td");
        const el = document.createElement("input");
        el.type = type;
        el.value = value ?? "";
        Object.assign(el, attributes);
        td.appendChild(el);
        return [td, el];
    }

    function updateEmptyState() {
        const hasRows = body.children.length > 0;
        empty.hidden = hasRows;
        tableWrap.hidden = !hasRows;
    }

    function actionsCell(...buttons) {
        const td = document.createElement("td");
        const wrap = document.createElement("div");
        wrap.className = "actions";
        wrap.append(...buttons);
        td.appendChild(wrap);
        return td;
    }

    function renderRow(expense) {
        const row = document.createElement("tr");
        row.dataset.id = expense.id;
        row.append(
            flaggedCell(expense.date, expense.warnings?.date),
            flaggedCell(expense.store_name, expense.warnings?.store_name),
            cell(expense.category_name),
            cell(String(expense.items.length), "number"),
            cell(formatAmount(expense.total, expense.currency), "number"),
            cell(expense.currency),
            actionsCell(
                button("Edit", "button-secondary", () => row.replaceWith(renderEditRow(expense))),
                button("Delete", "button-danger", () => row.replaceWith(renderDeleteRow(expense)))
            )
        );
        return labelCells(table, row);
    }

    function renderEditRow(expense) {
        const row = document.createElement("tr");
        const [dateCell, date] = input("date", expense.date);
        const [storeCell, store] = input("text", expense.store_name, { maxLength: 200 });
        const categoryCell = document.createElement("td");
        const category = document.createElement("select");
        categoryOptions(category, categories, expense.category);
        categoryCell.appendChild(category);
        const [totalCell, total] = input("number", expense.total, { min: "0", step: "0.001" });
        total.style.textAlign = "right";
        const [currencyCell, currency] = input("text", expense.currency, { maxLength: 3, size: 4 });

        const save = button("Save", "", async () => {
            save.disabled = true;
            showErrors(pageErrors, []);
            try {
                const updated = await apiFetch(`/api/expenses/${expense.id}/`, {
                    method: "PATCH",
                    json: {
                        date: date.value,
                        store_name: store.value.trim(),
                        category: category.value || null,
                        total: total.value,
                        currency: currency.value.trim().toUpperCase(),
                    },
                });
                row.replaceWith(renderRow(updated));
                // Saved; just point out anything that still looks unusual.
                showErrors(pageWarnings, Object.values(updated.warnings || {}).map((w) => `${updated.store_name}: ${w}`));
            } catch (error) {
                showErrors(pageErrors, error.messages || [String(error)]);
                save.disabled = false;
            }
        });

        row.append(
            dateCell,
            storeCell,
            categoryCell,
            cell(String(expense.items.length), "number"),
            totalCell,
            currencyCell,
            actionsCell(save, button("Cancel", "button-secondary", () => {
                showErrors(pageErrors, []);
                row.replaceWith(renderRow(expense));
            }))
        );
        return labelCells(table, row);
    }

    function renderDeleteRow(expense) {
        const row = document.createElement("tr");
        const message = cell(`Delete the ${formatAmount(expense.total, expense.currency)} ${expense.currency} expense at ${expense.store_name} on ${expense.date}?`);
        message.colSpan = 6;

        const confirm = button("Yes, delete", "button-danger", async () => {
            confirm.disabled = true;
            showErrors(pageErrors, []);
            try {
                await apiFetch(`/api/expenses/${expense.id}/`, { method: "DELETE" });
                // Reload so the next expense moves up into this page. If this was the
                // only row on a later page, that page no longer exists: go back one.
                const lastRowOnPage = body.children.length === 1;
                await load(lastRowOnPage && currentPage > 1 ? currentPage - 1 : currentPage);
            } catch (error) {
                showErrors(pageErrors, error.messages || [String(error)]);
                confirm.disabled = false;
            }
        });

        row.append(message, actionsCell(confirm, button("Cancel", "button-secondary", () => row.replaceWith(renderRow(expense)))));
        return row;
    }

    function updatePagination(data) {
        const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE));
        pagination.hidden = data.count <= PAGE_SIZE;
        previousButton.disabled = !data.previous;
        nextButton.disabled = !data.next;
        pageInfo.textContent = `Page ${currentPage} of ${totalPages} · ${data.count} expenses`;
    }

    async function load(page = 1) {
        previousButton.disabled = true;
        nextButton.disabled = true;
        try {
            const data = await apiFetch(`/api/expenses/?page=${page}`);
            currentPage = page;
            body.replaceChildren(...data.results.map(renderRow));
            updateEmptyState();
            updatePagination(data);
        } catch (error) {
            showErrors(pageErrors, error.messages || [String(error)]);
        } finally {
            loading.hidden = true;
        }
    }

    previousButton.addEventListener("click", () => {
        showErrors(pageErrors, []);
        load(currentPage - 1);
    });
    nextButton.addEventListener("click", () => {
        showErrors(pageErrors, []);
        load(currentPage + 1);
    });

    load();
})();
