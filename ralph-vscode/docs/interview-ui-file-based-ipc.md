# Interview UI: File-Based IPC (v3.5)

## Problem

The original `ralph interview` interaction tried to parse the CLI's interactive choice prompts directly from PTY stdout. This was unreliable because:

- `node-pty` presents as a real TTY, so Python's `prompt_toolkit` renders interactive arrow-key menus with ANSI escape sequences and screen redraws.
- The PTY output included a `WARNING: your terminal doesn't support cursor position requests (CPR).` message that corrupted question extraction.
- The same `↑↓ to move` hint appeared twice in the output (before and after the WARNING), causing duplicate `stdin_prompt` events.
- Implementing "edit a previous answer" required killing and restarting the process with auto-replayed answers — fragile and confusing to users.

## Solution: File-Based IPC

Instead of parsing PTY output, the extension and CLI communicate via JSON files in the project's `.ralph/<project>/` directory.

### Flow

```
Python CLI                          Extension Host                Webview
-----------                         ---------------               -------
generate questions
write → interview_questions.json
print sentinel line ──────────────→ detect sentinel
                                    read questions file
                                    postMessage(stdin_interview) ──→ show multi-question form
                                                                      user fills all answers
                                                                      Submit All
                                    ←── postMessage(submit_interview)
                                    write → interview_answers.json
poll for answers file ←────────────
read answers
delete both files
continue with spec generation
```

### Sentinel Line

Python prints `[ralph-vscode] interview_questions_ready` to stdout after writing the questions file. The extension detects this line in `onData`, suppresses it from the webview, and reads the file synchronously.

### File Formats

**`interview_questions.json`** — written by Python, read by extension:
```json
[
  { "question": "What is the main goal?", "options": ["Automate X", "Improve Y", "Describe yourself..."] },
  ...
]
```

**`interview_answers.json`** — written by extension, read by Python:
```json
[
  { "question": "What is the main goal?", "answer": "Automate X" },
  ...
]
```

Both files are deleted by Python after answers are consumed.

### Backward Compatibility

The VS Code code path in `ralph/run.py` is gated behind the `RALPH_VSCODE` environment variable, which is only set by the extension's process spawn. Running `ralph interview` in a terminal is completely unaffected — it continues to use the existing TTY/non-TTY paths unchanged.

## Component Changes

### `ralph/run.py`
- Added `_DESCRIBE_YOURSELF` and `_VSCODE_SENTINEL` module-level constants.
- Added `_collect_guided_answers_vscode(questions, ralph_dir)`: writes questions JSON, prints sentinel, polls for answers file (600s timeout).
- `_collect_guided_answers()` gained a `ralph_dir=""` parameter; delegates to the VS Code path when `RALPH_VSCODE` is set.
- Call site in `run_interview_loop` passes `ralph_dir=self.ralph_dir`.

### `src/processManager.ts`
- Removed all PTY buffer/parse machinery: `CHOICE_HINT`, `MAX_OUTPUT_BUFFER`, `parsePromptFromBuffer`, `outputBuffer` map, `promptPending` set, `suppressEcho` map.
- Adds `RALPH_VSCODE: '1'` to the spawned process environment.
- In `onData`: detects sentinel, reads questions file synchronously, sends `{ type: 'stdin_interview', questions }` to webview. Sentinel line is not forwarded to the webview.

### `src/extension.ts`
- Added `submit_interview` message handler: writes `msg.answers` as JSON to `interview_answers.json`, unblocking Python's poll loop.

### `src/messages.ts`
- Removed `StdinReadyMessage`, `StdinPromptMessage`.
- Added `StdinInterviewMessage`: `{ type: 'stdin_interview', questions: Array<{ question, options }> }`.
- Added `SubmitInterviewAnswersMessage`: `{ type: 'submit_interview', answers: Array<{ question, answer }> }`.

### `webview/app.tsx`
- Removed all complex interview state: refs (`isInterviewModeRef`, `interviewBufferRef`, `pendingAutoAnswersRef`, `pendingRestartRef`, `interviewHistoryRef`, `interviewRunArgsRef`, `prevPromptRef`), stdout buffering, edit/restart logic.
- Added single `interviewQuestions: InterviewQuestion[] | null` state, set on `stdin_interview`, cleared on submit or `process_done`.
- `handleInterviewSubmit`: appends Q&A summary lines to OutputArea, then posts `submit_interview`.

### `webview/components/StdinInput.tsx`
- Rewritten as a multi-question scrollable form.
- All questions shown at once; each has its own radio-button list.
- Selecting "Describe yourself..." on any question reveals a textarea for that question only.
- Single "Submit All" button submits answers for all questions together.

### `webview/components/OutputArea.tsx`
- Removed `onEditAnswer` prop and Edit button from `interview_qa` rendering (no longer needed).
- `interview_qa` lines now simply show the question and the selected/typed answer.

## Future Improvement

Questions could be shown one at a time (next question appears after answering the current one) for a more guided feel. The file-based IPC approach supports this naturally — the form state just needs to track which question is active.
