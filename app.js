// ─── State ──────────────────────────────────────────────────────────────────
const STORAGE_KEY = 'xgp_game_statuses';

const state = {
  search: '',
  genres: new Set(),        // active genre filters
  players: new Set(),       // active player mode filters
  statusFilters: new Set(), // 'completed','dropped','important','none'
  sort: 'az',
  view: 'grid',
  statuses: loadStatuses(),
};

// ─── Persistence ────────────────────────────────────────────────────────────
function loadStatuses() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveStatuses() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.statuses));
  } catch {}
}

function setGameStatus(id, status) {
  if (state.statuses[id] === status) {
    delete state.statuses[id]; // toggle off
  } else {
    state.statuses[id] = status;
  }
  saveStatuses();
}

// ─── Filtering & Sorting ────────────────────────────────────────────────────
function getFilteredGames() {
  // Deduplicate by id
  const seen = new Set();
  let list = GAMES.filter(g => {
    if (seen.has(g.id)) return false;
    seen.add(g.id);
    return true;
  });

  // Search
  if (state.search) {
    const q = state.search.toLowerCase();
    list = list.filter(g =>
      g.title.toLowerCase().includes(q) ||
      g.developer.toLowerCase().includes(q) ||
      g.genres.some(gen => gen.toLowerCase().includes(q))
    );
  }

  // Genre filters (all selected genres must be present — AND logic)
  if (state.genres.size > 0) {
    list = list.filter(g =>
      [...state.genres].every(gen => g.genres.includes(gen))
    );
  }

  // Player mode filters (OR logic — any selected mode matches)
  if (state.players.size > 0) {
    list = list.filter(g =>
      (g.players || []).some(p => state.players.has(p))
    );
  }

  // Status filters
  if (state.statusFilters.size > 0) {
    list = list.filter(g => {
      const s = state.statuses[g.id] || 'none';
      return state.statusFilters.has(s);
    });
  }

  // Sort
  switch (state.sort) {
    case 'az':
      list.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case 'za':
      list.sort((a, b) => b.title.localeCompare(a.title));
      break;
    case 'year-new':
      list.sort((a, b) => b.year - a.year);
      break;
    case 'year-old':
      list.sort((a, b) => a.year - b.year);
      break;
    case 'status': {
      const order = { important: 0, completed: 1, dropped: 2, none: 3 };
      list.sort((a, b) => {
        const sa = state.statuses[a.id] || 'none';
        const sb = state.statuses[b.id] || 'none';
        return (order[sa] ?? 3) - (order[sb] ?? 3) || a.title.localeCompare(b.title);
      });
      break;
    }
  }

  return list;
}

// ─── Render ──────────────────────────────────────────────────────────────────
function render() {
  const games = getFilteredGames();
  renderGrid(games);
  updateStats();
  updateResultsCount(games.length);
}

