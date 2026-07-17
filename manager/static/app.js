'use strict';

let personas = [];
let editingName = null;
let launchingName = null;
let apiKey = '';

const byId = (id) => document.getElementById(id);

function node(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function promptForKey() {
  const entered = window.prompt('Enter your PyPlayVNC API key:');
  apiKey = entered ? entered.trim() : '';
  return apiKey;
}

async function api(method, path, body) {
  if (!apiKey && !promptForKey()) throw new Error('API key required');
  const request = async () => {
    const options = {
      method,
      headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
    };
    if (body !== undefined) options.body = JSON.stringify(body);
    return fetch(path, options);
  };

  let response = await request();
  if (response.status === 401 || response.status === 403) {
    apiKey = '';
    if (!promptForKey()) throw new Error('API key required');
    response = await request();
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}

function toast(message, type = 'ok') {
  const element = byId('toast');
  element.textContent = String(message);
  element.className = `show ${type}`;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => element.classList.remove('show'), 3500);
}

function accountList(accounts) {
  const wrapper = node('div', 'accounts');
  for (const account of accounts || []) {
    const tag = node('span', 'account-tag');
    tag.append('🌐 ');
    const site = node('strong', '', account.site);
    tag.append(site);
    if (account.email) tag.append(document.createTextNode(` ${account.email}`));
    wrapper.append(tag);
  }
  return wrapper;
}

function personaCard(persona) {
  const card = node('div', `card${persona.browser_running ? ' running' : ''}`);
  const header = node('div', 'card-header');
  const titleBlock = node('div');
  titleBlock.append(node('div', 'card-name', persona.name));
  const badge = persona.browser_running
    ? node('span', 'badge badge-active', '● Running')
    : persona.has_session
      ? node('span', 'badge badge-session', '✓ Session saved')
      : node('span', 'badge badge-idle', '○ No session');
  titleBlock.append(badge);
  header.append(titleBlock);
  card.append(header);

  if (persona.meta.description) card.append(node('div', 'card-desc', persona.meta.description));
  if (persona.meta.accounts?.length) card.append(accountList(persona.meta.accounts));
  if (persona.meta.notes) card.append(node('div', 'notes-text', persona.meta.notes));

  const actions = node('div', 'card-actions');
  const browserButton = node(
    'button',
    persona.browser_running ? 'btn-warn btn-sm' : 'btn-success btn-sm',
    persona.browser_running ? '⏹ Stop Browser' : '▶ Open Browser',
  );
  browserButton.addEventListener('click', () => persona.browser_running
    ? killBrowser(persona.name)
    : openLaunchModal(persona.name));

  const edit = node('button', 'btn-ghost btn-sm', '✎ Edit');
  edit.addEventListener('click', () => openEditModal(persona.name));
  const remove = node('button', 'btn-danger btn-sm', '🗑');
  remove.addEventListener('click', () => deletePersona(persona.name));
  actions.append(browserButton, edit, remove);
  card.append(actions);
  return card;
}

function render() {
  const grid = byId('grid');
  grid.replaceChildren();
  if (!personas.length) {
    const empty = node('div', 'empty');
    empty.style.gridColumn = '1 / -1';
    empty.append(node('div', 'icon', '🎭'), node('div', '', 'No personas yet. Create one to get started.'));
    grid.append(empty);
    return;
  }
  for (const persona of personas) grid.append(personaCard(persona));
}

async function loadPersonas() {
  try {
    personas = await api('GET', '/api/personas');
    render();
    byId('headerStatus').textContent = `${personas.length} persona${personas.length === 1 ? '' : 's'}`;
  } catch (error) {
    toast(`Failed to load: ${error.message}`, 'err');
  }
}

function closePersonaModal() { byId('modalOverlay').classList.remove('open'); }
function closeLaunchModal() { byId('launchOverlay').classList.remove('open'); }

function openCreateModal() {
  editingName = null;
  byId('modalTitle').textContent = 'New Persona';
  byId('f_name').value = '';
  byId('f_name').disabled = false;
  byId('f_desc').value = '';
  byId('f_notes').value = '';
  byId('accountsContainer').replaceChildren();
  byId('modalSaveBtn').textContent = 'Create';
  byId('modalOverlay').classList.add('open');
  byId('f_name').focus();
}

function openEditModal(name) {
  const persona = personas.find((candidate) => candidate.name === name);
  if (!persona) return;
  editingName = name;
  byId('modalTitle').textContent = `Edit · ${name}`;
  byId('f_name').value = name;
  byId('f_name').disabled = true;
  byId('f_desc').value = persona.meta.description || '';
  byId('f_notes').value = persona.meta.notes || '';
  byId('accountsContainer').replaceChildren();
  for (const account of persona.meta.accounts || []) addAccountRow(account.site, account.email);
  byId('modalSaveBtn').textContent = 'Save Changes';
  byId('modalOverlay').classList.add('open');
}

function addAccountRow(site = '', email = '') {
  const row = node('div', 'account-row');
  row.style.marginBottom = '6px';
  const siteGroup = node('div', 'form-group');
  siteGroup.style.margin = '0';
  siteGroup.append(node('label', '', 'Site'));
  const siteInput = node('input', 'acc-site');
  siteInput.placeholder = 'example.com';
  siteInput.value = site;
  siteGroup.append(siteInput);

  const emailGroup = node('div', 'form-group');
  emailGroup.style.margin = '0';
  emailGroup.append(node('label', '', 'Account label (optional)'));
  const emailInput = node('input', 'acc-email');
  emailInput.placeholder = 'local label';
  emailInput.value = email;
  emailGroup.append(emailInput);

  const remove = node('button', 'btn-danger btn-sm', '✕');
  remove.style.marginTop = '18px';
  remove.addEventListener('click', () => row.remove());
  row.append(siteGroup, emailGroup, remove);
  byId('accountsContainer').append(row);
}

async function savePersona() {
  const name = byId('f_name').value.trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(name)) {
    toast('Name must use 1–64 letters, numbers, hyphens, or underscores', 'err');
    return;
  }
  const accounts = [...document.querySelectorAll('.account-row')].map((row) => ({
    site: row.querySelector('.acc-site').value.trim(),
    email: row.querySelector('.acc-email').value.trim(),
  })).filter((account) => account.site);
  const payload = {
    description: byId('f_desc').value.trim(),
    notes: byId('f_notes').value.trim(),
    accounts,
  };
  const button = byId('modalSaveBtn');
  button.disabled = true;
  button.textContent = 'Saving…';
  try {
    if (editingName) await api('PUT', `/api/personas/${encodeURIComponent(editingName)}`, payload);
    else await api('POST', '/api/personas', {name, ...payload});
    closePersonaModal();
    await loadPersonas();
  } catch (error) {
    toast(error.message, 'err');
  } finally {
    button.disabled = false;
    button.textContent = editingName ? 'Save Changes' : 'Create';
  }
}

