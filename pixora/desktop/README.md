# Pixora для Windows

Это отдельное desktop-окно Pixora на Electron. Приложение открывает общий аккаунт Pixora в отдельном окне Windows; данные и авторизация остаются на сервере.

## Сборка установщика

GitHub Actions автоматически собирает установщик после изменений в этой папке на ветке `pixora-preview`.

Открой вкладку Actions репозитория, выбери запуск **Build Pixora for Windows**, затем скачай артефакт **Pixora-Windows-Installer** из завершённого запуска. Внутри ZIP находится установщик `Pixora Setup.exe`.

Для локального запуска: `npm install`, затем `npm start`.
Для сборки: `npm run dist`.

Адрес сервиса задаётся переменной окружения `PIXORA_APP_URL`; по умолчанию используется опубликованный preview-адрес Pixora.
