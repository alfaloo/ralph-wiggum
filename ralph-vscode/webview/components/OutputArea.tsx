import * as React from 'react';
import { useEffect, useRef, useContext } from 'react';
import { marked } from 'marked';
import { VscodeContext } from '../app';

export interface OutputLine {
  type: 'stdout' | 'stderr' | 'error' | 'user_answer';
  text: string;
}

export interface OutputAreaProps {
  outputLines: OutputLine[];
  onClear: () => void;
}

const ANSI_REGEX = /\x1B\[[0-9;]*[mGKHFJ]/g;

function stripAnsi(text: string): string {
  return text.replace(ANSI_REGEX, '');
}

// Heuristic: if trimmed text starts with markdown markers, treat as markdown block
const MARKDOWN_START = /^(#|\*\*|- \[|> |\|)/;

function looksLikeMarkdown(text: string): boolean {
  return MARKDOWN_START.test(text.trim());
}

// Strip <script> tags from HTML for basic safety
function sanitizeHtml(html: string): string {
  return html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
}

// Regexes for PR/MR URL detection (non-global, used with exec loop)
const PR_URL_PATTERN = /https:\/\/github\.com\/[^\s]+\/pull\/\d+|https:\/\/gitlab\.com\/[^\s]+\/merge_requests\/\d+/g;

function containsPrUrl(text: string): boolean {
  PR_URL_PATTERN.lastIndex = 0;
  return PR_URL_PATTERN.test(text);
}

function renderWithPrUrls(
  text: string,
  onOpenUrl: (url: string) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  const regex = new RegExp(PR_URL_PATTERN.source, 'g');
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const url = match[0];
    parts.push(
      <a
        key={match.index}
        href="#"
        style={{ color: 'var(--vscode-textLink-foreground)' }}
        onClick={(e: React.MouseEvent) => {
          e.preventDefault();
          onOpenUrl(url);
        }}
      >
        {url}
      </a>,
    );
    lastIndex = match.index + url.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

export function OutputArea({ outputLines, onClear }: OutputAreaProps): React.ReactElement {
  const { postMessage } = useContext(VscodeContext);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever new lines arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto' });
  }, [outputLines]);

  const handleOpenUrl = (url: string) => {
    postMessage({ type: 'open_url', url });
  };

  const renderLine = (line: OutputLine, index: number): React.ReactElement => {
    const cleaned = stripAnsi(line.text);

    if (line.type === 'error') {
      const isNotFound =
        line.text.includes('ralph not found') || line.text.includes('ralph_not_found');
      return (
        <div
          key={index}
          style={{
            background: 'var(--vscode-inputValidation-errorBackground, rgba(90,29,29,0.6))',
            color: 'var(--vscode-inputValidation-errorForeground, #f48771)',
            borderLeft: '3px solid var(--vscode-inputValidation-errorBorder, #f48771)',
            padding: '4px 8px',
            margin: '4px 0',
            fontWeight: 'bold',
            borderRadius: '2px',
          }}
        >
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
      return (
        <div key={index} style={{ color: 'var(--vscode-editorWarning-foreground)' }}>
          {cleaned}
        </div>
      );
    }

    if (line.type === 'user_answer') {
      return (
        <div
          key={index}
          style={{
            fontStyle: 'italic',
            color: 'var(--vscode-descriptionForeground)',
            marginTop: '4px',
          }}
        >
          {'You: '}
          {cleaned}
        </div>
      );
    }

    // stdout: check for markdown first
    if (looksLikeMarkdown(cleaned)) {
      const rawHtml = marked.parse(cleaned) as string;
      const safeHtml = sanitizeHtml(rawHtml);
      return (
        <div
          key={index}
          className="output-markdown"
          dangerouslySetInnerHTML={{ __html: safeHtml }}
        />
      );
    }

    // stdout: check for PR/MR URLs
    if (containsPrUrl(cleaned)) {
      return <div key={index}>{renderWithPrUrls(cleaned, handleOpenUrl)}</div>;
    }

    // Plain stdout
    return <div key={index}>{cleaned}</div>;
  };

  return (
    <div style={{ position: 'relative' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          padding: '4px 4px 0',
        }}
      >
        <button className="btn" onClick={onClear} title="Clear output">
          Clear
        </button>
      </div>
      <div className="output-area">
        {outputLines.map((line, index) => renderLine(line, index))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
