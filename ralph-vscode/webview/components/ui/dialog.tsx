import * as React from 'react';
import { cn } from '../../lib/utils';

// Portal-free dialog for VSCode webviews.
// Radix UI uses React.createPortal (renders into document.body) which can fail
// silently inside VSCode's sandboxed iframe. Using position:fixed inline is
// equally correct and always works in the webview context.

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

function Dialog({ open, onOpenChange, children }: DialogProps) {
  // Close on Escape key
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onOpenChange(false); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9998 }}
        onClick={() => onOpenChange(false)}
      />
      {/* Centered content wrapper */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
        <div style={{ pointerEvents: 'auto' }}>
          {children}
        </div>
      </div>
    </>
  );
}

interface DialogCloseProps {
  asChild?: boolean;
  children: React.ReactElement<{ onClick?: React.MouseEventHandler }>;
  onClick?: React.MouseEventHandler;
}

// DialogClose must be used inside a DialogContent that receives onClose via context
const DialogCloseContext = React.createContext<() => void>(() => { });

function DialogClose({ children }: DialogCloseProps) {
  const onClose = React.useContext(DialogCloseContext);
  return React.cloneElement(children, { onClick: onClose });
}

interface DialogContentProps {
  className?: string;
  children: React.ReactNode;
  onClose?: () => void;
}

function DialogContent({ className, children, onClose }: DialogContentProps) {
  return (
    <DialogCloseContext.Provider value={onClose ?? (() => { })}>
      <div
        className={cn(
          'w-full max-w-lg rounded-lg p-6 shadow-xl',
          'border border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]',
          'bg-[var(--vscode-editor-background)] text-[var(--vscode-foreground)]',
          className
        )}
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </DialogCloseContext.Provider>
  );
}

function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('mb-4 pb-3 border-b border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))]', className)}
      {...props}
    />
  );
}

function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn('text-sm font-semibold uppercase tracking-wide text-[var(--vscode-descriptionForeground)]', className)}
      {...props}
    />
  );
}

function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('mt-6 pt-4 border-t border-[var(--vscode-panel-border,var(--vscode-editorGroup-border))] flex justify-end gap-2', className)}
      {...props}
    />
  );
}

export { Dialog, DialogClose, DialogContent, DialogHeader, DialogTitle, DialogFooter };
