// Theme toggle
const themeToggle = document.getElementById('themeToggle');
const html = document.documentElement;

const savedTheme = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-theme', savedTheme);
updateToggleIcon(savedTheme);

themeToggle.addEventListener('click', () => {
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateToggleIcon(next);
});

function updateToggleIcon(theme) {
  themeToggle.textContent = theme === 'dark' ? '🌙' : '☀️';
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

// ===== Load races from JSON =====
async function loadRaces() {
  const grid = document.getElementById('racesGrid');
  const updatedEl = document.getElementById('racesUpdated');

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
        const isSecondary = !['Value possible', 'Watchlist'].includes(tag);
        return `<span class="tag ${isSecondary ? 'tag-secondary' : ''}">${tag}</span>`;
      }).join('');

      return `
        <article class="race-card">
          <div class="race-card-header">
            <span class="track-badge">${race.track}</span>
            <span class="race-time">${race.time}</span>
          </div>
          <h3 class="race-title">${race.title}</h3>
          <div class="race-meta">
            <span>${race.distance || ''}</span>
            <span>${race.purse || ''}</span>
          </div>
          <div class="race-preview">
            <p>${race.preview || ''}</p>
          </div>
          <div class="race-tags">${tagsHtml}</div>
        </article>
      `;
    }).join('');

    document.querySelectorAll('.race-card').forEach(el => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(16px)';
      el.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
      observer.observe(el);
    });

  } catch (err) {
    console.error(err);
    grid.innerHTML = '<div class="loading-placeholder">Ошибка загрузки гонок. Проверьте data/races.json</div>';
  }
}

document.querySelectorAll('.track-card, .analytics-card, .value-item').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(16px)';
  el.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
  observer.observe(el);
});

// Contact form (Formspree)
const contactForm = document.getElementById('contactForm');
const formStatus = document.getElementById('formStatus');

if (contactForm) {
  contactForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    formStatus.textContent = 'Отправка...';
    formStatus.className = 'form-note';

    const formData = new FormData(contactForm);

    try {
      const res = await fetch(contactForm.action, {
        method: 'POST',
        body: formData,
        headers: { 'Accept': 'application/json' }
      });

      if (res.ok) {
        formStatus.textContent = 'Сообщение отправлено. Спасибо!';
        formStatus.className = 'form-note success';
        contactForm.reset();
      } else {
        throw new Error('Ошибка отправки');
      }
    } catch (err) {
      formStatus.textContent = 'Не удалось отправить. Замените YOUR_FORM_ID в форме на свой Formspree ID.';
      formStatus.className = 'form-note error';
    }
  });
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
      <a class="news-item" href="${item.url || '#'}" target="_blank" rel="noopener">
        <div class="news-item-meta">
          <span class="news-source">${item.source || 'News'}</span>
          <span class="news-time">${item.time || ''}</span>
        </div>
        <div class="news-item-title">${item.title}</div>
        ${item.summary ? `<div class="news-item-summary">${item.summary}</div>` : ''}
      </a>
    `).join('');
  } catch (err) {
    console.error(err);
    list.innerHTML = '<div class="loading-placeholder">Не удалось загрузить новости</div>';
  }
}

// Init
loadRaces();
loadNews();
console.log('USA Racing Analytics loaded');
