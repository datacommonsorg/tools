# Custom Data Commons Narratives Front-End UI

This directory contains the React SPA frontend application for Custom Data Commons instances. It serves as the primary visual client for interacting with the local Data Agent sidecar and rendering various interactive charts and metrics cards dynamically configured via branding packages.

## Layout & Architecture

* **React + Vite**: Pre-configured dev server and production builder.
* **Tailwind CSS v4**: Theme engine styling. Brand tokens are fetched from the server and loaded dynamically using CSS variables inside `src/index.css`.
* **Hash-based Routing**: Normalized routes parsed using window hash (`#/<route>`) inside `src/hooks/useHashRoute.ts` to keep client-side navigation lightweight and avoid server routing overrides.

## Getting Started

### 1. Installation
Install the project dependencies using npm:
```bash
npm install
```

### 2. Run Local Development Server
Launch the development server on port 3000:
```bash
npm run dev
```
Open [http://localhost:3000/](http://localhost:3000/) in your browser.

### 3. Production Build
Compile and bundle the project files for production deployment:
```bash
npm run build
```
This builds static artifacts into the `dist/` directory.

### 4. Running Lint Checks
Run the TypeScript compiler type-checker:
```bash
npm run lint
```
