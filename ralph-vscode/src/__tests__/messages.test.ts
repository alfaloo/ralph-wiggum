// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

vi.mock('../../webview/app', async () => {
  const { createContext } = await import('react');
  return {
    VscodeContext: createContext<{ postMessage: (m: unknown) => void }>({ postMessage: () => {} }),
  };
});

import { CommandDialog } from '../../webview/components/CommandDialog';
import { VscodeContext } from '../../webview/app';

import type {
  StdoutMessage,
  StderrMessage,
  ProcessDoneMessage,
  ProcessStartedMessage,
  StdinReadyMessage,
  ShowConfirmMessage,
  StateUpdateMessage,
  SettingsUpdateMessage,
  RalphNotFoundMessage,
  RunCommandMessage,
  StdinInputMessage,
  StopCommandMessage,
  OpenUrlMessage,
  ExtensionToWebviewMessage,
  WebviewToExtensionMessage,
} from '../messages';

// Sample instances of every message type
const extensionToWebviewSamples: ExtensionToWebviewMessage[] = [
  { type: 'stdout', chunk: 'hello world\n' } satisfies StdoutMessage,
  { type: 'stderr', chunk: 'error output\n' } satisfies StderrMessage,
  { type: 'process_done', exitCode: 0 } satisfies ProcessDoneMessage,
  { type: 'process_started' } satisfies ProcessStartedMessage,
  { type: 'stdin_ready' } satisfies StdinReadyMessage,
  { type: 'show_confirm', message: 'Are you sure?' } satisfies ShowConfirmMessage,
  {
    type: 'state_update',
    file: 'tasks',
    projectName: 'my-project',
    content: '{"tasks":[]}',
  } satisfies StateUpdateMessage,
  {
    type: 'settings_update',
    settings: { '--limit': 10, '--verbose': true },
  } satisfies SettingsUpdateMessage,
  { type: 'ralph_not_found' } satisfies RalphNotFoundMessage,
];

const webviewToExtensionSamples: WebviewToExtensionMessage[] = [
  { type: 'run_command', command: 'execute', args: ['--limit', '5'] } satisfies RunCommandMessage,
  { type: 'stdin_input', text: 'my answer\n' } satisfies StdinInputMessage,
  { type: 'stop_command' } satisfies StopCommandMessage,
  { type: 'open_url', url: 'https://github.com/owner/repo/pull/42' } satisfies OpenUrlMessage,
];

const allSamples = [...extensionToWebviewSamples, ...webviewToExtensionSamples];

describe('Message type discriminants', () => {
  it('each message type has a unique type discriminant', () => {
    const types = allSamples.map((msg) => msg.type);
    const uniqueTypes = new Set(types);
    expect(uniqueTypes.size).toBe(types.length);
  });

  it('ExtensionToWebviewMessage types are all unique', () => {
    const types = extensionToWebviewSamples.map((msg) => msg.type);
    const uniqueTypes = new Set(types);
    expect(uniqueTypes.size).toBe(types.length);
  });

  it('WebviewToExtensionMessage types are all unique', () => {
    const types = webviewToExtensionSamples.map((msg) => msg.type);
    const uniqueTypes = new Set(types);
    expect(uniqueTypes.size).toBe(types.length);
  });

  it('no type discriminant is shared across both union types', () => {
    const extTypes = extensionToWebviewSamples.map((msg) => msg.type);
    const webTypes = new Set<string>(webviewToExtensionSamples.map((msg) => msg.type));
    for (const t of extTypes) {
      expect(webTypes.has(t)).toBe(false);
    }
  });
});

