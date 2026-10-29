import '@testing-library/jest-dom';

// Jest environment: Next.js App Router pages use useRouter() from next/navigation.
// Provide a minimal router context so unit tests can render pages that read it.
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    refresh: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    prefetch: jest.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));