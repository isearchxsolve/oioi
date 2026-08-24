```javascript
// server/routes/generate.js
const express = require('express');
const fetch = require('node-fetch');

const router = express.Router();

const NVIDIA_NIM_URL = process.env.NVIDIA_NIM_URL || 'https://integrate.api.nvidia.com/v1/chat/completions';
const NVIDIA_NIM_MODEL = process.env.NVIDIA_NIM_MODEL || 'meta/llama-3.1-70b-instruct';

// Auth middleware: require Bearer JWT
function requireBearerJwt(req, res, next) {
  const authHeader = req.headers.authorization || req.headers.Authorization;

  if (!authHeader || typeof authHeader !== 'string') {
    return res.status(401).json({ error: 'Missing Authorization header' });
  }

  const parts = authHeader.trim().split(/\s+/);
  if (parts.length !== 2 || parts[0] !== 'Bearer' || !parts[1]) {
    return res.status(401).json({ error: 'Invalid Authorization header. Expected: Bearer <token>' });
  }

  const token = parts[1];

  // Basic JWT format validation (header.payload.signature)
  const jwtSegments = token.split('.');
  if (jwtSegments.length !== 3) {
    return res.status(401).json({ error: 'Malformed JWT token' });
  }

  try {
    // Decode header and payload for downstream use (no signature verification here;
    // a real deployment should verify the signature against a trusted secret/Keycloak JWKS)
    const headerJson = Buffer.from(jwtSegments[0].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
    const payloadJson = Buffer.from(jwtSegments[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');

    const header = JSON.parse(headerJson);
    const payload = JSON.parse(payloadJson);

    // Expiry check (exp is in seconds since epoch)
    if (typeof payload.exp === 'number' && Date.now() / 1000 > payload.exp) {
      return res.status(401).json({ error: 'Token expired' });
    }

    req.user = payload;
    req.token = token;
    req.jwtHeader = header;
    return next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid JWT token', details: err.message });
  }
}

function buildSystemPrompt(stack) {
  const stackHint = stack ? ` Target stack: ${stack}.` : '';
  return [
    'You are an expert software engineer.',
    `Generate production-quality, runnable source code only.${stackHint}`,
    'Respond strictly with a JSON object of the form {"code": "<the code as a single string with \\n for newlines>"}.',
    'Do not include explanations, markdown fences, or any text outside the JSON object.',
  ].join(' ');
}

function extractCodeFromNimResponse(data) {
  // NVIDIA NIM follows the OpenAI chat completions schema.
  if (!data || !Array.isArray(data.choices) || data.choices.length === 0) {
    throw new Error('Empty response from NVIDIA NIM');
  }

  const message = data.choices[0].message || data.choices[0].delta || {};
  let content = (message.content || '').toString();

  if (!content) {
    throw new Error('No content returned from NVIDIA NIM');
  }

  // Try to parse the model output as JSON; fall back to raw text.
  let code = null;
  const jsonMatch = content.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      if (typeof parsed.code === 'string') {
        code = parsed.code;
      }
    } catch (_) {
      // ignore — fall through to raw extraction
    }
  }

  if (code === null) {
    // Strip surrounding markdown fences if present.
    const fenceMatch = content.match(/```(?:[a-zA-Z0-9_+-]*)\n([\s\S]*?)```/);
    if (fenceMatch) {
      code = fenceMatch[1];
    } else {
      code = content;
    }
  }

  return code;
}

router.post('/code', requireBearerJwt, async (req, res) => {
  try {
    const { prompt, stack } = req.body || {};

    if (typeof prompt !== 'string' || prompt.trim().length === 0) {
      return res.status(400).json({ error: 'Field "prompt" is required and must be a non-empty string' });
    }
    if (prompt.length > 8000) {
      return res.status(400).json({ error: 'Field "prompt" exceeds maximum length of 8000 characters' });
    }
    if (stack !== undefined && (typeof stack !== 'string' || stack.trim().length === 0)) {
      return res.status(400).json({ error: 'Field "stack" must be a string when provided' });
    }

    const apiKey = process.env.NVIDIA_API_KEY;
    if (!apiKey) {
      return res.status(500).json({ error: 'Server is missing NVIDIA_API_KEY configuration' });
    }

    const systemPrompt = buildSystemPrompt(stack);

    const nimResponse = await fetch(NVIDIA_NIM_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
      },
      body: JSON.stringify({
        model: NVIDIA_NIM_MODEL,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt },
        ],
        temperature: 0.2,
        top_p: 0.9,
        max_tokens: 2048,
        stream: false,
      }),
    });

    if (!nimResponse.ok) {
      const errorText = await nimResponse.text().catch(() => '');
      return res.status(502).json({
        error: 'NVIDIA NIM request failed',
        status: nimResponse.status,
        details: errorText.slice(0, 1000),
      });
    }

    const data = await nimResponse.json();
    const code = extractCodeFromNimResponse(data);

    if (typeof code !== 'string' || code.length === 0) {
      return res.status(502).json({ error: 'Failed to extract code from NVIDIA NIM response' });
    }

    return res.status(200).json({ code });
  } catch (err) {
    return res.status(500).json({
      error: 'Internal server error',
      details: err && err.message ? err.message : String(err),
    });
  }
});

module.exports = router;
```