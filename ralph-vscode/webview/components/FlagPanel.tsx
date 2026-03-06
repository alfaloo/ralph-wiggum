import * as React from 'react';
import { useState, useEffect, useRef } from 'react';

export interface FlagPanelProps {
  activeCommand: string | null;
  settings: Record<string, unknown>;
  isRunning: boolean;
  onRun: (cmd: string, args: string[]) => void;
}

function settingNum(settings: Record<string, unknown>, key: string): number | '' {
  const val = settings[key];
  if (typeof val === 'number') return val;
  if (typeof val === 'string') {
    const n = Number(val);
    if (!isNaN(n)) return n;
  }
  return '';
}

function settingBool(settings: Record<string, unknown>, key: string): boolean {
  const val = settings[key];
  if (typeof val === 'boolean') return val;
  return false;
}

function settingStr(settings: Record<string, unknown>, key: string): string {
  const val = settings[key];
  if (typeof val === 'string') return val;
  return '';
}

function initState(settings: Record<string, unknown>) {
  return {
    rounds: (settingNum(settings, '--rounds') || 1) as number,
    verbose: settingBool(settings, '--verbose'),
    commentText: '',
    limit: settingNum(settings, '--limit'),
    base: settingStr(settings, '--base'),
    resume: false,
    asynchronous: settingBool(settings, '--asynchronous'),
    force: false,
    provider: settingStr(settings, '--provider') || 'github',
  };
}

