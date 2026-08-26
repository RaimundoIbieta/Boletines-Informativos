# Setup Supabase + envío en la nube

## 1. Esquema SQL

1. https://supabase.com/dashboard/project/ryznnccmqyvujrlhriml/sql/new  
2. Ejecuta `schema.sql`  
3. Si aplica: `update_prices.sql`, `seed_pae.sql`, **`send_requests.sql`** (botón Probar envío), **`period_selection.sql`** (rango de noticias configurable), **`period_include_send_day.sql`** (que el rango llegue hasta el día del envío), **`semimonthly_bulletins.sql`** (agenda 15/fin de mes y secciones), **`panorama_output_format.sql`** (formato panorama por secciones) y **`media_analysis.sql`** (Analizador de Medios)

## 2. Auth

1. Authentication → Providers → Email  
2. Desactiva **Confirm email** (pruebas)  
3. Desactiva **Allow new users to sign up** (solo admin crea cuentas)  

## 3. Admin y usuarios

1. Tu correo `raimundoibieta@gmail.com` es superadmin  
2. En **Admin** creas usuarios y les das plan  
3. Cada usuario (o tú) configura boletines, correos y día/hora en la web  

## 4. Envío automático en la nube (GitHub Actions)

No depende de tu Mac. GitHub revisa cada 30 minutos y envía los boletines cuya frecuencia corresponde (hora Chile).

### Secrets (una sola vez)

1. Abre: https://github.com/RaimundoIbieta/Boletines-Informativos/settings/secrets/actions  
2. **New repository secret** y crea estos:

| Nombre | Dónde sacarlo |
|--------|----------------|
| `GMAIL_USER` | Tu Gmail (ej. raimundoibieta@gmail.com) |
| `GMAIL_APP_PASSWORD` | Contraseña de aplicación de Google |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → `service_role` |
| `SUPABASE_URL` (opcional) | `https://ryznnccmqyvujrlhriml.supabase.co` |

### Probar a mano

1. https://github.com/RaimundoIbieta/Boletines-Informativos/actions  
2. Workflow **Envío de boletines (nube)** → **Run workflow**  
3. Si marcas “Enviar todos…”, manda ahora (sin esperar el día/hora)

### Flujo diario

1. En la web agregas/quitas correos y eliges día/hora  
2. Botón **Probar envío**: guarda y encola una prueba (GitHub la manda en ≤10 min)  
3. GitHub Actions también envía en el día/hora programados  
4. Si cambias de Mac o se apaga, **no pasa nada**

## 5. Sugerir búsquedas y ejes con IA (opcional)

En el editor de boletín, el botón **Sugerir búsquedas y ejes con IA** rellena esas dos secciones a partir del título/enfoque. El usuario puede editar, borrar o agregar líneas.

Para que use Gemini (y no solo el generador local):

1. Instala CLI: https://supabase.com/docs/guides/cli  
2. `supabase login` y `supabase link --project-ref ryznnccmqyvujrlhriml`  
3. `supabase secrets set GEMINI_API_KEY=tu_clave`  
4. `supabase functions deploy suggest-bulletin`

## 6. Analizador de Medios (piloto admin)

Sección privada `#/analizador` (solo superadmin). Resultados en Storage privado; **no** se publican en GitHub Pages.

1. Ejecuta `media_analysis.sql` en el SQL Editor (crea tablas, RLS, buckets y RPC).
2. Secrets de GitHub Actions (además de los de boletines):
   - `GEMINI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL` (ya usados)
3. Secrets de Edge Functions (opcional, para disparo inmediato):
   - `supabase secrets set GITHUB_PAT=ghp_...` (token con `actions:write`)
   - `supabase secrets set GITHUB_REPO=RaimundoIbieta/Boletines-Informativos`
4. Despliega la función:
   - `supabase functions deploy queue-media-analysis`
