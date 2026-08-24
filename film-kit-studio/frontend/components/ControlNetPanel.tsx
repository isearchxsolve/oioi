"use client";

import { useState, useCallback, useRef, useEffect } from 'react';
import type { ControlNetType } from '@/lib/types';

interface ControlNetTypeConfig {
  key: ControlNetType;
  label: string;
  desc: string;
  icon: string;
}

const CONTROLNET_TYPES: ControlNetTypeConfig[] = [
  { key: 'canny', label: 'Canny Edges', desc: 'Structure & outlines', icon: '📐' },
  { key: 'depth', label: 'Depth Map', desc: '3D layout & distance', icon: '📏' },
  { key: 'openpose', label: 'OpenPose', desc: 'Human pose & gesture', icon: '🕺' },
  { key: 'normal', label: 'Normal Map', desc: 'Surface orientation', icon: '📐' },
  { key: 'lineart', label: 'Line Art', desc: 'Clean line preservation', icon: '✏️' },
  { key: 'tile', label: 'Tile/Upscale', desc: 'High-res detail', icon: '🔍' },
] as const;

interface ControlNetInput {
  type: ControlNetType;
  image_url: string;
  scale: number;
  guidance_start: number;
  guidance_end: number;
}

interface ControlNetPanelProps {
  inputs: ControlNetInput[];
  onUpdate?: (inputs: ControlNetInput[]) => void;
  disabled?: boolean;
}

