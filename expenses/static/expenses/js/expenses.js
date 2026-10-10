(function () {
    const { apiFetch, showErrors, categoryOptions } = window.Masroofi;
    const categories = JSON.parse(document.getElementById("categories-data").textContent);

    const body = document.getElementById("expenses-body");
    const pageErrors = document.getElementById("page-errors");
    const loading = document.getElementById("loading");
    const empty = document.getElementById("empty");
    const tableWrap = document.getElementById("table-wrap");

    function cell(text, className) {
        const td = document.createElement("td");
        td.textContent = text;
        if (className) td.className = className;
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
            cell(expense.date),
            cell(expense.store_name),
            cell(expense.category_name),
            cell(String(expense.items.length), "number"),
            cell(expense.total, "number"),
            cell(expense.currency),
            actionsCell(
                button("Edit", "button-secondary", () => row.replaceWith(renderEditRow(expense))),
                button("Delete", "button-danger", () => row.replaceWith(renderDeleteRow(expense)))
            )
        );
        return row;
    }

    function renderEditRow(expense) {
        const row = document.createElement("tr");
        const [dateCell, date] = input("date", expense.date);
        const [storeCell, store] = input("text", expense.store_name, { maxLength: 200 });
        const categoryCell = document.createElement("td");
        const category = document.createElement("select");
        categoryOptions(category, categories, expense.category);
        categoryCell.appendChild(category);
        const [totalCell, total] = input("number", expense.total, { min: "0", step: "0.01" });
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
        return row;
    }

    function renderDeleteRow(expense) {
        const row = document.createElement("tr");
        const message = cell(`Delete the ${expense.total} ${expense.currency} expense at ${expense.store_name} on ${expense.date}?`);
        message.colSpan = 6;

        const confirm = button("Yes, delete", "button-danger", async () => {
            confirm.disabled = true;
            showErrors(pageErrors, []);
            try {
                await apiFetch(`/api/expenses/${expense.id}/`, { method: "DELETE" });
                row.remove();
                updateEmptyState();
            } catch (error) {
                showErrors(pageErrors, error.messages || [String(error)]);
                confirm.disabled = false;
            }
        });

        row.append(message, actionsCell(confirm, button("Cancel", "button-secondary", () => row.replaceWith(renderRow(expense)))));
        return row;
    }

    async function load() {
        try {
            const expenses = await apiFetch("/api/expenses/");
            body.replaceChildren(...expenses.map(renderRow));
            updateEmptyState();
        } catch (error) {
            showErrors(pageErrors, error.messages || [String(error)]);
        } finally {
            loading.hidden = true;
        }
    }

    load();
})();
