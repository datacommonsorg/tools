# Data Commons Headless Trends SDK

A TypeScript client library and orchestration framework for interacting with the
Data Commons V2 Graph API. The Headless Trends SDK provides data fetching,
stitching, and mapping capabilities, separating raw network contracts from
public domain types, and formats data structures directly for popular charting
engines.

---

## Features
* **Simplified V2 Query APIs**: Retrieve statistical variables and entity
  observations without raw JSON parsing boilerplate.
* **Auto-Pagination**: Automatic next-page token stitching with custom safety
  caps.
* **In-Memory Caching**: FIFO-based client map cache for query speedups and
  duplicate request suppression.
* **Time-Series Alignment**: Combines primary variables with custom denominators
  for aligned calculations (e.g. per-capita scaling).
* **Charting Adapters**: Standard formatting adapters for Recharts and
  Highcharts time-series data.
* **Modern Tooling**: Strict type safety, Google style guidelines compliance,
  and Vitest test suites.

---

## Installation

Install the package directly:
```bash
npm install @datacommons/headless-sdk
```

Or reference locally in a monorepo workspace:
```json
"dependencies": {
  "@datacommons/headless-sdk": "file:../headless_sdk"
}
```

---

## Quick Start

### 1. Initialize Client
```typescript
import { createDataCommonsClient } from '@datacommons/headless-sdk';

const client = createDataCommonsClient({
  apiBaseUrl: 'https://api.datacommons.org', // Optional (defaults to prod API)
  apiKey: 'YOUR_API_KEY',                  // Optional
  maxPages: 5,                              // Optional pagination cap
});
```

### 2. Fetch Variable and Entities Metadata
```typescript
import { getMetadata } from '@datacommons/headless-sdk';

const metadata = await getMetadata(client, {
  statisticalVariable: 'Count_Person',
  observationProperties: [{ entity: 'geoId/06' }],
});

console.log(metadata.statisticalVariable.name); // "Population"
console.log(metadata.entities['geoId/06'].name); // "California"
```

### 3. Query and Format Aligned Observations
```typescript
import { getObservations, toRecharts } from '@datacommons/headless-sdk';

const response = await getObservations(client, {
  statisticalVariableDcid: 'Count_Person',
  observationProperties: [{ entity: 'geoId/06' }, { entity: 'geoId/12' }],
  facetDcid: '20254455', // Optional specific source/methodology filter
});

// Format wide-format series for Recharts
const rechartsData = toRecharts(response);
```

---

## Development Scripts

Run scripts from the `headless_sdk/` root directory:

* **Build Library**: `npm run build` (outputs compilation to `dist/`)
* **Run Unit Tests**: `npm run test` (compiles and runs vitest test runner)
* **Check Types**: `npm run check-types` (TypeScript compiler dry run check)
* **Lint Codebase**: `npm run lint` (checks and highlights formatting and style violations)

---

## Running the Reference App

To run the interactive React dashboard:
```bash
cd reference-app
npm install
npm run dev
```
Open [http://localhost:5173/](http://localhost:5173/) in your web browser.
