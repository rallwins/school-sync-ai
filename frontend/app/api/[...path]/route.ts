// Server-side proxy used on Vercel: the browser talks to this same-origin route, which forwards
// to the backend and adds the shared API key. The key never reaches the browser.
// Vercel limits request bodies to ~4.5 MB; the backend is configured below that.
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60; // Lambda cold starts can take ~20s

const PASS_REQUEST = ["content-type"];
const PASS_RESPONSE = ["content-type", "content-disposition"];

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const base = process.env.BACKEND_URL;
  if (!base) {
    return Response.json(
      { detail: { code: "not_configured", message: "BACKEND_URL is not set." } },
      { status: 500 },
    );
  }
  const { path } = await ctx.params;
  const url = `${base.replace(/\/$/, "")}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  for (const h of PASS_REQUEST) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  if (process.env.BACKEND_API_KEY) headers.set("x-api-key", process.env.BACKEND_API_KEY);

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer(),
      signal: AbortSignal.timeout(55_000),
    });
  } catch {
    return Response.json(
      { detail: { code: "upstream_unreachable", message: "Backend did not respond in time." } },
      { status: 504 },
    );
  }
  const out = new Headers();
  for (const h of PASS_RESPONSE) {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST };
