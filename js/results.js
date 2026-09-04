// Results board — data/results.json (place 1/2/3)
(function () {
  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function placeCell(place) {
    if (place == null || place === '') {
      return '<td class="col-place result-card__pending">—</td>';
    }
    const p = Number(place);
    const cls = p === 1 ? 'place-1' : p === 2 ? 'place-2' : p === 3 ? 'place-3' : '';
    return '<td class="col-place ' + cls + '">' + esc(place) + '</td>';
  }

  function horseRows(horses) {
    const list = (horses || []).slice().sort((a, b) => {
      const pa = a.place == null ? 999 : Number(a.place);
      const pb = b.place == null ? 999 : Number(b.place);
      if (pa !== pb) return pa - pb;
      return (a.post || 0) - (b.post || 0);
    });
    return list
      .map((h) => {
        const ml = h.ml != null ? h.ml : '—';
        return (
          '<tr>' +
          '<td class="col-post">' +
          esc(h.post != null ? h.post : '') +
          '</td>' +
          '<td class="col-name">' +
          esc(h.name || h.horse || '') +
          '</td>' +
          '<td class="col-ml">' +
          esc(ml) +
          '</td>' +
          placeCell(h.place) +
          '</tr>'
        );
      })
      .join('');
  }

  function raceCard(race) {
    const status = race.status || 'pending';
    const badge =
      status === 'official'
        ? '<span class="result-badge result-badge--ok">official</span>'
        : '<span class="result-badge result-badge--pending">pending</span>';
    const meta = [race.time, race.distance, race.purse].filter(Boolean).join(' · ');
    const hasPlace = (race.horses || []).some((h) => h.place != null);
    return (
      '<article class="result-card' +
      (hasPlace ? ' result-card--done' : '') +
      '">' +
      '<div class="result-card__header">' +
      '<span>' +
      esc(race.track || '') +
      '</span>' +
      badge +
      '</div>' +
      '<div class="result-card__title">' +
      esc(race.title || 'Race') +
      (meta ? ' <span style="font-weight:400;opacity:.7">· ' + esc(meta) + '</span>' : '') +
      '</div>' +
      '<div class="race-table-wrap">' +
      '<table class="race-table">' +
      '<thead><tr>' +
      '<th class="col-post">№</th>' +
      '<th class="col-name">Лошадь</th>' +
      '<th class="col-ml">ML</th>' +
      '<th class="col-place">Место</th>' +
      '</tr></thead>' +
      '<tbody>' +
      horseRows(race.horses) +
      '</tbody></table></div></article>'
    );
  }

  async function loadResults() {
    const board = document.getElementById('resultsBoard');
    const meta = document.getElementById('resultsMeta');
    if (!board) return;

    try {
      const res = await fetch('data/results.json?t=' + Date.now());
      if (!res.ok) throw new Error('results.json ' + res.status);
      const data = await res.json();

      const races = data.races || [];
      const withPlace = races.filter((r) =>
        (r.horses || []).some((h) => h.place != null)
      );
      const official = races.filter((r) => r.status === 'official');

      if (meta) {
        const parts = [];
        if (data.date) parts.push('Дата: ' + data.date);
        parts.push(withPlace.length + ' с местами / ' + races.length);
        if (data.source) parts.push(data.source);
        if (data.updated) {
          try {
            parts.push(
              new Date(data.updated).toLocaleString('ru-RU', {
                day: 'numeric',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              })
            );
          } catch (e) {}
        }
        meta.textContent = parts.join(' · ');
      }

      if (!races.length) {
        board.innerHTML =
          '<div class="loading-placeholder">Результатов пока нет</div>';
        return;
      }

      // Сначала заезды с местами, потом остальные
      const sorted = races.slice().sort((a, b) => {
        const ap = (a.horses || []).some((h) => h.place != null) ? 0 : 1;
        const bp = (b.horses || []).some((h) => h.place != null) ? 0 : 1;
        if (ap !== bp) return ap - bp;
        return String(a.id || '').localeCompare(String(b.id || ''));
      });

      board.innerHTML =
        '<div class="results-list">' +
        sorted.map(raceCard).join('') +
        '</div>';
    } catch (err) {
      console.error(err);
      board.innerHTML =
        '<div class="loading-placeholder results-error">Не удалось загрузить результаты</div>';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadResults);
  } else {
    loadResults();
  }
})();
