import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import { Toast, ToastProvider, useToast } from '@/components/ui/Toast'
import { Loader2, Sparkles, Copy, Download, Save, AlertCircle, CheckCircle, Loader2 as LoaderIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

// Types
interface ScriptFormData {
  topic: string
  style: string
  duration: number
  platform: string
  tone: string
  target_audience: string
  key_points: string
  language: string
}

interface ScriptResponse {
  id: string
  topic: string
  style: string
  duration: number
  platform: string
  tone: string
  target_audience: string
  key_points: string[]
  language: string
  content: string
  created_at: string
  updated_at: string
}

interface ScriptHistoryItem {
  id: string
  topic: string
  style: string
  duration: number
  platform: string
  created_at: string
}

const STYLES = [
  { value: 'educational', label: 'Educational' },
  { value: 'entertainment', label: 'Entertainment' },
  { value: 'promotional', label: 'Promotional' },
  { value: 'documentary', label: 'Documentary' },
  { value: 'tutorial', label: 'Tutorial/How-to' },
  { value: 'storytelling', label: 'Storytelling' },
  { value: 'review', label: 'Review/Comparison' },
  { value: 'vlog', label: 'Vlog/Personal' },
  { value: 'news', label: 'News/Commentary' },
  { value: 'motivational', label: 'Motivational/Inspirational' },
]

const PLATFORMS = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'instagram_reels', label: 'Instagram Reels' },
  { value: 'youtube_shorts', label: 'YouTube Shorts' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'twitter', label: 'Twitter/X' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'twitch', label: 'Twitch' },
]

const TONES = [
  { value: 'professional', label: 'Professional' },
  { value: 'casual', label: 'Casual/Friendly' },
  { value: 'authoritative', label: 'Authoritative/Expert' },
  { value: 'conversational', label: 'Conversational' },
  { value: 'humorous', label: 'Humorous/Witty' },
  { value: 'inspiring', label: 'Inspiring/Motivational' },
  { value: 'dramatic', label: 'Dramatic/Intense' },
  { value: 'minimalist', label: 'Minimalist/Concise' },
  { value: 'energetic', label: 'Energetic/Enthusiastic' },
  { value: 'calm', label: 'Calm/Soothing' },
]

const DURATIONS = [
  { value: 15, label: '15 seconds (Shorts/Reels/TikTok)' },
  { value: 30, label: '30 seconds (Shorts/Reels/TikTok)' },
  { value: 60, label: '60 seconds (Shorts/Reels/TikTok)' },
  { value: 90, label: '90 seconds' },
  { value: 120, label: '2 minutes' },
  { value: 180, 'label': '3 minutes' },
  { value: 300, label: '5 minutes' },
  { value: 600, label: '10 minutes' },
  { value: 900, label: '15 minutes' },
  { value: 1200, label: '20 minutes' },
  { value: 1800, label: '30 minutes' },
]

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'it', label: 'Italian' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'zh', label: 'Chinese (Simplified)' },
  { value: 'hi', label: 'Hindi' },
  { value: 'ar', label: 'Arabic' },
  { value: 'ru', label: 'Russian' },
]

const DEFAULT_FORM: ScriptFormData = {
  topic: '',
  style: 'educational',
  duration: 60,
  platform: 'youtube',
  tone: 'professional',
  target_audience: '',
  key_points: '',
  language: 'en',
}

const DURATION_OPTIONS = DURATIONS.map(d => ({ value: d.value.toString(), label: d.label }))

