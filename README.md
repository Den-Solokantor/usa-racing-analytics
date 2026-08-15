# USA Racing Analytics

Независимая аналитика по американским скачкам.  
Сайт + данные + место для будущих инструментов.

## Быстрый старт

```bash
# просто открыть локально
python -m http.server 8000
# или
npx serve .
```

Открой http://localhost:8000

## Структура

```
usa-racing-analytics/
├── index.html          # Главная страница
├── css/style.css       # Стили
├── js/main.js          # Логика (загрузка гонок, тема, форма)
├── data/
│   └── races.json      # Гонки дня — редактируй только этот файл
├── assets/             # Картинки (пока пусто)
├── .gitignore
└── README.md
```

## Как обновлять гонки

Редактируй `data/races.json`:

```json
{
  "updated": "2026-08-15T10:00:00Z",
  "races": [
    {
      "id": "sar-8",
      "track": "Saratoga",
      "time": "15:40 ET",
      "title": "Race 8 · Allowance Optional Claiming",
      "distance": "1 mile · Turf",
      "purse": "Purse $110,000",
      "preview": "Текст аналитики...",
      "tags": ["Value possible", "Turf"]
    }
  ]
}
```

Сайт подхватывает изменения автоматически.

## Форма обратной связи

1. Создай форму на [formspree.io](https://formspree.io)
2. В `index.html` замени `YOUR_FORM_ID` на свой ID

## Деплой

### Netlify Drop
Перетащи папку на [app.netlify.com/drop](https://app.netlify.com/drop)

### GitHub Pages
1. Settings → Pages → Source: `main` / root
2. Сайт будет на `https://USERNAME.github.io/REPO_NAME/`

### Vercel / Cloudflare Pages
Аналогично через Git.

## Планы / TODO

- [ ] Подключить более удобный источник данных (вместо ручного JSON)
- [ ] Страницы по отдельным трекам
- [ ] Архив прошлых обзоров
- [ ] Простые скрипты для подготовки `races.json`

## Важно

Официального публичного API у Equibase нет.  
Парсинг сайта Equibase нарушает их ToS — не рекомендуется для постоянной работы.

---

© 2026 USA Racing Analytics