function renderGrid(games) {
  const grid = document.getElementById('game-grid');
  grid.innerHTML = '';

  if (games.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24"><path d="M9.5 16A6.5 6.5 0 1 1 16 9.5 6.51 6.51 0 0 1 9.5 16zm0-11A4.5 4.5 0 1 0 14 9.5 4.51 4.51 0 0 0 9.5 5zM20 21a1 1 0 0 1-.71-.29l-3.4-3.39a1 1 0 0 1 1.42-1.42l3.39 3.4A1 1 0 0 1 20 21z"/></svg>
        <h3>No games found</h3>
        <p>Try adjusting your filters or search query.</p>
      </div>`;
    return;
  }

  const isList = state.view === 'list';

  // Inject sticky header row for list/table view
  if (isList) {
    const header = document.createElement('div');
    header.className = 'list-header';
    header.innerHTML = `
      <span></span>
      <span>Title</span>
      <span>Genre / Players</span>
      <span>Developer</span>
      <span>Year</span>
      <span>Status</span>`;
    grid.appendChild(header);
  }

  games.forEach(game => {
    const status = state.statuses[game.id] || null;
    const card = document.createElement('div');
    card.className = `game-card${status ? ` status-${status}` : ''}`;
    card.dataset.id = game.id;

    const ribbonLabel = { completed: 'Completed', dropped: 'Dropped', important: 'Important' };
    const ribbon = status
      ? `<span class="status-ribbon ${status}">${ribbonLabel[status]}</span>`
      : '';

    const genres  = game.genres.map(g => `<span class="genre-tag">${g}</span>`).join('');
    const players = (game.players || []).map(p => `<span class="genre-tag player-tag">${p}</span>`).join('');
    const tooltipTags = [...game.genres, ...(game.players || [])].map(t => `<span class="genre-tag">${t}</span>`).join('');
    const tooltip = isList ? `<span class="genres-tooltip">${tooltipTags}</span>` : '';

    const statusBtns = ['completed', 'dropped', 'important'].map(s => `
      <button class="status-btn${status === s ? ' active' : ''}"
              data-id="${game.id}"
              data-status="${s}"
              title="${s.charAt(0).toUpperCase() + s.slice(1)}">
        <span>${s === 'completed' ? '✓' : s === 'dropped' ? '✕' : '★'}</span>
        ${isList ? '' : `<span>${s.charAt(0).toUpperCase() + s.slice(1)}</span>`}
      </button>`).join('');

    card.innerHTML = isList ? `
      <img class="card-img"
           src="${game.image}"
           alt="${game.title}"
           loading="lazy"
           onerror="this.src='images/placeholder.svg';this.classList.add('errored');">
      <div class="card-body">
        <div class="card-title">${game.title}</div>
        <div class="card-genres">${genres}${players}${tooltip}</div>
        <div class="card-developer">${game.developer || ''}</div>
        <div class="card-year">${game.year && game.year <= 3000 ? game.year : '--'}</div>
        <div class="status-selector">${statusBtns}</div>
      </div>` : `
      ${ribbon}
      <img class="card-img"
           src="${game.image}"
           alt="${game.title}"
           loading="lazy"
           onerror="this.src='images/placeholder.svg';this.classList.add('errored');">
      <div class="card-body">
        <div class="card-title">${game.title}</div>
        <div class="card-genres">${genres}${players}</div>
        <div class="status-selector">${statusBtns}</div>
      </div>`;

    grid.appendChild(card);
  });
}

function updateStats() {
  const seen = new Set();
  const all = GAMES.filter(g => {
    if (seen.has(g.id)) return false;
    seen.add(g.id);
    return true;
  });
  const counts = { completed: 0, dropped: 0, important: 0 };
  for (const g of all) {
    const s = state.statuses[g.id];
    if (s && counts[s] !== undefined) counts[s]++;
  }
  document.getElementById('stat-completed').textContent = counts.completed;
  document.getElementById('stat-dropped').textContent = counts.dropped;
  document.getElementById('stat-important').textContent = counts.important;
  document.getElementById('stat-total').textContent = all.length;
}

function updateResultsCount(n) {
  const el = document.getElementById('results-count');
  el.innerHTML = `Showing <strong>${n}</strong> game${n !== 1 ? 's' : ''}`;
}

// ─── Event delegation for status buttons ────────────────────────────────────
document.getElementById('game-grid').addEventListener('click', e => {
  const btn = e.target.closest('.status-btn');
  if (!btn) return;
  const { id, status } = btn.dataset;
  setGameStatus(id, status);
  render();
});

// ─── Sidebar controls ────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', e => {
  state.search = e.target.value.trim();
  render();
});

document.getElementById('sort').addEventListener('change', e => {
  state.sort = e.target.value;
  render();
});

// Genre chips — "Co-op" is treated identically to any other genre
document.getElementById('genre-chips').addEventListener('click', e => {
  const chip = e.target.closest('.chip[data-genre]');
  if (!chip) return;
  const genre = chip.dataset.genre;

  if (genre === '__all__') {
    state.genres.clear();
    document.querySelectorAll('#genre-chips .chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
  } else {
    document.querySelector('#genre-chips .chip[data-genre="__all__"]').classList.remove('active');
    if (state.genres.has(genre)) {
      state.genres.delete(genre);
      chip.classList.remove('active');
    } else {
      state.genres.add(genre);
      chip.classList.add('active');
    }
    if (state.genres.size === 0) {
      document.querySelector('#genre-chips .chip[data-genre="__all__"]').classList.add('active');
    }
  }
  render();
});

// Player mode chips
document.getElementById('player-chips').addEventListener('click', e => {
  const chip = e.target.closest('.chip[data-player]');
  if (!chip) return;
  const p = chip.dataset.player;
  if (state.players.has(p)) {
    state.players.delete(p);
    chip.classList.remove('active');
  } else {
    state.players.add(p);
    chip.classList.add('active');
  }
  render();
});

// Status filter chips
document.getElementById('status-chips').addEventListener('click', e => {
  const chip = e.target.closest('.chip[data-status-filter]');
  if (!chip) return;
  const sf = chip.dataset.statusFilter;
  if (state.statusFilters.has(sf)) {
    state.statusFilters.delete(sf);
    chip.classList.remove('active');
  } else {
    state.statusFilters.add(sf);
    chip.classList.add('active');
  }
  render();
});

// View toggle
document.querySelectorAll('.view-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    state.view = btn.dataset.view;
    document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b === btn));
    document.getElementById('game-grid').classList.toggle('list-view', state.view === 'list');
    render();
  });
});

// Reset all filters
document.getElementById('btn-reset').addEventListener('click', () => {
  state.search = '';
  state.genres.clear();
  state.players.clear();
  state.statusFilters.clear();
  state.sort = 'az';
  document.getElementById('search').value = '';
  document.getElementById('sort').value = 'az';
  document.querySelectorAll('#genre-chips .chip').forEach(c => c.classList.remove('active'));
  document.querySelector('#genre-chips .chip[data-genre="__all__"]').classList.add('active');
  document.querySelectorAll('#player-chips .chip').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('#status-chips .chip').forEach(c => c.classList.remove('active'));
  render();
});

// ─── Genre tooltip positioning ───────────────────────────────────────────────
document.getElementById('game-grid').addEventListener('mousemove', e => {
  const cell = e.target.closest('.card-genres');
  if (!cell) return;
  const tip = cell.querySelector('.genres-tooltip');
  if (!tip) return;
  tip.style.left = (e.clientX + 12) + 'px';
  tip.style.top  = (e.clientY + 12) + 'px';
});

// ─── Init ────────────────────────────────────────────────────────────────────
render();
