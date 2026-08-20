// Theme toggle
const themeToggle = document.getElementById('themeToggle');
const html = document.documentElement;

const savedTheme = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-theme', savedTheme);
updateToggleIcon(savedTheme);

if (themeToggle) {
  themeToggle.addEventListener('click', () => {
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateToggleIcon(next);
  });
}

function updateToggleIcon(theme) {
  if (themeToggle) {
    themeToggle.textContent = theme === 'dark' ? '🌙' : '☀️';
  }
}

// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
    const targetId = this.getAttribute('href');
    if (targetId === '#') return;
    const target = document.querySelector(targetId);
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// Intersection Observer
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ===== Load races (таблица № | Лошадь | ML) =====
async function loadRaces() {
  const grid = document.getElementById('racesGrid');
  const updatedEl = document.getElementById('racesUpdated');
  if (!grid) return;

  try {
    const res = await fetch('data/races.json?t=' + Date.now());
    if (!res.ok) throw new Error('Не удалось загрузить races.json');

    const data = await res.json();

    if (data.updated && updatedEl) {
      const date = new Date(data.updated);
      updatedEl.textContent = 'Обновлено: ' + date.toLocaleString('ru-RU', {
        day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit'
      });
    }

    if (!data.races || data.races.length === 0) {
      grid.innerHTML = '<div class="loading-placeholder">На сегодня гонок пока нет</div>';
      return;
    }

    grid.innerHTML = data.races.map(race => {
      const tagsHtml = (race.tags || []).map(tag => {
        const primary = ['Value possible', 'Watchlist', 'Live odds'].includes(tag);
        return `<span class="tag ${primary ? '' : 'tag-secondary'}">${escapeHtml(tag)}</span>`;
      }).join('');

      let bodyHtml = '';
      if (race.horses && race.horses.length) {
        const hasWin = race.horses.some(h => h.win != null);
        const rows = race.horses.map(h => {
          const ml = h.ml != null ? h.ml : '—';
          const winCell = hasWin
            ? `<td class="col-win">${h.win != null ? escapeHtml(h.win) : '—'}</td>`
            : '';
          return `<tr>
              <td class="col-post">${h.post != null ? escapeHtml(h.post) : ''}</td>
              <td class="col-name">${escapeHtml(h.name || '')}</td>
              <td class="col-ml">${escapeHtml(ml)}</td>
              ${winCell}
            </tr>`;
        }).join('');

        bodyHtml = `
          <div class="race-table-wrap">
            <table class="race-table">
              <thead>
                <tr>
                  <th class="col-post">№</th>
                  <th class="col-name">Лошадь</th>
                  <th class="col-ml">ML</th>
                  ${hasWin ? '<th class="col-win">Live</th>' : ''}
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          </div>`;
      } else if (race.preview) {
        bodyHtml = `<div class="race-preview"><p>${escapeHtml(race.preview)}</p></div>`;
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
          ${bodyHtml}
          <div class="race-tags">${tagsHtml}</div>
        </article>`;
    }).join('');

    document.querySelectorAll('.race-card').forEach(el => {
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    });

  } catch (err) {
    console.error(err);
    grid.innerHTML = '<div class="loading-placeholder">Ошибка загрузки гонок. Проверьте data/races.json</div>';
  }
}

// ===== Load news =====
async function loadNews() {
  const list = document.getElementById('newsList');
  if (!list) return;

  try {
    const res = await fetch('data/news.json?t=' + Date.now());
    if (!res.ok) throw new Error('news.json not found');
    const data = await res.json();

    if (!data.items || data.items.length === 0) {
      list.innerHTML = '<div class="loading-placeholder">Новостей пока нет</div>';
      return;
    }

    list.innerHTML = data.items.map(item => `
      <a class="news-item" href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener">
        <div class="news-item-meta">
          <span class="news-source">${escapeHtml(item.source || 'News')}</span>
          <span class="news-time">${escapeHtml(item.time || '')}</span>
        </div>
        <div class="news-item-title">${escapeHtml(item.title)}</div>
        ${item.summary ? `<div class="news-item-summary">${escapeHtml(item.summary)}</div>` : ''}
      </a>
    `).join('');
  } catch (err) {
    console.error(err);
    list.innerHTML = '<div class="loading-placeholder">Не удалось загрузить новости</div>';
  }
}

document.querySelectorAll('.track-card, .analytics-card, .value-item').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(16px)';
  el.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
  observer.observe(el);
});

const contactForm = document.getElementById('contactForm');
const formStatus = document.getElementById('formStatus');

if (contactForm) {
  contactForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (formStatus) {
      formStatus.textContent = 'Отправка...';
      formStatus.className = 'form-note';
    }
    const formData = new FormData(contactForm);
    try {
      const res = await fetch(contactForm.action, {
        method: 'POST',
        body: formData,
        headers: { Accept: 'application/json' }
      });
      if (res.ok) {
        if (formStatus) {
          formStatus.textContent = 'Сообщение отправлено. Спасибо!';
          formStatus.className = 'form-note success';
        }
        contactForm.reset();
      } else {
        throw new Error('Ошибка отправки');
      }
    } catch (err) {
      if (formStatus) {
        formStatus.textContent =
          'Не удалось отправить. Замените YOUR_FORM_ID в форме на свой Formspree ID.';
        formStatus.className = 'form-note error';
      }
    }
  });
}

loadRaces();
loadNews();
console.log('USA Racing Analytics loaded');
