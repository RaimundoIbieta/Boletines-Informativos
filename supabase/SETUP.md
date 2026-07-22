# Setup Supabase + envío en la nube

## 1. Esquema SQL

1. https://supabase.com/dashboard/project/ryznnccmqyvujrlhriml/sql/new  
2. Ejecuta `schema.sql`  
3. Si aplica: `update_prices.sql`, `seed_pae.sql` y **`send_requests.sql`** (botón Probar envío)

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
