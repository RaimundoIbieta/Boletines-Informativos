import { parseRoute, onRouteChange, navigate } from './router.js';
import {
  initAuth,
  getUser,
  signOut,
  isSuperAdmin,
  hasActiveSubscription,
  onAuthChange,
} from './auth.js';
import { renderAuthButton, renderLogin } from './pages/login.js';
import { renderPlan, renderAdmin } from './pages/admin.js';
import { renderApp, renderBulletinEditor } from './pages/bulletins.js';
import { renderArchive } from './pages/archive.js';
import { APP_CONFIG } from './config.js';

const view = document.getElementById('view');
const authSlot = document.getElementById('auth-slot');
const nav = document.getElementById('main-nav');

function renderNav() {
  const u = getUser();
  const links = [];
  links.push(`<a href="#/">Inicio</a>`);
  if (u) {
    links.push(`<a href="#/app">Mis boletines</a>`);
    links.push(`<a href="#/archivo">Archivo</a>`);
    if (isSuperAdmin()) links.push(`<a href="#/admin">Admin</a>`);
  } else {
    links.push(`<a href="#/login">Entrar</a>`);
    links.push(`<a href="#/registro">Registro</a>`);
  }
  nav.innerHTML = links.join('');
  renderAuthButton(authSlot);
}

function renderHome() {
  const u = getUser();
  view.innerHTML = `
    <section class="hero">
      <p class="chip">Etapa de pruebas · herramientas free</p>
      <h1>${APP_CONFIG.brandName}</h1>
      <p class="lede">${APP_CONFIG.tagline}. Crea boletines por temática, define búsquedas web, destinatarios y frecuencia. El admin activa tu plan.</p>
      <div class="btn-row">
        ${
          u
            ? `<a class="btn" href="#/${hasActiveSubscription() || isSuperAdmin() ? 'app' : 'plan'}">Ir a mi panel</a>`
            : `<a class="btn" href="#/registro">Crear cuenta</a><a class="btn btn-secondary" href="#/login">Entrar</a>`
        }
        <a class="btn btn-secondary" href="#/archivo">Ver archivo público</a>
      </div>
    </section>
  `;
}

async function renderRoute(route) {
  renderNav();
  const name = route.name;
  if (name === 'salir') {
    await signOut();
    navigate('#/');
    return;
  }
  if (name === 'login') return renderLogin(view, 'login');
  if (name === 'registro') return renderLogin(view, 'registro');
  if (name === 'plan') return renderPlan(view);
  if (name === 'admin') return renderAdmin(view);
  if (name === 'app') return renderApp(view);
  if (name === 'archivo') return renderArchive(view);
  if (name === 'boletin') return renderBulletinEditor(view, route.parts[1] || 'nuevo');
  return renderHome();
}

await initAuth(() => {
  renderNav();
});
onRouteChange((route) => {
  renderRoute(route).catch((e) => {
    view.innerHTML = `<div class="card"><p class="error">${e.message}</p>
      <p class="muted">Si dice que falta una tabla, ejecuta el SQL de <code>supabase/schema.sql</code> en el SQL Editor de Supabase.</p></div>`;
  });
});
onAuthChange(() => renderNav());
