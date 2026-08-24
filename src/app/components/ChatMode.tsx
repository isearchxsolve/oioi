'use client';

import React, { useState, useEffect, useRef } from 'react';
import { 
  Bot, 
  Send, 
  Mic, 
  MicOff, 
  RotateCcw, 
  Copy, 
  Check, 
  X,
  Sparkles,
  MessageSquare,
  Zap,
  Settings
} from 'lucide-react';
import { Button, Card, CardHeader, CardContent, Input, Label, Select, SelectTrigger, SelectValue, SelectContent, SelectItem, Toaster, toast } from '@/components/ui';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'agent';
  content: string;
  agent?: string;
  timestamp: Date;
  status?: 'sending' | 'sent' | 'error';
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  mode: 'smart' | 'chat';
}

const CHAT_API = '/api/v1/chat';

// Sentinel for "no explicit model, let the backend decide". Radix's Select rejects an empty-string
// item value outright, so the empty selection needs a placeholder token.
const SERVER_DEFAULT_MODEL = '__server_default__';

const ChatMode: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: "Welcome to OiiOii.ai Chat Mode! I'm your creative director. How can I help you create an animated story today? You can:\n\n• Describe a story idea and I'll guide the 7-agent team\n• Ask me to refine specific elements (characters, scenes, style)\n• Request re-generation of any agent's output\n• Get creative suggestions and feedback\n\nWhat's your story idea?",
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [agentProgress, setAgentProgress] = useState<Record<string, number>>({});
  const [mode, setMode] = useState<'smart' | 'chat'>('chat');
  // Empty = server default. Was 'gemini-2.5-flash', which is not a model this gateway serves:
  // MEASURED 2026-08-24 it answers 401 "No cookie auth credentials found". The value was also
  // never transmitted (see the mutation below), so the dropdown could not influence an answer.
  const [selectedModel, setSelectedModel] = useState('');
  // The backend keys a conversation by sessionId and returns the one it used. This was thrown away,
  // so every message opened a NEW session: the Director had no memory of the previous turn and
  // "Recent Chats" grew one entry per message instead of one per conversation.
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  // Scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch chat sessions
  const { data: sessions } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: async () => {
      try {
        const { data } = await axios.get(`${CHAT_API}/sessions`);
        return data;
      } catch {
        return [];
      }
    }
  });

  // The model list the "Model" dropdown offers. Was five hardcoded ids -- gemini-2.5-flash,
  // llama-3.3-70b, claude-3-5-sonnet, mixtral-8x7b, qwen-2.5-72b -- written by hand and never
  // checked against the registry, so a user could pick a model the backend cannot reach.
  const { data: modelRegistry } = useQuery({
    queryKey: ['llm-models'],
    queryFn: async () => {
      const { data } = await axios.get('/api/v1/models/');
      return data;
    },
  });
  const llmModels: any[] = modelRegistry?.llm_models ?? [];

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: async ({ message }: { message: string }) => {
      const { data } = await axios.post(`${CHAT_API}/send`, {
        message,
        sessionId,
        mode,
        // Actually sent now, so the dropdown selects the model that answers.
        model: selectedModel || undefined,
      });
      return data;
    },
    onSuccess: (response) => {
      // Keep the conversation on one session, and let the sidebar see the new turn.
      if (response.sessionId) setSessionId(response.sessionId);
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      // Handle agent streaming updates
      if (response.agentUpdates) {
        response.agentUpdates.forEach((update: any) => {
          setAgentProgress(prev => ({ ...prev, [update.agent]: update.progress }));
          if (update.status === 'running') {
            setActiveAgent(update.agent);
          }
        });
      }
    }
  });

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: new Date(),
      status: 'sent'
    };
    
    setMessages(prev => [...prev, userMessage]);
    const currentInput = input;
    setInput('');
    setIsLoading(true);
    
    try {
      const response = await sendMessageMutation.mutateAsync({ message: currentInput });
      
      // Add assistant response
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.content || 'Processing...',
        timestamp: new Date(),
        status: 'sent'
      };
      
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error: any) {
      // Show what actually went wrong. A bare "Failed to send message" hid a 401 from the gateway
      // ("No cookie auth credentials found") behind the same words as a network drop.
      const detail =
        error?.response?.data?.detail ||
        error?.response?.data?.error ||
        error?.message ||
        'unknown error';
      toast.error(`Chat failed: ${detail}`);
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Request failed: ${detail}`,
        timestamp: new Date(),
        status: 'error'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAgentAction = async (action: string, agentName: string) => {
    // This used to be a `for (i=0; i<=100; i+=10)` sleep loop that filled a progress bar over two
    // seconds and then announced "<agent> has completed: <action>" -- no request was ever made and
    // no agent ever ran. It is a real call now: the quick action asks the Director, on this same
    // session, to do that agent's job, so the answer lands in the transcript like any other turn.
    if (isLoading) return;
    setActiveAgent(agentName);
    setAgentProgress(prev => ({ ...prev, [agentName]: 10 }));
    setIsLoading(true);

    const ask = `As the ${agentName}, ${action.toLowerCase()} for the story we are working on. `
      + `If we have not settled on a story yet, say so and ask for one instead of inventing it.`;
    setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      role: 'user',
      content: ask,
      timestamp: new Date(),
      status: 'sent',
    }]);

    try {
      const response = await sendMessageMutation.mutateAsync({ message: ask });
      setAgentProgress(prev => ({ ...prev, [agentName]: 100 }));
      setMessages(prev => [...prev, {
        id: `agent-${Date.now()}`,
        role: 'agent',
        content: response.content || '(empty response)',
        agent: agentName,
        timestamp: new Date(),
        status: 'sent',
      }]);
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || 'unknown error';
      setAgentProgress(prev => ({ ...prev, [agentName]: 0 }));
      toast.error(`${agentName} failed: ${detail}`);
      setMessages(prev => [...prev, {
        id: `agent-error-${Date.now()}`,
        role: 'agent',
        content: `${agentName} failed: ${detail}`,
        agent: agentName,
        timestamp: new Date(),
        status: 'error',
      }]);
    } finally {
      setIsLoading(false);
      setActiveAgent(null);
    }
  };

  const handleNewChat = () => {
    // Drop the server-side session too, otherwise "New chat" kept posting into the old
    // conversation and the Director carried over context the user thought they had cleared.
    setSessionId(undefined);
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: "New chat started! What would you like to create today?",
        timestamp: new Date()
      }
    ]);
  };

  const AGENTS = [
    { name: 'Scriptwriter', action: 'Write/Refine Script', description: 'Story structure, dialogue, scenes' },
    { name: 'Art Director', action: 'Define Visual Style', description: 'Color palette, lighting, mood' },
    { name: 'Character Designer', action: 'Design Characters', description: 'Appearance, expressions, consistency' },
    { name: 'Scene Designer', action: 'Design Scenes', description: 'Environments, backgrounds, composition' },
    { name: 'Storyboard Artist', action: 'Create Storyboard', description: 'Panel layout, camera angles' },
    { name: 'Animator', action: 'Animate Scenes', description: 'Motion, timing, camera movement' },
    { name: 'Sound Director', action: 'Design Audio', description: 'Music, SFX, voice lines' },
    { name: 'Director', action: 'Final Review', description: 'Approval, final cut, export' },
  ];

  return (
    <div className="flex h-screen bg-[#0a0a0f] text-slate-100">
      {/* Sidebar */}
      <aside className="w-80 border-r border-slate-800 bg-[#0c0d14] flex flex-col">
        <div className="p-4 border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-6 h-6 text-cyan-400" />
            <h2 className="font-bold text-lg">Chat Mode</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">Conversational agent control</p>
        </div>

        {/* Mode Selector */}
        <div className="p-4 border-b border-slate-800">
          <div className="flex space-x-2">
            <Button 
              variant={mode === 'smart' ? 'default' : 'outline'} 
              onClick={() => setMode('smart')}
              className="flex-1"
            >
              <Zap className="mr-2 h-3 w-3" />
              <span className="text-xs">Smart</span>
            </Button>
            <Button 
              variant={mode === 'chat' ? 'default' : 'outline'} 
              onClick={() => setMode('chat')}
              className="flex-1"
            >
              <MessageSquare className="mr-2 h-3 w-3" />
              <span className="text-xs">Chat</span>
            </Button>
          </div>
          <p className="text-xs text-slate-400 mt-2 text-center">
            {mode === 'smart' 
              ? 'One-click full pipeline execution' 
              : 'Step-by-step conversational control'}
          </p>
        </div>

        {/* Model Selector */}
        <div className="p-4 border-b border-slate-800">
          <Label className="text-xs font-semibold text-slate-300 mb-2 block">
            Model {llmModels.length > 0 && (
              <span className="font-normal text-slate-500">({llmModels.length} available)</span>
            )}
          </Label>
          <Select
            value={selectedModel || SERVER_DEFAULT_MODEL}
            onValueChange={(v) => setSelectedModel(v === SERVER_DEFAULT_MODEL ? '' : v)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select model..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SERVER_DEFAULT_MODEL}>Server default</SelectItem>
              {llmModels.map((m: any) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.name ?? m.id}
                  {m.provider ? ` — ${m.provider}` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Agent Quick Actions */}
        <div className="flex-1 p-4 overflow-y-auto">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Quick Agent Actions</h3>
          <div className="space-y-2">
            {AGENTS.map((agent) => (
              <Button
                key={agent.name}
                variant="outline"
                size="sm"
                className="w-full justify-start text-left px-3 py-2"
                onClick={() => handleAgentAction(agent.action, agent.name)}
                disabled={isLoading}
              >
                <div className="flex items-center space-x-2 w-full">
                  <Bot className="h-4 w-4 text-indigo-400" />
                  <div className="flex-1 text-left">
                    <p className="text-xs font-medium">{agent.name}</p>
                    <p className="text-[10px] text-slate-400">{agent.description}</p>
                  </div>
                  {agentProgress[agent.name] !== undefined && agentProgress[agent.name] > 0 && (
                    <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-indigo-500 transition-all duration-300"
                        style={{ width: `${agentProgress[agent.name]}%` }}
                      />
                    </div>
                  )}
                </div>
              </Button>
            ))}
          </div>
        </div>

        {/* Session History */}
        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-300">Recent Chats</h3>
            <Button variant="ghost" size="icon" onClick={handleNewChat} className="h-6 w-6">
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {sessions?.slice(0, 5).map((session: any) => (
              <button
                key={session.id}
                className={`w-full text-left p-2 rounded text-xs transition-colors ${
                  session.id === sessionId
                    ? 'bg-slate-800 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
                onClick={() => {
                  // The click handler was an empty body with a `// Load session` comment, so the
                  // list was decorative. The session rows carry their full message array, so
                  // restoring one is just a re-hydrate -- no extra fetch needed.
                  setSessionId(session.id);
                  setMessages(
                    (session.messages ?? []).map((m: any, i: number) => ({
                      id: `${session.id}-${i}`,
                      role: m.role,
                      content: m.content,
                      timestamp: new Date((session.updatedAt ?? 0) * 1000),
                      status: 'sent' as const,
                    }))
                  );
                }}
              >
                {session.title}
              </button>
            ))}
            {!sessions?.length && (
              <p className="text-xs text-slate-500 text-center py-4">No recent chats</p>
            )}
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Chat Header */}
        <header className="border-b border-slate-800 bg-[#0d0e15]/90 backdrop-blur-md px-6 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Bot className="w-6 h-6 text-cyan-400" />
            <div>
              <h2 className="font-semibold">Creative Director</h2>
              <p className="text-xs text-slate-400">
                {activeAgent ? `${activeAgent} is working...` : 'Ready to assist'}
              </p>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            {activeAgent && (
              <div className="flex items-center space-x-2 px-3 py-1 bg-indigo-600/20 border border-indigo-500/30 rounded-full">
                <Bot className="h-3 w-3 text-indigo-400" />
                <span className="text-xs font-medium text-indigo-300">{activeAgent}</span>
                <div className="w-20 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-indigo-500 animate-pulse"
                    style={{ width: `${agentProgress[activeAgent] || 0}%` }}
                  />
                </div>
              </div>
            )}
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.map((message) => (
            <div 
              key={message.id} 
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[70%] ${message.role === 'user' ? 'order-2' : 'order-1'}`}>
                <div className={`flex items-start space-x-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${message.role === 'user' ? 'bg-slate-700' : 'bg-indigo-600'}`}>
                    {message.role === 'user' ? (
                      <span className="text-xs font-bold">U</span>
                    ) : message.role === 'agent' ? (
                      <Bot className="h-4 w-4 text-white" />
                    ) : (
                      <Sparkles className="h-4 w-4 text-white" />
                    )}
                  </div>
                  
                  <div className={`max-w-full ${message.role === 'user' ? 'text-right' : ''}`}>
                    {(message.role === 'assistant' || message.role === 'agent') && (
                      <p className="text-xs text-slate-400 mb-1">
                        {message.agent ? `${message.agent} • ` : ''}Assistant
                      </p>
                    )}
                    
                    <div 
                      className={`rounded-2xl p-4 ${
                        message.role === 'user' 
                          ? 'bg-indigo-600 text-white rounded-br-none' 
                          : message.role === 'agent'
                            ? 'bg-indigo-600/20 border border-indigo-500/30 text-slate-100 rounded-bl-none'
                            : 'bg-slate-800 text-slate-100 rounded-bl-none'
                      }`}
                    >
                      <p className="whitespace-pre-wrap text-sm">{message.content}</p>
                    </div>
                    
                    <p className={`text-[10px] text-slate-500 mt-1 ${message.role === 'user' ? 'text-right' : ''}`}>
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="max-w-[70%]">
                <div className="flex items-start space-x-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center">
                    <Sparkles className="h-4 w-4 text-white" />
                  </div>
                  <div className="bg-slate-800 rounded-2xl rounded-bl-none p-4">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-800 bg-[#0d0e15]/90 backdrop-blur-md p-4">
          <div className="flex items-end space-x-3">
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message the Creative Director... (Enter to send, Shift+Enter for new line)"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 pr-12 text-sm text-slate-200 focus:outline-none focus:border-cyan-500/60 resize-none min-h-[50px] max-h-48"
                rows={1}
              />
            </div>
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              size="icon"
              className="h-10 w-10 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50"
            >
              <Send className="h-5 w-5" />
            </Button>
          </div>
          <p className="text-[10px] text-slate-500 text-center mt-2">
            {mode === 'smart' 
              ? 'Smart Mode: One-click full pipeline. Describe your idea and watch the team work.'
              : 'Chat Mode: Guide each agent step by step. Ask for refinements, re-generations, or creative input.'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default ChatMode;