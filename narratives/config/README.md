# config/ — one instance's bucket contents

Everything in this directory is uploaded to **one GCS bucket per instance**
(`gs://<project>-config/`) at the bucket root at deploy time. The bucket is read
by the React UI (`branding.json`) and by the agent sidecar
(`agent-config.json`, `prompts/`).

**One instance, one bucket, one set of files.** There is no shared framework
directory across instances and no namespace prefix inside the bucket. A second
instance gets its own GCP project, its own bucket, and its own copy of these
files.

The two `*.json` files that carry real values — `branding.json` and
`agent-config.json` — are **not** in this directory. Copy the `.example.json`
files, fill them in for your instance, and upload those. Keeping instance values
out of the repo is deliberate.

## Contents

| File / dir | Purpose | Consumed by |
|---|---|---|
| `branding.schema.json` | JSON Schema for `branding.json` | Validation at config-edit time |
| `branding.example.json` | Copy this to `branding.json` and edit | Reference when bootstrapping an instance |
| `agent-config.schema.json` | JSON Schema for `agent-config.json` | Validation at config-edit time |
| `agent-config.example.json` | Copy this to `agent-config.json` and edit | Reference when bootstrapping an instance |
| `prompts/*.md` | System prompts for the tool loop, the file-search phase, and the synthesizer | Agent sidecar |

## How a new instance customises this

1. Copy `branding.example.json` → `branding.json`. Set `instance_name`, `colors`,
   `fonts`, `navigation`, `suggestions`.
2. Copy `agent-config.example.json` → `agent-config.json`. Set the Gemini model
   choices, thinking levels, `gemini.filestores[]` corpus ID, and
   `query_param_key`. Prefer Secret Manager over writing API keys into the file.
3. **Edit `prompts/*.md` for your instance** — see below.
4. Upload the directory to the instance's config bucket. `DEPLOY.md` does this.

### Editing the prompts

The prompts shipped here are deliberately generic: they describe how the agent
should search, cite and format, and they name no country, agency, currency or
dataset. The agent loads `prompts/<slot>.md` from **your instance's bucket**, so
every instance keeps its own copy — edit them the same way you edit
`branding.json`.

They are literal text. The only thing substituted at runtime is
`{{CURRENT_DATETIME}}`; anything else in braces is sent to the model as-is.

What is usually worth adding:

- **A default place**, if questions that name no place should assume one.
- **What you call sub-national units** — states, provinces, regions, counties.
- **Your fiscal year**, if it isn't the calendar year.
- **Your custom datasets** — the most valuable edit, see below.

#### Tell the agent about your custom data

If you have loaded custom data, list the variables and their DCIDs in
`prompts/mcp.md`.

This matters more than it looks. The ingest job builds the search index from
each variable's **description**, not its name — so `search_indicators("average
annual wage")` may not match a variable literally called *Average Annual Wage*,
while a phrase resembling its description will. Listing the DCIDs lets the agent
use them directly instead of guessing at search terms, which is both more
reliable and far fewer tool calls.

Keep the list short. It is sent on every tool-loop iteration, so it costs tokens
on each request.

### Using your own logo (optional)

The app ships a bundled logo and uses it by default, so this step is not
required. To override it per instance, add a `logo` key to `branding.json` and
upload the image alongside it:

```json
"logo": "assets/logo.png"
```

A relative path is resolved against the config bucket, so `assets/logo.png` means
`gs://<project>-config/assets/logo.png`. An absolute `https://…` URL is used
as-is. Omit the key and the bundled logo is shown.

No code change and no image rebuild — instance customisation happens entirely in
this directory. A branding change is `gsutil cp branding.json …` plus a browser
refresh.

## What is NOT in this directory

- **Secrets** — `DC_API_KEY`, `MAPS_API_KEY`, `GEMINI_API_KEYS` and `DB_PASS`
  live in Secret Manager and are mounted into the Cloud Run service at runtime.
- **The file-search corpus** — uploaded out of band to Gemini File Search; only
  the resulting `fileSearchStores/<id>` is referenced in `agent-config.json`.
- **Source CSVs for data ingest** — those live in `../sample-data/` and go to the
  per-instance *data* bucket, not this config bucket.

## What is configured by environment variable, not by these files

A few runtime values deliberately do not live in `agent-config.json`, because the
agent reads them from its environment:

| Value | Where it comes from |
|---|---|
| Gemini API keys | `GEMINI_API_KEYS_SECRET` → Secret Manager |
| Gemini demo API keys | `GEMINI_DEMO_API_KEYS_SECRET` → Secret Manager |
| MCP endpoint | `MCP_PORT` — the agent builds `http://localhost:${MCP_PORT}/mcp` |
| Agent listen port | `PROXY_PORT` |
| Timezone for `{{CURRENT_DATETIME}}` | `TIMEZONE` |
| Config bucket URL | `BRAND_CONFIG_URL` |

