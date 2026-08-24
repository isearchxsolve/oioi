import { render, screen, fireEvent } from '@testing-library/react'
import { ProjectDetailPage } from '@/app/projects/[id]/page'

// Mock the API
jest.mock('@/lib/api', () => ({
  api: {
    getProject: jest.fn().mockResolvedValue({
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
    }),
    updateScene: jest.fn().mockResolvedValue({}),
    reorderScenes: jest.fn().mockResolvedValue([]),
    listCharacters: jest.fn().mockResolvedValue([]),
    createCharacter: jest.fn().mockResolvedValue({ id: 'char-1', name: 'Hero', description: 'A hero' }),
    uploadCharacterImage: jest.fn().mockResolvedValue({ reference_image_path: 'test.png' }),
    triggerScript: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerVisuals: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerAudio: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerClips: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerStitch: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerFullPipeline: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    getTask: jest.fn().mockResolvedValue({ id: 'task-1', status: 'completed', progress: 100, message: 'Done', result: { output_path: 'output.mp4' } }),
    getConstants: jest.fn().mockResolvedValue({
      aspects: { '16:9': { width: 1920, height: 1080 } },
      voices: { aria: 'en-US-AriaNeural' },
      music_moods: ['ambient'],
      visual_styles: ['cinematic'],
      providers: { visual: 'cosmos', voice: 'edge', music: 'ffmpeg', script: 'nim' },
    }),
    startDirectorRun: jest.fn().mockResolvedValue({ run_id: 'run-1', status: 'planning' }),
    getDirectorRun: jest.fn().mockResolvedValue({ run_id: 'run-1', status: 'completed' }),
    getDirectorReport: jest.fn().mockResolvedValue({}),
    cancelDirectorRun: jest.fn().mockResolvedValue({}),
    listDirectorRuns: jest.fn().mockResolvedValue([]),
    downloadEDL: jest.fn(),
    downloadFCPXML: jest.fn(),
    downloadPremiereXML: jest.fn(),
    downloadDaVinciDRT: jest.fn(),
  },
}))

// Mock useSSE
jest.mock('@/lib/useSSE', () => ({
  useSSE: jest.fn(() => ({ connected: true })),
}))

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: 'test-1' }),
  useRouter: () => ({ push: jest.fn() }),
}))

describe('ProjectDetailPage', () => {
  it('renders project name and description', async () => {
    render(<ProjectDetailPage />)
    expect(screen.getByText('Test Project')).toBeInTheDocument()
    expect(screen.getByText('A test film')).toBeInTheDocument()
  })

  it('shows pipeline panel', async () => {
    render(<ProjectDetailPage />)
    expect(screen.getByText('Pipeline')).toBeInTheDocument()
  })
})