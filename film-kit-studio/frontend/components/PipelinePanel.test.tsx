import { render, screen, fireEvent } from '@testing-library/react'
import { PipelinePanel } from '@/components/PipelinePanel'

// Mock the API
jest.mock('@/lib/api', () => ({
  api: {
    triggerScript: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending', progress: 0, message: 'Starting...' }),
    triggerVisuals: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerAudio: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerClips: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerStitch: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerFullPipeline: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    getConstants: jest.fn().mockResolvedValue({
      aspects: { '16:9': { width: 1920, height: 1080 } },
      voices: { aria: 'en-US-AriaNeural' },
      music_moods: ['ambient', 'tense', 'bright'],
      visual_styles: ['cinematic'],
      providers: { visual: 'cosmos', voice: 'edge', music: 'ffmpeg', script: 'nim' },
    }),
    getTask: jest.fn().mockResolvedValue({ id: 'task-1', status: 'completed', progress: 100, message: 'Done' }),
  },
}))

jest.mock('@/lib/useSSE', () => ({
  useSSE: jest.fn(() => ({ connected: true })),
}))

const mockProject = {
  id: 'test-1',
  name: 'Test Project',
  idea: 'A test film',
  style: 'cinematic',
  aspect: '16:9',
  voice: 'aria',
  seed: 12345,
  music: false,
  music_mood: 'ambient',
  num_scenes: 6,
  transition_mode: 'cut',
  status: 'draft',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  scenes: [],
  characters: [],
}

describe('PipelinePanel', () => {
  it('renders pipeline panel with project info', () => {
    render(<PipelinePanel project={mockProject} onTrigger={jest.fn()} isBusy={false} />)
    expect(screen.getByText('Pipeline')).toBeInTheDocument()
    expect(screen.getByText('Test Project')).toBeInTheDocument()
  })

  it('shows pipeline steps', () => {
    render(<PipelinePanel project={mockProject} onTrigger={jest.fn()} isBusy={false} />)
    expect(screen.getByText('Generate Script')).toBeInTheDocument()
    expect(screen.getByText('Generate Visuals')).toBeInTheDocument()
    expect(screen.getByText('Generate Audio')).toBeInTheDocument()
    expect(screen.getByText('Render Clips')).toBeInTheDocument()
    expect(screen.getByText('Stitch Film')).toBeInTheDocument()
  })

  it('shows trigger buttons with correct labels', () => {
    render(<PipelinePanel project={mockProject} onTrigger={jest.fn()} isBusy={false} />)
    // There are 5 step buttons with "Run" and 1 full pipeline button
    const runButtons = screen.getAllByRole('button', { name: /run/i })
    expect(runButtons.length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /generate full film/i })).toBeInTheDocument()
  })

  it('disables buttons when busy', () => {
    render(<PipelinePanel project={mockProject} onTrigger={jest.fn()} isBusy={true} />)
    const runButtons = screen.getAllByRole('button', { name: /run/i })
    const fullPipelineButton = screen.getByRole('button', { name: /generate full film/i })
    runButtons.forEach(btn => expect(btn).toBeDisabled())
    expect(fullPipelineButton).toBeDisabled()
  })
})