These are set on the container (see `agent/Dockerfile`), not in this directory.

### API keys are never in this directory

`agent-config.schema.json` defines no field for API keys, and the `gemini` object
is `additionalProperties: false` — so adding `api_keys` or `api_key` to
`agent-config.json` is a **schema validation error**, not a supported option.
That is deliberate: it keeps this file safe to commit and to serve from a config
bucket, and removes the chance of a key leaking by being pasted into the wrong
file.

A deployed instance resolves its keys from Secret Manager. Point
`GEMINI_API_KEYS_SECRET` at a secret whose value is a JSON array of keys; the
agent rotates across them.

Local development is the one exception, and it does not use this directory: the
agent still honours a `gemini.api_keys` array in an **uncommitted, local**
`agent/config.json`. When it falls back to that path it logs a warning, so a
misconfigured deployment is visible in the logs rather than silent.

## Every branding key has a consumer

`branding.schema.json` deliberately defines only keys the UI actually reads:
`instance_name`, `logo`, `colors`, `fonts`, `navigation`, `suggestions`
(`suggestion_chips` is accepted as a legacy alias), `metrics` and
`schema_version`. `src/hooks/use_branding.ts` is the single translation point
from this wire format to the UI's domain type.

Do not add a key to the schema without adding the code that reads it. An unread
key looks like a supported feature and silently does nothing.

## `branding.metrics` — Key Metrics dashboard composition

The Metrics tab is driven entirely from `branding.json`. Each instance declares
the tabs and tiles it wants; the UI renders them with Data Commons web components
(`<datacommons-line>`, `-bar`, `-map`, …).

### Shape

```jsonc
{
  "metrics": {
    "tabs": [
      {
        "id": "population",                 // unique within tabs[]
        "label": "Population",              // shown in the sub-tab strip
        "tiles": [                          // REQUIRED — cards in the main grid
          {
            "type": "highlight",            // headline-number tile
            "title": "World population",    // our wrapper card's header
            "header": "World population",   // the DC component's own caption
            "variable": "Count_Person",     // single DCID
            "place": "Earth"                // single place DCID
          },
          {
            "type": "line",
            "title": "Population over time",
            "header": "Population over time",
            "variables": "Count_Person",    // space-separated DCID list
            "places": "country/USA country/CHN"
            // single-place components take `place`; multi-place take `places`
          }
        ]
      }
    ]
  }
}
```

Highlight tiles are ordinary tiles with `type: "highlight"`; they render with the
component's native chip styling and appear wherever you put them in `tiles[]`.

### Per-component required attributes

| Tile `type` | Required keys | Common optional keys |
|---|---|---|
| `line` | `header`, `variables`, (`place` ∥ `places` ∥ `parentPlace`+`childPlaceType`) | `colors`, `startDate`, `endDate`, `timeScale` |
| `bar` | `header`, `variables`, (`places` ∥ `parentPlace`+`childPlaceType`) | `sort`, `horizontal`, `stacked`, `lollipop`, `maxPlaces`, `colors` |
| `map` | `header`, `variable`, `parentPlace`, `childPlaceType` | `date`, `colors`, `geoJsonProp` |
| `ranking` | `header`, `variable`, `parentPlace`, `childPlaceType` | `rankingCount`, `showHighestLowest`, `showLowest`, `showMultiColumn` |
| `highlight` | `header`, `variable`, `place` | `date`, `unit` |
| `scatter` | `header`, `variables` (two DCIDs), `parentPlace`, `childPlaceType` | `showPlaceLabels`, `showQuadrants` |
| `pie` | `header`, `place`, `variables` | `donut` |
| `gauge` | `header`, `variable`, `place`, `min`, `max` | `unit`, `perCapita` |
| `slider` | `header`, `variable`, `parentPlace`, `childPlaceType` | `publish`, `date` |

### Choosing DCIDs for your region

Place and variable DCIDs are not enforced by code — they must resolve against
the upstream Data Commons graph plus whatever custom data the instance ingested.
Two things worth checking before authoring tiles:

- **Sub-national place DCIDs differ by country.** Some regions use
  `wikidataId/Q####`, others `geoId/…`. Look up the identifiers the upstream
  graph actually uses for your places rather than assuming a scheme.
- **`childPlaceType` must match the local administrative hierarchy** — commonly
  `AdministrativeArea1` for the first sub-national level and
  `AdministrativeArea2` for the second, or `Country` when the parent is `Earth`.

### Fallback when `metrics` is absent

If `branding.json` omits `metrics`, the UI falls back to `DEFAULT_METRICS_TABS`
(`src/components/metrics_page.tsx:40`) — four tabs, Population / Economy /
Health / Environment, with generic global-comparison tiles. Every Custom Data
Commons backend serves these out of the box, which makes them a useful
smoke test before authoring instance-specific tabs.
