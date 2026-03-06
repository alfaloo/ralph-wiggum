import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function arrayRange(start: number, stop: number, step = 1): number[] {
  return Array.from({ length: (stop - start) / step + 1 }, (_, index) => start + index * step);
}
