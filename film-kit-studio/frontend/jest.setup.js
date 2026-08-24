# ─────────────────────────────────────────────────────────────────
# Frontend Test Configuration
# ─────────────────────────────────────────────────────────────────
import '@testing-library/jest-dom'

# Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
    }
  },
  usePathname() {
    return '/projects/123'
  },
  useSearchParams() {
    return new URLSearchParams()
  }
}))

# Mock API client
jest.mock('@/lib/api', () => ({
  api: {
    healthCheck: jest.fn().mockResolvedValue({ status: 'ok', ffmpeg_available: true }),
    getConstants: jest.fn().mockResolvedValue({
      aspects: { '16:9': { width: 1920, height: 1080 } },
      voices: { aria: 'en-US-AriaNeural' },
      music_moods: ['ambient', 'tense', 'bright'],
      visual_styles: ['cinematic'],
      providers: { visual: 'cosmos', voice: 'edge', music: 'ffmpeg', script: 'nim' },
    }),
    getProject: jest.fn().mockResolvedValue({
      id: 'test-project',
      name: 'Test Project',
      idea: 'Test idea',
      style: 'cinematic',
      aspect: '16:9',
      voice: 'aria',
      seed: 12345,
      music: false,
      music_mood: 'ambient',
      num_scenes: 3,
      transition_mode: 'cut',
      status: 'draft',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      scenes: [],
      characters: [],
    }),
    listProjects: jest.fn().mockResolvedValue([]),
    createProject: jest.fn().mockResolvedValue({ id: 'new-project' }),
    updateProject: jest.fn().mockResolvedValue({}),
    deleteProject: jest.fn().mockResolvedValue({}),
    updateScene: jest.fn().mockResolvedValue({}),
    reorderScenes: jest.fn().mockResolvedValue([]),
    listCharacters: jest.fn().mockResolvedValue([]),
    createCharacter: jest.fn().mockResolvedValue({ id: 'char-1' }),
    getCharacter: jest.fn().mockResolvedValue({ id: 'char-1', name: 'Hero', description: 'A hero' }),
    updateCharacter: jest.fn().mockResolvedValue({}),
    deleteCharacter: jest.fn().mockResolvedValue({}),
    uploadCharacterImage: jest.fn().mockResolvedValue({ reference_image_path: 'test.png' }),
    triggerScript: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerVisuals: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerAudio: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerClips: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerStitch: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    triggerFullPipeline: jest.fn().mockResolvedValue({ id: 'task-1', status: 'pending' }),
    getTask: jest.fn().mockResolvedValue({ id: 'task-1', status: 'completed', progress: 100, message: 'Done' }),
    imageUrl: jest.fn().mockReturnValue('/api/media/image/test/test.png'),
    clipUrl: jest.fn().mockReturnValue('/api/media/clip/test/test.mp4'),
    videoUrl: jest.fn().mockReturnValue('/api/media/video/test/test.mp4'),
    srtUrl: jest.fn().mockReturnValue('/api/media/srt/test/test.srt'),
    startDirectorRun: jest.fn().mockResolvedValue({ run_id: 'run-1', status: 'planning' }),
    getDirectorRun: jest.fn().mockResolvedValue({ run_id: 'run-1', status: 'completed' }),
    getDirectorReport: jest.fn().mockResolvedValue({ run_id: 'run-1', final_score: 0.9 }),
    cancelDirectorRun: jest.fn().mockResolvedValue({}),
    listDirectorRuns: jest.fn().mockResolvedValue([]),
    downloadEDL: jest.fn().mockResolvedValue({}),
    downloadFCPXML: jest.fn().mockResolvedValue({}),
    downloadPremiereXML: jest.fn().mockResolvedValue({}),
    downloadDaVinciDRT: jest.fn().mockResolvedValue({}),
  }
}))

# Mock fetch globally
global.fetch = jest.fn()

# Suppress console errors in tests
const originalError = console.error
beforeAll(() => {
  console.error = (...args) => {
    if (args[0]?.includes?.('Warning: ReactDOM.render is no longer supported')) return
    originalError.call(console, ...args)
  }
})
afterAll(() => {
  console.error = originalError
})