5. Workflow **Análisis de medios (bajo demanda)** corre cada 15 min y también por `workflow_dispatch`.
6. Sin `GITHUB_PAT`, la solicitud queda `pending` y el cron la recoge igual.

### Qué cubre cada red

| Plataforma | Cómo se obtiene |
|---|---|
| Medios digitales, YouTube | Búsqueda pública automática |
| Reddit, Mastodon, Bluesky | API pública |
| **X (Twitter)** | Timeline público de las cuentas que indiques (sin login) + posts citados por medios |
| Instagram, Facebook, TikTok | Posts citados/incrustados por medios + enlaces y archivos que aportes |

X, Instagram, Facebook y TikTok **no permiten buscar por tema sin sesión**: cerraron la búsqueda
pública. Para X se lee el timeline público de cuentas concretas; para las otras tres solo hay
cobertura indirecta. Cada análisis muestra una tabla de cobertura con el método usado.

### Cualquier tema, no solo personas

El analizador es genérico: el tema, los actores y los rivales son parámetros del formulario.
Sirve igual para una política pública («reforma de pensiones»), una institución, una empresa,
una coyuntura electoral o una persona. Antes de analizar, descarta las piezas que el buscador
devolvió por compartir una palabra con la consulta pero que no tratan del tema, y reporta
cuántas descartó.

### Tendencia y proyección

Cada informe incluye la evolución en el tiempo y hacia dónde apunta:

- Agrupa por día, semana o mes según el largo del periodo.
- Indica si el volumen es creciente, estable o decreciente, y si el tono mejora o empeora.
- Proyecta los próximos tramos con una banda de incertidumbre calculada sobre la dispersión
  real de la serie.
- Con `GEMINI_API_KEY` agrega escenarios prospectivos con sus señales a vigilar.

No proyecta si la serie tiene menos de 4 tramos, y avisa cuando la serie es tan irregular que
la tendencia explica poco de la variación. **Una proyección extrapola lo observado: un hecho
nuevo puede romperla.**

### Cobertura geográfica estricta

El territorio funciona como una dimensión de análisis, no como una regla de descarte. Cada
pieza relevante se clasifica en:

- territorio objetivo;
- resto del país (cuando el objetivo es regional o comunal);
- contexto internacional;
- cruce entre el territorio objetivo y el extranjero; o
- ubicación indeterminada, si el texto no entrega evidencia verificable.

Una nota extranjera que hable del tema **se conserva**. El panel y los archivos exportados
separan su aporte de la conversación del territorio objetivo y muestran los países
mencionados. El clasificador no inventa una ubicación a partir del idioma o del tema.

### Qué opinan del actor

El informe incluye una sección «Qué se dice del actor» que mide la conversación **sobre** él:

- Clasifica cada mención como favorable, crítica o neutra, separando la voz de la audiencia
  (personas en Reddit, Bluesky, Mastodon) de la de los medios.
- Cuenta las comparaciones explícitas con los rivales que se indiquen («es mejor que»,
  «prefiero a», «X > Y») y reporta quién sale favorecido.
- Busca hilos de debate, no solo titulares, e incorpora comentarios de Reddit.

Con `GEMINI_API_KEY` configurada la clasificación la hace el modelo, que detecta ironía; sin la
clave se usa un léxico bilingüe que solo reconoce valoraciones explícitas. El informe avisa
cuando la muestra es insuficiente (menos de 10 menciones con postura), cuando una comparación
tiene menos de 5 casos y cuando el léxico produce un resultado casi unánime. **No es una encuesta
representativa**: describe lo publicado en las fuentes accesibles.

### Probar el piloto

1. Entra como admin → **Analizador** → **Nuevo análisis**
2. Tema ejemplo: `próximo presidente de Chile`
3. Actores: candidatos relevantes (uno por línea)
4. Territorio: Nacional · Periodo: últimos 30 días
5. Revisa panel, citas, cobertura por conector y export PDF/CSV/JSON
