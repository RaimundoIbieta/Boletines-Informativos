import { signIn, getUser, hasActiveSubscription, isSuperAdmin } from '../auth.js';
import { navigate } from '../router.js';

export function renderAuthButton(slot) {
  const u = getUser();
  if (!u) {
    slot.innerHTML = `<a class="btn btn-secondary" href="#/login">Entrar</a>`;
    return;
  }
  slot.innerHTML = `<span class="muted">${u.email}</span> <a class="btn btn-secondary" href="#/salir">Salir</a>`;
}

export function renderLogin(container) {
  container.innerHTML = `
    <div class="auth-card" style="max-width:420px;margin:0 auto">
      <h1 class="page-title">Iniciar sesión</h1>
      <p class="page-sub">Las cuentas las crea el administrador. Si aún no tienes acceso, contáctalo.</p>
      <label>Correo</label>
      <input id="email" type="email" />
      <label>Contraseña</label>
      <input id="password" type="password" />
      <div class="btn-row">
        <button class="btn" id="go">Entrar</button>
      </div>
      <p class="error" id="err"></p>
    </div>
  `;
  container.querySelector('#go').onclick = async () => {
    const err = container.querySelector('#err');
    err.textContent = '';
    try {
      await signIn(container.querySelector('#email').value, container.querySelector('#password').value);
      const u = getUser();
      if (isSuperAdmin()) navigate('#/admin');
      else if (hasActiveSubscription()) navigate('#/app');
      else navigate('#/plan');
    } catch (e) {
      err.textContent = e.message;
    }
  };
}
