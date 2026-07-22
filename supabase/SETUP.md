# Setup Supabase (etapa de pruebas)

## 1. Ejecutar el esquema

1. Abre: https://supabase.com/dashboard/project/ryznnccmqyvujrlhriml/sql/new  
2. Pega el contenido de `schema.sql`  
3. **Run**  
4. Si ya tenías planes con precios viejos: ejecuta también `update_prices.sql`  
5. Para importar el PAE del admin (si no aparece en la web): `seed_pae.sql`

## 2. Auth

1. Authentication → Providers → Email  
2. Desactiva **Confirm email** (pruebas)  
3. Desactiva **Allow new users to sign up** (solo el admin crea cuentas desde el panel)  
4. Guarda

## 3. Primer admin

1. Crea tu usuario admin (una vez) con `raimundoibieta@gmail.com` si aún no existe  
2. Quedarás como `superadmin`  
3. En **Admin** creas usuarios y les asignas plan

## 4. Flujo usuario

1. Tú creas su cuenta + plan (Básico 1 / Pro 3 / Empresa 10)  
2. El usuario entra, configura boletines, búsquedas, **correos** y **día/hora**  
3. El Mac del admin envía esos correos en la frecuencia de cada boletín

## 5. Motor Mac ↔ web (obligatorio para enviar)

En `.env` del repo (nunca lo subas a GitHub), agrega **una** de estas opciones:

### Opción A — service_role (recomendada)

Supabase → Project Settings → API → `service_role` (secret):

```
SUPABASE_URL=https://ryznnccmqyvujrlhriml.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...tu_service_role...
```

### Opción B — login del admin

```
SUPABASE_URL=https://ryznnccmqyvujrlhriml.supabase.co
SUPABASE_WORKER_EMAIL=raimundoibieta@gmail.com
SUPABASE_WORKER_PASSWORD=tu_clave_de_la_web
```

Luego en el Mac:

```bash
cd "/Users/raimundoibietaazocar/Boletines Informativos"
export PYTHONPATH=src
.venv/bin/python -m boletin sync-schedule
```

El LaunchAgent revisa cada 30 minutos y solo envía los boletines cuya frecuencia aplica (ventana de 30 min, una vez por periodo).