export function ScriptGenerator() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [activeTab, setActiveTab] = useState<'generate' | 'history'>('generate')
  const [formData, setFormData] = useState<ScriptFormData>(DEFAULT_FORM)
  const [errors, setErrors] = useState<Partial<ScriptFormData>>({})
  const [isGenerating, setIsGenerating] = useState(false)
  const [generatedScript, setGeneratedScript] = useState<ScriptResponse | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [history, setHistory] = useState<ScriptHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyPage, setHistoryPage] = useState(1)
  const [hasMoreHistory, setHasMoreHistory] = useState(true)
  const [copySuccess, setCopySuccess] = useState(false)

  // Validate form
  const validateForm = useCallback(() => {
    const newErrors: Partial<ScriptFormData> = {}
    if (!formData.topic.trim()) newErrors.topic = 'Topic is required'
    if (!formData.target_audience.trim()) newErrors.target_audience = 'Target audience is required'
    if (formData.duration < 15) newErrors.duration = 'Minimum duration is 15 seconds'
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }, [formData])

  // Handle form input changes
  const handleChange = useCallback((field: keyof ScriptFormData, value: string | number) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: undefined }))
    }
  }, [errors])

  // Handle key points change
  const handleKeyPointsChange = useCallback((value: string) => {
    handleChange('key_points', value)
  }, [handleChange])

  // Generate script
  const handleGenerate = async () => {
    if (!validateForm()) return

    if (!api.isAuthenticated()) {
      toast({ title: 'Authentication required', description: 'Please log in to generate scripts', variant: 'destructive' })
      navigate('/login')
      return
    }

    setIsGenerating(true)
    try {
      const keyPoints = formData.key_points
        .split('\n')
        .map(p => p.trim())
        .filter(p => p.length > 0)

      const response = await api.generateScript({
        topic: formData.topic,
        style: formData.style,
        duration: formData.duration,
        platform: formData.platform,
        tone: formData.tone,
        target_audience: formData.target_audience,
        key_points: keyPoints.length > 0 ? keyPoints : undefined,
        language: formData.language,
      })

      setGeneratedScript(response)
      toast({ title: 'Script generated!', description: 'Your script has been generated successfully.', variant: 'default' })
      setActiveTab('generate') // Stay on generate tab to show result
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to generate script. Please try again.'
      toast({ title: 'Generation failed', description: message, variant: 'destructive' })
    } finally {
      setIsGenerating(false)
    }
  }, [formData, validateForm, toast, navigate])

  // Save script
  const handleSave = async () => {
    if (!generatedScript || isSaving) return

    setIsSaving(true)
    try {
      // The script is already saved by the API when generated
      // This would be an update if we had edit functionality
      toast({ title: 'Saved!', description: 'Script has been saved to your history.', variant: 'default' })
      setIsSaving(false)
      // Refresh history
      loadHistory(1, true)
    } catch (error: any) {
      toast({ title: 'Save failed', description: error.response?.data?.detail || 'Failed to save script', variant: 'destructive' })
      setIsSaving(false)
    }
  }

  // Copy script to clipboard
  const handleCopy = async () => {
    if (!generatedScript) return
    try {
      await navigator.clipboard.writeText(generatedScript.content)
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch {
      toast({ title: 'Copy failed', description: 'Failed to copy to clipboard', variant: 'destructive' })
    }
  }

  // Download script as text file
  const handleDownload = () => {
    if (!generatedScript) return
    const blob = new Blob([generatedScript.content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${generatedScript.topic.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_script.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // Load script history
  const loadHistory = async (page = 1, reset = false) => {
    if (!api.isAuthenticated()) return
    setHistoryLoading(true)
    try {
      const response = await api.getScripts(page, 20)
      const scripts = response.data || response.scripts || response
      if (reset) {
        setHistory(scripts)
      } else {
        setHistory(prev => [...prev, ...scripts])
      }
      setHasMoreHistory(scripts.length === 20)
      setHistoryPage(page)
    } catch (error) {
      console.error('Failed to load history:', error)
    } finally {
      setHistoryLoading(false)
    }
  }

  // Load history when tab changes
  useEffect(() => {
    if (activeTab === 'history' && history.length === 0) {
      loadHistory(1, true)
    }
  }, [activeTab])

  // Load more history
  const loadMoreHistory = () => {
    if (!historyLoading && hasMoreHistory) {
      loadHistory(historyPage + 1, false)
    }
  }

  // View script from history
  const handleViewScript = async (scriptId: string) => {
    try {
      const script = await api.getScript(scriptId)
      setGeneratedScript(script)
      setActiveTab('generate')
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to load script', variant: 'destructive' })
    }
  }

  // Delete script from history
  const handleDeleteScript = async (scriptId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this script?')) return
    try {
      await api.deleteScript(scriptId)
      setHistory(prev => prev.filter(s => s.id !== scriptId))
      toast({ title: 'Deleted', description: 'Script has been deleted', variant: 'default' })
    } catch (error) {
      toast({ title: 'Error', description: 'Failed to delete script', variant: 'destructive' })
    }
  }

  // Create video project from script
  const handleCreateVideo = () => {
    if (!generatedScript) return
    navigate('/video-generator', { state: { script: generatedScript } })
  }

  // Reset form
  const handleReset = () => {
    setFormData(DEFAULT_FORM)
    setErrors({})
    setGeneratedScript(null)
  }

  // Format key points for display
  const formatKeyPoints = (points: string[]) => {
    return points.map((p, i) => `${i + 1}. ${p}`).join('\n')
  }

  // Format duration for display
  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
  }

  return (
    <ToastProvider>
      <div className="min-h-screen bg-dark-50 dark:bg-dark-950">
        {/* Header */}
        <header className="bg-white dark:bg-dark-900 border-b border-dark-200 dark:border-dark-800 sticky top-0 z-40">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="p-2 rounded-lg text-dark-500 hover:bg-dark-100 dark:text-dark-400 dark:hover:bg-dark-800 transition-colors"
                  aria-label="Back to dashboard"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <div>
                  <h1 className="text-xl font-bold text-dark-900 dark:text-white">Script Generator</h1>
                  <p className="text-sm text-dark-500 dark:text-dark-400">Generate AI-powered video scripts</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
                  Dashboard
                </Button>
                <Button variant="ghost" size="sm" onClick={() => navigate('/video-generator')}>
                  Video Generator
                </Button>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="generate" className="flex items-center justify-center gap-2">
                <Sparkles className="w-4 h-4" />
                Generate Script
              </TabsTrigger>
              <TabsTrigger value="history" className="flex items-center justify-center gap-2">
                <LoaderIcon className="w-4 h-4" />
                History
              </TabsTrigger>
            </TabsList>

            {/* Generate Tab */}
            <TabsContent value="generate" className="mt-6">
              <div className="grid lg:grid-cols-[1fr_480px] gap-8">
                {/* Form Panel */}
                <div className="space-y-6">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-primary-500" />
                        Script Details
                      </CardTitle>
                      <CardDescription>
                        Fill in the details below to generate your video script
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      {/* Topic */}
                      <div>
                        <Input
                          label="Video Topic *"
                          placeholder="e.g., How to build a personal brand on LinkedIn"
                          value={formData.topic}
                          onChange={(e) => handleChange('topic', e.target.value)}
                          error={errors.topic}
                          maxLength={200}
                        />
                        <p className="mt-1 text-sm text-dark-500 dark:text-dark-400">
                          Be specific about your topic for better results
                        </p>
                      </div>

                      {/* Style & Platform Row */}
                      <div className="grid sm:grid-cols-2 gap-4">
                        <div>
                          <Select
                            label="Style *"
                            value={formData.style}
                            onValueChange={(v) => handleChange('style', v)}
                            options={STYLES}
                            error={errors.style}
                          />
                        </div>
                        <div>
                          <Select
                            label="Platform *"
                            value={formData.platform}
                            onValueChange={(v) => handleChange('platform', v)}
                            options={PLATFORMS}
                            error={errors.platform}
                          />
                        </div>
                      </div>

                      {/* Duration & Tone Row */}
                      <div className="grid sm:grid-cols-2 gap-4">
                        <div>
                          <Select
                            label="Duration (seconds) *"
                            value={formData.duration.toString()}
                            onValueChange={(v) => handleChange('duration', parseInt(v))}
                            options={DURATION_OPTIONS}
                            error={errors.duration}
                          />
                        </div>
                        <div>
                          <Select
                            label="Tone *"
                            value={formData.tone}
                            onValueChange={(v) => handleChange('tone', v)}
                            options={TONES}
                            error={errors.tone}
                          />
                        </div>
                      </div>

                      {/* Language & Target Audience Row */}
                      <div className="grid sm:grid-cols-2 gap-4">
                        <div>
                          <Select
                            label="Language"
                            value={formData.language}
                            onValueChange={(v) => handleChange('language', v)}
                            options={LANGUAGES}
                          />
                        </div>
                        <div>
                          <Input
                            label="Target Audience *"
                            placeholder="e.g., Marketing professionals aged 25-40"
                            value={formData.target_audience}
                            onChange={(e) => handleChange('target_audience', e.target.value)}
                            error={errors.target_audience}
                            maxLength={200}
                          />
                        </div>
                      </div>

                      {/* Key Points */}
                      <div>
                        <Textarea
                          label="Key Points (Optional)"
                          placeholder="Enter key points to cover, one per line:\n- Hook: Start with a shocking statistic\n- Problem: Address the pain point\n- Solution: Present your method\n- Proof: Show results/case studies\n- CTA: Subscribe for more tips"
                          value={formData.key_points}
                          onChange={handleKeyPointsChange}
                          rows={6}
                          helperText="Optional: Add specific points you want covered in the script"
                        />
                      </div>

                      {/* Action Buttons */}
                      <div className="flex flex-col sm:flex-row gap-4 pt-4 border-t border-dark-200 dark:border-dark-700">
                        <Button
                          onClick={handleGenerate}
                          disabled={isGenerating}
                          className="flex-1 flex items-center justify-center gap-2"
                          size="lg"
                        >
                          {isGenerating ? (
                            <>
                              <Loader2 className="w-5 h-5 animate-spin" />
                              Generating...
                            </>
                          ) : (
                            <>
                              <Sparkles className="w-5 h-5" />
                              Generate Script
                            </>
                          )}
                        </Button>
                        <Button
                          variant="outline"
                          onClick={handleReset}
                          disabled={isGenerating}
                          className="flex-1"
                        >
                          Reset Form
                        </Button>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Tips Card */}
                  <Card className="border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-900/20">
                    <CardContent className="pt-6">
                      <h3 className="font-semibold text-dark-900 dark:text-white mb-3 flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-primary-500" />
                        Tips for Better Scripts
                      </h3>
                      <ul className="space-y-2 text-sm text-dark-600 dark:text-dark-300">
                        <li className="flex items-start gap-2"><span className="text-primary-500">•</span> Be specific about your topic - "How to grow on LinkedIn" works better than "LinkedIn tips"</li>
                        <li className="flex items-start gap-2"><span className="text-primary-500">•</span> Define your target audience clearly - demographics, interests, pain points</li>
                        <li className="flex items-start gap-2"><span className="text-primary-500">•</span> Add key points to ensure important topics are covered</li>
                        <li className="flex items-start gap-2"><span className="text-primary-500">•</span> Match duration to platform - 15-60s for Shorts/Reels/TikTok, 3-10min for YouTube</li>
                        <li className="flex items-start gap-2"><span className="text-primary-500">•</span> Choose tone that matches your brand voice</li>
                      </ul>
                    </CardContent>
                  </Card>
                </div>

                {/* Result Panel */}
                <div className="space-y-6">
                  {generatedScript ? (
                    <Card className="h-full flex flex-col">
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div>
                            <CardTitle className="flex items-center gap-2">
                              <CheckCircle className="w-5 h-5 text-green-500" />
                              Script Generated
                            </CardTitle>
                            <CardDescription>
                              {generatedScript.style} • {formatDuration(generatedScript.duration)} • {generatedScript.platform}
                            </CardDescription>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleCopy}
                              className="gap-1"
                            >
                              <Copy className="w-4 h-4" />
                              {copySuccess ? 'Copied!' : 'Copy'}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleDownload}
                              className="gap-1"
                            >
                              <Download className="w-4 h-4" />
                              Download
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={handleSave}
                              disabled={isSaving}
                              className="gap-1"
                            >
                              <Save className="w-4 h-4" />
                              {isSaving ? 'Saving...' : 'Save'}
                            </Button>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="flex-1 overflow-y-auto p-0">
                        <div className="p-6 space-y-6">
                          {/* Script Meta */}
                          <div className="grid sm:grid-cols-2 gap-4 text-sm text-dark-600 dark:text-dark-400 border-b border-dark-200 dark:border-dark-700 pb-4">
                            <div><span className="font-medium text-dark-900 dark:text-white">Topic:</span> {generatedScript.topic}</div>
                            <div><span className="font-medium text-dark-900 dark:text-white">Style:</span> {generatedScript.style}</div>
                            <div><span className="font-medium text-dark-900 dark:text-white">Platform:</span> {generatedScript.platform}</div>
                            <div><span className="font-medium text-dark-900 dark:text-white">Tone:</span> {generatedScript.tone}</div>
                            <div><span className="font-medium text-dark-900 dark:text-white">Duration:</span> {formatDuration(generatedScript.duration)}</div>
                            <div><span className="font-medium text-dark-900 dark:text-white">Language:</span> {generatedScript.language}</div>
                            <div className="sm:col-span-2"><span className="font-medium text-dark-900 dark:text-white">Target Audience:</span> {generatedScript.target_audience}</div>
                            {generatedScript.key_points && generatedScript.key_points.length > 0 && (
                              <div className="sm:col-span-2">
                                <span className="font-medium text-dark-900 dark:text-white">Key Points:</span>
                                <ul className="mt-1 ml-4 list-disc text-sm">
                                  {generatedScript.key_points.map((p, i) => <li key={i}>{p}</li>)}
                                </ul>
                              </div>
                            )}
                          </div>

                          {/* Script Content */}
                          <div className="prose prose-dark dark:prose-invert max-w-none">
                            <pre className="whitespace-pre-wrap text-base leading-relaxed text-dark-900 dark:text-dark-100 font-sans">
                              {generatedScript.content}
                            </pre>
                          </div>
                        </div>
                      </CardContent>
                      <CardContent className="border-t border-dark-200 dark:border-dark-700 p-4">
                        <Button
                          onClick={handleCreateVideo}
                          className="w-full flex items-center justify-center gap-2"
                          size="lg"
                        >
                          <LoaderIcon className="w-5 h-5" />
                          Create Video from Script
                        </Button>
                        <p className="text-center text-sm text-dark-500 dark:text-dark-400 mt-2">
                          Opens Video Generator with this script pre-loaded
                        </p>
                      </CardContent>
                    </Card>
                  ) : (
                    // Empty State
                    <Card className="h-[500px] flex items-center justify-center border-dashed border-dark-200 dark:border-dark-700">
                      <CardContent className="text-center p-12">
                        <Sparkles className="w-16 h-16 text-dark-300 dark:text-dark-600 mx-auto mb-4" />
                        <h3 className="text-xl font-semibold text-dark-900 dark:text-white mb-2">Your Script Will Appear Here</h3>
                        <p className="text-dark-500 dark:text-dark-400 mb-6 max-w-sm mx-auto">
                          Fill in the form and click "Generate Script" to create your AI-powered video script
                        </p>
                        <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-dark-500 dark:text-dark-400">
                          <span className="flex items-center gap-1"><Sparkles className="w-4 h-4" /> AI-Powered</span>
                          <span className="flex items-center gap-1"><LoaderIcon className="w-4 h-4" /> Fast Generation</span>
                          <span className="flex items-center gap-1"><Copy className="w-4 h-4" /> Copy & Download</span>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              </div>
            </TabsContent>

            {/* History Tab */}
            <TabsContent value="history" className="mt-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <LoaderIcon className="w-5 h-5" />
                    Script History
                  </CardTitle>
                  <CardDescription>
                    View and manage your previously generated scripts
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {historyLoading && history.length === 0 ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
                    </div>
                  ) : history.length === 0 ? (
                    <div className="text-center py-12">
                      <LoaderIcon className="w-16 h-16 text-dark-300 dark:text-dark-600 mx-auto mb-4" />
                      <h3 className="text-xl font-semibold text-dark-900 dark:text-white mb-2">No Scripts Yet</h3>
                      <p className="text-dark-500 dark:text-dark-400 mb-6">Generate your first script to see it here</p>
                      <Button onClick={() => setActiveTab('generate')}>
                        <Sparkles className="w-4 h-4 mr-2" />
                        Generate Script
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {history.map((script) => (
                        <div
                          key={script.id}
                          className="group p-4 border border-dark-200 dark:border-dark-700 rounded-lg hover:border-primary-300 dark:hover:border-primary-700 transition-colors cursor-pointer"
                          onClick={() => handleViewScript(script.id)}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <h4 className="font-medium text-dark-900 dark:text-white truncate">{script.topic}</h4>
                              <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-dark-500 dark:text-dark-400">
                                <span className="px-2 py-0.5 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded-full text-xs">
                                  {script.style}
                                </span>
                                <span className="px-2 py-0.5 bg-dark-100 dark:bg-dark-800 rounded-full text-xs">
                                  {formatDuration(script.duration)}
                                </span>
                                <span className="px-2 py-0.5 bg-dark-100 dark:bg-dark-800 rounded-full text-xs capitalize">
                                  {script.platform.replace('_', ' ')}
                                </span>
                                <span>{new Date(script.created_at).toLocaleDateString()}</span>
                              </div>
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => handleDeleteScript(script.id, e)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity text-red-500 hover:text-red-600"
                            >
                              <AlertCircle className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      ))}

                      {hasMoreHistory && (
                        <Button
                          variant="outline"
                          className="w-full"
                          onClick={loadMoreHistory}
                          disabled={historyLoading}
                        >
                          {historyLoading ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin mr-2" />
                              Loading...
                            </>
                          ) : (
                            'Load More'
                          )}
                        </Button>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </main>
      </div>
      <Toast />
    </ToastProvider>
  )
}

export default ScriptGenerator