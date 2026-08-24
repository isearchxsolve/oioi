import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DirectorPanel } from '@/components/DirectorPanel'
import { api } from '@/lib/api'

// Mock the API
jest.mock('@/lib/api', () => ({
  api: {
    startDirectorRun: jest.fn().mockResolvedValue({ run_id: 'run-123', status: 'planning', message: 'Started' }),
    getDirectorRun: jest.fn().mockResolvedValue({ run_id: 'run-123', status: 'completed', current_iteration: 1, max_iterations: 3, latest_score: 0.9, latest_passed: true }),
    getDirectorReport: jest.fn().mockResolvedValue({ run_id: 'run-123', final_score: 0.9, passed: true, iterations_run: 1, total_generations: 3, total_re_rolls: 1, critique_history: [] }),
    cancelDirectorRun: jest.fn().mockResolvedValue({ message: 'Cancelled', run_id: 'run-123' }),
    listDirectorRuns: jest.fn().mockResolvedValue([]),
    downloadEDL: jest.fn().mockReturnValue('/api/director/run-123/edl'),
    downloadFCPXML: jest.fn().mockReturnValue('/api/director/run-123/fcpxml'),
    downloadPremiereXML: jest.fn().mockReturnValue('/api/director/run-123/premiere'),
    downloadDaVinciDRT: jest.fn().mockReturnValue('/api/director/run-123/davinci'),
    directorEventSource: jest.fn().mockReturnValue('/api/director/run-123/events'),
  },
}))

// Mock EventSource
global.EventSource = jest.fn().mockImplementation(() => ({
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  close: jest.fn(),
  onerror: null,
  onmessage: null,
}))

const mockProjectId = 'project-123'

describe('DirectorPanel', () => {
  it('renders config tab by default', () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    expect(screen.getByText('Configure')).toBeInTheDocument()
    expect(screen.getByText('Film Idea / Logline')).toBeInTheDocument()
    expect(screen.getByText('Genre')).toBeInTheDocument()
    expect(screen.getByText('Target Duration (seconds)')).toBeInTheDocument()
  })

  it('shows genre dropdown', () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    expect(screen.getByRole('combobox', { name: /genre/i })).toBeInTheDocument()
  }

  it('has start button', () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    expect(screen.getByRole('button', { name: /start autonomous run/i })).toBeInTheDocument()
  })

  it('disables start button when idea is empty', () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    const startButton = screen.getByRole('button', { name: /start autonomous run/i })
    expect(startButton).toBeDisabled()
  })

  it('enables start button when idea is entered', () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    const textarea = screen.getByLabelText(/film idea/i)
    fireEvent.change(textarea, { target: { value: 'A test film idea' } })
    expect(screen.getByRole('button', { name: /start autonomous run/i })).not.toBeDisabled()
  })

  it('switches to monitor tab after starting', async () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    const textarea = screen.getByLabelText(/film idea/i)
    fireEvent.change(textarea, { target: { value: 'A test film idea' } })
    fireEvent.click(screen.getByRole('button', { name: /start autonomous run/i }))
    await waitFor(() => {
      expect(screen.getByText('Monitor')).toBeInTheDocument()
    })
  })

  it('shows cancel button when running', async () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    const textarea = screen.getByLabelText(/film idea/i)
    fireEvent.change(textarea, { target: { value: 'A test film idea' } })
    fireEvent.click(screen.getByRole('button', { name: /start autonomous run/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })
  })

  it('switches to report tab', async () => {
    render(<DirectorPanel projectId={mockProjectId} />)
    const textarea = screen.getByLabelText(/film idea/i)
    fireEvent.change(textarea, { target: { value: 'A test film idea' } })
    fireEvent.click(screen.getByRole('button', { name: /start autonomous run/i }))
    await waitFor(() => {
      expect(screen.getByText('Report')).toBeInTheDocument()
    })
  })
})