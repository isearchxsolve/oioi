"""OiiOii.ai clone backend package — multi-provider free-tier AI adapters.

NVIDIA NIM is explicitly excluded (AC-10). All AI inference is routed through
the unified AIProviderAdapter interface implemented by free-tier providers
(OpenRouter, Groq, Gemini, fal, Replicate, Cloudflare, Hugging Face, Cohere).
"""
