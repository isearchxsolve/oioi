import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import {
  Video,
  FileText,
  Cpu,
  FolderKanban,
  Sparkles,
  TrendingUp,
  Clock,
  CheckCircle,
  Loader2,
  AlertCircle,
  ArrowRight,
  Plus,
  ExternalLink,
  Brain,
  Cube,
  Image,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'

export function Dashboard() {
  const navigate = useNavigate()
  
  const { data: projectsData } = useQuery({
    queryKey: ['projects', 1, 5],
    queryFn: () => api.getVideoProjects(1, 5),
  })
  
  const { data: scriptsData } = useQuery({
    queryKey: ['scripts', 1, 5],
    queryFn: () => api.getScripts(1, 5),
  })
  
  const { data: modelsData } = useQuery({
    queryKey: ['models'],
    queryFn: () => api.getModels(),
  })
  
  const projects = projectsData?.items || []
  const scripts = scriptsData?.items || []
  const models = modelsData?.models || []
  
  const recentProjects = projects.slice(0, 4)
  const recentScripts = scripts.slice(0, 4)
  const readyModels = models.filter(m => m.status === 'ready').slice(0, 4)
  
  const stats = {
    totalProjects: projectsData?.total || 0,
    completedProjects: projects.filter(p => p.status === 'completed').length,
    totalScripts: scriptsData?.total || 0,
    readyModels: models.filter(m => m.status === 'ready').length,
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-900 dark:text-white flex items-center gap-3">
          <Sparkles className="h-8 w-8 text-primary-600" />
          Dashboard
        </h1>
        <p className="text-dark-500 dark:text-dark-400 mt-1">
          Overview of your AI video generation workspace
        </p>
      </div>
      
      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Total Projects</p>
                <p className="text-3xl font-bold text-dark-900 dark:text-white">{stats.totalProjects}</p>
              </div>
              <div className="p-3 bg-primary-100 dark:bg-primary-900/30 rounded-xl">
                <FolderKanban className="h-6 w-6 text-primary-600 dark:text-primary-400" />
              </div>
            </div>
            <Button variant="ghost" size="sm" className="w-full mt-4" onClick={() => navigate('/projects')}>
              <ArrowRight className="h-4 w-4 mr-1" />
              View All
            </Button>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Completed Videos</p>
                <p className="text-3xl font-bold text-green-600 dark:text-green-400">{stats.completedProjects}</p>
              </div>
              <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-xl">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
            </div>
            <Button variant="ghost" size="sm" className="w-full mt-4" onClick={() => navigate('/projects?status=completed')}>
              <ArrowRight className="h-4 w-4 mr-1" />
              View Completed
            </Button>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Scripts Generated</p>
                <p className="text-3xl font-bold text-dark-900 dark:text-white">{stats.totalScripts}</p>
              </div>
              <div className="p-3 bg-purple-100 dark:bg-purple-900/30 rounded-xl">
                <FileText className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
            </div>
            <Button variant="ghost" size="sm" className="w-full mt-4" onClick={() => navigate('/scripts')}>
              <ArrowRight className="h-4 w-4 mr-1" />
              View Scripts
            </Button>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Ready Models</p>
                <p className="text-3xl font-bold text-dark-900 dark:text-white">{stats.readyModels}</p>
              </div>
              <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-xl">
                <Cpu className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
            </div>
            <Button variant="ghost" size="sm" className="w-full mt-4" onClick={() => navigate('/models')}>
              <ArrowRight className="h-4 w-4 mr-1" />
              View Models
            </Button>
          </CardContent>
        </Card>
      </div>
      
      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="hover:shadow-lg transition-shadow cursor-pointer border-2 border-dashed border-dark-200 dark:border-dark-700"
          onClick={() => navigate('/scripts/generate')}>
          <CardContent className="p-6 text-center">
            <div className="p-3 bg-primary-100 dark:bg-primary-900/30 rounded-xl w-fit mx-auto mb-4">
              <FileText className="h-8 w-8 text-primary-600 dark:text-primary-400" />
            </div>
            <h3 className="font-semibold text-dark-900 dark:text-white mb-2">Generate Script</h3>
            <p className="text-dark-500 dark:text-dark-400 text-sm mb-4">
              Create AI-powered video scripts for any platform
            </p>
            <Button variant="outline" size="sm">
              <Plus className="h-3 w-3 mr-1" />
              Create Script
            </Button>
          </CardContent>
        </Card>
        
        <Card className="hover:shadow-lg transition-shadow cursor-pointer border-2 border-dashed border-dark-200 dark:border-dark-700"
          onClick={() => navigate('/videos/generate')}>
          <CardContent className="p-6 text-center">
            <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-xl w-fit mx-auto mb-4">
              <Video className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="font-semibold text-dark-900 dark:text-white mb-2">Generate Video</h3>
            <p className="text-dark-500 dark:text-dark-400 text-sm mb-4">
              Create videos using NVIDIA NIM models
            </p>
            <Button variant="outline" size="sm">
              <Plus className="h-3 w-3 mr-1" />
              Create Video
            </Button>
          </CardContent>
        </Card>
        
        <Card className="hover:shadow-lg transition-shadow cursor-pointer border-2 border-dashed border-dark-200 dark:border-dark-700"
          onClick={() => navigate('/models')}>
          <CardContent className="p-6 text-center">
            <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-xl w-fit mx-auto mb-4">
              <Cpu className="h-8 w-8 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="font-semibold text-dark-900 dark:text-white mb-2">Browse Models</h3>
            <p className="text-dark-500 dark:text-dark-400 text-sm mb-4">
              Explore available NVIDIA NIM models
            </p>
            <Button variant="outline" size="sm">
              <ExternalLink className="h-3 w-3 mr-1" />
              View Models
            </Button>
          </CardContent>
        </Card>
      </div>
      
      {/* Recent Activity */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent Projects */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FolderKanban className="h-5 w-5" />
              Recent Projects
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => navigate('/projects')}>
              View All
              <ArrowRight className="h-3 w-3 ml-1" />
            </Button>
          </CardHeader>
          <CardContent>
            {recentProjects.length === 0 ? (
              <div className="text-center py-8">
                <FolderKanban className="h-12 w-12 text-dark-300 dark:text-dark-600 mx-auto mb-3" />
                <p className="text-dark-500 dark:text-dark-400">No projects yet</p>
                <Button variant="outline" size="sm" className="mt-2" onClick={() => navigate('/projects')}>
                  Create Project
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {recentProjects.map(project => (
                  <div
                    key={project.id}
                    className="flex items-center gap-4 p-3 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50 transition-colors"
                    onClick={() => navigate(`/projects/${project.id}`)}
                  >
                    <div className="relative h-16 w-16 rounded-lg bg-dark-100 dark:bg-dark-800 overflow-hidden flex-shrink-0">
                      {project.thumbnail_url ? (
                        <img src={project.thumbnail_url} alt={project.title} className="w-full h-full object-cover" />
                      ) : (
                        <Video className="h-8 w-8 text-dark-400 mx-auto my-auto" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-dark-900 dark:text-white truncate">{project.title}</p>
                      <p className="text-sm text-dark-500 dark:text-dark-400 truncate">
                        {project.prompt?.slice(0, 80)}...
                      </p>
                      <div className="flex items-center gap-3 mt-1 text-xs text-dark-400">
                        <span>{project.model}</span>
                        <span>{project.duration}s</span>
                        <span>{project.resolution}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {project.status === 'completed' && (
                        <Badge variant="success">Completed</Badge>
                      )}
                      {project.status === 'processing' && (
                        <Badge variant="warning">
                          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          Processing
                        </Badge>
                      )}
                      {project.status === 'failed' && (
                        <Badge variant="destructive">Failed</Badge>
                      )}
                      {project.status === 'pending' && (
                        <Badge variant="secondary">Pending</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        
        {/* Sidebar */}
        <div className="space-y-6">
          {/* Recent Scripts */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Recent Scripts
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => navigate('/scripts')}>
                View All
              </Button>
            </CardHeader>
            <CardContent>
              {recentScripts.length === 0 ? (
                <div className="text-center py-6">
                  <FileText className="h-10 w-10 text-dark-300 dark:text-dark-600 mx-auto mb-3" />
                  <p className="text-dark-500 dark:text-dark-400 text-sm">No scripts yet</p>
                  <Button variant="outline" size="sm" className="mt-2" onClick={() => navigate('/scripts/generate')}>
                    Generate Script
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {recentScripts.map(script => (
                    <div
                      key={script.id}
                      className="p-3 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50 transition-colors"
                      onClick={() => navigate(`/scripts/${script.id}`)}
                    >
                      <p className="font-medium text-dark-900 dark:text-white truncate mb-1">{script.topic}</p>
                      <div className="flex items-center gap-2 text-xs text-dark-500">
                        <Badge variant="outline" className="text-xs">{script.style}</Badge>
                        <Badge variant="outline" className="text-xs">{script.platform}</Badge>
                        <span>{formatDistanceToNow(new Date(script.created_at), { addSuffix: true })}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
          
          {/* Ready Models */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5" />
                Ready Models
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => navigate('/models')}>
                View All
              </Button>
            </CardHeader>
            <CardContent>
              {readyModels.length === 0 ? (
                <div className="text-center py-6">
                  <Cpu className="h-10 w-10 text-dark-300 dark:text-dark-600 mx-auto mb-3" />
                  <p className="text-dark-500 dark:text-dark-400 text-sm">No models loaded</p>
                  <Button variant="outline" size="sm" className="mt-2" onClick={() => navigate('/models')}>
                    Load Models
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {readyModels.map(model => (
                    <div
                      key={model.id}
                      className="p-3 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50 transition-colors"
                      onClick={() => navigate(`/playground?model=${model.id}`)}
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary-100 dark:bg-primary-900/30 rounded-lg">
                          {model.category === 'llm' && <Brain className="h-4 w-4 text-primary-600" />}
                          {model.category === 'video' && <Video className="h-4 w-4 text-primary-600" />}
                          {model.category === '3d' && <Cube className="h-4 w-4 text-primary-600" />}
                          {model.category === 'image' && <Image className="h-4 w-4 text-primary-600" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-dark-900 dark:text-white truncate text-sm">{model.name}</p>
                          <p className="text-xs text-dark-500 truncate">{model.id}</p>
                        </div>
                        <Badge variant="success" className="text-xs">Ready</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent          </Card>
          
          {/* Quick Links */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Quick Links
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <a href="https://build.nvidia.com/explore/discover" target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50 transition-colors">
                <ExternalLink className="h-5 w-5 text-primary-600" />
                <span className="text-sm text-dark-700 dark:text-dark-300">NVIDIA NGC Catalog</span>
              </a>
              <a href="https://docs.nvidia.com/nim/" target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50 transition-colors">
                <BookOpen className="h-5 w-5 text-blue-600" />
                <span className="text-sm text-dark-700 dark:text-dark-300">NIM Documentation</span>
              </a>
              <a href="https://github.com/NVIDIA/nim" target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-dark-50 dark:hover:bg-dark-800/50 transition-colors">
                <Github className="h-5 w-5 text-dark-600" />
                <span className="text-sm text-dark-700 dark:text-dark-300">NIM GitHub</span>
              </a>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

// Missing imports
import { BookOpen, Github } from 'lucide-react'