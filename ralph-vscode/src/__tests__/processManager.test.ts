import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EventEmitter } from 'events';

// vi.hoisted ensures these are initialized before vi.mock() factory calls
const { mockSpawn, mockKill } = vi.hoisted(() => ({
  mockSpawn: vi.fn(),
  mockKill: vi.fn(),
}));

vi.mock('child_process', () => ({
  spawn: mockSpawn,
}));

vi.mock('vscode', () => ({
  window: {
    showInformationMessage: vi.fn().mockResolvedValue(undefined),
  },
}));

// Import after mocks are set up
import { RalphProcessManager } from '../processManager';

function createMockChild() {
  const child = new EventEmitter() as any;
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.stdin = { write: vi.fn() };
  child.kill = mockKill;
  return child;
}

// Y/N regex patterns tested directly — mirrors processManager.ts definitions
// plus the third pattern from extension.ts (Update base branch, used during init)
const YN_PATTERNS = [
  /already exists\. Overwrite\? \(y\/n\):/,
  /Delete branch '.*'\. This cannot be undone\. \(y\/n\):/,
  /Update base branch to '.*'\? \(y\/n\):/,
];

describe('RalphProcessManager', () => {
  let manager: RalphProcessManager;
  let mockChild: any;
  let mockPanel: any;

  beforeEach(() => {
    vi.clearAllMocks();
    mockChild = createMockChild();
    mockSpawn.mockReturnValue(mockChild);
    manager = new RalphProcessManager('/workspace');
    mockPanel = {
      webview: {
        postMessage: vi.fn(),
      },
    };
  });

  describe('run() — single-process enforcement', () => {
    it('does not spawn a second process when one is already running for the same project', () => {
      // Start first process
      manager.run('my-project', 'execute', [], mockPanel);
      expect(mockSpawn).toHaveBeenCalledTimes(1);
      expect(manager.isRunning('my-project')).toBe(true);

      // Attempt to start a second process for the same project
      manager.run('my-project', 'execute', [], mockPanel);
      expect(mockSpawn).toHaveBeenCalledTimes(1); // still only called once
    });

    it('allows a new process for a different project while one is running', () => {
      manager.run('project-a', 'execute', [], mockPanel);
      expect(mockSpawn).toHaveBeenCalledTimes(1);

      const mockChild2 = createMockChild();
      mockSpawn.mockReturnValueOnce(mockChild2);
      manager.run('project-b', 'execute', [], mockPanel);
      expect(mockSpawn).toHaveBeenCalledTimes(2);
    });
  });

  describe('stop()', () => {
    it('sends SIGTERM to the running child process', () => {
      manager.run('my-project', 'execute', [], mockPanel);
      manager.stop('my-project');
      expect(mockKill).toHaveBeenCalledWith('SIGTERM');
    });

    it('does nothing when no process is running for the project', () => {
      manager.stop('non-existent-project');
      expect(mockKill).not.toHaveBeenCalled();
    });
  });

  describe('Y/N prompt regex patterns', () => {
    describe('should match intended prompt strings', () => {
      it('matches the validation.md overwrite prompt', () => {
        const line = 'validation.md already exists. Overwrite? (y/n):';
        expect(YN_PATTERNS[0].test(line)).toBe(true);
      });

      it('matches the undo delete branch prompt', () => {
        const line = "Delete branch 'feature/my-branch'. This cannot be undone. (y/n):";
        expect(YN_PATTERNS[1].test(line)).toBe(true);
      });

      it('matches the init update base branch prompt', () => {
        const line = "Update base branch to 'main'? (y/n):";
        expect(YN_PATTERNS[2].test(line)).toBe(true);
      });

      it('delete branch pattern matches any branch name', () => {
        const line = "Delete branch 'release/v2.0-beta'. This cannot be undone. (y/n):";
        expect(YN_PATTERNS[1].test(line)).toBe(true);
      });

      it('update base branch pattern matches any branch name', () => {
        const line = "Update base branch to 'develop'? (y/n):";
        expect(YN_PATTERNS[2].test(line)).toBe(true);
      });
    });

    describe('should not match unrelated stdout lines', () => {
      const unrelatedLines = [
        'Do you want to proceed?',
        'Are you sure? (yes/no)',
        'Continue? [y/N]',
        'File not found.',
        'Running ralph execute...',
        'Task completed successfully.',
        '',
      ];

      for (const line of unrelatedLines) {
        it(`does not match: "${line || '(empty string)'}"`, () => {
          for (const pattern of YN_PATTERNS) {
            expect(pattern.test(line)).toBe(false);
          }
        });
      }

      it('overwrite pattern does not match delete branch prompt', () => {
        const line = "Delete branch 'main'. This cannot be undone. (y/n):";
        expect(YN_PATTERNS[0].test(line)).toBe(false);
      });

      it('delete branch pattern does not match overwrite prompt', () => {
        const line = 'validation.md already exists. Overwrite? (y/n):';
        expect(YN_PATTERNS[1].test(line)).toBe(false);
      });

      it('update base branch pattern does not match overwrite prompt', () => {
        const line = 'validation.md already exists. Overwrite? (y/n):';
        expect(YN_PATTERNS[2].test(line)).toBe(false);
      });
    });
  });
});
