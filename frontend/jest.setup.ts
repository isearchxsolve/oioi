import '@testing-library/jest-dom'

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => jest.fn(),
  useLocation: () => ({ pathname: '/', search: '', hash: '', state: null }),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), jest.fn()],
}))

// Mock API client
jest.mock('@/lib/api', () => ({
  api: {
    isAuthenticated: jest.fn().mockReturnValue(true),
    getAccessToken: jest.fn().mockReturnValue('mock-token'),
    generateScript: jest.fn().mockResolvedValue({
      id: 'script-123',
      topic: 'Test Topic',
      style: 'educational',
      duration: 60,
      platform: 'youtube',
      tone: 'professional',
      target_audience: 'Test Audience',
      key_points: ['Point 1', 'Point 2'],
      language: 'en',
      content: 'This is a test script content.',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    getScripts: jest.fn().mockResolvedValue({
      data: [
        {
          id: 'script-1',
          topic: 'Test Script 1',
          style: 'educational',
          duration: 60,
          platform: 'youtube',
          created_at: new Date().toISOString(),
        },
        {
          id: 'script-2',
          topic: 'Test Script 2',
          style: 'tutorial',
          duration: 120,
          platform: 'youtube',
          created_at: new Date().toISOString(),
        },
      ],
    }),
    getScript: jest.fn().mockResolvedValue({
      id: 'script-123',
      topic: 'Test Topic',
      style: 'educational',
      duration: 60,
      platform: 'youtube',
      tone: 'professional',
      target_audience: 'Test Audience',
      key_points: ['Point 1', 'Point 2'],
      language: 'en',
      content: 'This is a test script content.',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }),
    deleteScript: jest.fn().mockResolvedValue({}),
    listModels: jest.fn().mockResolvedValue({
      data: [
        { id: 'model-1', name: 'Model 1', type: 'text' },
        { id: 'model-2', name: 'Model 2', type: 'image' },
      ],
    }),
    healthCheck: jest.fn().mockResolvedValue({ status: 'ok' }),
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

// Mock navigator.clipboard
Object.defineProperty(navigator, 'clipboard', {
  writable: true,
  value: {
    writeText: jest.fn().mockResolvedValue(undefined),
    readText: jest.fn().mockResolvedValue(''),
  },
})

// Mock URL.createObjectURL
global.URL.createObjectURL = jest.fn().mockReturnValue('blob:mock-url')
global.URL.revokeObjectURL = jest.fn()

// Suppress console.error for known React warnings
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