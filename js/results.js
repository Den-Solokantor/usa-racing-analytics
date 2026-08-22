// ===== Результаты дня — тот же вид, что «Сегодня», + колонка Место =====

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function placeClass(place) {
  if (place === 1) return 'place-1';
  if (place === 2) return 'place-2';
  if (place === 3) return 'place-3';
  return '';
}

function renderHorsesTable(horses, showPlaces) {
  if (!horses || !horses.length) {
    return '<p class="race-preview">Нет данных по лошадям</p>';
  }

  const sorted = [...horses].sort((a, b) => {
    if (showPlaces) {
      const pa = a.place != null ? a.place : 999;
      const pb = b.place != null ? b.place : 999;
      if (pa !== pb) return pa - pb;
    }
    return (a.post || 0) - (b.post || 0);
  });

  const rows = sorted
    .map((h) => {
      const placeCell = showPlaces
        ? `<td class="col-place ${placeClass(h.place)}">${
            h.place != null ? escapeHtml(h.place) : '—'
          }</td>`
        : '';
      const ml = h.ml != null ? h.ml : '—';
      return `<tr>
        <td class="col-post">${h.post != null ? escapeHtml(h.post) : ''}</td>
        <td class="col-name">${escapeHtml(h.name || '')}</td>
        <td class="col-ml">${escapeHtml(ml)}</td>
        ${placeCell}
      </tr>`;
    })
    .join('');

  return `
    <div class="race-table-wrap">
      <table class="race-table">
        <thead>
          <tr>
            <th class="col-post">№</th>
            <th class="col-name">Лошадь</th>
            <th class="col-ml">ML</th>
            ${showPlaces ? '<th class="col-place">Место</th>' : ''}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function raceFromLegacyTrackRace(t, r) {
  // Старый формат tracks[].races → одна «карточка»
  const pending =
    r.status === 'pending' ||
    !r.winner ||
    String(r.winner).indexOf('ожидание') !== -1;

  const horses = [];
  if (!pending && r.winner) {
    horses.push({
      post: r.post || '',
      name: r.winner,
      ml: r.odds || null,
      place: 1,
    });
  }

  return {
    id: `${(t.code || t.track || 'x').toLowerCase()}-r${r.race}`,
    track: t.track || t.code || '',
    time: r.time || '',
    title: r.title || (r.race != null ? 'Race ' + r.race : 'Заезд'),
    distance: '',
    purse: '',
    status: pending ? 'pending' : 'official',
    tags: pending ? ['Pending'] : ['Result'],
    horses,
    _legacyWinner: r.winner,
    _legacyJockey: r.jockey,
    _pending: pending,
  };
}

async function loadResults() {
  const board = document.getElementById('resultsBoard');
  const metaEl = document.getElementById('resultsMeta');
  if (!board) return;

  try {
    const res = await fetch('data/results.json?t=' + Date.now());
    if (!res.ok) throw new Error('results.json HTTP ' + res.status);
    const data = await res.json();

    if (metaEl) {
      const parts = [];
      if (data.date) parts.push('Дата: ' + data.date);
      if (data.source) parts.push('источник: ' + data.source);
      if (data.updated) {
        try {
          parts.push(
            'обновлено ' +
              new Date(data.updated).toLocaleString('ru-RU', {
                day: 'numeric',
                month: 'long',
                hour: '2-digit',
                minute: '2-digit',
              })
          );
        } catch (e) {}
      }
      metaEl.textContent = parts.join(' · ');
    }

    let races = data.races || [];

    // Совместимость со старым форматом tracks[]
    if (!races.length && data.tracks && data.tracks.length) {
      races = [];
      data.tracks.forEach((t) => {
        (t.races || []).forEach((r) => {
          races.push(raceFromLegacyTrackRace(t, r));
        });
      });
    }

    // Stakes (OTB) — простые карточки
    const stakes = data.stakes_results || [];

    if (!races.length && !stakes.length) {
      board.innerHTML =
        '<div class="loading-placeholder">Результатов пока нет. После забегов заполни places в data/results.json</div>';
      return;
    }

    let html = '';

    if (races.length) {
      board.style.display = 'grid';
      board.style.gridTemplateColumns =
        'repeat(auto-fill, minmax(300px, 1fr))';
      board.style.gap = '20px';

      html += races
        .map((race) => {
          const official = race.status === 'official';
          const showPlaces =
            official ||
            (race.horses || []).some((h) => h.place != null);

          const tags = (race.tags || []).map((tag) => {
            return `<span class="tag tag-secondary">${escapeHtml(tag)}</span>`;
          }).join('');

          let body;
          if (race.horses && race.horses.length) {
            body = renderHorsesTable(race.horses, showPlaces);
          } else if (race._pending) {
            body =
              '<div class="race-tags"><span class="tag tag-secondary">Ожидаем результат…</span></div>';
          } else if (race._legacyWinner) {
            body = `<div class="race-meta"><span>Победитель: <strong>${escapeHtml(
              race._legacyWinner
            )}</strong></span></div>`;
          } else {
            body =
              '<div class="race-tags"><span class="tag tag-secondary">Нет поля</span></div>';
          }

          return `
            <article class="race-card">
              <div class="race-card-header">
                <span class="track-badge">${escapeHtml(race.track || '')}</span>
                <span class="race-time">${escapeHtml(race.time || '')}</span>
              </div>
              <h3 class="race-title">${escapeHtml(race.title || '')}</h3>
              <div class="race-meta">
                <span>${escapeHtml(race.distance || '')}</span>
                <span>${escapeHtml(race.purse || '')}</span>
              </div>
              ${body}
              <div class="race-tags">${tags}</div>
            </article>`;
        })
        .join('');
    }

    if (stakes.length) {
      html += `<div style="grid-column:1/-1;margin-top:12px;font-weight:600">Крупные stakes</div>`;
      html += stakes
        .map(
          (s) => `
        <article class="race-card">
          <div class="race-card-header">
            <span class="track-badge">${escapeHtml(s.track || '')}</span>
          </div>
          <h3 class="race-title">${escapeHtml(s.title || '')}</h3>
          <div class="race-meta">
            <span>Победитель: <strong>${escapeHtml(s.winner || '—')}</strong></span>
          </div>
        </article>`
        )
        .join('');
    }

    if (data.note) {
      html += `<p class="section-desc" style="grid-column:1/-1;font-size:0.85rem;opacity:0.7">${escapeHtml(
        data.note
      )}</p>`;
    }

    board.innerHTML = html;
  } catch (err) {
    console.error(err);
    board.innerHTML =
      '<div class="loading-placeholder">Ошибка загрузки results.json</div>';
  }
}

loadResults();
console.log('Results module loaded (card+places)');
