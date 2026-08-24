import '@testing-library/jest-dom'

// Mock Next.js router
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

// Mock API client
jest.mock('@/lib/api', () => ({
  api: {
    healthCheck: jest.fn().mockResolvedValue({ status: 'ok', ffmpeg_available: true }),
    getConstants: jest.fn().mockResolvedValue({
      aspects: { '16:9': { width: 1920, height: 1080 } },
      voices: { aria: 'en-US-AriaNeural' },
      music_moods: ['ambient', 'tense', 'bright'],
      visual_styles: ['cinematic'],
      providers: {
        visual: 'cosmos',
        voice: 'edge',
        music: 'ffmpeg',
        script: 'nim',
      },
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
    imageUrl: jest.fn().mockReturnValue('http://localhost:8000/api/media/image/test/image.png'),
    clipUrl: jest.fn().mockReturnValue('http://localhost:8000/api/media/clip/test/clip.mp4'),
    videoUrl: jest.fn().mockReturnValue('http://localhost:8000/api/media/video/test/video.mp4'),
    srtUrl: jest.fn().mockReturnValue('http://localhost:8000/api/media/srt/test.srt'),
  },
}))

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

// Mock ResizeObserver
global.ResizeObserver = jest.fn().mockImplementation(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}))

// Suppress console.error for known warnings in tests
const originalError = console.error
beforeAll(() => {
  console.error = (...args) => {
    if (
      typeof args[0] === 'string' &&
      args[0].includes('Warning: ReactDOM.render is no longer supported')
    ) {
      return
    }
    originalError.call(console, ...args)
  }
})
afterAll(() => {
  console.error = originalError
})