#!/bin/bash
# Останавливать скрипт при ошибках (кроме тех, что мы обрабатываем вручную)
set -e

# Пути к файлам (абсолютные)
SOURCE_FILE="/home/denis/claude_parse_tk/races_for_site.json"
TARGET_DIR="/home/denis/usa-racing-analytics"
TARGET_FILE="$TARGET_DIR/data/races.json"

echo "=== 1. Копирование свежих данных из парсера ==="
if [ -f "$SOURCE_FILE" ]; then
    cp "$SOURCE_FILE" "$TARGET_FILE"
    echo "Файл успешно скопирован в data/races.json"
else
    echo "Внимание: Файл $SOURCE_FILE не найден! Пропускаем копирование."
fi

# Переходим в папку репозитория, чтобы команды git работали из любого места
cd "$TARGET_DIR"

echo "=== 2. Индексируем измененные данные ==="
# Безопасно добавляем конкретные файлы данных. 
# Если файла нет или он не изменен, скрипт не упадет благодаря || true
git add data/races.json 2>/dev/null || true
git add data/news.json 2>/dev/null || true
git add data/results.json 2>/dev/null || true

echo "=== 3. Создаем локальный коммит ==="
CURRENT_DATE=$(date +"%Y-%m-%d %H:%M")

# Проверяем, есть ли изменения готовые к коммиту (staged).
# Использование '|| true' защищает от падения set -e, так как git diff возвращает 1, если изменения есть.
if git diff --cached --quiet; then
    echo "Изменений в данных не обнаружено. Переходим к синхронизации..."
else
    git commit -m "chore: auto-update data ($CURRENT_DATE)"
    echo "Локальный коммит успешно создан."
fi

echo "=== 4. Получаем обновления из GitHub (Интеграция) ==="
# Скачиваем новые коммиты, если они появились на гитхабе, и аккуратно накатываем наши поверх
git pull origin main --rebase -Xours

echo "=== 5. Отправляем изменения на GitHub ==="
git push origin main

echo "=== Готово! Сайт обновлен. ==="
