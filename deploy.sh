#!/bin/bash

# Прерывать выполнение скрипта при любой ошибке
set -e

# Проверяем, есть ли вообще изменения для коммита
if [ -z "$(git status --porcelain)" ]; then
    echo "=== Изменений не обнаружено. Скрипт завершен. ==="
    exit 0
fi

echo "=== 1. Индексируем измененные данные ==="
# Добавляем конкретные файлы, если их нет — добавляем всё измененное
git add data/races.json data/news.json data/results.json 2>/dev/null || git add .

echo "=== 2. Создаем локальный коммит ==="
CURRENT_DATE=$(date +"%Y-%m-%d %H:%M")
git commit -m "chore: auto-update data ($CURRENT_DATE)"

echo "=== 3. Получаем обновления из GitHub (Интеграция) ==="
# Подтягиваем изменения. Стратегия -Xours автоматически разрешит конфликты 
# в пользу ваших только что сгенерированных локальных файлов.
git pull origin main --rebase -Xours

echo "=== 4. Отправляем изменения на GitHub ==="
git push origin main

echo "=== Готово! Сайт обновлен. ==="
