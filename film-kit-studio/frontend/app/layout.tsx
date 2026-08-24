import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Film Kit Studio — AI Filmmaking',
  description: 'Browser-based AI filmmaking platform — from idea to finished film.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
