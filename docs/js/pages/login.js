import {
  signIn,
  signUp,
  getUser,
  hasActiveSubscription,
  isSuperAdmin,
} from '../auth.js';
import { navigate } from '../router.js';

export function renderAuthButton(slot) {
  const u = getUser();
  if (!u) {
    slot.innerHTML = `<a class="btn btn-secondary" href="#/login">Entrar</a>`;
    return;
  }
  slot.innerHTML = `<span class="muted">${u.email}</span> <a class="btn btn-secondary" href="#/salir">Salir</a>`;
}

export function renderLogin(container, mode = 'login') {
  const isReg = mode === 'registro';
  container.innerHTML = `
    <div class="auth-card" style="max-width:420px;margin:0 auto">
      <h1 class="page-title">${isReg ? 'Crear cuenta' : 'Iniciar sesión'}</h1>
      <p class="page-sub">${isReg ? 'En pruebas: el admin activa tu plan después.' : 'Accede a tus boletines.'}</p>
      ${isReg ? `<label>Nombre</label><input id="name" />` : ''}
      <label>Correo</label>
      <input id="email" type="email" />
      <label>Contraseña</label>
      <input id="password" type="password" />
      <div class="btn-row">
        <button class="btn" id="go">${isReg ? 'Registrarme' : 'Entrar'}</button>
        <a class="btn btn-secondary" href="#/${isReg ? 'login' : 'registro'}">${isReg ? 'Ya tengo cuenta' : 'Crear cuenta'}</a>
      </div>
      <p class="error" id="err"></p>
    </div>
  `;
  container.querySelector('#go').onclick = async () => {
    const err = container.querySelector('#err');
    err.textContent = '';
    try {
      const email = container.querySelector('#email').value;
      const password = container.querySelector('#password').value;
      if (isReg) {
        const name = container.querySelector('#name')?.value || '';
        await signUp(email, password, name);
      } else {
        await signIn(email, password);
      }
      const u = getUser();
      if (isSuperAdmin()) navigate('#/admin');
      else if (hasActiveSubscription()) navigate('#/app');
      else navigate('#/plan');
    } catch (e) {
      err.textContent = e.message;
    }
  };
}
