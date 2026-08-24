/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  // MEASURED 2026-08-24: `GET :3011/api/v1/assets/` ended up at `http://127.0.0.1:8010/api/v1/assets/`
  // after 2 redirects. Next strips the trailing slash (308), the rewritten request reaches FastAPI
  // without it, and FastAPI's redirect_slashes bounces the BROWSER to the backend origin -- so the
  // proxy was being routed around, every Library/Models/Styles call became cross-origin, and the
  // whole thing only appeared to work because :8010 happens to be reachable and permissive. Keeping
  // the slash means the rewrite matches FastAPI's actual route and nothing redirects.
  skipTrailingSlashRedirect: true,
  experimental: {
    // MEASURED 2026-08-24: POST /api/v1/projects/{id}/pipeline/scriptwriter returned
    // "500 Internal Server Error" (body: the literal string "Internal Server Error", not JSON) in
    // exactly 30.01s through the proxy, while the SAME request straight to :8010 answered HTTP 200
    // in 43.1s with all four agents completed. The 500 was Next's own rewrite proxy giving up:
    // proxyTimeout defaults to 30 seconds.
    //
    // That default cannot work here. One agent call against the OmniRoute gateway takes 5-40s and a
    // scriptwriter run makes four of them back to back; the full 7-agent run makes eight and has
    // been measured at 497s. So every pipeline run in the UI was guaranteed to fail at 30s no matter
    // how healthy the backend was -- and it failed with an opaque non-JSON 500, which is why the UI
    // could only report a bare "HTTP 500".
    //
    // Set to 4 hours because the target is feature-length: a multi-hour film means one video job per
    // scene across hundreds of scenes, so the Animator half runs for hours, not minutes. Note this
    // only stops the PROXY from being the thing that kills a long run -- holding a single HTTP
    // request open for three hours is still the wrong shape (a reload, a sleep, or any dropped
    // connection loses the run, and the UI cannot show progress while it blocks). The pipeline job
    // routes below are the actual fix; this ceiling is just no longer the limiting factor.
    proxyTimeout: 4 * 60 * 60 * 1000,
  },
  async rewrites() {
    // MEASURED 2026-08-24: every tab in the UI showed "HTTP 500" and `curl :3011/api/v1/assets/`
    // came back as an OmniRoute SSE chat completion ("model":"gpt-5.3-instant"). Two bugs here:
    //
    //  1. The fallback pointed at :8000, which is a different app entirely (the NeonBuild node
    //     bridge). The OiiOii backend listens on :8010. So with NEXT_PUBLIC_API_URL unset -- which
    //     it is, there is no such key in .env -- every /api call was proxied to a stranger.
    //  2. `destination: process.env.NEXT_PUBLIC_API_URL` used the bare value, dropping both the
    //     `/api` prefix and the `:path*` interpolation. Setting that variable would therefore
    //     collapse all 40-odd API routes onto one URL rather than fixing anything.
    //
    // The variable now supplies the ORIGIN only, and the path is appended here, so :path* can no
    // longer be swallowed.
    const backend = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8010';
    const origin = backend.replace(/\/+$/, '');
    return [
      // MEASURED: `:path*` does not capture a trailing slash, so `/api/v1/assets/` was rewritten to
      // `/api/v1/assets` and FastAPI (redirect_slashes, routes declared at "/") answered 307 with an
      // ABSOLUTE location of http://127.0.0.1:8010/api/v1/assets/ -- bouncing the browser straight
      // past the proxy to the backend origin. This rule keeps the slash so the rewritten path
      // matches the route exactly and nothing redirects.
      {
        source: '/api/:path*/',
        destination: `${origin}/api/:path*/`,
      },
      {
        source: '/api/:path*',
        destination: `${origin}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;