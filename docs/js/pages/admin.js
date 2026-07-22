import { APP_CONFIG } from '../config.js';
import {
  getUser,
  hasActiveSubscription,
  isSuperAdmin,
  fetchPlans,
  fetchAllProfiles,
  fetchSubscriptions,
  adminGrantPlan,
  adminCreateUser,
} from '../auth.js';
import { navigate } from '../router.js';

export async function renderPlan(container) {
  const u = getUser();
  if (!u) return navigate('#/login');
  if (hasActiveSubscription() || isSuperAdmin()) return navigate('#/app');

  let plans = [];
  try {
    plans = await fetchPlans();
  } catch {
    plans = [];
  }

  container.innerHTML = `
    <h1 class="page-title">Tu plan</h1>
    <p class="page-sub">${APP_CONFIG.pricingNote}</p>
    <div class="grid grid-3">
      ${plans
        .map(
          (p) => `
        <div class="card">
          <span class="chip">${p.name}</span>
          <div class="pricing-amount">$${(p.price_clp || 0).toLocaleString('es-CL')}<span class="muted"> / mes</span></div>
          <p class="muted">Hasta <strong>${p.max_bulletins}</strong> boletín(es)</p>
          <p>${p.description || ''}</p>
        </div>`
        )
        .join('')}
    </div>
    <div class="card" style="margin-top:16px">
      <p>Aún no tienes un plan activo. El administrador debe crear tu cuenta y asignarte un plan.</p>
      <a class="btn btn-secondary" href="#/">Volver</a>
    </div>
  `;
}

export async function renderAdmin(container) {
  const u = getUser();
  if (!u) return navigate('#/login');
  if (!isSuperAdmin()) {
    container.innerHTML = `<p class="error">Solo el administrador puede entrar aquí.</p>`;
    return;
  }

  const [profiles, subs, plans] = await Promise.all([
    fetchAllProfiles(),
    fetchSubscriptions(),
    fetchPlans(),
  ]);
  const subMap = Object.fromEntries(subs.map((s) => [s.email, s]));

  container.innerHTML = `
    <h1 class="page-title">Admin</h1>
    <p class="page-sub">Solo tú creas usuarios y les asignas un plan de pago.</p>

    <div class="card">
      <h2>Crear usuario + plan</h2>
      <label>Nombre</label>
      <input id="name" placeholder="Nombre del cliente" />
      <label>Correo</label>
      <input id="email" type="email" placeholder="usuario@empresa.cl" />
      <label>Contraseña temporal</label>
      <input id="password" type="text" placeholder="mínimo 6 caracteres" />
      <label>Plan</label>
      <select id="plan">
        ${plans
          .map(
            (p) =>
              `<option value="${p.id}">${p.name} — ${p.max_bulletins} boletín(es) — $${(p.price_clp || 0).toLocaleString('es-CL')}/mes</option>`
          )
          .join('')}
      </select>
      <label>Meses de acceso</label>
      <input id="months" type="number" min="1" value="1" />
      <div class="btn-row">
        <button class="btn" id="create">Crear usuario</button>
      </div>
      <p class="error" id="err"></p>
      <p class="muted" id="ok"></p>
    </div>

    <div class="card" style="margin-top:16px">
      <h2>Renovar / cambiar plan de un usuario existente</h2>
      <label>Correo</label>
      <input id="email2" type="email" list="user-emails" />
      <datalist id="user-emails">
        ${profiles.map((p) => `<option value="${p.email}">`).join('')}
      </datalist>
      <label>Plan</label>
      <select id="plan2">
        ${plans
          .map(
            (p) =>
              `<option value="${p.id}">${p.name} — $${(p.price_clp || 0).toLocaleString('es-CL')}/mes</option>`
          )
          .join('')}
      </select>
      <label>Meses a agregar</label>
      <input id="months2" type="number" min="1" value="1" />
      <div class="btn-row">
        <button class="btn btn-secondary" id="grant">Actualizar plan</button>
      </div>
      <p class="error" id="err2"></p>
      <p class="muted" id="ok2"></p>
    </div>

    <div class="card" style="margin-top:16px">
      <h2>Usuarios</h2>
      <table class="table">
        <thead><tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Plan</th><th>Hasta</th></tr></thead>
        <tbody>
          ${profiles
            .map((p) => {
              const s = subMap[p.email] || {};
              return `<tr>
                <td>${p.name || ''}</td>
                <td>${p.email}</td>
                <td>${p.role}</td>
                <td>${s.plan || '—'}</td>
                <td>${s.until ? new Date(s.until).toLocaleDateString('es-CL') : '—'}</td>
              </tr>`;
            })
            .join('')}
        </tbody>
      </table>
    </div>
  `;

  container.querySelector('#create').onclick = async () => {
    const err = container.querySelector('#err');
    const ok = container.querySelector('#ok');
    err.textContent = '';
    ok.textContent = '';
    try {
      const created = await adminCreateUser({
        email: container.querySelector('#email').value,
        password: container.querySelector('#password').value,
        name: container.querySelector('#name').value,
        planId: container.querySelector('#plan').value,
        months: container.querySelector('#months').value,
      });
      ok.textContent = `Usuario creado: ${created.email}`;
      await renderAdmin(container);
    } catch (e) {
      err.textContent = e.message;
    }
  };

  container.querySelector('#grant').onclick = async () => {
    const err = container.querySelector('#err2');
    const ok = container.querySelector('#ok2');
    err.textContent = '';
    ok.textContent = '';
    try {
      await adminGrantPlan(
        container.querySelector('#email2').value,
        container.querySelector('#plan2').value,
        container.querySelector('#months2').value
      );
      ok.textContent = 'Plan actualizado.';
      await renderAdmin(container);
    } catch (e) {
      err.textContent = e.message;
    }
  };
}
