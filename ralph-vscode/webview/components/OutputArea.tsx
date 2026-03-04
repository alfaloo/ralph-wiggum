import * as React from 'react';
import { useEffect, useRef, useContext } from 'react';
import { marked } from 'marked';
import { VscodeContext } from '../app';
import { Button } from './ui/button';

export interface OutputLine {
  type: 'stdout' | 'stderr' | 'error' | 'user_answer';
  text: string;
}

export interface OutputAreaProps {
  outputLines: OutputLine[];
  lastCommand: string | null;
  onClear: () => void;
}

const ANSI_REGEX = /\x1B\[[0-9;]*[mGKHFJ]/g;
function stripAnsi(text: string): string { return text.replace(ANSI_REGEX, ''); }

const MARKDOWN_START = /^(#|\*\*|- \[|> |\|)/;
function looksLikeMarkdown(text: string): boolean { return MARKDOWN_START.test(text.trim()); }

function sanitizeHtml(html: string): string {
  return html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
}

const PR_URL_PATTERN = /https:\/\/github\.com\/[^\s]+\/pull\/\d+|https:\/\/gitlab\.com\/[^\s]+\/-\/merge_requests\/\d+/g;

function containsPrUrl(text: string): boolean {
  PR_URL_PATTERN.lastIndex = 0;
  return PR_URL_PATTERN.test(text);
}

function renderWithPrUrls(text: string, onOpenUrl: (url: string) => void): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  const regex = new RegExp(PR_URL_PATTERN.source, 'g');
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    const url = match[0];
    parts.push(
      <a key={match.index} href="#"
        style={{ color: 'var(--vscode-textLink-foreground)' }}
        onClick={(e: React.MouseEvent) => { e.preventDefault(); onOpenUrl(url); }}>
        {url}
      </a>
    );
    lastIndex = match.index + url.length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

export function OutputArea({ outputLines, lastCommand, onClear }: OutputAreaProps) {
  const { postMessage } = useContext(VscodeContext);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto' });
  }, [outputLines]);

  const handleOpenUrl = (url: string) => postMessage({ type: 'open_url', url });

  const renderLine = (line: OutputLine, index: number): React.ReactElement => {
    const cleaned = stripAnsi(line.text);

    if (line.type === 'error') {
      const isNotFound = line.text.includes('ralph not found') || line.text.includes('ralph_not_found');
      return (
        <div key={index} style={{
          background: 'var(--vscode-inputValidation-errorBackground, rgba(90,29,29,0.6))',
          color: 'var(--vscode-inputValidation-errorForeground, #f48771)',
          borderLeft: '3px solid var(--vscode-inputValidation-errorBorder, #f48771)',
          padding: '4px 8px', margin: '4px 0', fontWeight: 'bold', borderRadius: '2px',
        }}>
          ⚠ {cleaned}
          {isNotFound && (
            <div style={{ fontWeight: 'normal', marginTop: '4px', fontSize: '0.9em' }}>
              Please check that the <code>ralph</code> CLI is installed and available on your PATH.
            </div>
          )}
        </div>
      );
    }

    if (line.type === 'stderr') {
      return <div key={index} style={{ color: 'var(--vscode-editorWarning-foreground)' }}>{cleaned}</div>;
    }

    if (line.type === 'user_answer') {
      return (
        <div key={index} style={{ fontStyle: 'italic', color: 'var(--vscode-descriptionForeground)', marginTop: '4px' }}>
          {'You: '}{cleaned}
        </div>
      );
    }

    if (looksLikeMarkdown(cleaned)) {
      const rawHtml = marked.parse(cleaned) as string;
      return <div key={index} className="output-markdown" dangerouslySetInnerHTML={{ __html: sanitizeHtml(rawHtml) }} />;
    }

    if (containsPrUrl(cleaned)) {
      return <div key={index}>{renderWithPrUrls(cleaned, handleOpenUrl)}</div>;
    }

    return <div key={index}>{cleaned}</div>;
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Command reference bar */}
      {lastCommand && (
        <div className="flex-shrink-0 flex items-center gap-2 px-3 py-1.5 border-b border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]"
          style={{ background: 'var(--vscode-textCodeBlock-background, var(--vscode-editor-background))' }}>
          <span className="text-xs" style={{ color: 'var(--vscode-descriptionForeground)' }}>$</span>
          <code className="text-xs flex-1 truncate" style={{ fontFamily: 'var(--vscode-editor-font-family)' }}>
            {lastCommand}
          </code>
        </div>
      )}

      {/* Toolbar row */}
      <div className="flex-shrink-0 flex justify-end px-2 py-1 border-b border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]">
        <Button size="sm" variant="ghost" onClick={onClear}>Clear</Button>
      </div>

      {/* Scrollable output */}
      <div className="flex-1 overflow-y-auto px-3 py-2" style={{
        fontFamily: 'var(--vscode-editor-font-family)',
        fontSize: 'var(--vscode-editor-font-size)',
        background: 'var(--vscode-terminal-background, var(--vscode-editor-background))',
      }}>
        {outputLines.map((line, index) => renderLine(line, index))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