async function deletePersona(name) {
  if (!window.confirm(`Delete persona “${name}”? This permanently removes its local browser profile.`)) return;
  try {
    await api('DELETE', `/api/personas/${encodeURIComponent(name)}`);
    await loadPersonas();
  } catch (error) {
    toast(error.message, 'err');
  }
}

function openLaunchModal(name) {
  launchingName = name;
  byId('launchUrl').value = 'https://example.com';
  byId('launchOverlay').classList.add('open');
}

async function confirmLaunch() {
  const url = byId('launchUrl').value.trim();
  const button = byId('launchConfirmBtn');
  button.disabled = true;
  button.textContent = 'Launching…';
  try {
    await api('POST', `/api/personas/${encodeURIComponent(launchingName)}/launch?url=${encodeURIComponent(url)}`);
    closeLaunchModal();
    await loadPersonas();
  } catch (error) {
    toast(error.message, 'err');
  } finally {
    button.disabled = false;
    button.textContent = '🚀 Launch';
  }
}

async function killBrowser(name) {
  try {
    await api('POST', `/api/personas/${encodeURIComponent(name)}/kill`);
    await loadPersonas();
  } catch (error) {
    toast(error.message, 'err');
  }
}

byId('newPersonaBtn').addEventListener('click', openCreateModal);
byId('refreshBtn').addEventListener('click', loadPersonas);
byId('resetKeyBtn').addEventListener('click', () => { apiKey = ''; promptForKey(); loadPersonas(); });
byId('addAccountBtn').addEventListener('click', () => addAccountRow());
byId('cancelPersonaBtn').addEventListener('click', closePersonaModal);
byId('modalSaveBtn').addEventListener('click', savePersona);
byId('cancelLaunchBtn').addEventListener('click', closeLaunchModal);
byId('launchConfirmBtn').addEventListener('click', confirmLaunch);
byId('modalOverlay').addEventListener('click', (event) => { if (event.target === byId('modalOverlay')) closePersonaModal(); });
byId('launchOverlay').addEventListener('click', (event) => { if (event.target === byId('launchOverlay')) closeLaunchModal(); });
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') { closePersonaModal(); closeLaunchModal(); }
});

promptForKey();
loadPersonas();
window.setInterval(loadPersonas, 10000);
