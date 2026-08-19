// ===== Load race results (winners) from JSON =====
// Читает data/results.json:
//   - tracks[].races[]  (основной формат)
//   - results[]         (плоский список, опционально)
//   - stakes_results[]  (крупные stakes, опционально)
// Стили: те же классы, что у карточек гонок (race-card и т.д.)

const resultsObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

function isPendingWinner(r) {
  if (!r) return true;
  if (r.status === 'pending') return true;
  const w = String(r.winner || '').trim();
  if (!w) return true;
  if (w.indexOf('ожидание') !== -1) return true;
  return false;
}

function renderRaceCard(r, trackName, trackCode) {
  const pending = isPendingWinner(r);
  const raceLabel = r.race != null ? 'R' + r.race : '';
  const title = r.title || (raceLabel ? 'Race ' + r.race : 'Заезд');

  const winnerHtml = pending
    ? `<div class="race-tags"><span class="tag tag-secondary">Ожидаем результат…</span></div>`
    : `
      <div class="race-meta">
        <span>Победитель: <strong>${r.winner}</strong></span>
        ${r.jockey ? `<span>жокей ${r.jockey}</span>` : ''}
        ${r.odds ? `<span>${r.odds}</span>` : ''}
      </div>
    `;

  return `
    <article class="race-card">
      <div class="race-card-header">
        <span class="track-badge">${trackName || trackCode || ''}</span>
        <span class="race-time">${raceLabel || r.time || ''}</span>
      </div>
      <h3 class="race-title">${title}</h3>
      ${winnerHtml}
    </article>
  `;
}

async function loadResults() {
  const board = document.getElementById('resultsBoard');
  const metaEl = document.getElementById('resultsMeta');
  if (!board) return;

  try {
    const res = await fetch('data/results.json?t=' + Date.now());
    if (!res.ok) throw new Error('Не удалось загрузить results.json');

    const data = await res.json();

    if (metaEl) {
      const parts = [];
      if (data.date) parts.push('Дата: ' + data.date);
      if (data.source === 'placeholder') {
        parts.push('ожидание официальных результатов');
      } else if (data.source) {
        parts.push('источник: ' + data.source);
      }
      if (data.updated) {
        try {
          const date = new Date(data.updated);
          parts.push(
            'обновлено ' +
              date.toLocaleString('ru-RU', {
                day: 'numeric',
                month: 'long',
                hour: '2-digit',
                minute: '2-digit'
              })
          );
        } catch (e) {
          /* ignore */
        }
      }
      metaEl.textContent = parts.join(' · ');
    }

    const tracks = data.tracks || [];
    const todayResults = data.results || [];
    const stakesResults = data.stakes_results || [];

    const hasTracks = tracks.some(t => (t.races || []).length > 0);
    const hasFlat = todayResults.length > 0;
    const hasStakes = stakesResults.length > 0;

    if (!hasTracks && !hasFlat && !hasStakes) {
      board.innerHTML = '<div class="loading-placeholder">Результатов пока нет</div>';
      return;
    }

    let html = '';

    // --- Основной формат: tracks → races ---
    if (hasTracks) {
      tracks.forEach(t => {
        const races = t.races || [];
        if (!races.length) return;

        html += `
          <div style="grid-column: 1 / -1; margin-top: 8px; margin-bottom: 4px;">
            <strong style="font-size: 1.1rem;">${t.track || ''}</strong>
            ${t.code ? `<span style="opacity:0.55; margin-left:8px; font-size:0.8rem;">${t.code}</span>` : ''}
          </div>
        `;

        html += races
          .map(r => renderRaceCard(r, t.track, t.code))
          .join('');
      });
    }

    // --- Плоский список results[] (если есть) ---
    if (hasFlat) {
      html += todayResults
        .map(r => renderRaceCard(r, r.track, r.code || ''))
        .join('');
    }

    // --- Stakes ---
    if (hasStakes) {
      html += `
        <div class="section-desc" style="grid-column: 1 / -1; margin-top: 20px; font-weight: 600;">
          Крупные заезды (stakes)
        </div>
      `;

      const sorted = [...stakesResults].sort((a, b) =>
        (b.title || '').localeCompare(a.title || '')
      );

      html += sorted
        .map(s => {
          const pending = isPendingWinner(s);
          return `
            <article class="race-card">
              <div class="race-card-header">
                <span class="track-badge">${s.track || ''}</span>
              </div>
              <h3 class="race-title">${s.title || ''}</h3>
              ${
                pending
                  ? `<div class="race-tags"><span class="tag tag-secondary">Ожидаем результат…</span></div>`
                  : `<div class="race-meta"><span>Победитель: <strong>${s.winner || '—'}</strong></span></div>`
              }
              ${
                s.link
                  ? `<div class="race-tags"><a class="tag" href="${s.link}" target="_blank" rel="noopener">Видеоповтор →</a></div>`
                  : ''
              }
            </article>
          `;
        })
        .join('');
    }

    if (data.note) {
      html += `
        <div class="section-desc" style="grid-column: 1 / -1; font-size: 0.85rem; opacity: 0.7; margin-top: 12px;">
          ${data.note}
        </div>
      `;
    }

    board.innerHTML = html;

    // Сетка, как у гонок дня
    board.style.display = 'grid';
    board.style.gridTemplateColumns = 'repeat(auto-fill, minmax(280px, 1fr))';
    board.style.gap = '16px';

    document.querySelectorAll('#resultsBoard .race-card').forEach(el => {
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    });
  } catch (err) {
    console.error(err);
    board.innerHTML =
      '<div class="loading-placeholder">Ошибка загрузки результатов. Проверьте data/results.json</div>';
  }
}

loadResults();
console.log('Results module loaded');
