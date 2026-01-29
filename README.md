# Terraria Server (TShock)

Скрипты для развертывания **ванильно-подобного** сервера Terraria с полным управлением через веб-интерфейс.

Сервер работает на TShock, но настроен так, что игроки не видят никаких отличий от ванильного сервера — без регистрации, команд и сообщений TShock.

## Возможности

- **Ванильный опыт** — игроки не видят TShock, не нужна регистрация
- **Веб-админка** — полное управление сервером через браузер
- **Управление игроками** — kick, ban, unban
- **Управление миром** — время, погода, вторжения, боссы
- **Broadcast** — сообщения всем игрокам
- **Выполнение команд** — любые TShock команды через веб

---

## Быстрый старт на VPS

### 1. Подключись к серверу

```bash
ssh root@your-server-ip
```

### 2. Склонируй репозиторий

```bash
cd /opt
git clone https://github.com/Melnikov37/Terraria-Server.git terraria
cd terraria
```

### 3. Запусти установку

```bash
chmod +x install.sh
sudo ./install.sh
```

**ВАЖНО:** Сохрани пароль админки, который покажется в конце установки!

### 4. Открой порты

```bash
sudo ufw allow 7777/tcp
sudo ufw allow 7777/udp
sudo ufw allow 5000/tcp  # Веб-админка
```

### 5. Запусти сервер

```bash
sudo systemctl start terraria
sudo systemctl start terraria-admin
```

### 6. Открой админку

```
http://your-server-ip:5000
```

Войди с логином `admin` и паролем из установки.

---

## Управление

### Команды systemctl

```bash
# Игровой сервер
sudo systemctl start terraria
sudo systemctl stop terraria
sudo systemctl restart terraria
sudo systemctl status terraria

# Веб-админка
sudo systemctl start terraria-admin
sudo systemctl stop terraria-admin

# Логи
sudo journalctl -u terraria -f
```

### Веб-админка

| Раздел | Функции |
|--------|---------|
| **Dashboard** | Статус сервера, онлайн игроки, start/stop/restart |
| **Players** | Kick, ban, unban, список банов |
| **World** | Время, погода, вторжения, broadcast, команды |
| **Config** | Настройки сервера (порт, пароль, макс. игроков) |

---

## Структура файлов

```
/opt/terraria/
├── TShock.Server           # Сервер
├── serverconfig.txt        # Основной конфиг
├── worlds/                 # Миры
├── tshock/
│   ├── config.json         # Конфиг TShock
│   └── tshock.sqlite       # База данных
├── ServerPlugins/          # Плагины
└── admin/
    ├── app.py              # Веб-админка
    ├── .env                # Креденшалы (REST токен, пароль)
    ├── requirements.txt
    └── templates/
```

---

## Конфигурация

### Файл .env (креденшалы админки)

```bash
# Посмотреть
cat /opt/terraria/admin/.env

# Там находятся:
# - REST_TOKEN — токен для TShock REST API
# - ADMIN_PASSWORD — пароль веб-админки
# - SECRET_KEY — секрет Flask
```

### Изменить пароль админки

```bash
nano /opt/terraria/admin/.env
# Измени ADMIN_PASSWORD=новый_пароль
sudo systemctl restart terraria-admin
```

---

## Ванильность

Сервер настроен максимально "ванильно":

| Настройка | Значение |
|-----------|----------|
| Требуется логин | Нет |
| Сообщения TShock | Скрыты |
| Защита спавна | Отключена |
| Командный префикс | Скрыт от игроков |
| Автосохранение | Каждые 10 минут (тихо) |

Игроки просто подключаются и играют как на обычном сервере.

---

## Troubleshooting

### Не могу подключиться к серверу

```bash
# Проверь статус
sudo systemctl status terraria

# Проверь порт
sudo netstat -tlnp | grep 7777

# Проверь файрвол
sudo ufw status
```

### Админка не работает

```bash
# Проверь статус
sudo systemctl status terraria-admin

# Проверь логи
sudo journalctl -u terraria-admin -n 50

# Проверь .env файл
cat /opt/terraria/admin/.env
```

### REST API не отвечает

1. Убедись что сервер запущен и прошла загрузка мира
2. Проверь что REST включен в `/opt/terraria/tshock/config.json`:
   ```json
   "RESTApiEnabled": true,
   "RESTApiPort": 7878
   ```

### Сбросить пароль админки

```bash
# Сгенерировать новый пароль
NEW_PASS=$(openssl rand -hex 16)
echo "New password: $NEW_PASS"

# Записать в .env
sed -i "s/ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$NEW_PASS/" /opt/terraria/admin/.env

# Перезапустить админку
sudo systemctl restart terraria-admin
```

---

## Требования

- Linux (Debian 11+, Ubuntu 20.04+)
- 1GB RAM минимум (2GB+ рекомендуется)
- .NET 8.0 Runtime (устанавливается автоматически)
- Python 3.10+

---

## Порты

| Порт | Протокол | Назначение |
|------|----------|------------|
| 7777 | TCP/UDP | Игровой сервер |
| 7878 | TCP | REST API (только localhost) |
| 5000 | TCP | Веб-админка |
