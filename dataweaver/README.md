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
| `pnpm test` | Run unit tests across packages |
| `pnpm lint` | Run type checking, Biome, and Stylelint |
| `pnpm fix` | Auto-format and fix Biome and Stylelint issues |
| `pnpm preview` | Serve the built apps |
| `pnpm generate:tokens` | Regenerate `packages/tokens/dist/` (`tokens.css` + `_tokens.scss` + `tokens.ts`) from `packages/tokens/src/*.json` |

## Code style

TypeScript follows the [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html), enforced as closely as possible through Biome (see `biome.json`).

CSS and SCSS follow the [Google HTML/CSS Style Guide](https://google.github.io/styleguide/htmlcssguide.html), enforced through Stylelint for `.scss` (see `stylelint.config.mjs`) and Biome for plain `.css`.

Where a guideline can't be linted automatically, please follow it by convention.

## Linting and testing

Code quality is enforced using Biome, TypeScript, and Stylelint, along with Vitest for unit testing.

### Linting and type checking

To run type checking (TypeScript), code linting (Biome), and stylesheet linting (Stylelint):

```bash
pnpm lint
```

### Auto-formatting and fixing

To format code and automatically fix linting issues:

```bash
pnpm fix
```

### Unit tests

To run unit tests across packages:

```bash
pnpm test
```

## Dependency Check

To run a dependency check and update interactively, run the following command from the root of the `/dataweaver` directory:

```bash
pnpm up --latest --recursive --interactive
```

This recursively checks all packages in the repo for outdated dependencies and lets you select which ones to update.

Select the packages you want to update (using the `space` key), then press `enter` to update the selected ones.

## Contributing

Before submitting a Pull Request for review, ensure the following:

- **Coding standards**: All code conforms to the conventions in [`FRONTEND.md`](FRONTEND.md), the repository root [`README.md`](../README.md), and the [Google Style Guides](https://google.github.io/styleguide/) (specifically [TypeScript](https://google.github.io/styleguide/tsguide.html) and [HTML/CSS](https://google.github.io/styleguide/htmlcssguide.html)).
- **Linting and unit tests**: Run `pnpm lint && pnpm test` to perform type checking, code/style linting, and unit tests.
- **Build verification**: Ensure the application builds cleanly by running `pnpm build`.
- **Runtime verification**: Once built, verify the application runs as expected by running `pnpm preview` and visiting the local URL (typically `http://localhost:3000`).