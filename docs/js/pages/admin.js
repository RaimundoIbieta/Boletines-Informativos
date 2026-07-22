import { APP_CONFIG } from '../config.js';
import {
  getUser,
  hasActiveSubscription,
  isSuperAdmin,
  fetchPlans,
  fetchAllProfiles,
  fetchSubscriptions,
  adminGrantPlan,
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
    <h1 class="page-title">Elige tu plan</h1>
    <p class="page-sub">${APP_CONFIG.pricingNote}</p>
    <div class="grid grid-3">
      ${plans
        .map(
          (p) => `
        <div class="card">
          <span class="chip">${p.name}</span>
          <div class="pricing-amount">$${(p.price_clp || 0).toLocaleString('es-CL')}</div>
          <p class="muted">Hasta <strong>${p.max_bulletins}</strong> boletín(es)</p>
          <p>${p.description || ''}</p>
        </div>`
        )
        .join('')}
    </div>
    <div class="card" style="margin-top:16px">
      <p>En pruebas, el <strong>admin</strong> activa tu plan desde el panel Admin (sin cobro aún).</p>
      <p class="muted">Tu correo: ${u.email}</p>
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
    <p class="page-sub">Activa el acceso de usuarios asignando un plan. El cobro real (Mercado Pago) vendrá después.</p>

    <div class="card">
      <h2>Otorgar / renovar plan</h2>
      <label>Correo del usuario (debe haberse registrado en la web)</label>
      <input id="email" type="email" placeholder="usuario@empresa.cl" />
      <label>Plan</label>
      <select id="plan">
        ${plans.map((p) => `<option value="${p.id}">${p.name} (${p.max_bulletins} boletines) — $${p.price_clp}</option>`).join('')}
      </select>
      <label>Meses</label>
      <input id="months" type="number" min="1" value="1" />
      <div class="btn-row">
        <button class="btn" id="grant">Activar plan</button>
      </div>
      <p class="error" id="err"></p>
      <p class="muted" id="ok"></p>
    </div>

    <div class="card" style="margin-top:16px">
      <h2>Usuarios registrados</h2>
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

  container.querySelector('#grant').onclick = async () => {
    const err = container.querySelector('#err');
    const ok = container.querySelector('#ok');
    err.textContent = '';
    ok.textContent = '';
    try {
      await adminGrantPlan(
        container.querySelector('#email').value,
        container.querySelector('#plan').value,
        container.querySelector('#months').value
      );
      ok.textContent = 'Plan activado.';
      await renderAdmin(container);
    } catch (e) {
      err.textContent = e.message;
    }
  };
}
