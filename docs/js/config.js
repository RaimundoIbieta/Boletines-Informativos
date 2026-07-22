/** Config pública (anon key — segura en frontend) */
export const CACHE_VERSION = '4';

export const APP_CONFIG = {
  superadminEmail: 'raimundoibieta@gmail.com',
  supabaseUrl: 'https://ryznnccmqyvujrlhriml.supabase.co',
  // Preferir JWT anon clásica (compatibilidad supabase-js)
  supabaseAnonKey:
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ5em5uY2NtcXl2dWpybGhyaW1sIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ3MjY0NjEsImV4cCI6MjEwMDMwMjQ2MX0.lAjWArOOVgs9NnCt9ZBwYEDDAjyaThRBOgQKGMWbX-U',
  brandName: 'Boletines Informativos',
  tagline: 'Inteligencia semanal a tu medida',
  pricingNote: 'Etapa de pruebas · cobro real (Mercado Pago) próximamente',
};
