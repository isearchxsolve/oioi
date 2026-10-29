import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Home from '../app/page';

// The page boots with an auth bootstrap: it reads a stored access token, calls
// /api/v1/auth/me with it, and only then renders the studio. Fixture: a stored
// token + mocked bootstrap/registry endpoints so the REAL page renders.
const TOKEN = 'test-token';

beforeEach(() => {
  window.localStorage.setItem('oioi_access_token', TOKEN);
  (global as any).fetch = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    // plain objects: jsdom may not provide global Response in this setup
    const ok = (body: any) => ({ ok: true, status: 200, json: async () => body });
    if (url.includes('/api/v1/auth/me')) {
      return ok({ id: 1, email: 'test@example.com', username: 'test' });
    }
    if (url.includes('/api/v1/auth/bootstrap-status')) {
      return ok({ owner_configured: true });
    }
    if (url.includes('/registry') || url.includes('/models') || url.includes('/styles')) {
      return ok({ models: [], styles: [], agents: [] });
    }
    return ok({});
  });
});

afterEach(() => {
  window.localStorage.clear();
  jest.restoreAllMocks();
});

describe('OiiOii.ai Canvas & Studio Frontend', () => {
  it('renders the studio title and 7-agent pipeline banner once authenticated', async () => {
    render(<Home />);
    await waitFor(() => expect(screen.getByText(/Autonomous 7-Agent AI Animation Engine/i)).toBeInTheDocument());
    expect(screen.getByText(/OiiOii.ai Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Free-Tier Multi-Provider \(NVIDIA-Free\)/i)).toBeInTheDocument();
  });

  it('switches between Agent Team, Models, and Styles tabs', async () => {
    render(<Home />);
    await waitFor(() => expect(screen.getByRole('button', { name: /Agent Team/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Agent Team/i }));
    expect(screen.getByText(/The 7-Agent Animation Team/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Scriptwriter/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Director/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /25\+ Free Models/i }));
    expect(screen.getByText(/Model Registry/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /150\+ Styles/i }));
    expect(screen.getByText(/Cinematic Visual Styles/i)).toBeInTheDocument();
  });

  it('starts with empty storyboard panels and adds a panel on demand', async () => {
    render(<Home />);
    await waitFor(() => expect(screen.getByRole('button', { name: /Add Storyboard Panel/i })).toBeInTheDocument());
    const addBtn = screen.getByRole('button', { name: /Add Storyboard Panel/i });
    fireEvent.click(addBtn);
    await waitFor(() => expect(screen.getByText(/Scene 1: New Sequence/i)).toBeInTheDocument());
  });
});