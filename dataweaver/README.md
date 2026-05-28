# dataweaver

Monorepo for Dataweaver. Managed with [pnpm workspaces](https://pnpm.io/workspaces).

## Workspace layout

```
apps/
  web/         Next.js app (App Router)
packages/
  tokens/      Design tokens (JSON → generated .scss / .ts)
```

## Installation

All commands run from the root of the monorepo.

### Node.js version

Install [nvm](https://github.com/nvm-sh/nvm) and run:

```bash
nvm use
```

### Dependencies

```bash
pnpm i
```

## Scripts

| Command | What it does |
| --- | --- |
| `pnpm dev` | Run all apps in dev mode |
| `pnpm build` | Build all apps |
| `pnpm preview` | Serve the built apps |
| `pnpm generate:tokens` | Regenerate `_generated.module.scss` + `generated.ts` from `packages/tokens/src/*.json` |

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

To run a dependency check and update interactively, run the following command from the root of the monorepo:

```bash
pnpm up --latest --recursive --interactive
```

This recursively checks all packages in the repo for outdated dependencies and lets you select which ones to update.

Select the packages you want to update (using the `space` key), then press `enter` to update the selected ones.
