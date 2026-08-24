'use client';

/**
 * Client-side context providers for the whole app.
 *
 * MEASURED 2026-08-24: the app crashed with a Next.js error overlay reading
 *   "Error: No QueryClient set, use QueryClientProvider to set one"
 *      at src/app/components/ChatMode.tsx (58:37) @ useQueryClient
 * because no QueryClientProvider existed anywhere in the tree. `@tanstack/react-query` was in
 * package.json and two components (ChatMode.tsx:58, Canvas.tsx:61) called useQueryClient(), but
 * layout.tsx rendered {children} bare. useQueryClient() throws rather than returning null when
 * there is no provider above it, so the whole route went down, which is why a persistent
 * "1 error" badge sat in the corner of every tab.
 *
 * This lives in its own file because layout.tsx is a server component -- it exports `metadata`,
 * which is illegal in a 'use client' module -- so the provider cannot be declared inline there.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  // Created in state, not at module scope: a module-level client is shared across every request
  // when this runs on the server, which leaks one user's cached data into another's render.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // A pipeline run takes ~20-500s and the Library/registry endpoints are cheap; refetching
            // on every window focus mid-run just adds noise.
            refetchOnWindowFocus: false,
            staleTime: 30_000,
            retry: 1,
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
