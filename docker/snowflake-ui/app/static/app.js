"use strict";

const el = {
  sql: document.getElementById("sql"),
  run: document.getElementById("run"),
  clear: document.getElementById("clear"),
  refresh: document.getElementById("refresh"),
  results: document.getElementById("results"),
  tree: document.getElementById("tree"),
  status: document.getElementById("status"),
};

/* ---------- helpers ---------- */

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

async function getJSON(url, options) {
  const res = await fetch(url, options);
  return res.json();
}

/* ---------- status ---------- */

async function refreshStatus() {
  try {
    const res = await fetch("/healthz");
    const up = res.ok;
    el.status.dataset.state = up ? "up" : "down";
    el.status.textContent = up ? "connected" : "unreachable";
  } catch {
    el.status.dataset.state = "down";
    el.status.textContent = "unreachable";
  }
}

/* ---------- object tree ---------- */

function tableNode(database, schema, table) {
  const details = node("details", "table");
  details.appendChild(node("summary", null, table.name));

  const select = node("button", "select", "SELECT *");
  select.type = "button";
  select.addEventListener("click", () => {
    el.sql.value = `SELECT *\nFROM ${database}.${schema}.${table.name}\nLIMIT 100;`;
    el.sql.focus();
    run();
  });
  details.appendChild(select);

  const columns = node("ul", "columns");
  for (const column of table.columns) {
    const li = node("li");
    li.appendChild(node("span", column.nullable ? "name" : "name required", column.name));
    li.appendChild(node("span", "type", column.type));
    columns.appendChild(li);
  }
  details.appendChild(columns);
  return details;
}

async function loadTree() {
  el.tree.textContent = "Loading…";
  const data = await getJSON("/api/objects");
  el.tree.textContent = "";

  if (data.error) {
    el.tree.appendChild(node("p", "note", data.error));
    return;
  }
  if (!data.databases.length) {
    el.tree.appendChild(node("p", "note", "No databases found."));
    return;
  }

  for (const database of data.databases) {
    const dbNode = node("details", "database");
    dbNode.open = true;
    dbNode.appendChild(node("summary", null, database.name));

    for (const schema of database.schemas) {
      const schemaNode = node("details", "schema");
      schemaNode.open = true;
      schemaNode.appendChild(node("summary", null, schema.name));
      for (const table of schema.tables) {
        schemaNode.appendChild(tableNode(database.name, schema.name, table));
      }
      dbNode.appendChild(schemaNode);
    }

    if (!database.schemas.length) {
      dbNode.appendChild(node("p", "note", "No tables."));
    }
    el.tree.appendChild(dbNode);
  }
}

/* ---------- results ---------- */

function resultBlock(result) {
  const block = node("div", "result");

  const head = node("div", "result-head");
  head.appendChild(node("div", "result-sql", result.sql));
  if (result.columns.length) {
    head.appendChild(node("span", "badge", `${result.rows.length} row${result.rows.length === 1 ? "" : "s"}`));
  } else {
    head.appendChild(node("span", "badge", "no result set"));
  }
  head.appendChild(node("span", "badge", `${result.elapsedMs} ms`));
  if (result.truncated) {
    head.appendChild(node("span", "badge warn", "truncated"));
  }
  block.appendChild(head);

  if (!result.columns.length) return block;

  const table = node("table");
  const thead = node("thead");
  const headRow = node("tr");
  for (const column of result.columns) headRow.appendChild(node("th", null, column));
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = node("tbody");
  for (const row of result.rows) {
    const tr = node("tr");
    for (const value of row) {
      tr.appendChild(value === null ? node("td", "null", "NULL") : node("td", null, String(value)));
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  block.appendChild(table);
  return block;
}

function errorBlock(message, failedSql) {
  const block = node("div", "error");
  block.appendChild(node("h3", null, "Error"));
  if (failedSql) block.appendChild(node("div", "result-sql", failedSql));
  block.appendChild(node("pre", null, message));
  return block;
}

function render(data) {
  el.results.textContent = "";
  for (const result of data.results) el.results.appendChild(resultBlock(result));
  if (data.error) el.results.appendChild(errorBlock(data.error, data.failedSql));
  if (!data.results.length && !data.error) {
    el.results.appendChild(node("p", "empty", "Nothing to run."));
  }
}

/* ---------- run ---------- */

async function run() {
  const sql = el.sql.value.trim();
  if (!sql) return;

  el.run.disabled = true;
  el.run.textContent = "Running…";
  try {
    render(
      await getJSON("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql }),
      })
    );
    // DDL in the editor changes the tree, and reloading is cheap here.
    loadTree();
    refreshStatus();
  } catch (e) {
    el.results.textContent = "";
    el.results.appendChild(errorBlock(String(e)));
  } finally {
    el.run.disabled = false;
    el.run.textContent = "Run";
  }
}

el.run.addEventListener("click", run);
el.refresh.addEventListener("click", loadTree);
el.clear.addEventListener("click", () => {
  el.sql.value = "";
  el.sql.focus();
});
el.sql.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    run();
  }
});

refreshStatus();
loadTree();
setInterval(refreshStatus, 15000);
