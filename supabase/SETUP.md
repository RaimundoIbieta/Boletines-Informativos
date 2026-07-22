# Setup Supabase (etapa de pruebas)

## 1. Ejecutar el esquema

1. Abre: https://supabase.com/dashboard/project/ryznnccmqyvujrlhriml/sql/new  
2. Pega el contenido de `schema.sql`  
3. **Run**

## 2. Auth (pruebas sin confirmar correo)

1. Authentication → Providers → Email  
2. Desactiva **Confirm email** (solo mientras pruebas)  
3. Guarda

## 3. Primer admin

1. Entra a la web → **Crear cuenta** con `raimundoibieta@gmail.com`  
2. Quedarás como `superadmin` automáticamente  
3. Ve a **Admin** y activa planes a otros usuarios registrados

## 4. Flujo usuario

1. Se registra  
2. Tú le asignas plan (Básico 1 / Pro 3 / Empresa 10)  
3. Crea boletines, búsquedas web, correos y frecuencia
