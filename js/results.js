// ===== Load race results (winners) from JSON =====
// Работает поверх существующих #resultsBoard / #resultsMeta из index.html.
// Использует те же CSS-классы, что и loadRaces() в main.js (race-card,
// track-badge, race-time, race-title, race-meta, tag, tag-secondary),
// поэтому отдельный CSS-файл не нужен.

const resultsObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

async function loadResults() {
  const board = document.getElementById('resultsBoard');
  const metaEl = document.getElementById('resultsMeta');
  if (!board) return;

  try {
    const res = await fetch('data/results.json?t=' + Date.now());
    if (!res.ok) throw new Error('Не удалось загрузить results.json');

    const data = await res.json();

    if (data.updated && metaEl) {
      const date = new Date(data.updated);
      metaEl.textContent = 'Обновлено: ' + date.toLocaleString('ru-RU', {
        day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit'
      });
    }

    const todayResults = data.results || [];
    const stakesResults = data.stakes_results || [];

    if (todayResults.length === 0 && stakesResults.length === 0) {
      board.innerHTML = '<div class="loading-placeholder">Результатов пока нет</div>';
      return;
    }

    let html = '';

    // --- Обычные заезды дня ---
    html += todayResults.map(r => {
      const isPending = r.status === 'pending' || !r.winner;

      const winnerHtml = isPending
        ? `<div class="race-tags"><span class="tag tag-secondary">Ожидаем результат…</span></div>`
        : `
          <div class="race-meta">
            <span>Победитель: <strong>${r.winner}</strong></span>
            ${r.jockey ? `<span>жокей ${r.jockey}</span>` : ''}
          </div>
        `;

      return `
        <article class="race-card">
          <div class="race-card-header">
            <span class="track-badge">${r.track || ''}</span>
            <span class="race-time">${r.time || ''}</span>
          </div>
          <h3 class="race-title">${r.title || ''}</h3>
          ${winnerHtml}
        </article>
      `;
    }).join('');

    // --- Крупные stakes-заезды (авто из RSS) ---
    if (stakesResults.length > 0) {
      const sorted = [...stakesResults].sort((a, b) => (b.title || '').localeCompare(a.title || ''));

      html += `
        <div class="section-desc" style="grid-column: 1 / -1; margin-top: 20px; font-weight: 600;">
          Крупные заезды (stakes)
        </div>
      `;

      html += sorted.map(s => `
        <article class="race-card">
          <div class="race-card-header">
            <span class="track-badge">${s.track || ''}</span>
          </div>
          <h3 class="race-title">${s.title || ''}</h3>
          <div class="race-meta">
            <span>Победитель: <strong>${s.winner || '—'}</strong></span>
          </div>
          ${s.link ? `
            <div class="race-tags">
              <a class="tag" href="${s.link}" target="_blank" rel="noopener">Видеоповтор →</a>
            </div>
          ` : ''}
        </article>
      `).join('');

      html += `
        <div class="section-desc" style="grid-column: 1 / -1; font-size: 0.8rem; opacity: 0.7;">
          Данные по крупным заездам предоставлены
          <a href="https://www.offtrackbetting.com/" target="_blank" rel="noopener">OffTrackBetting.com</a>
        </div>
      `;
    }

    board.innerHTML = html;

    document.querySelectorAll('#resultsBoard .race-card').forEach(el => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(16px)';
      el.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
      resultsObserver.observe(el);
    });

  } catch (err) {
    console.error(err);
    board.innerHTML = '<div class="loading-placeholder">Ошибка загрузки результатов. Проверьте data/results.json</div>';
  }
}

loadResults();
console.log('Results module loaded');
