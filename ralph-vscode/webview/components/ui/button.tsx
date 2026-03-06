import * as React from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'stop' | 'ghost';
  size?: 'sm' | 'default';
}

export function Button({ className, variant = 'default', size = 'default', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded cursor-pointer',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        size === 'sm' && 'px-2 py-0.5 text-xs',
        size === 'default' && 'px-3 py-1 text-sm',
        variant === 'default' && 'btn',
        variant === 'stop' && 'btn-stop',
        variant === 'ghost' && 'bg-transparent hover:opacity-80',
        className
      )}
      {...props}
    />
  );
}