describe('Message JSON serialisation roundtrip', () => {
  for (const sample of allSamples) {
    it(`${sample.type} survives JSON.stringify → JSON.parse without data loss`, () => {
      const serialised = JSON.stringify(sample);
      const parsed = JSON.parse(serialised);
      expect(parsed).toEqual(sample);
    });
  }

  it('state_update with all file types roundtrips correctly', () => {
    const fileCases: StateUpdateMessage['file'][] = ['tasks', 'validation', 'spec'];
    for (const file of fileCases) {
      const msg: StateUpdateMessage = {
        type: 'state_update',
        file,
        projectName: 'test-project',
        content: `content for ${file}`,
      };
      expect(JSON.parse(JSON.stringify(msg))).toEqual(msg);
    }
  });

  it('process_done with non-zero exit code roundtrips correctly', () => {
    const msg: ProcessDoneMessage = { type: 'process_done', exitCode: 1 };
    expect(JSON.parse(JSON.stringify(msg))).toEqual(msg);
  });

  it('settings_update with nested settings roundtrips correctly', () => {
    const msg: SettingsUpdateMessage = {
      type: 'settings_update',
      settings: {
        '--limit': 20,
        '--base': 'develop',
        '--verbose': false,
        '--asynchronous': true,
        nested: { key: 'value' },
      },
    };
    expect(JSON.parse(JSON.stringify(msg))).toEqual(msg);
  });
});

describe('CommandDialog — single-agent mode', () => {
  let mockPostMessage: ReturnType<typeof vi.fn>;
  let mockOnClose: ReturnType<typeof vi.fn>;
  let mockOnRun: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockPostMessage = vi.fn();
    mockOnClose = vi.fn();
    mockOnRun = vi.fn();
  });

  afterEach(() => {
    cleanup();
  });

  function renderDialog(command: string, settings: Record<string, unknown> = {}) {
    render(
      React.createElement(
        VscodeContext.Provider,
        { value: { postMessage: mockPostMessage as (m: unknown) => void } },
        React.createElement(CommandDialog, {
          command,
          settings,
          onClose: mockOnClose as () => void,
          onRun: mockOnRun as (cmd: string, args: string[]) => void,
        })
      )
    );
  }

  it('single_checkbox_present_in_execute_dialog', () => {
    renderDialog('execute');
    expect(screen.getByLabelText('--single')).toBeTruthy();
  });

  it('single_checkbox_present_in_oneshot_dialog', () => {
    renderDialog('oneshot');
    expect(screen.getByLabelText('--single')).toBeTruthy();
  });

  it('single_flag_included_in_run_command_args', () => {
    renderDialog('execute');
    const singleCheckbox = screen.getByLabelText('--single') as HTMLInputElement;
    fireEvent.click(singleCheckbox);
    expect(singleCheckbox.checked).toBe(true);
    const runButton = screen.getByRole('button', { name: /Run/ });
    fireEvent.click(runButton);
    expect(mockOnRun).toHaveBeenCalledOnce();
    const args: string[] = mockOnRun.mock.calls[0][1];
    const singleIdx = args.indexOf('--single');
    expect(singleIdx).toBeGreaterThanOrEqual(0);
    expect(args[singleIdx + 1]).toBe('true');
  });

  it('single_and_async_checkboxes_mutually_disabled', () => {
    renderDialog('execute');
    const singleCheckbox = screen.getByLabelText('--single') as HTMLInputElement;
    const asyncCheckbox = screen.getByLabelText('--asynchronous') as HTMLInputElement;

    // Check single → async should become disabled
    fireEvent.click(singleCheckbox);
    expect(asyncCheckbox.disabled).toBe(true);

    // Uncheck single, then check async → single should become disabled
    fireEvent.click(singleCheckbox);
    expect(asyncCheckbox.disabled).toBe(false);
    fireEvent.click(asyncCheckbox);
    expect(singleCheckbox.disabled).toBe(true);
  });

  it('client_validation_blocks_both_flags', () => {
    // Initialize with both flags true via settings
    renderDialog('execute', { '--single': true, '--asynchronous': true });
    const runButton = screen.getByRole('button', { name: /Run/ });
    fireEvent.click(runButton);
    expect(mockPostMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'show_error' })
    );
    expect(mockOnRun).not.toHaveBeenCalled();
  });
});
