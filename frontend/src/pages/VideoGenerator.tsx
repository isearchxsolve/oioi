import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'
import { Label } from '@/components/ui/Label'
import { api } from '@/lib/api'
import toast from 'react-hot-toast'
import {
  Video,
  Loader2,
  Copy,
  Download,
  Sparkles,
  ArrowRight,
  Check,
  Play,
  Settings,
  Image,
  Clock,
  Layers,
  AlertCircle,
  CheckCircle,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

const videoModels = [
  { id: 'nvidia/cosmos-reason2-8b', name: 'NVIDIA Cosmos Reason 2 8B', description: 'Video reasoning and generation', maxDuration: 10, category: 'Video' },
  { id: 'nvidia/nemotron-3-ultra', name: 'Nemotron 3 Ultra', description: 'High-quality LLM for prompt engineering', maxDuration: 30, category: 'LLM' },
  { id: 'meta/llama-3.1-405b-instruct', name: 'Llama 3.1 405B', description: 'Large language model', maxDuration: 30, category: 'LLM' },
  { id: 'mistralai/mixtral-8x22b-instruct', name: 'Mixtral 8x22B', description: 'Mixture of experts model', maxDuration: 30, category: 'LLM' },
  { id: 'google/gemma-2-27b-it', name: 'Gemma 2 27B', description: 'Google\'s open model', maxDuration: 30, category: 'LLM' },
]

const resolutions = [
  { value: '576x1024', label: '576x1024 (Portrait)' },
  { value: '1024x576', label: '1024x576 (Landscape)' },
  { value: '1024x1024', label: '1024x1024 (Square)' },
  { value: '768x768', label: '768x768 (Square HD)' },
]

const aspectRatios = [
  { value: '16:9', label: '16:9 (Landscape)' },
  { value: '9:16', label: '9:16 (Portrait)' },
  { value: '1:1', label: '1:1 (Square)' },
  { value: '4:3', label: '4:3 (Standard)' },
  { value: '21:9', label: '21:9 (Cinematic)' },
]

export function VideoGenerator() {
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [model, setModel] = useState('nvidia/cosmos-reason2-8b')
  const [duration, setDuration] = useState(5)
  const [resolution, setResolution] = useState('1024x576')
  const [aspectRatio, setAspectRatio] = useState('16:9')
  const [fps, setFps] = useState(24)
  const [seed, setSeed] = useState<number | undefined>(undefined)
  const [style, setStyle] = useState('')
  const [guidanceScale, setGuidanceScale] = useState(7.5)
  const [numInferenceSteps, setNumInferenceSteps] = useState(25)
  const [generatedVideo, setGeneratedVideo] = useState<string | null>(null)
  const [videoId, setVideoId] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'generating' | 'completed' | 'failed'>('idle')
  const [progress, setProgress] = useState(0)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [enhancedPrompt, setEnhancedPrompt] = useState<string | null>(null)
  
  const selectedModel = videoModels.find(m => m.id === model)
  const maxDuration = selectedModel?.maxDuration || 10
  
  const { data: videos } = useQuery({
    queryKey: ['videos', 1, 10],
    queryFn: () => api.getVideoProjects(1, 10),
  })
  
  const generateMutation = useMutation({
    mutationFn: async (data: {
      model: string
      prompt: string
      negative_prompt?: string
      width: number
      height: number
      duration: number
      fps: number
      guidance_scale: number
      num_inference_steps: number
      seed?: number
    }) => {
      const response = await api.generateVideo(data)
      return response
    },
    onMutate: () => {
      setStatus('generating')
      setProgress(0)
      setGeneratedVideo(null)
      setVideoId(null)
      setTaskId(null)
      setEnhancedPrompt(null)
      // Simulate progress
      const interval = setInterval(() => {
        setProgress(prev => Math.min(prev + 5, 90))
      }, 1500)
      return () => clearInterval(interval)
    },
    onSuccess: (data) => {
      setTaskId(data.request_id)
      setVideoId(data.request_id)
      setEnhancedPrompt(data.enhanced_prompt || null)
      // Poll for completion
      pollVideoStatus(data.request_id)
    },
    onError: (error: any) => {
      setStatus('failed')
      toast.error(error.response?.data?.detail || 'Failed to generate video')
    },
  })
  
  const pollVideoStatus = async (id: string) => {
    try {
      const response = await api.getVideoStatus(id)
      if (response.status === 'completed') {
        setGeneratedVideo(response.video_url)
        setStatus('completed')
        setProgress(100)
        toast.success('Video prompt generated successfully!')
        queryClient.invalidateQueries({ queryKey: ['videos'] })
      } else if (response.status === 'failed') {
        setStatus('failed')
        toast.error('Video generation failed: ' + (response.error || 'Unknown error'))
      } else {
        // Still processing
        setProgress(prev => Math.min(prev + 10, 95))
        setTimeout(() => pollVideoStatus(id), 3000)
      }
    } catch (error) {
      console.error('Polling error:', error)
      setTimeout(() => pollVideoStatus(id), 5000)
    }
  }
  
  const handleGenerate = () => {
    if (!prompt.trim()) {
      toast.error('Please enter a prompt')
      return
    }
    
    const [width, height] = resolution.split('x').map(Number)
    
    generateMutation.mutate({
      model,
      prompt,
      negative_prompt: negativePrompt || undefined,
      width,
      height,
      duration,
      fps,
      guidance_scale: guidanceScale,
      num_inference_steps: numInferenceSteps,
      seed,
    })
  }
  
  const handleCopy = () => {
    if (generatedVideo) {
      navigator.clipboard.writeText(generatedVideo)
      toast.success('Video URL copied to clipboard')
    }
  }
  
  const handleDownload = async () => {
    if (videoId) {
      try {
        const blob = await api.downloadVideo(videoId)
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `video-${videoId}.mp4`
        a.click()
        window.URL.revokeObjectURL(url)
      } catch (error) {
        toast.error('Failed to download video')
      }
    }
  }
  
  const handleNewVideo = () => {
    setGeneratedVideo(null)
    setVideoId(null)
    setTaskId(null)
    setEnhancedPrompt(null)
    setStatus('idle')
    setProgress(0)
  }
  
  const handleDeleteVideo = async (id: string) => {
    if (confirm('Are you sure you want to delete this video?')) {
      try {
        await api.deleteVideoProject(id)
        toast.success('Video deleted')
        queryClient.invalidateQueries({ queryKey: ['videos'] })
      } catch (error) {
        toast.error('Failed to delete video')
      }
    }
  }
  
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-red-500" />
      case 'generating':
      case 'processing':
        return <Loader2 className="h-4 w-4 text-yellow-500 animate-spin" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }
  
  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
        return 'Completed'
      case 'failed':
        return 'Failed'
      case 'generating':
      case 'processing':
        return 'Processing'
      default:
        return 'Pending'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-900 dark:text-white flex items-center gap-3">
          <Video className="h-8 w-8 text-primary-600" />
          Video Generator
        </h1>
        <p className="text-dark-500 dark:text-dark-400 mt-1">
          Generate enhanced video prompts using NVIDIA NIM models (Cosmos, Nemotron, Llama, etc.)
        </p>
      </div>
      
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Input Form */}
        <div className="lg:col-span-1 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Generation Settings
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <Label htmlFor="model">Model</Label>
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {videoModels.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 text-xs bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded">
                              {m.category}
                            </span>
                            <p className="font-medium">{m.name}</p>
                          </div>
                          <p className="text-xs text-dark-500 mt-0.5">{m.description}</p>
                          <p className="text-xs text-dark-400 mt-0.5">Max duration: {m.maxDuration}s</p>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <Label htmlFor="prompt">Prompt</Label>
                <Textarea
                  id="prompt"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Describe the video you want to generate..."
                  rows={4}
                  helperText="Be as descriptive as possible for best results"
                />
              </div>
              
              <div>
                <Label htmlFor="negativePrompt">Negative Prompt (Optional)</Label>
                <Textarea
                  id="negativePrompt"
                  value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  placeholder="What to avoid in the video..."
                  rows={2}
                />
              </div>
              
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="duration">Duration (seconds)</Label>
                  <Input
                    id="duration"
                    type="number"
                    value={duration}
                    onChange={(e) => setDuration(Math.min(parseInt(e.target.value) || 1, maxDuration))}
                    min={1}
                    max={maxDuration}
                    helperText={`Max ${maxDuration}s for ${selectedModel?.name}`}
                  />
                </div>
                <div>
                  <Label htmlFor="fps">FPS</Label>
                  <Select value={fps.toString()} onValueChange={(v) => setFps(parseInt(v))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[24, 30, 60].map((f) => (
                        <SelectItem key={f} value={f.toString()}>{f} FPS</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="resolution">Resolution</Label>
                  <Select value={resolution} onValueChange={setResolution}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {resolutions.map((r) => (
                        <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="aspectRatio">Aspect Ratio</Label>
                  <Select value={aspectRatio} onValueChange={setAspectRatio}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {aspectRatios.map((a) => (
                        <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="guidanceScale">Guidance Scale</Label>
                  <Input
                    id="guidanceScale"
                    type="range"
                    min={1}
                    max={20}
                    step={0.5}
                    value={guidanceScale}
                    onChange={(e) => setGuidanceScale(parseFloat(e.target.value))}
                    className="w-full"
                  />
                  <p className="text-sm text-dark-500 text-center">{guidanceScale}</p>
                </div>
                <div>
                  <Label htmlFor="numInferenceSteps">Inference Steps</Label>
                  <Input
                    id="numInferenceSteps"
                    type="range"
                    min={10}
                    max={50}
                    step={1}
                    value={numInferenceSteps}
                    onChange={(e) => setNumInferenceSteps(parseInt(e.target.value))}
                    className="w-full"
                  />
                  <p className="text-sm text-dark-500 text-center">{numInferenceSteps}</p>
                </div>
              </div>
              
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="seed">Seed (Optional)</Label>
                  <Input
                    id="seed"
                    type="number"
                    value={seed || ''}
                    onChange={(e) => setSeed(e.target.value ? parseInt(e.target.value) : undefined)}
                    placeholder="Random"
                  />
                </div>
                <div>
                  <Label htmlFor="style">Style (Optional)</Label>
                  <Input
                    id="style"
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                    placeholder="Cinematic, anime, realistic..."
                  />
                </div>
              </div>
              
              <Button
                onClick={handleGenerate}
                disabled={status === 'generating' || !prompt.trim()}
                className="w-full"
                size="lg"
                loading={status === 'generating'}
              >
                {status === 'generating' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating... {progress}%
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Generate Video Prompt
                  </>
                )}
              </Button>
            </CardContent          </Card>
          
          {/* Model Info */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5" />
                Model Information
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {selectedModel && (
                <>
                  <div className="flex justify-between">
                    <span className="text-dark-500">Model</span>
                    <span className="font-medium">{selectedModel.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-dark-500">Category</span>
                    <span className="font-medium">{selectedModel.category}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-dark-500">Max Duration</span>
                    <span className="font-medium">{selectedModel.maxDuration}s</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-dark-500">Description</span>
                    <span className="font-medium text-dark-700 dark:text-dark-300">{selectedModel.description}</span>
                  </div>
                </>
              )}
            </CardContent          </Card>
        </div>
        
        {/* Output & History */}
        <div className="lg:col-span-2 space-y-6">
          {/* Current Generation */}
          {status === 'idle' && (
            <Card>
              <CardContent className="py-16 px-6 text-center">
                <Video className="h-16 w-16 text-dark-300 dark:text-dark-600 mx-auto mb-4" />
                <h3 className="text-xl font-semibold text-dark-900 dark:text-white mb-2">
                  Ready to Generate
                </h3>
                <p className="text-dark-500 dark:text-dark-400 mb-6 max-w-md mx-auto">
                  Configure your settings on the left and click "Generate Video Prompt" to create an enhanced prompt using NVIDIA NIM models.
                </p>
                <div className="flex items-center justify-center gap-6 text-sm text-dark-500">
                  <div className="flex items-center gap-1">
                    <Sparkles className="h-4 w-4" />
                    <span>NVIDIA NIM Models</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Settings className="h-4 w-4" />
                    <span>Customizable Settings</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="h-4 w-4" />
                    <span>Fast Generation</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          
          {status === 'generating' && (
            <Card>
              <CardContent className="py-16 px-6 text-center">
                <div className="flex flex-col items-center gap-6">
                  <div className="relative">
                    <div className="h-20 w-20 border-4 border-primary-500/20 rounded-full" />
                    <div className="absolute inset-0 border-4 border-primary-500 rounded-full animate-spin border-t-transparent" />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-dark-900 dark:text-white">
                      Generating Enhanced Prompt...
                    </h3>
                    <p className="text-dark-500 dark:text-dark-400 mt-1">
                      Using {selectedModel?.name} to create a detailed video prompt
                    </p>
                    <div className="mt-6 w-64 mx-auto">
                      <div className="h-2 bg-dark-200 dark:bg-dark-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary-500 rounded-full transition-all duration-300"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                      <p className="text-sm text-dark-500 mt-2">{progress}% complete</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          
          {status === 'completed' && (
            <>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="flex items-center gap-2">
                    <Video className="h-5 w-5" />
                    Enhanced Video Prompt
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" onClick={handleCopy} size="sm">
                      <Copy className="h-4 w-4 mr-2" />
                      Copy Prompt
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="relative aspect-video rounded-lg bg-dark-100 dark:bg-dark-800 overflow-hidden p-6">
                    {enhancedPrompt ? (
                      <pre className="whitespace-pre-wrap text-dark-900 dark:text-white font-mono text-sm">
                        {enhancedPrompt}
                      </pre>
                    ) : (
                      <div className="flex items-center justify-center h-full text-dark-500">
                        <Video className="h-12 w-12" />
                        <span className="ml-3">Prompt generated successfully</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-4 flex items-center gap-4 text-sm text-dark-500 flex-wrap">
                    <span>Model: {selectedModel?.name}</span>
                    <span>Duration: {duration}s</span>
                    <span>Resolution: {resolution}</span>
                    <span>FPS: {fps}</span>
                    <span>Guidance: {guidanceScale}</span>
                    <span>Steps: {numInferenceSteps}</span>
                  </div>
                </CardContent              </Card>
              
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ArrowRight className="h-5 w-5" />
                    Next Steps
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex gap-4 flex-wrap">
                  <Button onClick={handleNewVideo} size="lg">
                    <RotateCcw className="h-4 w-4 mr-2" />
                    Generate Another
                  </Button>
                  <Button variant="outline" onClick={handleNewVideo} size="lg">
                    <Video className="h-4 w-4 mr-2" />
                    New Video
                  </Button>
                  <p className="text-sm text-dark-500 self-center">
                    Use this enhanced prompt with video generation services like Runway, Pika, or Sora
                  </p>
                </CardContent>
              </Card>
            </>
          )}
          
          {status === 'failed' && (
            <Card className="border-red-200 dark:border-red-900">
              <CardContent className="py-12 px-6 text-center">
                <div className="flex flex-col items-center gap-4">
                  <div className="h-16 w-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <AlertCircle className="h-8 w-8 text-red-500" />
                  </div>
                  <h3 className="text-xl font-semibold text-dark-900 dark:text-white">
                    Generation Failed
                  </h3>
                  <p className="text-dark-500 dark:text-dark-400 max-w-md">
                    Something went wrong while generating your video prompt. Please try again or adjust your settings.
                  </p>
                  <Button onClick={handleNewVideo} variant="outline">
                    Try Again
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
          
          {/* Video History */}
          {videos && videos.items && videos.items.length > 0 && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <Video className="h-5 w-5" />
                  Recent Videos
                </CardTitle>
                <span className="text-sm text-dark-500">{videos.total} total</span>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {videos.items.slice(0, 5).map((video: any) => (
                    <div
                      key={video.id}
                      className="flex items-center gap-4 p-3 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50"
                    >
                      <div className="relative h-16 w-16 rounded-lg bg-dark-100 dark:bg-dark-800 overflow-hidden flex-shrink-0">
                        {video.thumbnail_url ? (
                          <img
                            src={video.thumbnail_url}
                            alt={video.title}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Video className="h-8 w-8 text-dark-400 mx-auto my-auto" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-dark-900 dark:text-white truncate">
                          {video.title || video.prompt?.slice(0, 50) + '...'}
                        </p>
                        <p className="text-sm text-dark-500 dark:text-dark-400 truncate">
                          {video.prompt?.slice(0, 100)}...
                        </p>
                        <div className="flex items-center gap-3 mt-1 text-xs text-dark-400">
                          <span>{video.model}</span>
                          <span>{video.duration}s</span>
                          <span>{video.resolution}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {getStatusIcon(video.status)}
                        <span className="text-sm font-medium text-dark-700 dark:text-dark-300">
                          {getStatusLabel(video.status)}
                        </span>
                        {video.status === 'completed' && video.video_url && (
                          <a
                            href={video.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 text-dark-400 hover:text-primary-600"
                            title="Open video"
                          >
                            <Play className="h-4 w-4" />
                          </a>
                        )}
                        <button
                          onClick={() => handleDeleteVideo(video.id)}
                          className="p-2 text-dark-400 hover:text-red-500"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                {videos.total > 5 && (
                  <div className="text-center mt-4">
                    <a href="/videos" className="text-primary-600 hover:underline text-sm">
                      View all {videos.total} videos
                    </a>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}