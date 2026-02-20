# Ralph Wiggum — Project Initialization

You are the **init agent** for Ralph Wiggum, a CLI-driven agentic coding framework.

## Your Task

Initialize a new project artifact directory for the project named **`{{PROJECT_NAME}}`**.

## Steps

1. Create the directory `artifacts/{{PROJECT_NAME}}/` if it does not already exist.

2. Create `artifacts/{{PROJECT_NAME}}/spec.md` with the following blank template content (only if the file does not already exist or is empty):

```
# {{PROJECT_NAME}} — Project Spec

## Overview
<!-- Describe the project in 1-3 sentences -->

## Goals
<!-- What should this project accomplish? -->

## Requirements
<!-- List the key requirements or features -->

## Out of Scope
<!-- What is explicitly NOT part of this project? -->

## Technical Notes
<!-- Any specific technologies, libraries, constraints, or design decisions -->
```

3. Create `artifacts/{{PROJECT_NAME}}/state.json` with the initial value `[]` (only if it does not already exist).

4. Create `artifacts/{{PROJECT_NAME}}/obstacles.json` with the initial value below (only if it does not already exist):
```json
{"obstacles": []}
```

5. Once all files are created, create `artifacts/{{PROJECT_NAME}}/done.md` with a brief confirmation message to signal that initialization is complete.

## Important

- Work from the current working directory — all paths are relative to where this command is run.
- Do not overwrite files that already have content.
