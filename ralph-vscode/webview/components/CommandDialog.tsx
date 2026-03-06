import * as React from 'react';
import { useState, useEffect } from 'react';
import { Dialog, DialogClose, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { arrayRange, cn } from '../lib/utils';

export interface CommandDialogProps {
  command: string | null;
  settings: Record<string, unknown>;
  onClose: () => void;
  onRun: (cmd: string, args: string[]) => void;
}

function settingNum(settings: Record<string, unknown>, key: string): number | '' {
  const val = settings[key];
  if (typeof val === 'number') return val;
  if (typeof val === 'string') { const n = Number(val); if (!isNaN(n)) return n; }
  return '';
}
function settingBool(settings: Record<string, unknown>, key: string): boolean {
  const val = settings[key];
  return typeof val === 'boolean' ? val : false;
}
function settingStr(settings: Record<string, unknown>, key: string): string {
  const val = settings[key];
  return typeof val === 'string' ? val : '';
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

function Field({
  label,
  children,
  className = ''
}: {
  label: string;
  className?: string;
  children: React.ReactNode
}) {
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <label className="text-base text-left shrink-0 text-foreground">
        {label}
      </label>
      <div className="flex-1 w-full">{children}</div>
    </div>
  );
}


function CheckField({ 
  label, 
  checked, 
  onChange, 
  className = ''
}: { 
  label: string; 
  checked: boolean; 
  className?: string; 
  onChange: (v: boolean) => void 
}) {
  return (
    <label className={cn("flex items-center gap-2 cursor-pointer text-base select-none", className)}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="w-3.5 h-3.5" />
      <span className='mb-0.5'>{label}</span>
    </label>
  );
}

export function CommandDialog({ command, settings, onClose, onRun }: CommandDialogProps) {
  const [rounds, setRounds] = useState(1);
  const [verbose, setVerbose] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [limit, setLimit] = useState<number | ''>('');
  const [base, setBase] = useState('');
  const [resume, setResume] = useState(false);
  const [asynchronous, setAsynchronous] = useState(false);
  const [force, setForce] = useState(false);
  const [provider, setProvider] = useState('github');

  const setRoundsRef = React.useRef(setRounds);
  const setVerboseRef = React.useRef(setVerbose);
  const setCommentTextRef = React.useRef(setCommentText);
  const setLimitRef = React.useRef(setLimit);
  const setBaseRef = React.useRef(setBase);
  const setResumeRef = React.useRef(setResume);
  const setAsynchronousRef = React.useRef(setAsynchronous);
  const setForceRef = React.useRef(setForce);
  const setProviderRef = React.useRef(setProvider);

  useEffect(() => {
    if (!command) return;
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
  }, [command, settings]);

  const handleRun = () => {
    if (!command) return;
    const args: string[] = [];

    switch (command) {
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

    onRun(command, args);
    onClose();
  };

  const renderFlags = () => {
    switch (command) {
      case 'interview':
        return (
          <div className="flex flex-col gap-3 w-96">
            <Field label="Rounds" className='flex-col items-start gap-1'>
              <select className='w-full' value={rounds} onChange={e => setRounds(Math.max(1, Number(e.target.value) || 1))}>
                {arrayRange(1, 10).map(e => (<option key={e} value={e}>{e}</option>))}
              </select>
              <span className='text-description-color block text-md mt-1'>Number of interview rounds</span>
            </Field>

            <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
          </div>
        );

      case 'comment':
        return (
          <div className="flex flex-col gap-3 w-96">
            <Field label="Comment *" className='flex-col items-start gap-1'>
              <textarea rows={10} value={commentText} className='w-full text-base'
                onChange={e => setCommentText(e.target.value)}
                placeholder="Enter your comment here..." />
              <span className='text-description-color block text-md mt-1'>A description of the amendments to make</span>
            </Field>
            <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
          </div>
        );

      case 'enrich':
        return <div className='w-96'>
          <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
        </div>;

      case 'execute':
        return (
          <div className="flex flex-col gap-3 w-96">
            <Field label="Maximum number of agent iterations" className='flex-col items-start gap-1'>
              <input type="number" min={1} max={50} value={limit} className='w-full'
                onChange={e => setLimit(e.target.value === '' ? '' : Number(e.target.value))} />
              <span className='text-description-color block text-md mt-1'>Upper bound (default: 20)</span>
            </Field>
            <Field label="Base branch" className='flex-col items-start gap-1'>
              <input type="text" value={base} className='w-full' placeholder="main"
                onChange={e => setBase(e.target.value)} />
              <span className='text-description-color block text-md mt-1'>Base branch to branch from when creating the project branch (overrides settings.json for this invocation only)</span>
            </Field>
            <div className="flex flex-col gap-4">
              <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
              <CheckField label="--resume" checked={resume} onChange={setResume} />
              <CheckField label="--asynchronous" checked={asynchronous} onChange={setAsynchronous} />
            </div>
          </div>
        );

      case 'validate':
        return <div className='w-96'>
          <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
        </div>;

      case 'undo':
        return (
          <div className='w-96'>
            <CheckField label='--force (irreversible)' checked={force} onChange={setForce} className='text-error-color' />
          </div>
          // <label className="flex items-center gap-2 cursor-pointer text-sm select-none"
          //   style={{ color: 'var(--vscode-charts-red, var(--vscode-errorForeground))' }}>
          //   <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} className="w-3.5 h-3.5" />
          //   <span>--force (irreversible)</span>
          // </label>
        );

      case 'retry':
        return (
          <div className="flex flex-col gap-3 w-96">
            <CheckField label="--force" checked={force} onChange={setForce} />
            <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
          </div>
        );

      case 'oneshot':
        return (
          <div className="flex flex-col gap-3 w-96">
            <Field label="Maximum number of agent iterations" className='flex-col items-start gap-1'>
              <input type="number" min={1} max={50} value={limit} className='w-full'
                onChange={e => setLimit(e.target.value === '' ? '' : Number(e.target.value))} />
              <span className='text-description-color block text-md mt-1'>Upper bound (default: 20)</span>
            </Field>
            <Field label="Base branch" className='flex-col items-start gap-1'>
              <input type="text" value={base} placeholder="main" className='w-full'
                onChange={e => setBase(e.target.value)} />
              <span className='text-description-color block text-md mt-1'>Base branch to branch from when creating the project branch (overrides settings.json for this invocation only)</span>
            </Field>
            <Field label="Repository provider" className='flex-col items-start gap-1'>
              <select value={provider} onChange={e => setProvider(e.target.value)} className='w-full'>
                <option value="github">github</option>
                <option value="gitlab">gitlab</option>
              </select>
              <span className='text-description-color block text-md mt-1'>Provider to use for this invocation only (github/gitlab)</span>
            </Field>
            <div className="flex flex-col gap-4">

              <div className='gap-0'>
                <CheckField label="--resume" checked={resume} onChange={setResume} />
                <span className='text-description-color block text-md mt-1'>Allow the agent to resume execution from an existing branch</span>
              </div>
              <div className='gap-0'>
                <CheckField label="--asynchronous" checked={asynchronous} onChange={setAsynchronous} />
                <span className='text-description-color block text-md mt-1'>Enable/disable asynchronous agent execution for this invocation only</span>
              </div>

              <CheckField label="--verbose" checked={verbose} onChange={setVerbose} />
            </div>
          </div>
        );

      case 'pr':
        return (
          <Field label="Repository provider" className='flex-col items-start gap-1'>
            <select value={provider} onChange={e => setProvider(e.target.value)} className='w-full'>
              <option value="github">github</option>
              <option value="gitlab">gitlab</option>
            </select>
            <span className='text-description-color block text-md mt-1'>Provider to use for this invocation only (github/gitlab)</span>
          </Field>
        );

      default:
        return null;
    }
  };

  const isRunDisabled = command === 'comment' && !commentText;

  return (
    <Dialog open={command !== null} onOpenChange={open => !open}>
      <DialogContent onClose={onClose}>
        <DialogHeader>
          <DialogTitle>Configure: {command}</DialogTitle>
        </DialogHeader>
        <div className="py-1">{renderFlags()}</div>
        <DialogFooter>
          <DialogClose>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button onClick={handleRun} disabled={isRunDisabled}>
            ▶ Run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
