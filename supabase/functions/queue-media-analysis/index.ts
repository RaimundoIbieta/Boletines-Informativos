import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
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

    const supabaseUrl = Deno.env.get("SUPABASE_URL") || "";
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
    if (!supabaseUrl) return json({ error: "Falta SUPABASE_URL" }, 500);

    // Validar JWT del usuario
    const userResp = await fetch(`${supabaseUrl}/auth/v1/user`, {
      headers: {
        Authorization: auth,
        apikey: anonKey,
      },
    });
    if (!userResp.ok) return json({ error: "Token inválido" }, 401);
    const user = await userResp.json();
    const userId = user?.id;
    if (!userId) return json({ error: "Sin usuario" }, 401);

    // Verificar superadmin
    const profileResp = await fetch(
      `${supabaseUrl}/rest/v1/profiles?id=eq.${userId}&select=role,disabled`,
      {
        headers: {
          Authorization: auth,
          apikey: anonKey,
        },
      },
    );
    const profiles = await profileResp.json();
    const profile = Array.isArray(profiles) ? profiles[0] : null;
    if (!profile || profile.role !== "superadmin" || profile.disabled) {
      return json({ error: "Piloto: solo administrador" }, 403);
    }

    const body = await req.json().catch(() => ({}));
    const requestId = String(body?.request_id || "").trim();
    if (!requestId) return json({ error: "Falta request_id" }, 400);

    const ghToken = Deno.env.get("GITHUB_PAT") || Deno.env.get("GH_WORKFLOW_TOKEN") || "";
    const ghRepo = Deno.env.get("GITHUB_REPO") || "RaimundoIbieta/Boletines-Informativos";
    if (!ghToken) {
      // Sin token: la cola queda pending y el cron del workflow la recoge
      return json({ queued: true, dispatched: false, reason: "Sin GITHUB_PAT; usará cron" });
    }

    const dispatch = await fetch(
      `https://api.github.com/repos/${ghRepo}/actions/workflows/analisis-medios.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${ghToken}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: {
            request_id: requestId,
          },
        }),
      },
    );
    if (!dispatch.ok) {
      const detail = await dispatch.text();
      return json({ queued: true, dispatched: false, detail: detail.slice(0, 400) }, 202);
    }
    return json({ queued: true, dispatched: true, request_id: requestId });
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
