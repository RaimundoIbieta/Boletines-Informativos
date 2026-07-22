import { APP_CONFIG } from './config.js';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.49.8';

let supabase = null;
let currentUser = null;
const listeners = new Set();

export function client() {
  if (!supabase) {
    supabase = createClient(APP_CONFIG.supabaseUrl, APP_CONFIG.supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return supabase;
}

function notify() {
  listeners.forEach((fn) => fn(currentUser));
}

export function onAuthChange(fn) {
  listeners.add(fn);
  fn(currentUser);
}

export function getUser() {
  return currentUser;
}

export function isSuperAdmin() {
  return currentUser?.role === 'superadmin';
}

export function hasActiveSubscription() {
  if (!currentUser) return false;
  if (currentUser.role === 'superadmin') return true;
  if (!currentUser.subscriptionUntil) return false;
  return new Date(currentUser.subscriptionUntil) > new Date();
}

export function maxBulletins() {
  if (!currentUser) return 0;
  if (currentUser.role === 'superadmin') return 999;
  return currentUser.maxBulletins || 1;
}

async function loadUser(sessionUser) {
  const sb = client();
  const email = (sessionUser.email || '').toLowerCase();
  let { data: profile } = await sb.from('profiles').select('*').eq('id', sessionUser.id).maybeSingle();
  if (!profile) {
    const role = email === APP_CONFIG.superadminEmail.toLowerCase() ? 'superadmin' : 'user';
    await sb.from('profiles').upsert({
      id: sessionUser.id,
      email,
      name: sessionUser.user_metadata?.name || email.split('@')[0],
      role,
    });
    ({ data: profile } = await sb.from('profiles').select('*').eq('id', sessionUser.id).maybeSingle());
  } else if (email === APP_CONFIG.superadminEmail.toLowerCase() && profile.role !== 'superadmin') {
    await sb.from('profiles').update({ role: 'superadmin' }).eq('id', sessionUser.id);
    profile.role = 'superadmin';
  }

  const { data: sub } = await sb.from('subscriptions').select('*').eq('email', email).maybeSingle();
  let max = 1;
  if (sub?.plan) {
    const { data: plan } = await sb.from('plans').select('*').eq('id', sub.plan).maybeSingle();
    max = plan?.max_bulletins || 1;
  }

  return {
    id: sessionUser.id,
    email,
    name: profile?.name || email.split('@')[0],
    role: profile?.role || 'user',
    disabled: !!profile?.disabled,
    subscriptionUntil: sub?.until || null,
    plan: sub?.plan || null,
    maxBulletins: max,
  };
}

export async function initAuth(onChange) {
  if (onChange) onAuthChange(onChange);
  const sb = client();
  const {
    data: { session },
  } = await sb.auth.getSession();
  if (session?.user) {
    currentUser = await loadUser(session.user);
    if (currentUser.disabled) {
      await sb.auth.signOut();
      currentUser = null;
    }
  }
  sb.auth.onAuthStateChange(async (_e, sess) => {
    if (sess?.user) {
      try {
        currentUser = await loadUser(sess.user);
        if (currentUser.disabled) {
          await sb.auth.signOut();
          currentUser = null;
        }
      } catch {
        currentUser = null;
      }
    } else {
      currentUser = null;
    }
    notify();
  });
  notify();
}

export async function signIn(email, password) {
  const sb = client();
  const { data, error } = await sb.auth.signInWithPassword({
    email: email.trim().toLowerCase(),
    password,
  });
  if (error) throw new Error('Correo o contraseña incorrectos.');
  currentUser = await loadUser(data.user);
  if (currentUser.disabled) {
    await sb.auth.signOut();
    currentUser = null;
    throw new Error('Cuenta deshabilitada.');
  }
  notify();
  return currentUser;
}

export async function signUp(email, password, name = '') {
  const em = email.trim().toLowerCase();
  if (password.length < 6) throw new Error('La contraseña debe tener al menos 6 caracteres.');
  const sb = client();
  const { data, error } = await sb.auth.signUp({
    email: em,
    password,
    options: { data: { name: name || em.split('@')[0] } },
  });
  if (error) throw new Error(error.message);
  if (!data.session) {
    throw new Error(
      'Cuenta creada. Si pide confirmar correo: en Supabase → Authentication → Providers → Email → desactiva "Confirm email" (etapa de pruebas).'
    );
  }
  currentUser = await loadUser(data.user);
  notify();
  return currentUser;
}

export async function signOut() {
  await client().auth.signOut();
  currentUser = null;
  notify();
}

/** Admin otorga plan (meses). */
export async function adminGrantPlan(email, planId, months = 1) {
  if (!isSuperAdmin()) throw new Error('Solo admin.');
  const sb = client();
  const em = email.trim().toLowerCase();
  const { data: existing } = await sb.from('subscriptions').select('*').eq('email', em).maybeSingle();
  let until = new Date();
  if (existing?.until && new Date(existing.until) > until) until = new Date(existing.until);
  until.setMonth(until.getMonth() + Math.max(1, Number(months) || 1));

  const { data: profiles } = await sb.from('profiles').select('id').eq('email', em).maybeSingle();
  const { error } = await sb.from('subscriptions').upsert({
    email: em,
    user_id: profiles?.id || null,
    plan: planId,
    until: until.toISOString(),
    activated_at: new Date().toISOString(),
    granted_by: currentUser.email,
    updated_at: new Date().toISOString(),
  });
  if (error) throw new Error(error.message);
}

export async function fetchPlans() {
  const { data, error } = await client().from('plans').select('*').eq('active', true).order('price_clp');
  if (error) throw new Error(error.message);
  return data || [];
}

export async function fetchAllProfiles() {
  if (!isSuperAdmin()) throw new Error('Solo admin.');
  const { data, error } = await client().from('profiles').select('*').order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return data || [];
}

export async function fetchSubscriptions() {
  if (!isSuperAdmin()) throw new Error('Solo admin.');
  const { data, error } = await client().from('subscriptions').select('*');
  if (error) throw new Error(error.message);
  return data || [];
}

export async function listMyBulletins() {
  const u = getUser();
  if (!u) throw new Error('Sin sesión');
  const { data, error } = await client()
    .from('bulletins')
    .select('*, bulletin_recipients(id, email)')
    .eq('user_id', u.id)
    .order('created_at', { ascending: false });
  if (error) throw new Error(error.message);
  return data || [];
}

export async function getBulletin(id) {
  const { data, error } = await client()
    .from('bulletins')
    .select('*, bulletin_recipients(id, email)')
    .eq('id', id)
    .maybeSingle();
  if (error) throw new Error(error.message);
  return data;
}

export async function createBulletin(payload) {
  const u = getUser();
  if (!u) throw new Error('Sin sesión');
  if (!hasActiveSubscription() && u.role !== 'superadmin') {
    throw new Error('Necesitas un plan activo.');
  }
  const existing = await listMyBulletins();
  if (existing.length >= maxBulletins()) {
    throw new Error(`Tu plan permite máximo ${maxBulletins()} boletín(es).`);
  }
  const { data, error } = await client()
    .from('bulletins')
    .insert({ ...payload, user_id: u.id })
    .select()
    .single();
  if (error) throw new Error(error.message);
  return data;
}

export async function updateBulletin(id, payload) {
  const { data, error } = await client().from('bulletins').update({ ...payload, updated_at: new Date().toISOString() }).eq('id', id).select().single();
  if (error) throw new Error(error.message);
  return data;
}

export async function deleteBulletin(id) {
  const { error } = await client().from('bulletins').delete().eq('id', id);
  if (error) throw new Error(error.message);
}

export async function setRecipients(bulletinId, emails) {
  const sb = client();
  await sb.from('bulletin_recipients').delete().eq('bulletin_id', bulletinId);
  const rows = [...new Set(emails.map((e) => e.trim().toLowerCase()).filter(Boolean))].map((email) => ({
    bulletin_id: bulletinId,
    email,
  }));
  if (!rows.length) return;
  const { error } = await sb.from('bulletin_recipients').insert(rows);
  if (error) throw new Error(error.message);
}

export async function listPublicArchive() {
  // runs publicados (lectura propia + demo: solo los del usuario; admin ve todos)
  const u = getUser();
  let q = client().from('bulletin_runs').select('*').order('created_at', { ascending: false }).limit(50);
  if (u && u.role !== 'superadmin') q = q.eq('user_id', u.id);
  const { data, error } = await q;
  if (error) return [];
  return data || [];
}