function ControlNetCard({ 
  typeConfig, 
  input, 
  preview, 
  isUploading, 
  disabled, 
  onFileSelect, 
  onRemove, 
  onScaleChange, 
  onGuidanceChange 
}: {
  typeConfig: typeof CONTROLNET_TYPES[0];
  input: ControlNetInput | undefined;
  preview: string | undefined;
  isUploading: boolean;
  disabled: boolean;
  onFileSelect: (file: File) => void;
  onRemove: () => void;
  onScaleChange: (scale: number) => void;
  onGuidanceChange: (field: 'guidance_start' | 'guidance_end', value: number) => void;
}) {
  const { key, label, desc, icon } = typeConfig;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.add('ring-2', 'ring-brand-500');
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.currentTarget.classList.remove('ring-2', 'ring-brand-500');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.remove('ring-2', 'ring-brand-500');
    const file = e.dataTransfer.files[0];
    if (file) onFileSelect(file);
  };

  return (
    <div className={`relative p-3 rounded-lg border-2 transition-all ${
      input 
        ? 'border-brand-500/50 bg-brand-500/5' 
        : 'border-gray-700 hover:border-gray-600'
    }`}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="absolute inset-0 opacity-0 cursor-pointer"
        onChange={(e) => e.target.files?.[0] && onFileSelect(e.target.files[0])}
        disabled={disabled || isUploading}
      />

      <div
        className="aspect-video rounded bg-gray-900/50 relative overflow-hidden"
        onClick={() => !disabled && !isUploading && triggerFileInput()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {preview ? (
          <>
            <img
              src={preview}
              alt={`${label} preview`}
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
              <span className="text-xs text-white/80 truncate">Uploaded</span>
              <button
                onClick={(e) => { e.stopPropagation(); onRemove(); }}
                className="p-1 bg-red-500/80 hover:bg-red-500 rounded text-white text-xs"
                title="Remove"
              >
                ✕
              </button>
            </div>
          </>
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-gray-500">
            <span className="text-3xl mb-1">{icon}</span>
            <span className="font-medium text-sm">{label}</span>
            <span className="text-xs">{desc}</span>
            {!disabled && (
              <span className="mt-2 text-xs text-gray-500">Click or drag to upload</span>
            )}
          </div>
        )}
        
        {isUploading && (
          <div className="absolute inset-0 bg-black/70 flex items-center justify-center">
            <div className="spinner" style={{ width: 24, height: 24 }} />
          </div>
        )}
      </div>

      {input && (
        <div className="mt-2 space-y-2 pt-2 border-t border-gray-700">
          <div>
            <label className="text-xs text-gray-400">Strength: {input.scale.toFixed(1)}</label>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={input.scale}
              onChange={(e) => onScaleChange(parseFloat(e.target.value))}
              className="w-full accent-brand-500"
              disabled={disabled}
            />
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <label>
              Start: <input type="number" min="0" max="1" step="0.1" value={input.guidance_start} onChange={(e) => onGuidanceChange('guidance_start', parseFloat(e.target.value))} className="w-full input-field bg-gray-800" disabled={disabled} />
            </label>
            <label>
              End: <input type="number" min="0" max="1" step="0.1" value={input.guidance_end} onChange={(e) => onGuidanceChange('guidance_end', parseFloat(e.target.value))} className="w-full input-field bg-gray-800" disabled={disabled} />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}

export function ControlNetPanel({ inputs: initialInputs, onUpdate, disabled = false }: ControlNetPanelProps) {
  const [inputs, setInputs] = useState<ControlNetInput[]>(initialInputs);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState<Record<string, boolean>>({});

  // Sync with props
  useEffect(() => {
    setInputs(initialInputs);
  }, [initialInputs]);

  const handleFileSelect = useCallback((type: string, file: File) => {
    if (!file.type.startsWith('image/')) return;

    setUploading(prev => ({ ...prev, [type]: true }));

    try {
      const url = URL.createObjectURL(file);
      setPreviewUrls(prev => ({ ...prev, [type]: url }));
      
      const newInput: ControlNetInput = {
        type: type as ControlNetType,
        image_url: url,
        scale: 1.0,
        guidance_start: 0.0,
        guidance_end: 1.0,
      };
      
      setInputs(prev => {
        const existing = prev.find(i => i.type === type);
        if (existing) {
          return prev.map(i => i.type === type ? newInput : i);
        }
        return [...prev, newInput];
      });
      
      onUpdate?.(inputs);
    } catch (e) {
      console.error('Failed to process ControlNet image:', e);
    } finally {
      setUploading(prev => ({ ...prev, [type]: false }));
    }
  }, [inputs, onUpdate]);

  const handleRemove = useCallback((type: string) => {
    setInputs(prev => prev.filter(i => i.type !== type));
    setPreviewUrls(prev => {
      const next = { ...prev };
      if (next[type]) {
        URL.revokeObjectURL(next[type]);
        delete next[type];
      }
      return next;
    });
    onUpdate?.(inputs.filter(i => i.type !== type));
  }, [inputs, onUpdate]);

  const handleScaleChange = useCallback((type: string, scale: number) => {
    setInputs(prev => prev.map(i => 
      i.type === type ? { ...i, scale: Math.max(0, Math.min(2, scale)) } : i
    ));
  }, []);

  const handleGuidanceChange = useCallback((type: string, field: 'guidance_start' | 'guidance_end', value: number) => {
    setInputs(prev => prev.map(i => 
      i.type === type ? { ...i, [field]: Math.max(0, Math.min(1, value)) } : i
    ));
  }, []);

  // Sync with props
  useEffect(() => {
    setInputs(initialInputs);
  }, [initialInputs]);

  return (
    <div className="glass-panel p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-lg">🎛️ ControlNet Conditioning</h3>
        {inputs.length > 0 && (
          <span className="px-2 py-0.5 bg-brand-500/20 text-brand-400 text-xs rounded">
            {inputs.length} active
          </span>
        )}
      </div>

      <p className="text-sm text-gray-400">
        Upload reference images to guide structure, pose, depth, or style. 
        Each type controls a different aspect of generation.
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {CONTROLNET_TYPES.map((typeConfig) => {
          const input = inputs.find(i => i.type === typeConfig.key);
          const preview = previewUrls[typeConfig.key];
          const isUploading = uploading[typeConfig.key];

          return (
            <ControlNetCard
              key={typeConfig.key}
              typeConfig={typeConfig}
              input={input}
              preview={preview}
              isUploading={isUploading}
              disabled={disabled}
              onFileSelect={(file) => handleFileSelect(typeConfig.key, file)}
              onRemove={() => handleRemove(typeConfig.key)}
              onScaleChange={(scale) => handleScaleChange(typeConfig.key, scale)}
              onGuidanceChange={(field, value) => handleGuidanceChange(typeConfig.key, field, value)}
            />
          );
        })}
      </div>

      {inputs.length > 0 && (
        <div className="p-3 bg-white/5 rounded-lg text-sm">
          <div className="font-medium mb-1">Active Conditioning:</div>
          <div className="flex flex-wrap gap-2">
            {inputs.map(i => (
              <span key={i.type} className="px-2 py-0.5 bg-brand-500/20 text-brand-400 rounded text-xs">
                {CONTROLNET_TYPES.find(t => t.key === i.type)?.icon} {i.type} ({i.scale.toFixed(1)}x)
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}