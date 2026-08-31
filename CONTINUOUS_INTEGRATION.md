# Continuous Integration (CI) Architecture

This repository uses a centralized GitHub Actions CI orchestrator ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) to manage testing across multiple applications in the monorepo. In a monorepo containing multiple independent applications (such as `dataweaver`, `narratives`, `bigtable_automation`, `gcf`), individual applications may have their own test suites, linters, and build requirements.

## Overview

GitHub Branch Protection enforces required status checks globally on all pull requests targeting protected branches (i.e. `main`). If each application ran a standalone workflow filtered by file paths, those tests would only run on PRs touching its respective application, and therefore cannot be enforced as a required status check.

To accommodate this limitation, this repository's CI system implements an **orchestrator pattern**:
- **Central Trigger**: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on all PRs and pushes targeting `main` / `master`.
- **Path Detection**: The `detect-changes` job uses `dorny/paths-filter` to inspect changed files and determine which apps have modifications.
- **Conditional Execution**: App-specific reusable workflows (e.g., [`.github/workflows/dataweaver_ci.yml`](.github/workflows/dataweaver_ci.yml)) run only when their relevant directory or workflow files change.
- **Aggregated Status Gate (`ci-final-status`)**: The aggregator job runs unconditionally (`if: always()`). Unaffected or skipped app workflows are treated as passing, while failures or cancellations cause `ci-final-status` to fail.
- **Single Branch Protection Check**: Only the `CI Final Status` check needs to be configured as a required status check in repository settings. Apps without tests or untouched apps pass automatically without blocking PRs.

## Adding CI Tests

To add automated CI checks and branch gating for an app in this monorepo:

### 1. Create the app-specific workflow
Create a workflow file under `.github/workflows/<app_name>_ci.yml` triggered via `workflow_call`:
```yaml
name: <App Name> CI

on:
  workflow_call:

permissions:
  contents: read

jobs:
  verify:
    name: Verify (Lint, Test, Build)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: <app_name>
    steps:
      - name: Checkout repository
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

      # Add setup steps (e.g., Node/Python/Go/Java setup, dependency install)
      # Add verification steps (e.g., lint, test, build)
```

### 2. Add path filter to the orchestrator
In [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
- Under `jobs.detect-changes.steps.filter.with.filters`, define the path matchers for your app:
  ```yaml
  <app_name>:
    - '<app_name>/**'
    - '.github/workflows/ci.yml'
    - '.github/workflows/<app_name>_ci.yml'
  ```
- Expose the filter output under `jobs.detect-changes.outputs`:
  ```yaml
  <app_name>: ${{ steps.filter.outputs.<app_name> }}
  ```

### 3. Add the app job to the orchestrator
In [`.github/workflows/ci.yml`](.github/workflows/ci.yml), add the job invoking your reusable workflow:
```yaml
  <app_name>:
    name: <App Name>
    needs: detect-changes
    if: needs.detect-changes.outputs.<app_name> == 'true'
    uses: ./.github/workflows/<app_name>_ci.yml
```

### 4. Register with the final status aggregator
Add your app job name to the `needs` list in `jobs.ci-final-status`:
```yaml
  ci-final-status:
    name: CI Final Status
    needs:
      - detect-changes
      - dataweaver
      - <app_name>
```

Once merged, PRs touching `<app_name>` will automatically execute your app's workflow, and passing results will be required for merging via the single `CI Final Status` check.
