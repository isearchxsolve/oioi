import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

class ApiClient {
  private client: AxiosInstance
  private accessToken: string | null = null
  private refreshToken: string | null = null

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    })

    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        if (this.accessToken) {
          config.headers.Authorization = `Bearer ${this.accessToken}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
        
        if (error.response?.status === 401 && !originalRequest._retry && this.refreshToken) {
          originalRequest._retry = true
          
          try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
              refresh_token: this.refreshToken,
            })
            
            this.setTokens(response.data.access_token, response.data.refresh_token)
            originalRequest.headers.Authorization = `Bearer ${this.accessToken}`
            
            return this.client(originalRequest)
          } catch (refreshError) {
            this.clearTokens()
            window.location.href = '/login'
            return Promise.reject(refreshError)
          }
        }
        
        return Promise.reject(error)
      }
    )

    // Load tokens from localStorage on init
    if (typeof window !== 'undefined') {
      this.accessToken = localStorage.getItem('access_token')
      this.refreshToken = localStorage.getItem('refresh_token')
    }
  }

  setTokens(accessToken: string, refreshToken: string) {
    this.accessToken = accessToken
    this.refreshToken = refreshToken
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', accessToken)
      localStorage.setItem('refresh_token', refreshToken)
    }
  }

  clearTokens() {
    this.accessToken = null
    this.refreshToken = null
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    }
  }

  getAccessToken() {
    return this.accessToken
  }

  isAuthenticated() {
    return !!this.accessToken
  }

  // Auth endpoints
  async login(email: string, password: string) {
    const response = await this.client.post('/auth/login', { email, password })
    this.setTokens(response.data.access_token, response.data.refresh_token)
    return response.data
  }

  async register(email: string, password: string, fullName: string) {
    const response = await this.client.post('/auth/register', { email, password, full_name: fullName })
    this.setTokens(response.data.access_token, response.data.refresh_token)
    return response.data
  }

  async logout() {
    try {
      await this.client.post('/auth/logout')
    } finally {
      this.clearTokens()
    }
  }

  async getCurrentUser() {
    const response = await this.client.get('/auth/me')
    return response.data
  }

  async refreshAccessToken() {
    if (!this.refreshToken) throw new Error('No refresh token')
    const response = await this.client.post('/auth/refresh', { refresh_token: this.refreshToken })
    this.setTokens(response.data.access_token, response.data.refresh_token)
    return response.data
  }

  // NIM endpoints
  async listModels() {
    const response = await this.client.get('/nim/models')
    return response.data
  }

  async getModel(modelId: string) {
    const response = await this.client.get(`/nim/models/${modelId}`)
    return response.data
  }

  async getModelsByCategory(category: string) {
    const response = await this.client.get(`/nim/models/category/${category}`)
    return response.data
  }

  async chatCompletion(data: {
    model: string
    messages: Array<{ role: string; content: string }>
    temperature?: number
    max_tokens?: number
    top_p?: number
    stream?: boolean
  }) {
    const response = await this.client.post('/nim/chat/completions', data)
    return response.data
  }

  async chatCompletionStream(
    data: {
      model: string
      messages: Array<{ role: string; content: string }>
      temperature?: number
      max_tokens?: number
      top_p?: number
    },
    onChunk: (chunk: string) => void
  ) {
    const response = await this.client.post('/nim/chat/completions/stream', data, {
      responseType: 'stream',
    })
    
    const reader = response.data.getReader()
    const decoder = new TextDecoder()
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            const parsed = JSON.parse(data)
            if (parsed.choices?.[0]?.delta?.content) {
              onChunk(parsed.choices[0].delta.content)
            }
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  }

  async generateText(data: {
    model: string
    prompt: string
    max_tokens?: number
    temperature?: number
    top_p?: number
    stream?: boolean
  }) {
    const response = await this.client.post('/nim/generate/text', data)
    return response.data
  }

  async generateTextStream(
    data: {
      model: string
      prompt: string
      max_tokens?: number
      temperature?: number
      top_p?: number
    },
    onChunk: (chunk: string) => void
  ) {
    const response = await this.client.post('/nim/generate/text/stream', data, {
      responseType: 'stream',
    })
    
    const reader = response.data.getReader()
    const decoder = new TextDecoder()
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      const lines = chunk.split('\n')
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            const parsed = JSON.parse(data)
            if (parsed.choices?.[0]?.delta?.content) {
              onChunk(parsed.choices[0].delta.content)
            }
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  }

  async generateImage(data: {
    model: string
    prompt: string
    negative_prompt?: string
    width?: number
    height?: number
    num_inference_steps?: number
    guidance_scale?: number
    seed?: number
  }) {
    const response = await this.client.post('/nim/generate/image', data)
    return response.data
  }

  async generateVideo(data: {
    model: string
    prompt: string
    negative_prompt?: string
    width?: number
    height?: number
    num_frames?: number
    fps?: number
    guidance_scale?: number
    seed?: number
  }) {
    const response = await this.client.post('/nim/generate/video', data)
    return response.data
  }

  async getVideoStatus(taskId: string) {
    const response = await this.client.get(`/nim/generate/video/${taskId}`)
    return response.data
  }

  async generateAudio(data: {
    model: string
    text: string
    voice?: string
    speed?: number
  }) {
    const response = await this.client.post('/nim/generate/audio', data)
    return response.data
  }

  async healthCheck() {
    const response = await this.client.get('/nim/health')
    return response.data
  }

  // User endpoints
  async getUserProfile() {
    const response = await this.client.get('/users/me')
    return response.data
  }

  async updateUserProfile(data: { full_name?: string; avatar_url?: string }) {
    const response = await this.client.patch('/users/me', data)
    return response.data
  }

  async getUserUsage() {
    const response = await this.client.get('/users/me/usage')
    return response.data
  }

  async getUserHistory(page = 1, limit = 20) {
    const response = await this.client.get('/users/me/history', { params: { page, limit } })
    return response.data
  }

  // Script generation
  async generateScript(data: {
    topic: string
    style: string
    duration: number
    platform: string
    tone: string
    target_audience: string
    key_points?: string[]
    language?: string
  }) {
    const response = await this.client.post('/scripts/generate', data)
    return response.data
  }

  async getScripts(page = 1, limit = 20) {
    const response = await this.client.get('/scripts', { params: { page, limit } })
    return response.data
  }

  async getScript(id: string) {
    const response = await this.client.get(`/scripts/${id}`)
    return response.data
  }

  async updateScript(id: string, data: Partial<{
    topic: string
    style: string
    duration: number
    platform: string
    tone: string
    target_audience: string
    key_points: string[]
    language: string
    content: string
  }>) {
    const response = await this.client.patch(`/scripts/${id}`, data)
    return response.data
  }

  async deleteScript(id: string) {
    const response = await this.client.delete(`/scripts/${id}`)
    return response.data
  }

  // Video projects
  async createVideoProject(data: {
    script_id?: string
    title: string
    model: string
    prompt: string
    settings: Record<string, any>
  }) {
    const response = await this.client.post('/videos/projects', data)
    return response.data
  }

  async getVideoProjects(page = 1, limit = 20) {
    const response = await this.client.get('/videos/projects', { params: { page, limit } })
    return response.data
  }

  async getVideoProject(id: string) {
    const response = await this.client.get(`/videos/projects/${id}`)
    return response.data
  }

  async deleteVideoProject(id: string) {
    const response = await this.client.delete(`/videos/projects/${id}`)
    return response.data
  }

  // Health check
  async healthCheck() {
    const response = await this.client.get('/health')
    return response.data
  }
}

export const api = new ApiClient()
export default api