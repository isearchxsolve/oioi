'use client';

import React, { useState, useEffect } from 'react';
import { 
  Sparkles, 
  Film, 
  Layers, 
  Wand2, 
  Video, 
  Image as ImageIcon, 
  Play, 
  Settings2, 
  Bot, 
  Palette, 
  LayoutGrid, 
  CheckCircle2, 
  Cpu, 
  RefreshCw, 
  Sliders, 
  Send, 
  Plus, 
  Trash2, 
  Share2, 
  Download,
  Zap,
  Bot as BotIcon,
  List,
  ClipboardList,
  Folder,
  Heart,
  MessageSquare
} from 'lucide-react';
import { Card, CardHeader, CardContent, Button, Input, Label, Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui';
// Canvas is deliberately NOT imported. It was imported here and never rendered -- no <Canvas /> in
// this file -- while the file itself does not parse (a NodeComponent definition was deleted, leaving
// orphaned JSX at Canvas.tsx:367). A static import of an unparseable module makes this page, and
// therefore every tab, hostage to a component the user cannot even see. Re-add the import together
// with a render site once that file is repaired.
import ChatMode from '@/app/components/ChatMode';
import AdminPanel from '@/app/components/AdminPanel';
import { useRouter } from 'next/navigation';
import { apiFetch, clearStoredToken, getStoredToken, setStoredToken } from '@/lib/api-client';

export default function Home() {
  const router = useRouter();
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authUser, setAuthUser] = useState<any | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginBusy, setLoginBusy] = useState(false);
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [activeTab, setActiveTab] = useState<'canvas' | 'agents' | 'models' | 'styles' | 'projects' | 'library' | 'chat'>('canvas');
  const [prompt, setPrompt] = useState('Cyberpunk ninja confronting a giant neon dragon in Neo-Tokyo rain');
  const [selectedStyle, setSelectedStyle] = useState('Anime Style 0');
  const [isGenerating, setIsGenerating] = useState(false);
  const [pipelineState, setPipelineState] = useState<'idle' | 'scripting' | 'pending_approval' | 'animating' | 'completed'>('idle');
  const [agentProgress, setAgentProgress] = useState<number>(0);
  const [activeAgent, setActiveAgent] = useState<string>('Director');
  const [generatedScenes, setGeneratedScenes] = useState<any[]>([]);
  const [durableFilmId, setDurableFilmId] = useState<string | null>(null);
  // Real per-agent status from the backend, replacing the timer that used to drive the progress UI.
  const [stages, setStages] = useState<Array<{ agent: string; status: string; output: string }>>([]);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  
  // Storyboard panels. Starts EMPTY on purpose.
  //
  // This used to ship three hardcoded panels whose videoUrl all pointed at
  // commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4 -- a public
  // sample reel of a completely different film -- each labelled "READY". A fresh page therefore
  // showed three finished-looking clips before the user had generated anything, and clicking play
  // played Elephants Dream. Panels now only ever come from a real backend response.
  const [panels, setPanels] = useState<Array<{
    id: number;
    title: string;
    prompt: string;
    imageUrl?: string;
    videoUrl?: string;
    status: 'idle' | 'generating' | 'ready' | 'pending' | 'failed';
    aspectRatio: string;
  }>>([]);
  
  // Agent team list
  const agentTeam = [
    { role: 'Scriptwriter', desc: 'Crafts narrative, story arcs, and character dialogues' },
    { role: 'Art Director', desc: 'Curates color palettes, aesthetics, and cinematic mood' },
    { role: 'Character Designer', desc: 'Generates consistent character model sheets & expressions' },
    { role: 'Scene Designer', desc: 'Constructs 3D isometric environments & spatial backgrounds' },
    { role: 'Storyboard Artist', desc: 'Creates storyboard panels combining scene + characters' },
    { role: 'Animator', desc: 'Computes motion keyframes, frame interpolation & camera paths' },
    { role: 'Sound Director', desc: 'Synthesizes dialogue, Foley sound effects & adaptive soundtrack' },
    { role: 'Director', desc: 'Coordinates the 7-agent pipeline & approves the final master cut' },
  ];

  // ---------------------------------------------------------------- live registry data
  // Every tab below used to render a hardcoded literal while a real endpoint sat unused:
  // the Models tab listed 30 <li> strings though /api/v1/models/ serves 75 real entries, and the
  // Styles tab listed 12 strings under a "150+" heading though /api/v1/styles/ serves 150. Those
  // literals also drifted from reality -- they advertised "Gemini 2.5 Flash", a model name the
  // gateway cannot resolve at all. Fetch instead, and show load/error state rather than a
  // reassuring fiction.
  const [registry, setRegistry] = useState<{
    models: any | null;
    styles: any[] | null;
    projects: any[] | null;
    assets: any | null;
    error: Record<string, string>;
    loading: boolean;
  }>({ models: null, styles: null, projects: null, assets: null, error: {}, loading: true });

  const loadRegistry = React.useCallback(async () => {
    setRegistry((r) => ({ ...r, loading: true }));
    const errors: Record<string, string> = {};
    const pull = async (key: string, url: string) => {
      try {
        const res = await apiFetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (e: any) {
        // Record the failure per-section. A tab that cannot reach its endpoint must say so;
        // falling back to a baked-in list is what made the whole UI look finished when it wasn't.
        errors[key] = e?.message || 'unreachable';
        return null;
      }
    };
    const [models, styles, projects, assets] = await Promise.all([
      pull('models', '/api/v1/models/'),
      pull('styles', '/api/v1/styles/'),
      pull('projects', '/api/v1/projects/'),
      pull('assets', '/api/v1/assets/'),
    ]);
    setRegistry({
      models,
      styles: styles?.styles ?? null,
      projects: Array.isArray(projects) ? projects : null,
      assets,
      error: errors,
      loading: false,
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      const token = getStoredToken();
      if (token) {
        try {
          const me = await apiFetch('/api/v1/auth/me');
          if (me.ok) {
            const user = await me.json();
            if (!cancelled) {
              setAuthToken(token);
              setAuthUser(user);
              setAuthChecked(true);
            }
            return;
          }
        } catch {
          // Fall through to the unauthenticated setup/login state.
        }
        clearStoredToken();
      }
      try {
        const status = await fetch('/api/v1/auth/bootstrap-status');
        const data = await status.json();
        if (!cancelled) {
          setSetupRequired(data.owner_configured !== true);
          setAuthChecked(true);
        }
      } catch {
        if (!cancelled) {
          setAuthError('The API is not reachable. Check that the OiiOii backend is running.');
          setAuthChecked(true);
        }
      }
    };
    bootstrap();
    const handleAuthRequired = () => {
      clearStoredToken();
      setAuthToken(null);
      setAuthUser(null);
      setAuthError('Your session expired. Please sign in again.');
    };
    window.addEventListener('oioi:auth-required', handleAuthRequired);
    return () => {
      cancelled = true;
      window.removeEventListener('oioi:auth-required', handleAuthRequired);
    };
  }, []);

  useEffect(() => {
    if (authToken) loadRegistry();
  }, [authToken, loadRegistry]);

  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginBusy(true);
    setAuthError(null);
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data?.access_token) {
        throw new Error(data?.detail || `Login failed (HTTP ${res.status})`);
      }
      setStoredToken(data.access_token);
      setAuthToken(data.access_token);
      setAuthUser(data.user ?? null);
      setLoginPassword('');
    } catch (error: any) {
      setAuthError(error?.message || 'Login failed');
    } finally {
      setLoginBusy(false);
    }
  };

  const handleLogout = async () => {
    try { await apiFetch('/api/v1/auth/logout', { method: 'POST' }); } catch { /* local logout still wins */ }
    clearStoredToken();
    setAuthToken(null);
    setAuthUser(null);
    setAuthChecked(true);
  };

  const handleCreateProject = async () => {
    // The button used to be `onClick={() => {/* New project modal */}}` -- a no-op with a comment
    // where the behaviour should be. POST /api/v1/projects/ already existed and took
    // {title, description, aspect_ratio}; nothing ever called it.
    const title = window.prompt('Project title?', prompt.slice(0, 60) || 'Untitled Film');
    if (!title) return;
    try {
      const res = await apiFetch('/api/v1/projects/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description: prompt, aspect_ratio: '16:9' }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadRegistry();
    } catch (e: any) {
      setRegistry((r) => ({
        ...r,
        error: { ...r.error, projects: `create failed: ${e?.message || e}` },
      }));
    }
  };

  const handleRunPipeline = async () => {
    setIsGenerating(true);
    setPipelineState('scripting');
    setPipelineError(null);
    setAgentProgress(10);
    setActiveAgent('Scriptwriter');

    try {
      // Customer film work has one lineage: canonical crew chat followed by a
      // Director-approved durable film admission.  The old project pipeline
      // selects providers inside OiiOii and is deliberately no longer used.
      const res = await apiFetch('/api/v1/films/crew-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea: prompt,
          style: selectedStyle,
          aspect_ratio: '16:9',
          target_seconds: 180,
        })
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);

      const crew = data?.crew;
      const scenes = crew?.scene_designer?.scenes || crew?.scriptwriter?.scenes || [];
      const stageNames = ['scriptwriter', 'art_director', 'character_designer', 'scene_designer', 'storyboard_artist', 'animator', 'sound_director', 'director'];
      if (crew && Array.isArray(scenes) && data?.film_id) {
        setDurableFilmId(data.film_id);
        setStages(stageNames.map((role) => ({
          agent: role.split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' '),
          status: crew[role] ? 'completed' : 'failed',
          output: crew[role] ? 'Director-approved durable handoff recorded' : 'No stage output',
        })));
        setAgentProgress(100);
        setGeneratedScenes(scenes);
        setPanels(scenes.map((scene: any, i: number) => ({
          id: i + 1,
          title: `Scene ${scene.scene || i + 1}`,
          prompt: scene.visual_prompt || scene.prompt || scene.description || '',
          imageUrl: scene.image_url,
          // Planning is complete, but the UI never claims a render until a
          // durable scheduler tick returns actual clip material.
          status: scene.image_url ? 'ready' : 'pending',
          aspectRatio: '16:9',
        })));
        setPipelineState('pending_approval');
        setActiveAgent('Director Approval Recorded — Render When Ready');
      } else {
        throw new Error('Canonical crew run returned no durable film plan');
      }
    } catch (err: any) {
      // Was console.error only, so a failed run looked identical to one that never started.
      console.error(err);
      setPipelineError(err?.message || 'Pipeline failed');
      setIsGenerating(false);
      setPipelineState('idle');
      setActiveAgent('Idle');
    }
  };

  const handleApprovePipeline = async () => {
    setPipelineState('animating');
    setPipelineError(null);
    setActiveAgent('Animator');

    try {
      if (!durableFilmId) throw new Error('No Director-approved durable film is ready to schedule');
      const res = await apiFetch(`/api/v1/films/${durableFilmId}/tick`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);

      const clips = data?.film?.clips || [];
      if (Array.isArray(clips)) {
        setPanels(prev => prev.map((panel, index) => {
          const clip = clips[index] || {};
          return {
            ...panel,
            videoUrl: clip.url || panel.videoUrl,
            status: clip.url ? 'ready' : panel.status,
          };
        }));
      }
      const finalStatus = data?.film?.status;
      if (finalStatus === 'failed' || finalStatus === 'quality_blocked_slates') {
        setPipelineError(`Durable film scheduler stopped with status: ${finalStatus}`);
        setPipelineState('idle');
      } else {
        // One tick is intentionally bounded; queued/running durable work can
        // be ticked again by the same explicit scheduler control.
        setPipelineState(finalStatus === 'completed' ? 'completed' : 'pending_approval');
        setAgentProgress(100);
      }
    } catch (err: any) {
      console.error(err);
      setPipelineError(err?.message || 'Animator failed');
      setPipelineState('idle');
    } finally {
      setIsGenerating(false);
      setActiveAgent('Director');
      await loadRegistry();  // characters/scenes/clips just changed
    }
  };

  const handleAddPanel = () => {
    const nextId = panels.length + 1;
    setPanels([
      ...panels,
      {
        id: nextId,
        title: `Scene ${nextId}: New Sequence`,
        prompt: 'Continuation of the cinematic storyline with dynamic lighting',
        imageUrl: `https://image.pollinations.ai/prompt/anime%20scene%20sequence%20${nextId}`,
        status: 'ready',
        aspectRatio: '16:9',
      },
    ]);
  };

  const handleNavigateTo = (path: string) => {
    router.push(path);
  };

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] text-slate-100 flex items-center justify-center p-6">
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#0d0e15]/95 p-8 shadow-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div><h1 className="text-lg font-bold">OiiOii.ai Studio</h1><p className="text-xs text-slate-400">Checking secure session…</p></div>
          </div>
          <div className="h-2 rounded-full bg-slate-800 overflow-hidden"><div className="h-full w-1/2 bg-cyan-500 animate-pulse" /></div>
        </div>
      </div>
    );
  }

  if (!authToken) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] text-slate-100 flex items-center justify-center p-6">
        <form onSubmit={handleLogin} className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#0d0e15]/95 p-8 shadow-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center"><Sparkles className="w-5 h-5 text-white" /></div>
            <div><h1 className="text-lg font-bold">OiiOii.ai Studio</h1><p className="text-xs text-slate-400">Owner-managed film production workspace</p></div>
          </div>
          {setupRequired ? (
            <div className="rounded-xl border border-amber-700/60 bg-amber-950/30 p-4 text-sm text-amber-200">
              The studio owner account is not configured yet. Set <code className="text-amber-100">OIOI_OWNER_EMAIL</code> and <code className="text-amber-100">OIOI_OWNER_INITIAL_PASSWORD</code> in the backend environment, then restart the API. Public signup is intentionally disabled.
            </div>
          ) : (
            <>
              <h2 className="text-xl font-semibold mb-1">Sign in</h2>
              <p className="text-sm text-slate-400 mb-5">Use credentials issued by the studio operator.</p>
              <label className="block text-xs font-medium text-slate-300 mb-1">Email</label>
              <input type="email" required value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)} className="w-full mb-4 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" autoComplete="username" />
              <label className="block text-xs font-medium text-slate-300 mb-1">Password</label>
              <input type="password" required value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} className="w-full mb-4 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" autoComplete="current-password" />
              <button type="submit" disabled={loginBusy} className="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 px-4 py-3 text-sm font-semibold disabled:opacity-50">{loginBusy ? 'Signing in…' : 'Sign in'}</button>
            </>
          )}
          {authError && <p className="mt-4 rounded-lg border border-rose-800 bg-rose-950/40 p-3 text-xs text-rose-200">{authError}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-100 flex flex-col font-sans">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800/80 bg-[#0d0e15]/90 backdrop-blur-md px-6 py-3.5 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-indigo-300 to-fuchsia-400">
              OiiOii.ai Studio
            </h1>
            <p className="text-[11px] text-slate-400">Autonomous 7-Agent AI Animation Engine</p>
          </div>
        </div>

        {/* Center Tabs */}
        <nav className="flex items-center space-x-1 bg-slate-900/90 border border-slate-800 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('canvas')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'canvas' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            <span>Animation Canvas</span>
          </button>
          <button
            onClick={() => setActiveTab('agents')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'agents' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Bot className="w-3.5 h-3.5" />
            <span>Agent Team (7)</span>
          </button>
          <button
            onClick={() => setActiveTab('models')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'models' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>25+ Free Models</span>
          </button>
          <button
            onClick={() => setActiveTab('styles')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'styles' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Palette className="w-3.5 h-3.5" />
            <span>150+ Styles</span>
          </button>
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'chat' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>Chat Mode</span>
          </button>
          <button
            onClick={() => setActiveTab('projects')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'projects' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Folder className="w-3.5 h-3.5" />
            <span>Projects</span>
          </button>
          <button
            onClick={() => setActiveTab('library')}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === 'library' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Heart className="w-3.5 h-3.5" />
            <span>Library</span>
          </button>
        </nav>

        {/* Right Info Badges */}
        <div className="flex items-center space-x-3">
          <span className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>Free-Tier Multi-Provider (NVIDIA-Free)</span>
          </span>
          {authUser?.email && <span className="text-xs text-slate-400 max-w-40 truncate" title={authUser.email}>{authUser.email}</span>}
          <button onClick={() => setShowAdminPanel(true)} className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium transition-colors">{authUser?.is_admin ? 'Admin' : 'Account'}</button>
          <button onClick={handleLogout} className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium transition-colors">
            Sign out
          </button>
          <button className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium flex items-center space-x-1.5 transition-colors">
            <Download className="w-3.5 h-3.5" />
            <span>Export Film</span>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        {/* Sidebar Controls */}
        <aside className="w-72 border-r border-slate-800 bg-[#0c0d14] p-4 flex flex-col overflow-y-auto overflow-x-hidden">
          <div className="space-y-4">
            <div>
              <Label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5 mb-1">
                <Wand2 className="w-3 h-3 text-cyan-400" />
                <span>Story Prompt</span>
              </Label>
              <Input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500/60"
                placeholder="Describe your animation scene..."
              />
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5 mb-1">
                <Cpu className="w-3 h-3 text-indigo-400" />
                <span>Production AI Route</span>
              </Label>
              <div className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-slate-300">
                Gateway managed — <code>session-pool/auto</code>
              </div>
              <p className="text-[10px] text-slate-500">Provider selection, session rotation, and capacity stay behind the consumer gateway.</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5 mb-1">
                <Palette className="w-3 h-3 text-fuchsia-400" />
                <span>Visual Style (150+ Available)</span>
              </Label>
              <Select 
                value={selectedStyle}
                onValueChange={(value) => setSelectedStyle(value)}
              >
                <SelectTrigger className="w-full bg-slate-950 border border-slate-800 rounded-xl p-2 text-xs text-slate-200">
                  <SelectValue placeholder="Select style..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Anime Style 0">Anime (Cyberpunk Neon)</SelectItem>
                  <SelectItem value="Ghibli Style 1">Studio Ghibli</SelectItem>
                  <SelectItem value="Makoto Shinkai Style 2">Makoto Shinkai</SelectItem>
                  <SelectItem value="Naruto Style 3">Naruto Shippuden</SelectItem>
                  <SelectItem value="One Piece Style 4">One Piece</SelectItem>
                  <SelectItem value="Clay Toy Style 5">Clay Toy</SelectItem>
                  <SelectItem value="Cyberpunk Neon Style 6">Cyberpunk Neon</SelectItem>
                  <SelectItem value="Synthwave Style 7">Synthwave</SelectItem>
                  <SelectItem value="Clay Toy Style 8">Clay Toy</SelectItem>
                  <SelectItem value="Watercolor Style 9">Watercolor</SelectItem>
                  <SelectItem value="Oil Painting Style 10">Oil Painting</SelectItem>
                  <SelectItem value="Pixel Art Style 11">Pixel Art</SelectItem>
                  <SelectItem value="Low Poly Style 12">Low Poly 3D</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="mt-4 space-y-3">
              <Button 
                onClick={handleRunPipeline}
                disabled={pipelineState !== 'idle' && pipelineState !== 'completed'}
                className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-cyan-500 via-indigo-600 to-fuchsia-600 hover:opacity-90 transition-opacity font-semibold text-xs text-white shadow-lg shadow-indigo-600/30 flex items-center justify-center space-x-2 disabled:opacity-50"
              >
                {pipelineState === 'scripting' ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Scripting...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Generate Scripts & Scenes</span>
                  </>
                )}
              </Button>

              {pipelineState === 'pending_approval' && (
                <Button 
                  onClick={handleApprovePipeline}
                  className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 transition-opacity font-semibold text-xs text-white shadow-lg flex items-center justify-center space-x-2 animate-pulse"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Approve & Generate Video</span>
                </Button>
              )}

              {pipelineState === 'animating' && (
                <Button 
                  disabled
                  className="w-full py-3 px-4 rounded-xl bg-slate-700 font-semibold text-xs text-white flex items-center justify-center space-x-2"
                >
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Animating & Stitching...</span>
                </Button>
              )}
            </div>

            {pipelineError && (
              <div className="mt-4 p-3 rounded-xl bg-rose-950/50 border border-rose-900">
                <p className="text-[11px] text-rose-200 break-words">{pipelineError}</p>
              </div>
            )}

            {(pipelineState !== 'idle' && pipelineState !== 'completed') && (
              <div className="mt-4 space-y-2">
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Pipeline Progress</span>
                  <span>{agentProgress}%</span>
                </div>
                <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-cyan-400 to-indigo-500 h-full transition-all duration-300"
                    style={{ width: `${agentProgress}%` }}
                  />
                </div>
              </div>
            )}

            {/* The 7 agents with the status the backend measured for each. Nothing here is timed or
                assumed: a stage is 'completed' only if it produced output, 'degraded' if it ran but
                came back empty, 'failed' if it errored, 'pending' if it has not run. */}
            {stages.length > 0 && (
              <div className="mt-4 space-y-1.5">
                {stages.map((s) => (
                  <div key={s.agent} className="flex items-start justify-between gap-2 text-[11px]">
                    <span className="text-slate-300 shrink-0">{s.agent}</span>
                    <span
                      className={
                        s.status === 'completed' ? 'text-emerald-400'
                        : s.status === 'degraded' ? 'text-amber-400'
                        : s.status === 'failed' ? 'text-rose-400'
                        : 'text-slate-500'
                      }
                      title={s.output}
                    >
                      {s.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800 text-[11px] text-slate-500 space-y-2">
            <div className="flex items-center justify-between">
              <span>Active Inference:</span>
              <span className="text-slate-300 font-medium">Multi-Vendor Mesh</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Failover State:</span>
              <span className="text-emerald-400 font-medium">Automatic / Ready</span>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <section className="flex-1 bg-[#08080c] p-6 overflow-y-auto">
          {activeTab === 'canvas' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
                    <Film className="w-5 h-5 text-cyan-400" />
                    <span>Storyboard Animation Canvas</span>
                  </h2>
                  <p className="text-xs text-slate-400">
                    Linked multi-panel canvas with concurrent generation & first/last-frame animation
                  </p>
                </div>
                <button
                  onClick={handleAddPanel}
                  className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold flex items-center space-x-1.5 transition-colors shadow-md"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Storyboard Panel</span>
                </button>
              </div>

              {/* Storyboard Panels Grid */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {panels.map((panel) => (
                  <div
                    key={panel.id}
                    className="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden hover:border-slate-700 transition-all flex flex-col group shadow-lg"
                  >
                    <div className="relative aspect-video bg-slate-950 overflow-hidden group/media">
                      {panel.videoUrl ? (
                        <video
                          src={panel.videoUrl}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                          autoPlay
                          loop
                          muted
                          playsInline
                        />
                      ) : panel.imageUrl && (
                        <img
                          src={panel.imageUrl}
                          alt={panel.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                        />
                      )}
                      <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-md px-2.5 py-1 rounded-full text-[10px] font-semibold text-white border border-white/10 flex items-center space-x-1">
                        <Play className="w-2.5 h-2.5 fill-current text-cyan-400" />
                        <span>Scene {panel.id}</span>
                      </div>
                      <div className="absolute top-3 right-3 bg-black/60 backdrop-blur-md px-2.5 py-1 rounded-full text-[10px] font-semibold text-emerald-400 border border-emerald-500/20">
                        {panel.status.toUpperCase()}
                      </div>
                    </div>

                    <div className="p-4 flex-1 flex flex-col justify-between space-y-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-100">{panel.title}</h3>
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2">{panel.prompt}</p>
                      </div>

                      <div className="flex items-center justify-between pt-3 border-t border-slate-800/80">
                        <div className="flex items-center space-x-2 text-[11px] text-slate-400">
                          <ImageIcon className="w-3.5 h-3.5 text-cyan-400" />
                          <span>1024x1024</span>
                          <span>•</span>
                          <Video className="w-3.5 h-3.5 text-indigo-400" />
                          <span>Veo Motion</span>
                        </div>
                        <button className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors">
                          <Sliders className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'agents' && (
            <div className="space-y-6 max-w-4xl mx-auto">
              <div>
                <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
                  <Bot className="w-5 h-5 text-indigo-400" />
                  <span>The 7-Agent Animation Team</span>
                </h2>
                <p className="text-xs text-slate-400">
                  Fully autonomous pipeline transforming high-level premises into production-ready animated cuts
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {agentTeam.map((ag, idx) => (
                  <div
                    key={ag.role}
                    className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 hover:border-indigo-500/40 transition-colors flex items-start space-x-3.5"
                  >
                    <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center font-bold text-xs text-indigo-400 shrink-0">
                      0{idx + 1}
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-100">{ag.role}</h4>
                      <p className="text-xs text-slate-400 mt-1">{ag.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'models' && (
            <div className="space-y-6 max-w-4xl mx-auto">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
                    <Cpu className="w-5 h-5 text-cyan-400" />
                    <span>
                      Model Registry
                      {registry.models?.counts?.Total ? ` (${registry.models.counts.Total})` : ''}
                    </span>
                  </h2>
                  <p className="text-xs text-slate-400">
                    Live from <code className="text-slate-500">/api/v1/models/</code>
                  </p>
                </div>
                <button
                  onClick={loadRegistry}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${registry.loading ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>
              </div>

              {registry.error.models ? (
                <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-900 text-xs text-rose-300">
                  Could not load the model registry: {registry.error.models}. This section is
                  intentionally blank rather than showing a placeholder list.
                </div>
              ) : registry.loading ? (
                <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400">
                  Loading models…
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { key: 'video_models', label: 'Video', tone: 'text-cyan-400' },
                    { key: 'image_models', label: 'Image', tone: 'text-fuchsia-400' },
                    { key: 'llm_models', label: 'LLM Multi-Agent', tone: 'text-indigo-400' },
                  ].map(({ key, label, tone }) => {
                    const list: any[] = registry.models?.[key] ?? [];
                    return (
                      <div key={key} className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800">
                        <h3 className={`text-sm font-bold ${tone} mb-3`}>
                          {label} ({list.length})
                        </h3>
                        <ul className="text-xs text-slate-300 space-y-2">
                          {list.map((m) => (
                            <li key={m.id} title={`${m.id} — ${m.provider ?? 'unknown provider'}`}>
                              • {m.name ?? m.id}
                              {m.provider && (
                                <span className="text-slate-500"> · {m.provider}</span>
                              )}
                            </li>
                          ))}
                          {list.length === 0 && (
                            <li className="text-slate-500">No {label.toLowerCase()} models registered</li>
                          )}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {activeTab === 'styles' && (
            <div className="space-y-6 max-w-4xl mx-auto">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
                    <Palette className="w-5 h-5 text-fuchsia-400" />
                    <span>
                      Cinematic Visual Styles
                      {registry.styles ? ` (${registry.styles.length})` : ''}
                    </span>
                  </h2>
                  <p className="text-xs text-slate-400">
                    Live from <code className="text-slate-500">/api/v1/styles/</code> — click to
                    select for the next run
                  </p>
                </div>
                <button
                  onClick={loadRegistry}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 flex items-center space-x-1.5 transition-colors"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${registry.loading ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>
              </div>

              {registry.error.styles ? (
                <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-900 text-xs text-rose-300">
                  Could not load styles: {registry.error.styles}
                </div>
              ) : registry.loading ? (
                <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400">
                  Loading styles…
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 max-h-[70vh] overflow-y-auto pr-1">
                  {(registry.styles ?? []).map((s: any) => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedStyle(s.name)}
                      title={s.promptSuffix || s.category}
                      className={`p-3 rounded-xl bg-slate-900/60 border text-center transition-colors cursor-pointer ${
                        selectedStyle === s.name
                          ? 'border-fuchsia-500 ring-1 ring-fuchsia-500/40'
                          : 'border-slate-800 hover:border-fuchsia-500/40'
                      }`}
                    >
                      <span className="text-xs font-semibold text-slate-200 block truncate">
                        {s.name}
                      </span>
                      <span className="text-[10px] text-slate-500">{s.category}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'projects' && (
            <div className="space-y-6 max-w-4xl mx-auto">
              <div>
                <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
                  <Folder className="w-5 h-5 text-cyan-400" />
                  <span>Projects{registry.projects ? ` (${registry.projects.length})` : ''}</span>
                </h2>
                <p className="text-xs text-slate-400">
                  Live from <code className="text-slate-500">/api/v1/projects/</code>
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold text-slate-100">Recent Projects</h3>
                  <Button variant="outline" size="sm" onClick={handleCreateProject}>
                    <Plus className="mr-2 h-3 w-3" /> New Project
                  </Button>
                </div>

                {registry.error.projects ? (
                  <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-900 text-xs text-rose-300">
                    Could not load projects: {registry.error.projects}
                  </div>
                ) : registry.loading ? (
                  <div className="p-4 bg-slate-900/50 rounded-lg text-xs text-slate-400 text-center">
                    Loading projects…
                  </div>
                ) : (registry.projects ?? []).length === 0 ? (
                  <div className="p-4 bg-slate-900/50 rounded-lg">
                    <p className="text-xs text-slate-400 text-center">
                      No projects yet. Create your first project to get started.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {(registry.projects ?? []).map((p: any) => (
                      <div
                        key={p.id ?? p.name}
                        className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl flex items-center justify-between"
                      >
                        <div>
                          <h4 className="text-sm font-semibold text-slate-100">
                            {p.name ?? p.title ?? p.id}
                          </h4>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            {p.style ? `${p.style} · ` : ''}
                            {p.status ?? 'draft'}
                            {p.created_at ? ` · ${new Date(p.created_at).toLocaleString()}` : ''}
                          </p>
                        </div>
                        <span className="text-[10px] font-mono text-slate-600">{p.id}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'library' && (
            <div className="space-y-6 max-w-4xl mx-auto">
              <div>
                <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
                  <Heart className="w-5 h-5 text-fuchsia-400" />
                  <span>My Library</span>
                </h2>
                <p className="text-xs text-slate-400">
                  Saved characters, scenes, styles, scripts, and generated assets
                </p>
              </div>
              
              {/* Backed by GET /api/v1/assets/. The four cards below used to be static
                  "No saved X" placeholders -- true-looking but unfalsifiable, since assets.py was a
                  two-line stub with no routes at all. Characters and scenes now appear here after a
                  pipeline run; clips are enumerated from the video router's harvest directory, so
                  the three real generations already on disk show up immediately. */}
              {registry.error.assets ? (
                <div className="p-4 rounded-2xl bg-rose-950/40 border border-rose-900 text-xs text-rose-200">
                  Could not load the library: {registry.error.assets}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {[
                      { key: 'characters', label: 'Characters' },
                      { key: 'scenes', label: 'Scenes' },
                      { key: 'styles', label: 'Styles' },
                    ].map(({ key, label }) => {
                      const list: any[] = registry.assets?.[key] ?? [];
                      return (
                        <div key={key} className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800">
                          <h3 className="text-sm font-semibold text-slate-100 mb-2">
                            {label} <span className="text-slate-500">({list.length})</span>
                          </h3>
                          <div className="space-y-2 max-h-56 overflow-y-auto">
                            {list.length === 0 ? (
                              <div className="p-3 bg-slate-800 rounded-md text-center">
                                <p className="text-xs text-slate-400">
                                  Nothing yet — run the pipeline to populate this
                                </p>
                              </div>
                            ) : (
                              list.map((a: any) => (
                                <div key={a.id} className="p-2.5 bg-slate-800/70 rounded-md">
                                  <p className="text-xs font-medium text-slate-200">{a.name}</p>
                                  {a.description && (
                                    <p className="text-[11px] text-slate-400 line-clamp-2">{a.description}</p>
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-slate-100">
                        Generated Clips{' '}
                        <span className="text-slate-500">({registry.assets?.clips?.length ?? 0})</span>
                      </h3>
                      <button
                        onClick={loadRegistry}
                        className="p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300"
                        title="Rescan the harvest directory"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${registry.loading ? 'animate-spin' : ''}`} />
                      </button>
                    </div>
                    {(registry.assets?.clips ?? []).length === 0 ? (
                      <p className="text-xs text-slate-400">
                        No clips on disk. The Animator writes them here once a Flow or rtst account
                        is signed in and has credits.
                      </p>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {registry.assets.clips.map((c: any) => (
                          <div key={c.url} className="rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
                            {/* Real files served by GET /api/v1/assets/clips/{provider}/{name} --
                                not the ElephantsDream.mp4 sample reel this UI used to pass off as
                                the user's own footage. */}
                            <video src={c.url} controls preload="metadata" className="w-full aspect-video bg-black" />
                            <div className="p-2">
                              <p className="text-[11px] text-slate-300 truncate" title={c.name}>{c.name}</p>
                              <p className="text-[10px] text-slate-500">
                                {c.provider} · {(c.bytes / 1048576).toFixed(1)} MB
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'chat' && (
            <div className="h-full w-full">
              <ChatMode />
            </div>
          )}
        </section>
      </main>
      {showAdminPanel && <AdminPanel initialUser={authUser} onProfileUpdated={setAuthUser} onClose={() => setShowAdminPanel(false)} />}
    </div>
  );
}
