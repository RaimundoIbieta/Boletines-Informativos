import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

type Body = {
  title?: string;
  short_label?: string;
  audience?: string;
  focus?: string;
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: cors });
  }

  try {
    const auth = req.headers.get("Authorization") || "";
    if (!auth.startsWith("Bearer ")) {
      return json({ error: "No autorizado" }, 401);
    }

    const body = (await req.json()) as Body;
    const title = (body.title || "").trim();
    const short_label = (body.short_label || "").trim();
    const audience = (body.audience || "").trim();
    const focus = (body.focus || "").trim();
    if (!title && !short_label && !focus) {
      return json({ error: "Falta título, etiqueta o enfoque" }, 400);
    }

    const apiKey = Deno.env.get("GEMINI_API_KEY") || "";
    if (!apiKey) {
      return json({ error: "Falta GEMINI_API_KEY en secrets de Supabase" }, 500);
    }

    const prompt = `Eres experto en newsletters de inteligencia de negocios en Chile.
Diseña la base de un boletín semanal a partir de estos datos:

- Título: ${title || "(sin título)"}
- Etiqueta: ${short_label || "(sin etiqueta)"}
- Audiencia: ${audience || "tomadores de decisión"}
- Enfoque: ${focus || "(sin enfoque)"}

Devuelve SOLO JSON válido con esta forma:
{
  "queries": [{"q":"consulta de búsqueda corta","topic":"TEMA_EN_MAYUSCULAS"}],
  "analysis_axes": ["eje 1", "eje 2"]
}

Reglas:
- Entre 5 y 8 búsquedas web en español, orientadas a Chile.
- Cada "q" debe ser corta y usable en Bing/Google News (evita OR muy complejos; máximo un OR simple).
- "topic" en MAYÚSCULAS_CON_GUION_BAJO (ej. MINERIA, JUNAEB_PAE, REGULACION).
- Entre 5 y 7 ejes de análisis concretos y accionables para la audiencia.
- No inventes URLs. No uses markdown.`;

    const models = ["gemini-flash-latest", "gemini-2.0-flash", "gemini-2.0-flash-lite"];
    let text = "";
    let lastErr = "";
    for (const model of models) {
      const url =
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": apiKey,
        },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: prompt }] }],
          generationConfig: {
            temperature: 0.4,
            responseMimeType: "application/json",
          },
        }),
      });
      if (!resp.ok) {
        lastErr = await resp.text();
        continue;
      }
      const data = await resp.json();
      text = data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
      if (text) break;
    }
    if (!text) {
      return json({ error: "Gemini no respondió", detail: lastErr.slice(0, 400) }, 502);
    }

    let parsed: { queries?: unknown; analysis_axes?: unknown };
    try {
      parsed = JSON.parse(text);
    } catch {
      const m = text.match(/\{[\s\S]*\}/);
      if (!m) return json({ error: "JSON inválido de Gemini" }, 502);
      parsed = JSON.parse(m[0]);
    }

    const queries = Array.isArray(parsed.queries)
      ? parsed.queries
        .map((item) => {
          if (!item || typeof item !== "object") return null;
          const row = item as { q?: string; topic?: string };
          const q = String(row.q || "").trim();
          const topic = String(row.topic || "GENERAL").trim().toUpperCase() || "GENERAL";
          return q ? { q, topic } : null;
        })
        .filter(Boolean)
        .slice(0, 10)
      : [];

    const analysis_axes = Array.isArray(parsed.analysis_axes)
      ? parsed.analysis_axes
        .map((x) => String(x || "").trim())
        .filter(Boolean)
        .slice(0, 10)
      : [];

    if (!queries.length) {
      return json({ error: "Sin búsquedas en la respuesta" }, 502);
    }

    return json({ queries, analysis_axes });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return json({ error: message }, 500);
  }
});

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}
