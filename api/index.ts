import type { VercelRequest, VercelResponse } from "@vercel/node";

// The Mythos backend runs locally -- this proxy forwards API calls to it.
// Set MYTHOS_BACKEND env var to override the default.
const BACKEND = process.env.MYTHOS_BACKEND || "http://localhost:7860";

async function proxy(path: string, req: VercelRequest, res: VercelResponse) {
  const url = `${BACKEND}${path}`;

  try {
    const resp = await fetch(url, {
      method: req.method || "POST",
      headers: { "Content-Type": "application/json" },
      body: req.method !== "GET" ? JSON.stringify(req.body) : undefined,
    });

    const data = await resp.text();
    res.setHeader("Content-Type", resp.headers.get("content-type") || "application/json");
    res.status(resp.status).send(data);
  } catch (err: any) {
    res.status(502).json({
      error: "Backend unreachable",
      detail: err?.message || "Could not connect to Mythos backend",
      hint: "Start the backend with: python main.py --mode web",
    });
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Enable CORS -- restrict to configured origin; default to same-origin
  const corsOrigin = process.env.MYTHOS_CORS_ORIGIN || "";
  if (corsOrigin) {
    res.setHeader("Access-Control-Allow-Origin", corsOrigin);
    res.setHeader("Vary", "Origin");
  }
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  const subpath = (req.query?.path as string) || "";
  // Prevent path traversal -- reject anything that could escape /api/
  if (subpath.includes("..") || subpath.includes("\0")) {
    return res.status(400).json({ error: "Invalid path" });
  }
  await proxy(`/api/${subpath}`, req, res);
}
