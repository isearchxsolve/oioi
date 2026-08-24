import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import toast from 'react-hot-toast'
import {
  FolderKanban,
  Plus,
  Search,
  Filter,
  MoreVertical,
  Edit,
  Trash2,
  Play,
  Eye,
  Copy,
  Download,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  Video,
  FileText,
  Sparkles,
  ArrowRight,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'

export function Projects() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'processing' | 'failed'>('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newProjectTitle, setNewProjectTitle] = useState('')
  const [newProjectScriptId, setNewProjectScriptId] = useState('')
  
  const { data: projectsData, isLoading, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.getVideoProjects(1, 50),
  })
  
  const { data: scripts } = useQuery({
    queryKey: ['scripts', 1, 100],
    queryFn: () => api.getScripts(1, 100),
  })
  
  const createProjectMutation = useMutation({
    mutationFn: (data: { title: string; script_id?: string }) => api.createVideoProject(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project created')
      setShowCreateModal(false)
      setNewProjectTitle('')
      setNewProjectScriptId('')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create project')
    },
  })
  
  const deleteProjectMutation = useMutation({
    mutationFn: (id: string) => api.deleteVideoProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Project deleted')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete project')
    },
  })
  
  const projects = projectsData?.items || []
  
  const filteredProjects = projects.filter(project => {
    const matchesSearch = project.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      project.prompt?.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'all' || project.status === statusFilter
    return matchesSearch && matchesStatus
  })
  
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-red-500" />
      case 'processing':
      case 'generating':
        return <Loader2 className="h-4 w-4 text-yellow-500 animate-spin" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }
  
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success">Completed</Badge>
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>
      case 'processing':
      case 'generating':
        return <Badge variant="warning">Processing</Badge>
      default:
        return <Badge variant="secondary">Pending</Badge>
    }
  }
  
  const handleCreateProject = () => {
    if (!newProjectTitle.trim()) {
      toast.error('Please enter a project title')
      return
    }
    createProjectMutation.mutate({
      title: newProjectTitle,
      script_id: newProjectScriptId || undefined,
    })
  }
  
  const handleDeleteProject = (id: string) => {
    if (confirm('Are you sure you want to delete this project?')) {
      deleteProjectMutation.mutate(id)
    }
  }
  
  const handleOpenVideo = (videoUrl: string) => {
    window.open(videoUrl, '_blank')
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-dark-900 dark:text-white flex items-center gap-3">
            <FolderKanban className="h-8 w-8 text-primary-600" />
            Video Projects
          </h1>
          <p className="text-dark-500 dark:text-dark-400 mt-1">
            Manage your video generation projects
          </p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Project
        </Button>
      </div>
      
      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Total Projects</p>
                <p className="text-3xl font-bold text-dark-900 dark:text-white">{projectsData?.total || 0}</p>
              </div>
              <div className="p-3 bg-primary-100 dark:bg-primary-900/30 rounded-xl">
                <FolderKanban className="h-6 w-6 text-primary-600 dark:text-primary-400" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-dark-500 dark:text-dark-400">Completed</p>
                <p className="text-3xl font-bold text-green-600 dark:text-green-400">
                  {projects.filter(p => p.status === 'completed').length}
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
                <p className="text-sm text-dark-500 dark:text-dark-400">Processing</p>
                <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
                  {projects.filter(p => p.status === 'processing' || p.status === 'generating').length}
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
                <p className="text-sm text-dark-500 dark:text-dark-400">Failed</p>
                <p className="text-3xl font-bold text-red-600 dark:text-red-400">
                  {projects.filter(p => p.status === 'failed').length}
                </p>
              </div>
              <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-xl">
                <AlertCircle className="h-6 w-6 text-red-600 dark:text-red-400" />
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
                placeholder="Search projects..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            
            <div className="flex gap-2">
              {['all', 'completed', 'processing', 'failed'].map(status => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status as any)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    statusFilter === status
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
      
      {/* Projects Grid */}
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6">
                <div className="h-4 bg-dark-200 dark:bg-dark-700 rounded w-3/4 mb-4" />
                <div className="h-3 bg-dark-200 dark:bg-dark-700 rounded w-1/2 mb-2" />
                <div className="h-3 bg-dark-200 dark:bg-dark-700 rounded w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <FolderKanban className="h-12 w-12 text-dark-300 dark:text-dark-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-dark-900 dark:text-white mb-2">
              {searchQuery || statusFilter !== 'all' ? 'No projects found' : 'No projects yet'}
            </h3>
            <p className="text-dark-500 dark:text-dark-400 mb-6">
              {searchQuery || statusFilter !== 'all'
                ? 'Try adjusting your search or filters'
                : 'Create your first video project'}
            </p>
            {!searchQuery && statusFilter === 'all' && (
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Project
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredProjects.map(project => (
            <ProjectCard
              key={project.id}
              project={project}
              onDelete={handleDeleteProject}
              onOpenVideo={handleOpenVideo}
            />
          ))}
        </div>
      )}
      
      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <Card className="w-full max-w-md animate-slide-up">
            <CardHeader>
              <CardTitle>Create New Project</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="label">Project Title</label>
                <Input
                  value={newProjectTitle}
                  onChange={(e) => setNewProjectTitle(e.target.value)}
                  placeholder="My Awesome Video"
                  autoFocus
                />
              </div>
              
              <div>
                <label className="label">Script (Optional)</label>
                <select
                  value={newProjectScriptId}
                  onChange={(e) => setNewProjectScriptId(e.target.value)}
                  className="w-full rounded-lg border border-dark-300 bg-white px-4 py-2.5 text-sm text-dark-900 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 dark:border-dark-600 dark:bg-dark-800 dark:text-dark-100"
                >
                  <option value="">No script</option>
                  {scripts?.items?.map((script: any) => (
                    <option key={script.id} value={script.id}>
                      {script.topic} ({script.style})
                    </option>
                  ))}
                </select>
              </div>
              
              <div className="flex gap-2 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </Button>
                <Button className="flex-1" onClick={handleCreateProject} loading={createProjectMutation.isPending}>
                  Create Project
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

function ProjectCard({ project, onDelete, onOpenVideo }: { project: any; onDelete: (id: string) => void; onOpenVideo: (url: string) => void }) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-red-500" />
      case 'processing':
      case 'generating':
        return <Loader2 className="h-4 w-4 text-yellow-500 animate-spin" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }
  
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success">Completed</Badge>
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>
      case 'processing':
      case 'generating':
        return <Badge variant="warning">Processing</Badge>
      default:
        return <Badge variant="secondary">Pending</Badge>
    }
  }

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
              <Video className="h-5 w-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-dark-900 dark:text-white truncate max-w-[200px]">
                {project.title}
              </h3>
              <p className="text-xs text-dark-500 dark:text-dark-400 font-mono">{project.id.slice(0, 8)}...</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {getStatusIcon(project.status)}
            {getStatusBadge(project.status)}
          </div>
        </div>
        
        {project.prompt && (
          <p className="text-sm text-dark-600 dark:text-dark-400 mb-3 line-clamp-2">
            {project.prompt}
          </p>
        )}
        
        <div className="flex items-center gap-3 text-xs text-dark-500 dark:text-dark-400 mb-3">
          {project.model && (
            <span className="flex items-center gap-1">
              <Sparkles className="h-3 w-3" />
              {project.model}
            </span>
          )}
          {project.duration && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {project.duration}s
            </span>
          )}
          {project.resolution && (
            <span className="flex items-center gap-1">
              <Video className="h-3 w-3" />
              {project.resolution}
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {project.status === 'completed' && project.video_url && (
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={() => onOpenVideo(project.video_url)}
            >
              <Play className="h-3 w-3 mr-1" />
              View Video
            </Button>
          )}
          {project.status === 'processing' || project.status === 'generating' ? (
            <Button variant="outline" size="sm" className="flex-1" disabled>
              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
              Processing...
            </Button>
          ) : project.status === 'failed' ? (
            <Button variant="outline" size="sm" className="flex-1" disabled>
              <AlertCircle className="h-3 w-3 mr-1" />
              Failed
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="flex-1" disabled>
              <Clock className="h-3 w-3 mr-1" />
              Pending
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(project.id)}
            className="text-red-500 hover:text-red-600"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
        
        <div className="mt-3 pt-3 border-t border-dark-200 dark:border-dark-700 flex items-center justify-between text-xs text-dark-400">
          <span>Created {formatDistanceToNow(new Date(project.created_at), { addSuffix: true })}</span>
          {project.script_id && (
            <span className="flex items-center gap-1">
              <FileText className="h-3 w-3" />
              Has script
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}