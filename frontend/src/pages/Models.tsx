import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import toast from 'react-hot-toast'
import {
  Cpu,
  CheckCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Settings,
  Zap,
  Brain,
  Cube,
  Image,
  Video,
  Layers,
  ExternalLink,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  Volume2,
  Play,
  Download,
  Info,
  Trash2,
  Eye,
} from 'lucide-react'

const modelCategories = [
  { id: 'all', label: 'All Models', icon: Layers },
  { id: 'llm', label: 'LLM', icon: Brain },
  { id: 'video', label: 'Video', icon: Video },
  { id: '3d', label: '3D', icon: Cube },
  { id: 'image', label: 'Image', icon: Image },
  { id: 'audio', label: 'Audio', icon: Volume2 },
]

export function Models() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [selectedStatus, setSelectedStatus] = useState('all')
  const [sortBy, setSortBy] = useState<'name' | 'status' | 'category'>('name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [showDetails, setShowDetails] = useState<string | null>(null)
  
  const { data: modelsData, isLoading, error, refetch } = useQuery({
    queryKey: ['models'],
    queryFn: () => api.getModels(),
    refetchInterval: 30000,
  })
  
  const loadModelMutation = useMutation({
    mutationFn: (modelId: string) => api.loadModel(modelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] })
      toast.success('Model loading started')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to load model')
    },
  })
  
  const unloadModelMutation = useMutation({
    mutationFn: (modelId: string) => api.unloadModel(modelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['models'] })
      toast.success('Model unloaded')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to unload model')
    },
  })
  
  const models = modelsData?.models || []
  
  const filteredModels = models
    .filter(model => {
      const matchesSearch = model.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        model.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        model.description?.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesCategory = selectedCategory === 'all' || model.category === selectedCategory
      const matchesStatus = selectedStatus === 'all' || model.status === selectedStatus
      return matchesSearch && matchesCategory && matchesStatus
    })
    .sort((a, b) => {
      let aVal = a[sortBy]
      let bVal = b[sortBy]
      if (typeof aVal === 'string') {
        aVal = aVal.toLowerCase()
        bVal = bVal.toLowerCase()
      }
      if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1
      if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1
      return 0
    })
  
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ready':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'loading':
        return <Loader2 className="h-4 w-4 text-yellow-500 animate-spin" />
      case 'error':
        return <AlertCircle className="h-4 w-4 text-red-500" />
      default:
        return <Cpu className="h-4 w-4 text-gray-500" />
    }
  }
  
  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'ready':
        return 'Ready'
      case 'loading':
        return 'Loading'
      case 'error':
        return 'Error'
      default:
        return 'Unavailable'
    }
  }
  
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ready':
        return <Badge variant="success">{getStatusLabel(status)}</Badge>
      case 'loading':
        return <Badge variant="warning">{getStatusLabel(status)}</Badge>
      case 'error':
        return <Badge variant="destructive">{getStatusLabel(status)}</Badge>
      default:
        return <Badge variant="secondary">{getStatusLabel(status)}</Badge>
    }
  }
  
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'llm':
        return <Brain className="h-4 w-4" />
      case 'video':
        return <Video className="h-4 w-4" />
      case '3d':
        return <Cube className="h-4 w-4" />
      case 'image':
        return <Image className="h-4 w-4" />
      case 'audio':
        return <Volume2 className="h-4 w-4" />
      default:
        return <Cpu className="h-4 w-4" />
    }
  }
  
  const handleLoadModel = (modelId: string) => {
    loadModelMutation.mutate(modelId)
  }
  
  const handleUnloadModel = (modelId: string) => {
    if (confirm('Are you sure you want to unload this model?')) {
      unloadModelMutation.mutate(modelId)
    }
  }
  
  const handleRefresh = () => {
    refetch()
    toast.success('Models refreshed')
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-dark-900 dark:text-white flex items-center gap-3">
            <Cpu className="h-8 w-8 text-primary-600" />
            NVIDIA NIM Models
          </h1>
          <p className="text-dark-500 dark:text-dark-400 mt-1">
            Manage and monitor NVIDIA NIM inference models
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={handleRefresh} loading={isLoading}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <a
            href="https://build.nvidia.com/explore/discover"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          >
            <ExternalLink className="h-4 w-4" />
            Browse NVIDIA NGC
          </a>
        </div>
      </div>
      
      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Total Models</p>
                <p className="text-3xl font-bold text-dark-900 dark:text-white">{models.length}</p>
              </div>
              <div className="p-3 bg-primary-100 dark:bg-primary-900/30 rounded-xl">
                <Cpu className="h-6 w-6 text-primary-600 dark:text-primary-400" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Ready</p>
                <p className="text-3xl font-bold text-green-600 dark:text-green-400">
                  {models.filter(m => m.status === 'ready').length}
                </p>
              </div>
              <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-xl">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Loading</p>
                <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
                  {models.filter(m => m.status === 'loading').length}
                </p>
              </div>
              <div className="p-3 bg-yellow-100 dark:bg-yellow-900/30 rounded-xl">
                <Loader2 className="h-6 w-6 text-yellow-600 dark:text-yellow-400 animate-spin" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Categories</p>
                <p className="text-3xl font-bold text-dark-900 dark:text-white">
                  {[...new Set(models.map(m => m.category))].length}
                </p>
              </div>
              <div className="p-3 bg-purple-100 dark:bg-purple-900/30 rounded-xl">
                <Layers className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      
      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-400" />
              <Input
                placeholder="Search models..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            
            <div className="flex flex-wrap gap-2">
              {modelCategories.map(cat => (
                <button
                  key={cat.id}
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    selectedCategory === cat.id
                      ? 'bg-primary-500 text-white'
                      : 'bg-dark-100 dark:bg-dark-800 text-dark-700 dark:text-dark-300 hover:bg-dark-200 dark:hover:bg-dark-700'
                  }`}
                >
                  <cat.icon className="h-4 w-4 inline mr-1" />
                  {cat.label}
                </button>
              ))}
            </div>
            
            <div className="flex gap-2">
              {['all', 'ready', 'loading', 'error', 'unavailable'].map(status => (
                <button
                  key={status}
                  onClick={() => setSelectedStatus(status)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    selectedStatus === status
                      ? 'bg-primary-500 text-white'
                      : 'bg-dark-100 dark:bg-dark-800 text-dark-700 dark:text-dark-300 hover:bg-dark-200 dark:hover:bg-dark-700'
                  }`}
                >
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
      
      {/* Models Grid */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[...Array(8)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6">
                <div className="h-4 bg-dark-200 dark:bg-dark-700 rounded w-3/4 mb-4" />
                <div className="h-3 bg-dark-200 dark:bg-dark-700 rounded w-1/2 mb-2" />
                <div className="h-3 bg-dark-200 dark:bg-dark-700 rounded w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredModels.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <Cpu className="h-12 w-12 text-dark-300 dark:text-dark-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-dark-900 dark:text-white mb-2">
              {searchQuery || selectedCategory !== 'all' || selectedStatus !== 'all'
                ? 'No models found'
                : 'No models available'}
            </h3>
            <p className="text-dark-500 dark:text-dark-400 mb-6">
              {searchQuery || selectedCategory !== 'all' || selectedStatus !== 'all'
                ? 'Try adjusting your search or filters'
                : 'Load models from NVIDIA NGC to get started'}
            </p>
            {!searchQuery && selectedCategory === 'all' && selectedStatus === 'all' && (
              <a
                href="https://build.nvidia.com/explore/discover"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
              >
                <ExternalLink className="h-4 w-4" />
                Browse NVIDIA NGC
              </a>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredModels.map(model => (
            <ModelCard
              key={model.id}
              model={model}
              onLoad={handleLoadModel}
              onUnload={handleUnloadModel}
              onToggleDetails={() => setShowDetails(showDetails === model.id ? null : model.id)}
              isExpanded={showDetails === model.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ModelCard({ 
  model, 
  onLoad, 
  onUnload, 
  onToggleDetails, 
  isExpanded 
}: { 
  model: any
  onLoad: (id: string) => void
  onUnload: (id: string) => void
  onToggleDetails: () => void
  isExpanded: boolean
}) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ready':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'loading':
        return <Loader2 className="h-4 w-4 text-yellow-500 animate-spin" />
      case 'error':
        return <AlertCircle className="h-4 w-4 text-red-500" />
      default:
        return <Cpu className="h-4 w-4 text-gray-500" />
    }
  }
  
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ready':
        return <Badge variant="success">Ready</Badge>
      case 'loading':
        return <Badge variant="warning">Loading</Badge>
      case 'error':
        return <Badge variant="destructive">Error</Badge>
      default:
        return <Badge variant="secondary">Unavailable</Badge>
    }
  }
  
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'llm':
        return <Brain className="h-4 w-4" />
      case 'video':
        return <Video className="h-4 w-4" />
      case '3d':
        return <Cube className="h-4 w-4" />
      case 'image':
        return <Image className="h-4 w-4" />
      case 'audio':
        return <Volume2 className="h-4 w-4" />
      default:
        return <Cpu className="h-4 w-4" />
    }
  }

  return (
    <Card className={`transition-all ${isExpanded ? 'shadow-lg' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-100 dark:bg-primary-900/30 rounded-lg">
              {getCategoryIcon(model.category)}
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-dark-900 dark:text-white truncate max-w-[200px]">
                {model.name}
              </h3>
              <p className="text-xs text-dark-500 dark:text-dark-400 font-mono truncate max-w-[200px]">
                {model.id}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {getStatusIcon(model.status)}
            {getStatusBadge(model.status)}
          </div>
        </div>
        
        {model.description && (
          <p className="text-sm text-dark-600 dark:text-dark-400 mb-3 line-clamp-2">
            {model.description}
          </p>
        )}
        
        <div className="flex items-center gap-3 text-xs text-dark-500 dark:text-dark-400 mb-3">
          <span className="flex items-center gap-1">
            {getCategoryIcon(model.category)}
            {model.category}
          </span>
          {model.version && (
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3" />
              v{model.version}
            </span>
          )}
          {model.size && (
            <span className="flex items-center gap-1">
              <Database className="h-3 w-3" />
              {model.size}
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {model.status === 'ready' && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="flex-1"
                onClick={() => onLoad(model.id)}
              >
                <Play className="h-3 w-3 mr-1" />
                Use Model
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onUnload(model.id)}
                className="text-red-500 hover:text-red-600"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
          {model.status === 'loading' && (
            <Button variant="outline" size="sm" className="flex-1" disabled>
              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              Loading...
            </Button>
          )}
          {model.status === 'error' && (
            <Button variant="outline" size="sm" className="flex-1" onClick={() => onLoad(model.id)}>
              <RefreshCw className="h-3 w-3 mr-1" />
              Retry
            </Button>
          )}
          {model.status === 'unavailable' && (
            <Button variant="outline" size="sm" className="flex-1" onClick={() => onLoad(model.id)}>
              <Download className="h-3 w-3 mr-1" />
              Load Model
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleDetails}
            className="text-dark-400 hover:text-dark-600"
          >
            <ChevronDown className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
          </Button>
        </div>
        
        {isExpanded && (
          <div className="mt-4 pt-4 border-t border-dark-200 dark:border-dark-700 space-y-3 animate-slide-down">
            <div className="grid gap-2 sm:grid-cols-2 text-sm">
              <div>
                <span className="text-dark-500">Model ID</span>
                <p className="font-mono text-dark-900 dark:text-white break-all">{model.id}</p>
              </div>
              <div>
                <span className="text-dark-500">Category</span>
                <p className="font-medium text-dark-900 dark:text-white capitalize">{model.category}</p>
              </div>
              {model.version && (
                <div>
                  <span className="text-dark-500">Version</span>
                  <p className="font-medium text-dark-900 dark:text-white">{model.version}</p>
                </div>
              )}
              {model.size && (
                <div>
                  <span className="text-dark-500">Size</span>
                  <p className="font-medium text-dark-900 dark:text-white">{model.size}</p>
                </div>
              )}
              {model.memory_required && (
                <div>
                  <span className="text-dark-500">VRAM Required</span>
                  <p className="font-medium text-dark-900 dark:text-white">{model.memory_required}</p>
                </div>
              )}
              {model.max_tokens && (
                <div>
                  <span className="text-dark-500">Max Tokens</span>
                  <p className="font-medium text-dark-900 dark:text-white">{model.max_tokens.toLocaleString()}</p>
                </div>
              )}
            </div>
            
            {model.capabilities && model.capabilities.length > 0 && (
              <div>
                <span className="text-sm text-dark-500">Capabilities</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {model.capabilities.map((cap: string) => (
                    <Badge key={cap} variant="outline" className="text-xs">
                      {cap}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            
            {model.endpoint && (
              <div>
                <span className="text-sm text-dark-500">Endpoint</span>
                <p className="font-mono text-xs text-dark-900 dark:text-white break-all mt-1">
                  {model.endpoint}
                </p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Missing imports
import { Database, Download, RefreshCw, ChevronDown } from 'lucide-react'