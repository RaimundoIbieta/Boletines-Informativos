const listeners = [];

export function parseRoute() {
  const raw = (location.hash || '#/').replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const parts = path.split('/').filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(query));
  return { name: parts[0] || 'home', parts, params };
}

export function navigate(hash) {
  location.hash = hash.startsWith('#') ? hash : `#/${hash}`;
}

export function onRouteChange(fn) {
  listeners.push(fn);
  window.addEventListener('hashchange', () => fn(parseRoute()));
  fn(parseRoute());
}
