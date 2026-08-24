// CharacterPanel.tsx - Character management panel for the project detail page

"use client";

import { useState, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { api } from "@/lib/api";
import type { Character, CharacterCreate, Scene } from "@/lib/types";

interface CharacterPanelProps {
  projectId: string;
  scenes: Scene[];
  onSceneUpdate: (sceneId: string, data: { character_id: string | null }) => void;
}

export function CharacterPanel({ projectId, scenes, onSceneUpdate }: CharacterPanelProps) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newCharacter, setNewCharacter] = useState<CharacterCreate>({ name: "", description: "" });
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [uploading, setUploading] = useState<string | null>(null);

  useEffect(() => {
    loadCharacters();
  }, [projectId]);

  const loadCharacters = async () => {
    try {
      const data = await api.listCharacters(projectId);
      setCharacters(data);
    } catch (err) {
      console.error("Failed to load characters:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCharacter.name.trim()) return;
    setCreating(true);
    try {
      const character = await api.createCharacter(projectId, newCharacter);
      setCharacters((prev) => [...prev, character]);
      setNewCharacter({ name: "", description: "" });
      setShowForm(false);
    } catch (err) {
      console.error("Failed to create character:", err);
      alert("Failed to create character");
    } finally {
      setCreating(false);
    }
  };

  const handleUpdate = async (charId: string) => {
    try {
      const updated = await api.updateCharacter(projectId, charId, { name: editName, description: editDesc });
      setCharacters((prev) => prev.map((c) => (c.id === charId ? updated : c)));
      setEditingId(null);
    } catch (err) {
      console.error("Failed to update character:", err);
      alert("Failed to update character");
    }
  };

  const handleDelete = async (charId: string) => {
    if (!confirm("Delete this character and its reference image?")) return;
    try {
      await api.deleteCharacter(projectId, charId);
      setCharacters((prev) => prev.filter((c) => c.id !== charId));
    } catch (err) {
      console.error("Failed to delete character:", err);
      alert("Failed to delete character");
    }
  };

  const handleImageUpload = async (charId: string, files: File[]) => {
    const file = files[0];
    if (!file) return;
    setUploading(charId);
    try {
      const updated = await api.uploadCharacterImage(projectId, charId, file);
      setCharacters((prev) => prev.map((c) => (c.id === charId ? updated : c)));
    } catch (err) {
      console.error("Failed to upload image:", err);
      alert("Failed to upload image");
    } finally {
      setUploading(null);
    }
  };

  const getImageUrl = (char: Character) => {
    if (!char.reference_image_path) return null;
    return api.imageUrl(projectId, char.reference_image_path.split("/").pop()!);
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-[var(--text-secondary)]">
        Loading characters...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          👥 Characters
          <span className="text-xs px-2 py-0.5 bg-[var(--bg-tertiary)] rounded-full text-[var(--text-secondary)]">
            {characters.length}
          </span>
        </h3>
        <button
          onClick={() => setShowForm(!showForm)}
          className="text-sm px-3 py-1.5 bg-[var(--accent)] text-white rounded hover:opacity-90 transition-opacity"
        >
          {showForm ? "Cancel" : "+ Add Character"}
        </button>
      </div>

      {/* Create Character Form */}
      {showForm && (
        <form onSubmit={handleCreate} className="space-y-3 p-4 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color)]">
          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Name *</label>
            <input
              type="text"
              value={newCharacter.name}
              onChange={(e) => setNewCharacter({ ...newCharacter, name: e.target.value })}
              required
              className="w-full px-3 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              placeholder="e.g., Detective Sarah"
              disabled={creating}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Description</label>
            <textarea
              value={newCharacter.description}
              onChange={(e) => setNewCharacter({ ...newCharacter, description: e.target.value })}
              rows={3}
              className="w-full px-3 py-2 bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              placeholder="Visual description for prompt conditioning: tall, dark hair, wears trench coat, serious expression..."
              disabled={creating}
            />
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              This description is folded into visual prompts as an identity lock.
            </p>
          </div>
          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={creating || !newCharacter.name.trim()}
              className="flex-1 px-4 py-2 bg-[var(--accent)] text-white rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {creating ? "Creating..." : "Create Character"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-[var(--bg-tertiary)] text-[var(--text-secondary)] rounded hover:bg-[var(--border-color)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Character List */}
      <div className="space-y-3">
        {characters.length === 0 && !showForm ? (
          <div className="p-6 text-center text-[var(--text-secondary)] border-2 border-dashed border-[var(--border-color)] rounded-lg">
            <p className="text-lg mb-2">No characters yet</p>
            <p className="text-sm">Create a character to enable reference image conditioning for visual generation.</p>
          </div>
        ) : (
          characters.map((char) => (
            <CharacterCard
              key={char.id}
              char={char}
              imageUrl={getImageUrl(char)}
              uploading={uploading === char.id}
              editing={editingId === char.id}
              editName={editName}
              editDesc={editDesc}
              onEditStart={() => {
                setEditingId(char.id);
                setEditName(char.name);
                setEditDesc(char.description);
              }}
              onEditCancel={() => setEditingId(null)}
              onEditSave={() => handleUpdate(char.id)}
              onDelete={() => handleDelete(char.id)}
              onImageUpload={handleImageUpload}
              scenes={scenes}
              onSceneAssign={onSceneUpdate}
            />
          ))
        )}
      </div>
    </div>
  );
}

interface CharacterCardProps {
  char: Character;
  imageUrl: string | null;
  uploading: boolean;
  editing: boolean;
  editName: string;
  editDesc: string;
  onEditStart: () => void;
  onEditCancel: () => void;
  onEditSave: () => void;
  onDelete: () => void;
  onImageUpload: (charId: string, files: File[]) => void;
  scenes: Scene[];
  onSceneAssign: (sceneId: string, data: { character_id: string | null }) => void;
}

function CharacterCard({
  char,
  imageUrl,
  uploading,
  editing,
  editName,
  editDesc,
  onEditStart,
  onEditCancel,
  onEditSave,
  onDelete,
  onImageUpload,
  scenes,
  onSceneAssign,
}: CharacterCardProps) {
  const scenesWithChar = scenes.filter((s) => s.character_id === char.id);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (files) => onImageUpload(char.id, files),
    accept: { "image/*": [".jpg", ".jpeg", ".png", ".webp"] },
    maxFiles: 1,
  });

  if (editing) {
    return (
      <div {...getRootProps()} className="p-3 bg-[var(--bg-tertiary)] rounded border border-[var(--accent)] space-y-2">
        <input
          type="text"
          value={editName}
          onChange={(e) => {/* handled by parent */}}
          className="w-full px-2 py-1 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded text-sm"
        />
        <textarea
          value={editDesc}
          onChange={(e) => {/* handled by parent */}}
          rows={2}
          className="w-full px-2 py-1 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded text-sm"
        />
        <div className="flex gap-2">
          <button onClick={onEditSave} className="flex-1 py-1 bg-[var(--accent)] text-white rounded text-sm hover:opacity-90">Save</button>
          <button onClick={onEditCancel} className="flex-1 py-1 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded text-sm hover:bg-[var(--bg-tertiary)]">Cancel</button>
        </div>
        <input {...getInputProps()} type="file" hidden />
      </div>
    );
  }

  return (
    <div {...getRootProps()} className="p-3 bg-[var(--bg-tertiary)] rounded border border-[var(--border-color)] space-y-3">
      <div className="flex items-start gap-3">
        {/* Image Dropzone / Preview */}
        <div
          className="relative w-16 h-16 flex-shrink-0 rounded-lg border-2 border-dashed overflow-hidden transition-colors"
          style={{ borderColor: isDragActive ? "var(--accent)" : "var(--border-color)" }}
        >
          {imageUrl ? (
            <img src={imageUrl} alt={char.name} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center text-[var(--text-secondary)] text-xs p-1">
              <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Drop image
            </div>
          )}
          {uploading && (
            <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
        <input {...getInputProps()} type="file" hidden />

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="font-medium truncate">{char.name}</h4>
            {char.reference_image_path && (
              <span className="text-xs px-1.5 py-0.5 bg-green-500/20 text-green-400 border border-green-500/30 rounded">
                Reference image set
              </span>
            )}
          </div>
          <p className="text-xs text-[var(--text-secondary)] truncate">{char.description || "No description"}</p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            Used in {scenesWithChar.length} scene{scenesWithChar.length !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1">
          <button
            onClick={onEditStart}
            className="text-xs px-2 py-1 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded hover:bg-[var(--bg-tertiary)] transition-colors"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            className="text-xs px-2 py-1 bg-red-500/20 text-red-400 border border-red-500/30 rounded hover:bg-red-500/30 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Scene Assignments */}
      {scenesWithChar.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs text-[var(--text-secondary)] flex items-center gap-1">
            <svg className="w-4 h-4 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
            Scenes using this character
          </summary>
          <div className="mt-2 space-y-1 ml-5 border-l border-[var(--border-color)] pl-3">
            {scenesWithChar.map((scene) => (
              <div key={scene.id} className="text-xs text-[var(--text-secondary)]">
                Scene {scene.index + 1}: {scene.narration.slice(0, 40)}...
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}