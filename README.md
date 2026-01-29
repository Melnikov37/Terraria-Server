# TShock Terraria Server

Скрипты для быстрого развертывания TShock сервера Terraria с веб-админкой.

**TShock** — расширенный сервер Terraria с системой прав, защитой регионов, плагинами и REST API.

## Быстрый старт на VPS

### 1. Подключитесь к серверу

```bash
ssh root@your-server-ip
```

### 2. Склонируйте репозиторий

```bash
cd /opt
git clone https://github.com/Melnikov37/Terraria-Server.git terraria
cd terraria
```

### 3. Запустите установку

```bash
chmod +x install.sh
sudo ./install.sh
```

### 4. Откройте порты в файрволе

```bash
# UFW (Ubuntu)
sudo ufw allow 7777/tcp
sudo ufw allow 7777/udp
sudo ufw allow 7878/tcp  # REST API (опционально)
sudo ufw allow 5000/tcp  # Web Admin (опционально)

# Или iptables
sudo iptables -A INPUT -p tcp --dport 7777 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 7777 -j ACCEPT
```

### 5. Запустите сервер

```bash
sudo systemctl start terraria
```

### 6. Настройте администратора

```bash
# Посмотрите токен в логах
sudo journalctl -u terraria | grep -i token

# Подключитесь к серверу через Terraria клиент и введите:
# /setup <token>
# /user add YourName YourPassword superadmin
# /login YourName YourPassword
```

---

## Управление сервером

```bash
sudo systemctl start terraria     # Запустить
sudo systemctl stop terraria      # Остановить
sudo systemctl restart terraria   # Перезапустить
sudo systemctl status terraria    # Статус
sudo journalctl -u terraria -f    # Логи в реальном времени
```

## Веб-админка

```bash
cd /opt/terraria/admin
pip3 install -r requirements.txt
python3 app.py
```

Открыть в браузере: `http://your-server-ip:5000`

### Запуск как сервис (production)

```bash
# Создать сервис
sudo tee /etc/systemd/system/terraria-admin.service << EOF
[Unit]
Description=Terraria Admin Panel
After=network.target

[Service]
Type=simple
User=terraria
WorkingDirectory=/opt/terraria/admin
ExecStart=/usr/bin/python3 /opt/terraria/admin/app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable terraria-admin
sudo systemctl start terraria-admin
```

---

## Структура файлов

```
/opt/terraria/
├── TShock.Server           # Исполняемый файл
├── serverconfig.txt        # Конфигурация сервера
├── worlds/                 # Миры
├── tshock/                 # Настройки TShock
│   ├── config.json         # Главный конфиг TShock
│   ├── sscconfig.json      # Server-Side Characters
│   └── ...
├── ServerPlugins/          # Плагины
└── admin/                  # Веб-админка
    ├── app.py
    └── templates/
```

---

## Конфигурация

### serverconfig.txt (основные настройки)

| Параметр | Описание |
|----------|----------|
| `world` | Путь к файлу мира |
| `autocreate` | Размер мира (1=small, 2=medium, 3=large) |
| `worldname` | Название мира |
| `difficulty` | 0=Classic, 1=Expert, 2=Master, 3=Journey |
| `maxplayers` | Максимум игроков (1-255) |
| `port` | Порт сервера (по умолчанию 7777) |
| `password` | Пароль сервера |

### tshock/config.json (после первого запуска)

| Параметр | Описание |
|----------|----------|
| `ServerPassword` | Пароль сервера |
| `ServerPort` | Порт (7777) |
| `MaxSlots` | Максимум игроков |
| `RestApiEnabled` | Включить REST API |
| `RestApiPort` | Порт REST API (7878) |
| `EnableWhitelist` | Вайтлист |
| `SpawnProtection` | Защита спавна |
| `SpawnProtectionRadius` | Радиус защиты |

---

## Полезные команды TShock

### В игре (чат)

```
/help                           # Список команд
/login <user> <pass>            # Войти в аккаунт
/register <pass>                # Зарегистрироваться
/user add <name> <pass> <group> # Создать пользователя
/group list                     # Список групп
/region define <name>           # Создать регион
/region protect <name> true     # Защитить регион
/kick <player>                  # Кикнуть игрока
/ban add <player>               # Забанить
/save                           # Сохранить мир
/off                            # Выключить сервер
```

### Группы по умолчанию

| Группа | Права |
|--------|-------|
| `guest` | Базовые права |
| `default` | Обычный игрок |
| `vip` | VIP права |
| `trustedadmin` | Админ |
| `superadmin` | Полные права |

---

## REST API

После включения в `config.json`:

```bash
# Статус сервера
curl http://localhost:7878/v3/server/status?token=YOUR_TOKEN

# Список игроков
curl http://localhost:7878/v2/players/list?token=YOUR_TOKEN

# Выполнить команду
curl -X POST http://localhost:7878/v3/server/rawcmd \
  -d "token=YOUR_TOKEN&cmd=/say Hello"
```

---

## Плагины

Плагины размещаются в `/opt/terraria/ServerPlugins/`

Популярные плагины:
- [TShock Plugin Browser](https://github.com/Pryaxis/Plugins)
- [Terracord](https://github.com/FragLand/terracord) - Discord интеграция
- [WorldEdit](https://github.com/Nopezal/WorldEdit) - Редактор мира

---

## Бэкап

```bash
# Ручной бэкап
cp -r /opt/terraria/worlds /backup/terraria-worlds-$(date +%Y%m%d)

# Автоматический (cron)
echo "0 */6 * * * root cp -r /opt/terraria/worlds /backup/terraria-\$(date +\%Y\%m\%d-\%H\%M)" | sudo tee /etc/cron.d/terraria-backup
```

---

## Troubleshooting

### Сервер не запускается

```bash
# Проверить логи
sudo journalctl -u terraria -n 50

# Проверить права
sudo chown -R terraria:terraria /opt/terraria

# Проверить .NET
dotnet --info
```

### Не могу подключиться

1. Проверьте файрвол: `sudo ufw status`
2. Проверьте порт: `sudo netstat -tlnp | grep 7777`
3. Проверьте статус: `sudo systemctl status terraria`

### Мир не создается

Убедитесь, что `worldpath` существует и имеет права записи:

```bash
sudo mkdir -p /opt/terraria/worlds
sudo chown terraria:terraria /opt/terraria/worlds
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `INSTALL_DIR` | `/opt/terraria` | Директория установки |
| `SERVER_USER` | `terraria` | Системный пользователь |
| `TSHOCK_VERSION` | `v5.2.0` | Версия TShock |

---

## Требования

- Linux (Debian 11+, Ubuntu 20.04+)
- 1GB RAM минимум (рекомендуется 2GB+)
- .NET 8.0 Runtime (устанавливается автоматически)
- Python 3.10+ (для веб-админки)
