# Data Weaver Experiment

Root of the `/dataweaver` directory. Managed with [pnpm workspaces](https://pnpm.io/workspaces).

## Workspace layout

```
apps/
  web/         Next.js app (App Router)
packages/
  tokens/      Design tokens (JSON → generated tokens.css / .scss / .ts, consumed via @package/tokens)
```

## Installation

All commands run from the root of the `/dataweaver` directory.

### Node.js version

Install [nvm](https://github.com/nvm-sh/nvm) and run:

```bash
nvm use
```

### Dependencies

```bash
corepack enable
pnpm i
```

## Scripts

| Command | What it does |
| --- | --- |
| `pnpm dev` | Run all apps in dev mode |
| `pnpm build` | Build all apps |
| `pnpm preview` | Serve the built apps |
| `pnpm generate:tokens` | Regenerate `packages/tokens/dist/` (`tokens.css` + `_tokens.scss` + `tokens.ts`) from `packages/tokens/src/*.json` |

## Code style

TypeScript follows the [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html), enforced as closely as possible through Biome (see `biome.json`).

CSS and SCSS follow the [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html), enforced through Stylelint for `.scss` (see `stylelint.config.mjs`) and Biome for plain `.css`.

Where a guideline can't be linted automatically, please follow it by convention.

## Linting

Linting by Biome, TypeScript and Stylelint. To check, run:

```bash
pnpm run lint
```

To automatically fix _most_ linting errors, run:

```bash
pnpm run fix
```

## Dependency Check

To run a dependency check and update interactively, run the following command from the root of the `/dataweaver` directory:

```bash
pnpm up --latest --recursive --interactive
```

This recursively checks all packages in the repo for outdated dependencies and lets you select which ones to update.

Select the packages you want to update (using the `space` key), then press `enter` to update the selected ones.
