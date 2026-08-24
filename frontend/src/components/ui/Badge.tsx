import * as React from 'react'
import { cn } from '@/lib/utils'

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          {
            'border-transparent bg-primary-100 text-primary-800 hover:bg-primary-100/80 dark:bg-primary-900/30 dark:text-primary-300':
              variant === 'default',
            'border-transparent bg-dark-100 text-dark-800 hover:bg-dark-100/80 dark:bg-dark-700 dark:text-dark-300':
              variant === 'secondary',
            'border-transparent bg-red-100 text-red-800 hover:bg-red-100/80 dark:bg-red-900/30 dark:text-red-300':
              variant === 'destructive',
            'text-dark-700 border-dark-300 bg-white hover:bg-dark-100 dark:text-dark-300 dark:border-dark-600 dark:bg-dark-800 hover:dark:bg-dark-700':
              variant === 'outline',
            'border-transparent bg-green-100 text-green-800 hover:bg-green-100/80 dark:bg-green-900/30 dark:text-green-300':
              variant === 'success',
            'border-transparent bg-yellow-100 text-yellow-800 hover:bg-yellow-100/80 dark:bg-yellow-900/30 dark:text-yellow-300':
              variant === 'warning',
          },
          className
        )}
        {...props}
      />
    )
  }
)
Badge.displayName = 'Badge'