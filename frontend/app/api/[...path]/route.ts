import { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const HOP_HEADERS = [
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
];
function stripHopHeaders(headers: Headers) {
  const connection = headers.get("connection");
  if (connection)
    connection.split(",").forEach((key) => headers.delete(key.trim()));
  HOP_HEADERS.forEach((key) => headers.delete(key));
}
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (
    path.some(
      (segment) =>
        !segment ||
        segment === "." ||
        segment === ".." ||
        /[\\/\0]/.test(segment),
    )
  )
    return Response.json({ detail: "Ruta no válida." }, { status: 400 });
  let destination: URL;
  try {
    const base = new URL(process.env.API_URL || "http://127.0.0.1:8000");
    if (
      !["http:", "https:"].includes(base.protocol) ||
      base.username ||
      base.password
    )
      throw new Error("invalid upstream");
    destination = new URL(
      "/api/" + path.map(encodeURIComponent).join("/"),
      base,
    );
    destination.search = request.nextUrl.search;
  } catch {
    return Response.json(
      { detail: "El servicio no está disponible temporalmente." },
      { status: 503 },
    );
  }
  const headers = new Headers(request.headers);
  stripHopHeaders(headers);
  headers.delete("x-forwarded-for");
  headers.delete("x-real-ip");
  headers.delete("forwarded");
  const signal = AbortSignal.any([request.signal, AbortSignal.timeout(120000)]);
  const options: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    signal,
    cache: "no-store",
  };
  if (!["GET", "HEAD"].includes(request.method) && request.body) {
    options.body = request.body;
    options.duplex = "half";
  }
  try {
    const upstream = await fetch(destination, options);
    const responseHeaders = new Headers(upstream.headers);
    stripHopHeaders(responseHeaders);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("set-cookie");
    for (const cookie of upstream.headers.getSetCookie())
      responseHeaders.append("set-cookie", cookie);
    responseHeaders.set("Cache-Control", "no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        detail: signal.aborted
          ? "La operación excedió el tiempo disponible. Inténtalo nuevamente."
          : "El servicio no está disponible temporalmente.",
      },
      { status: signal.aborted ? 504 : 502 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as HEAD,
  proxy as OPTIONS,
};