export function FlagPanel({ activeCommand, settings, isRunning, onRun }: FlagPanelProps): React.ReactElement | null {
  const [rounds, setRounds] = useState<number>(1);
  const [verbose, setVerbose] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [limit, setLimit] = useState<number | ''>('');
  const [base, setBase] = useState('');
  const [resume, setResume] = useState(false);
  const [asynchronous, setAsynchronous] = useState(false);
  const [force, setForce] = useState(false);
  const [provider, setProvider] = useState('github');

  const setRoundsRef = useRef(setRounds);
  const setVerboseRef = useRef(setVerbose);
  const setCommentTextRef = useRef(setCommentText);
  const setLimitRef = useRef(setLimit);
  const setBaseRef = useRef(setBase);
  const setResumeRef = useRef(setResume);
  const setAsynchronousRef = useRef(setAsynchronous);
  const setForceRef = useRef(setForce);
  const setProviderRef = useRef(setProvider);

  useEffect(() => {
    const s = initState(settings);
    setRoundsRef.current(s.rounds);
    setVerboseRef.current(s.verbose);
    setCommentTextRef.current('');
    setLimitRef.current(s.limit);
    setBaseRef.current(s.base);
    setResumeRef.current(false);
    setAsynchronousRef.current(s.asynchronous);
    setForceRef.current(false);
    setProviderRef.current(s.provider);
  }, [activeCommand, settings]);

  if (!activeCommand || activeCommand === 'status') {
    return null;
  }

  const handleRun = () => {
    if (!activeCommand) return;
    const args: string[] = [];

    switch (activeCommand) {
      case 'interview':
        args.push('--rounds', String(rounds));
        args.push('--verbose', String(verbose));
        break;
      case 'comment':
        if (commentText) args.push(commentText);
        args.push('--verbose', String(verbose));
        break;
      case 'enrich':
        args.push('--verbose', String(verbose));
        break;
      case 'execute':
        if (limit !== '') args.push('--limit', String(limit));
        if (base) args.push('--base', base);
        args.push('--verbose', String(verbose));
        if (resume) args.push('--resume');
        args.push('--asynchronous', String(asynchronous));
        break;
      case 'validate':
        args.push('--verbose', String(verbose));
        break;
      case 'undo':
        if (force) args.push('--force');
        break;
      case 'retry':
        if (force) args.push('--force');
        args.push('--verbose', String(verbose));
        break;
      case 'oneshot':
        if (limit !== '') args.push('--limit', String(limit));
        if (base) args.push('--base', base);
        args.push('--verbose', String(verbose));
        if (resume) args.push('--resume');
        args.push('--asynchronous', String(asynchronous));
        args.push('--provider', provider);
        break;
      case 'pr':
        args.push('--provider', provider);
        break;
    }

    onRun(activeCommand, args);
  };

  const renderFlags = () => {
    switch (activeCommand) {
      case 'interview':
        return (
          <>
            <label>
              --rounds:&nbsp;
              <input
                type="number"
                min={1}
                value={rounds}
                onChange={e => setRounds(Math.max(1, Number(e.target.value) || 1))}
                disabled={isRunning}
                style={{ width: 60 }}
              />
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={verbose}
                onChange={e => setVerbose(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--verbose
            </label>
          </>
        );

      case 'comment':
        return (
          <>
            <div style={{ marginBottom: 6 }}>
              <label>
                Comment (required):
                <textarea
                  rows={4}
                  style={{ width: '100%', boxSizing: 'border-box', marginTop: 4 }}
                  value={commentText}
                  onChange={e => setCommentText(e.target.value)}
                  disabled={isRunning}
                  placeholder="Enter your comment here..."
                />
              </label>
            </div>
            <label>
              <input
                type="checkbox"
                checked={verbose}
                onChange={e => setVerbose(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--verbose
            </label>
          </>
        );

      case 'enrich':
        return (
          <label>
            <input
              type="checkbox"
              checked={verbose}
              onChange={e => setVerbose(e.target.checked)}
              disabled={isRunning}
            />
            &nbsp;--verbose
          </label>
        );

      case 'execute':
        return (
          <>
            <label>
              --limit:&nbsp;
              <input
                type="number"
                min={1}
                value={limit}
                onChange={e => setLimit(e.target.value === '' ? '' : Number(e.target.value))}
                disabled={isRunning}
                style={{ width: 60 }}
              />
            </label>
            &nbsp;&nbsp;
            <label>
              --base:&nbsp;
              <input
                type="text"
                value={base}
                onChange={e => setBase(e.target.value)}
                disabled={isRunning}
                style={{ width: 100 }}
                placeholder="main"
              />
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={verbose}
                onChange={e => setVerbose(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--verbose
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={resume}
                onChange={e => setResume(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--resume
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={asynchronous}
                onChange={e => setAsynchronous(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--asynchronous
            </label>
          </>
        );

      case 'validate':
        return (
          <label>
            <input
              type="checkbox"
              checked={verbose}
              onChange={e => setVerbose(e.target.checked)}
              disabled={isRunning}
            />
            &nbsp;--verbose
          </label>
        );

      case 'undo':
        return (
          <label style={{ color: 'var(--vscode-charts-red, var(--vscode-errorForeground))' }}>
            <input
              type="checkbox"
              checked={force}
              onChange={e => setForce(e.target.checked)}
              disabled={isRunning}
            />
            &nbsp;--force (irreversible)
          </label>
        );

      case 'retry':
        return (
          <>
            <label>
              <input
                type="checkbox"
                checked={force}
                onChange={e => setForce(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--force
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={verbose}
                onChange={e => setVerbose(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--verbose
            </label>
          </>
        );

      case 'oneshot':
        return (
          <>
            <label>
              --limit:&nbsp;
              <input
                type="number"
                min={1}
                value={limit}
                onChange={e => setLimit(e.target.value === '' ? '' : Number(e.target.value))}
                disabled={isRunning}
                style={{ width: 60 }}
              />
            </label>
            &nbsp;&nbsp;
            <label>
              --base:&nbsp;
              <input
                type="text"
                value={base}
                onChange={e => setBase(e.target.value)}
                disabled={isRunning}
                style={{ width: 100 }}
                placeholder="main"
              />
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={verbose}
                onChange={e => setVerbose(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--verbose
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={resume}
                onChange={e => setResume(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--resume
            </label>
            &nbsp;&nbsp;
            <label>
              <input
                type="checkbox"
                checked={asynchronous}
                onChange={e => setAsynchronous(e.target.checked)}
                disabled={isRunning}
              />
              &nbsp;--asynchronous
            </label>
            &nbsp;&nbsp;
            <label>
              --provider:&nbsp;
              <select
                value={provider}
                onChange={e => setProvider(e.target.value)}
                disabled={isRunning}
              >
                <option value="github">github</option>
                <option value="gitlab">gitlab</option>
              </select>
            </label>
          </>
        );

      case 'pr':
        return (
          <label>
            --provider:&nbsp;
            <select
              value={provider}
              onChange={e => setProvider(e.target.value)}
              disabled={isRunning}
            >
              <option value="github">github</option>
              <option value="gitlab">gitlab</option>
            </select>
          </label>
        );

      default:
        return null;
    }
  };

  return (
    <div className="flag-panel">
      <span style={{ fontWeight: 600 }}>{activeCommand}</span>:&nbsp;
      {renderFlags()}
      &nbsp;&nbsp;
      <button
        className="btn"
        onClick={handleRun}
        disabled={isRunning || (activeCommand === 'comment' && !commentText)}
      >
        Run
      </button>
    </div>
  );
}
