"""HTML UI for the demo app — a real page a browser agent can drive.

The JSON ``/ui`` view is enough for an HTTP agent, but the whole point of the
Playwright adapter is to verify a *browser* agent: one that fills a form, clicks
a button, and concludes success from what the page shows. So this module serves
a minimal but genuine HTML page with:

  * ``#field`` / ``#value`` inputs and a ``#save`` button;
  * a ``#status`` banner that reads "Saved ✓" on any 2xx from the mutation
    endpoint — deliberately optimistic, so under a backend-write failure the
    banner still shows success and a UI-trusting agent falsely claims done;
  * a ``#result`` blob (the raw mutation response) and ``#current`` (the value
    the optimistic ``/ui`` view reports afterwards).

Nothing here decides truth; it reproduces the optimistic surface that makes
false completion possible. AOIE reads the authoritative ``/api``/DB behind it.
"""

from __future__ import annotations

import html

_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>AOIE Demo — {collection}/{record_id}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 40rem; }}
    label {{ display: block; margin: .5rem 0 .2rem; }}
    input {{ padding: .4rem; width: 100%; box-sizing: border-box; }}
    button {{ margin-top: 1rem; padding: .5rem 1rem; }}
    #status {{ margin-top: 1rem; font-weight: 600; min-height: 1.4rem; }}
    #status.ok {{ color: #157a3f; }}
    #status.err {{ color: #b00020; }}
    pre {{ background: #f4f4f6; padding: .8rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>{collection} / {record_id}</h1>
  <p>Current (optimistic UI): <code id="current">loading…</code></p>
  <label for="field">Field</label>
  <input id="field" value="{default_field}" />
  <label for="value">Value</label>
  <input id="value" value="" />
  <button id="save">Save</button>
  <div id="status" role="status"></div>
  <h2>Response</h2>
  <pre id="result"></pre>

  <script>
    const collection = {collection_json};
    const recordId = {record_id_json};
    const statusEl = document.getElementById("status");
    const resultEl = document.getElementById("result");
    const currentEl = document.getElementById("current");

    async function refreshCurrent() {{
      try {{
        const r = await fetch(`/ui/${{collection}}/${{recordId}}`);
        currentEl.textContent = r.ok ? JSON.stringify(await r.json()) : `(${{r.status}})`;
      }} catch (e) {{ currentEl.textContent = "(error)"; }}
    }}

    document.getElementById("save").addEventListener("click", async () => {{
      const field = document.getElementById("field").value;
      const value = document.getElementById("value").value;
      statusEl.textContent = "Saving…";
      statusEl.className = "";
      try {{
        const resp = await fetch(`/api/${{collection}}/${{recordId}}`, {{
          method: "PUT",
          headers: {{ "content-type": "application/json" }},
          body: JSON.stringify({{ fields: {{ [field]: value }} }}),
        }});
        const text = await resp.text();
        resultEl.textContent = text;
        if (resp.ok) {{
          // Optimistic on purpose: 2xx alone is treated as success.
          statusEl.textContent = "Saved ✓";
          statusEl.className = "ok";
        }} else {{
          statusEl.textContent = `Error ✗ (${{resp.status}})`;
          statusEl.className = "err";
        }}
      }} catch (e) {{
        statusEl.textContent = `Error ✗ (${{e}})`;
        statusEl.className = "err";
      }}
      await refreshCurrent();
    }});

    refreshCurrent();
  </script>
</body>
</html>
"""


def render_page(collection: str, record_id: str, default_field: str = "name") -> str:
    """Return the demo HTML for a target. Values are escaped for safe embedding."""
    import json

    return _PAGE.format(
        collection=html.escape(collection),
        record_id=html.escape(record_id),
        default_field=html.escape(default_field),
        collection_json=json.dumps(collection),
        record_id_json=json.dumps(record_id),
    )
