# Развёртывание CRM Sales Bot — Hetzner GPU Server

> Инструкция для системного администратора / DevOps-инженера.
> Цель: развернуть «машину» (on-prem сервер с Qwen-14B) на выделенном GPU-сервере Hetzner
> для интеграции в пайплайн **n8n → Redis → AI → n8n** (MVP).
>
> **Принцип MVP:** «машина» — **stateful**. Хранит память, историю диалогов и базу знаний
> на своей стороне. Получает только последнее сообщение, отдаёт готовый ответ.
> Со стороны WIPON — только доставка сообщения и отправка ответа в канал.

---

## 1. Заказ сервера на Hetzner

### Рекомендуемая конфигурация

| Параметр | GEX44 (рекомендуется) | GEX131 (избыточно) |
|---|---|---|
| CPU | Intel Core i5-13500 (14 ядер) | Intel Xeon Gold 5412U (24 ядра) |
| RAM | 64 GB DDR4 | 256 GB DDR5 ECC |
| GPU | NVIDIA RTX 4000 SFF Ada | NVIDIA RTX PRO 6000 Blackwell |
| VRAM | **20 GB GDDR6** | 96 GB GDDR7 |
| Цена | ~€184-205/мес + €264 setup | ~€889-988/мес + €1555 setup |
| ДЦ | Falkenstein (FSN1) | Nuremberg / Falkenstein |

**GEX44 — оптимальный выбор.** Модели ministral-3:14b-instruct-2512-q8_0 (~9 GB VRAM) + embeddings (~1 GB) умещаются в 20 GB VRAM с запасом.

### Заказ

1. Зайти на https://www.hetzner.com/dedicated-rootserver/matrix-gpu/
2. Выбрать **GEX44**
3. ОС: **Ubuntu 24.04 LTS**
4. Дополнительные диски: по желанию (встроенного NVMe достаточно)
5. Оформить заказ, дождаться активации (обычно 1-3 часа)

После активации на почту придёт:
- IP-адрес сервера
- root-пароль

---

## 2. Обзор архитектуры

### 2.1 Внешний пайплайн (MVP: WIPON → «машина»)

```
  WhatsApp / Instagram (входящее сообщение)
         │
         ▼
  ┌──────────────────────┐
  │  WIPON                │
  │  n8n workflow          │
  │       │               │
  │       ▼               │
  │  Redis буфер          │
  │  (~5 сек, merge       │
  │   сообщений)          │
  └───────┬──────────────┘
          │
          │  POST /api/v1/process
          │  Authorization: Bearer <api_key>
          │  { session_id, user_id, message: { text } }
          ▼
  ┌────────────────────────────────────────────┐
  │  «Машина» — Hetzner GEX44                  │
  │                                            │
  │  Nginx :443 → FastAPI :8000                │
  │       ↓                                    │
  │  CRM Sales Bot (stateful)                  │
  │  ├── память / история (SQLite)             │
  │  ├── KB поиск (FRIDA embeddings, in-proc)  │
  │  └── генерация ответа (Ollama ministral-3:14b-instruct-2512-q8_0)   │
  └───────┬────────────────────────────────────┘
          │
          │  { "answer": "текст ответа" }
          ▼
  ┌──────────────────────┐
  │  n8n workflow          │
  │  → отправка в канал   │
  └──────────────────────┘
```

### 2.2 Внутренняя архитектура сервера

```
                        Интернет
                           │
                    ┌──────┴──────┐
                    │   Hetzner   │
                    │  Firewall   │
                    └──────┬──────┘
                           │ :443 (HTTPS)
                           │ Authorization: Bearer <api_key>
┌──────────────────────────┼──────────────────────────┐
│             Hetzner GEX44 Server                    │
│                          │                          │
│                   ┌──────┴───────┐                  │
│                   │    Nginx     │                  │
│                   │  (reverse    │                  │
│                   │   proxy +    │                  │
│                   │   TLS)       │                  │
│                   │   :443       │                  │
│                   └──────┬───────┘                  │
│                          │ :8000                    │
│                   ┌──────┴───────┐                  │
│                   │  API-обёртка │                  │
│                   │  (FastAPI +  │                  │
│                   │   Uvicorn)   │                  │
│                   │   :8000      │                  │
│                   └──────┬───────┘                  │
│                          │                          │
│  ┌──────────┐     ┌──────┴───────┐     ┌─────────┐ │
│  │  Ollama  │◄────│  CRM Sales   │────►│ FRIDA   │ │
│  │ ministral-3:14b-instruct-2512-q8_0│     │     Bot      │     │embeddings│ │
│  │ :11434   │     │ (stateful)   │     │(in-proc)│ │
│  └──────────┘     └──────┬───────┘     └─────────┘ │
│       GPU                │                          │
│  RTX 4000 SFF      ┌────┴────┐                     │
│    20 GB VRAM       │ SQLite  │                     │
│                     │(snapshot│                     │
│                     │ storage)│                     │
│                     └─────────┘                     │
└─────────────────────────────────────────────────────┘
                           ▲
                           │ HTTPS POST /api/v1/process
                           │ Bearer <api_key>
              ┌────────────┴───────────┐
              │  WIPON (n8n workflow)   │
              │  WhatsApp / Instagram  │
              │  Redis (буфер ~5 сек)  │
              └────────────────────────┘
```

### 2.3 Идентификаторы

| Поле | Описание | Пример |
|---|---|---|
| `session_id` | ID бота / аккаунта | `BOT_7000` (WAHA), `recipientId` (IG) |
| `user_id` | ID конечного пользователя | номер телефона (WA), `senderId` (IG) |

**Критически важно:** память / состояние хранится по ключу `(session_id, user_id)`.
Разные пользователи внутри одного `BOT_7000` не смешиваются.

### 2.4 Ограничения MVP

| # | Ограничение |
|---|---|
| 1 | Передаётся **только последнее сообщение** (после Redis-буфферинга ~5 сек), не последние 10 |
| 2 | KB и KB-поиск **полностью на стороне «машины»** (никаких вызовов инструментов/поиска со стороны WIPON) |
| 3 | Стриминга нет |
| 4 | Медиа (картинки/аудио) — «машина» получает **готовый текст**: `"[image]: <описание>"`, `"[audio transcript]: <транскрипт>"` |
| 5 | Кросс-канальная склейка между Instagram и WhatsApp невозможна |
| 6 | Требуется надёжная сетевая связность: облачная инфраструктура WIPON ↔ сервер в HQ |

### 2.5 Сетевое подключение

Допустимые варианты (важен результат, способ согласуется отдельно):
- Публичный HTTPS endpoint + IP allowlist наших адресов + API key
- VPN site-to-site
- Reverse tunnel

**Авторизация обязательна:** `Authorization: Bearer <api_key>`

**Ключевой принцип:** «машина» — **stateful**. Хранит память, историю диалогов и базу знаний на своей стороне. Получает только последнее сообщение + идентификаторы, отдаёт готовый ответ.

---

## 3. Первоначальная настройка сервера

### 3.1 Подключение по SSH

```bash
# С локальной машины
ssh root@<IP_СЕРВЕРА>
```

### 3.2 Создание рабочего пользователя

```bash
# Создать пользователя
adduser deploy
usermod -aG sudo deploy

# Настроить SSH-ключ для пользователя
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### 3.3 Защита SSH

```bash
# Отредактировать /etc/ssh/sshd_config:
#   PermitRootLogin no
#   PasswordAuthentication no
#   PubkeyAuthentication yes

sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
# Ubuntu 24.04: имя сервиса обычно `ssh`
sudo systemctl restart ssh
```

> После этого убедитесь, что можете зайти как `ssh deploy@<IP_СЕРВЕРА>` прежде чем закрывать root-сессию.

### 3.4 Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git curl wget \
    nginx certbot python3-certbot-nginx ufw
```

### 3.5 Файрвол (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP (для Let's Encrypt)
sudo ufw allow 443/tcp     # HTTPS
# НЕ открывать 8000 и 11434 — они только для localhost
sudo ufw enable
sudo ufw status
```

---

## 4. Установка NVIDIA-драйверов

Hetzner ставит Ubuntu без GPU-драйверов. Нужно установить вручную.

```bash
# Проверить, видит ли система GPU
lspci | grep -i nvidia
# Должно показать: NVIDIA RTX 4000 SFF Ada Generation

# Установка драйверов
sudo apt install -y nvidia-driver-550
# Или через ubuntu-drivers:
# sudo ubuntu-drivers install

# Перезагрузка
sudo reboot

# После перезагрузки — проверка
nvidia-smi
# Должна отобразиться карта RTX 4000 SFF Ada, 20 GB VRAM
```

> Если `nvidia-smi` показывает карту — драйверы установлены корректно.

---

## 5. Установка Ollama

```bash
# Установка
curl -fsSL https://ollama.com/install.sh | sh

# Проверка
ollama --version

# Ollama автоматически создаёт systemd-сервис
sudo systemctl enable ollama
sudo systemctl start ollama

# Скачивание модели (~9 GB)
ollama pull ministral-3:14b-instruct-2512-q8_0

# Проверка
ollama list
# Должна появиться строка: ministral-3:14b-instruct-2512-q8_0 ... 9.3 GB

# Тест
curl http://localhost:11434/api/tags
```

---

## 6. Установка бота

### 6.1 Клонирование проекта

```bash
# Войти под рабочим пользователем
su - deploy

cd /home/deploy
git clone <URL_РЕПОЗИТОРИЯ> crm_sales_bot
cd crm_sales_bot
```

### 6.2 Python-окружение

```bash
cd /home/deploy/crm_sales_bot

# Создание виртуального окружения
python3 -m venv .venv

# Активация
source .venv/bin/activate

# Установка зависимостей бота
pip install -e .

# Установка зависимостей для API-сервера
pip install fastapi uvicorn

# Проверка
python3 -c "from src.bot import SalesBot; print('OK')"
```

> Для некоторых flow/режимов первый запуск может скачать embedding-модели (~1-2 GB):
> - `ai-forever/FRIDA` — для семантического поиска по базе знаний
> - `BAAI/bge-reranker-v2-m3` — для ре-ранкинга результатов
>
> В production API (`autonomous`) семантические embeddings по умолчанию отключены
> для снижения GPU/RAM нагрузки.

### 6.3 Проверка в интерактивном режиме

```bash
source /home/deploy/crm_sales_bot/.venv/bin/activate
python3 -m src.bot --flow autonomous

# В консоли бота набрать:
# > Привет, расскажи о вашей CRM
# Бот должен ответить осмысленно
# > /quit  — выход
```

---

## 7. API-обёртка (FastAPI, autonomous-only)

В репозитории уже есть production API: `src/api.py`.
Для деплоя используем и дорабатываем **этот** файл, не создаём новый с нуля.

> **MVP-контракт:** WIPON отправляет только последнее сообщение + идентификаторы.
> «Машина» сама хранит snapshot-ы в локальной SQLite, восстанавливает состояние по `(session_id, user_id)`
> и отдельно сохраняет собранные данные в таблицу `user_profiles`.

### 7.1 API-контракт

#### Запрос (WIPON → машина): `POST /api/v1/process`

Заголовки:
- `Authorization: Bearer <api_key>`
- `Content-Type: application/json`

```json
{
  "request_id": "uuid",
  "channel": "whatsapp|instagram",
  "session_id": "BOT_7000",
  "user_id": "77022951810",
  "message": {
    "text": "последнее сообщение (после Redis-буфферинга)",
    "timestamp_ms": 1770801587839
  },
  "context": {
    "time_of_day": "morning|day|evening|night",
    "timezone": "Asia/Qyzylorda",
    "meta": {}
  }
}
```

> Если вход был картинка/аудио, `message.text` содержит готовый текст:
> `"[image]: <описание/капшен>"` или `"[audio transcript]: <транскрипт>"`.
>
> **Важно:** `flow_name` в API-запрос не передаётся. Продовый API фиксирован на `flow_name="autonomous"`.

#### Ответ (машина → WIPON)

```json
{
  "answer": "текст ответа пользователю",
  "meta": {
    "model": "qwen-14b",
    "processing_ms": 0,
    "kb_used": true
  }
}
```

- `answer` — строка, готовая к отправке в канал (кроме стандартной нарезки на ≤200 символов на стороне WIPON).
- Ответ всегда валидный JSON.

#### Ошибки

При проблемах сервер возвращает структурированную ошибку **с non-2xx HTTP статусом**:

```json
{
  "error": {
    "code": "BAD_REQUEST|UNAUTHORIZED|RATE_LIMIT|INTERNAL",
    "message": "описание"
  }
}
```

Статусы:
- `400` → `BAD_REQUEST` (невалидный payload, пустой `message.text`)
- `401` → `UNAUTHORIZED` (нет/неверный Bearer token)
- `404` → `NOT_FOUND` (профиль не найден в `GET /api/v1/users/{user_id}/profile`)
- `429` → `RATE_LIMIT` (если будет включён rate-limit слой)
- `500` → `INTERNAL` (внутренняя ошибка)

Правило на стороне WIPON: любой non-2xx HTTP или наличие поля `error` → запрос неуспешен → включить fallback.

### 7.2 Что обязательно должно быть в `src/api.py`

Проверочный список текущей production-версии:
- `SalesBot` поднимается только в `autonomous` flow (`flow_name="autonomous"`).
- В SQLite есть две таблицы: `conversations` (snapshot) и `user_profiles` (собранные данные отдельно).
- Для SQLite включены `PRAGMA journal_mode=WAL` + `timeout/busy_timeout` для устойчивости под threadpool-нагрузкой.
- Ошибки API возвращаются структурированно (`{"error": ...}`) и с корректным HTTP-кодом.
- При восстановлении из snapshot вызывается `SalesBot.from_snapshot(..., enable_tracing=True)`.
- После каждого хода сохраняются и snapshot, и профиль пользователя.
- Доступен служебный endpoint `GET /api/v1/users/{user_id}/profile` для выгрузки накопленных данных.

### 7.3 Нефункциональные требования

| Параметр | Значение |
|---|---|
| Время ответа | ≤ 30–45 секунд (согласовать) |
| Логи | Не логировать полный текст переписки по умолчанию |
| Изоляция памяти | Ключ `(session_id, user_id)` — не смешивать пользователей |

---

## 8. Systemd-сервисы

### 8.1 Ollama (уже создан при установке)

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

### 8.2 CRM Sales Bot

Секреты и runtime-параметры храним отдельно в root-only env-файле:

```bash
sudo install -m 600 -o root -g root /dev/null /etc/crm-sales-bot.env
sudo nano /etc/crm-sales-bot.env
```

Пример содержимого `/etc/crm-sales-bot.env`:

```bash
API_KEY=<сгенерированный_длинный_ключ>
DB_PATH=/home/deploy/crm_sales_bot/data/conversations.db
SQLITE_TIMEOUT_SECONDS=30
SQLITE_BUSY_TIMEOUT_MS=5000
```

Создать файл `/etc/systemd/system/crm-sales-bot.service`:

```ini
[Unit]
Description=CRM Sales Bot API
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=deploy
WorkingDirectory=/home/deploy/crm_sales_bot
Environment=PATH=/home/deploy/crm_sales_bot/.venv/bin:/usr/bin:/bin
EnvironmentFile=/etc/crm-sales-bot.env
ExecStart=/home/deploy/crm_sales_bot/.venv/bin/uvicorn src.api:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1 \
    --log-level info
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> **--host 127.0.0.1** — бот слушает только localhost. Наружу трафик идёт через Nginx.
>
> **--workers 1** — обязательно. Это исключает дублирование тяжёлых runtime-компонентов
> и гонки при stateful-обработке одного пользователя в нескольких воркерах.
>
> `EnvironmentFile=/etc/crm-sales-bot.env` — API-ключ не хранится в unit-файле и не утекает в `systemctl cat`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable crm-sales-bot
sudo systemctl start crm-sales-bot

# Проверка
sudo systemctl status crm-sales-bot

# Логи
sudo journalctl -u crm-sales-bot -f
```

---

## 9. Nginx + TLS (Let's Encrypt)

### 9.1 DNS

Направить домен (например `bot.example.com`) на IP сервера:
```
bot.example.com → A → <IP_СЕРВЕРА>
```

Подождать 5-10 минут, проверить:
```bash
dig bot.example.com
```

### 9.2 Конфиг Nginx

Создать `/etc/nginx/sites-available/crm-sales-bot`:

```nginx
server {
    listen 80;
    server_name bot.example.com;

    # Редирект на HTTPS (после получения сертификата certbot сделает это сам)
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name bot.example.com;

    # TLS-сертификаты (будут созданы certbot)
    # ssl_certificate /etc/letsencrypt/live/bot.example.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/bot.example.com/privkey.pem;

    # Ограничение размера запроса (snapshots могут быть большими)
    client_max_body_size 10M;

    # Таймаут — бот может думать долго
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;

    # Rate limiting (опционально)
    # limit_req zone=api burst=10 nodelay;

    # IP allowlist (раскомментировать и указать IP WIPON-серверов)
    # allow <IP_WIPON_1>;
    # allow <IP_WIPON_2>;
    # deny all;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
    }
}
```

```bash
# Активировать конфиг
sudo ln -s /etc/nginx/sites-available/crm-sales-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 9.3 TLS-сертификат (Let's Encrypt)

```bash
sudo certbot --nginx -d bot.example.com

# Автообновление (certbot ставит таймер автоматически)
sudo systemctl status certbot.timer
```

После этого Nginx будет принимать HTTPS-запросы на :443 и проксировать их на бота на :8000.

---

## 10. Проверка после развёртывания

### 10.1 Изнутри сервера

```bash
# Health-check напрямую
curl http://127.0.0.1:8000/health
# {"status":"ok","model":"qwen-14b"}

# Ollama
curl http://127.0.0.1:11434/api/tags
```

### 10.2 Снаружи (с любой машины)

```bash
# Health-check через Nginx + TLS
curl https://bot.example.com/health
# {"status":"ok","model":"qwen-14b"}
```

### 10.3 Тестовый запрос (новый диалог)

```bash
curl -X POST https://bot.example.com/api/v1/process \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-api-key-here" \
  -d '{
    "session_id": "BOT_7000",
    "user_id": "77022951810",
    "channel": "whatsapp",
    "message": {
      "text": "Привет, расскажи о вашей CRM",
      "timestamp_ms": 1770801587839
    },
    "context": {
      "time_of_day": "day",
      "timezone": "Asia/Almaty"
    }
  }'
```

Ожидаемый ответ:

```json
{
  "answer": "Добрый день! Расскажите, пожалуйста, о вашей компании...",
  "meta": {
    "model": "qwen-14b",
    "processing_ms": 8500,
    "kb_used": false
  }
}
```

### 10.4 Тестовый запрос (продолжение диалога)

Повторный запрос от того же пользователя — «машина» сама восстановит контекст из SQLite:

```bash
curl -X POST https://bot.example.com/api/v1/process \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-api-key-here" \
  -d '{
    "session_id": "BOT_7000",
    "user_id": "77022951810",
    "channel": "whatsapp",
    "message": {
      "text": "Сколько стоит?",
      "timestamp_ms": 1770801592000
    }
  }'
```

> Snapshot не передаётся — он хранится на стороне «машины» по ключу `(BOT_7000, 77022951810)`.

### 10.5 Тест ошибки авторизации

```bash
curl -X POST https://bot.example.com/api/v1/process \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer wrong-key" \
  -d '{"session_id":"X","user_id":"Y","message":{"text":"test"}}'
# Ожидаемый ответ: HTTP 401 + структурированный JSON error
# {"error":{"code":"UNAUTHORIZED","message":"Invalid API key"}}
```

### 10.6 Тест отдельного профиля пользователя

После 2-3 диалоговых ходов проверить, что профиль сохраняется отдельно от snapshot:

```bash
curl -X GET "https://bot.example.com/api/v1/users/77022951810/profile" \
  -H "Authorization: Bearer your-secret-api-key-here"
```

Ожидаемый результат: JSON со списком `profiles` (история собранных данных по пользователю).

---

## 11. Конфигурация бота

### 11.1 Основной файл настроек

`src/settings.yaml` — все параметры бота: модель LLM, пороги, feature flags и др.

Ключевые секции:

| Секция | Что настраивает |
|---|---|
| `llm` | Модель, URL Ollama, таймаут |
| `retriever` | Поиск по базе знаний, модель эмбеддингов |
| `reranker` | Ре-ранкинг результатов поиска |
| `flow` | Активная методология продаж (в production API используется `autonomous`) |
| `feature_flags` | Включение/отключение 62 фич |

### 11.2 База знаний

`src/knowledge/data/` — 17 YAML-файлов с 1969 секциями: цены, продукты, оборудование, интеграции, FAQ и т.д.

### 11.3 Методологии продаж (flows)

В репозитории есть несколько flow для разработки/экспериментов, но production endpoint
`POST /api/v1/process` работает в режиме **autonomous-only**.

Переключение flow через API-запрос **не используется**.

### 11.4 Переменные окружения

Бизнес-конфигурация бота — в `src/settings.yaml`.
Операционные параметры сервиса (`API_KEY`, `DB_PATH`, SQLite timeouts, FF overrides) —
через `/etc/crm-sales-bot.env`, подключённый как `EnvironmentFile` в systemd.

Пример переопределения feature flags через окружение:

```bash
export FF_tone_analysis=true
export FF_reranker=false
```

Для systemd — добавить в `/etc/crm-sales-bot.env`:

```ini
FF_tone_analysis=true
```

---

## 12. Мониторинг и логи

### Логи сервисов

```bash
# Логи бота
sudo journalctl -u crm-sales-bot -f

# Логи Ollama
sudo journalctl -u ollama -f

# Логи Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Проверка GPU

```bash
# Текущая загрузка GPU
nvidia-smi

# Мониторинг в реальном времени
watch -n 2 nvidia-smi
```

### Проверка доступности

```bash
# Все сервисы одной командой
echo "Ollama: $(curl -so /dev/null -w '%{http_code}' http://127.0.0.1:11434/api/tags)"
echo "Bot:    $(curl -so /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)"
echo "Nginx:  $(curl -so /dev/null -w '%{http_code}' https://bot.example.com/health)"
```

---

## 13. Перезапуск и обновление

### Перезапуск

```bash
sudo systemctl restart crm-sales-bot
```

### Обновление кода

```bash
# SSH на сервер
ssh deploy@<IP_СЕРВЕРА>

cd /home/deploy/crm_sales_bot

# Остановить бота
sudo systemctl stop crm-sales-bot

# Обновить код
git pull

# Обновить зависимости (если изменились)
source .venv/bin/activate
pip install -e .

# Запустить бота
sudo systemctl start crm-sales-bot
```

### Обновление модели LLM

```bash
ollama pull ministral-3:14b-instruct-2512-q8_0
sudo systemctl restart ollama
```

---

## 14. Безопасность

### Что уже сделано (по инструкции выше)

- SSH: root-логин запрещён, только по ключам
- UFW: открыты только 22, 80, 443
- Ollama и API-сервер слушают только localhost
- TLS через Let's Encrypt
- Nginx как reverse proxy
- **API-ключ (Bearer token)** — авторизация в FastAPI (`Authorization: Bearer <api_key>`)
- **Nginx: заготовка IP allowlist** — раскомментировать и указать IP WIPON-серверов

### Управление API-ключом

API-ключ задаётся через `/etc/crm-sales-bot.env` (root-only, `0600`):

```bash
# Сгенерировать ключ
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Обновить env-файл
sudo nano /etc/crm-sales-bot.env
# API_KEY=<сгенерированный_ключ>

sudo systemctl restart crm-sales-bot
```

Этот же ключ передаётся команде WIPON для настройки n8n HTTP Request node.

### Рекомендации на будущее

| Мера | Как |
|---|---|
| Fail2ban | `sudo apt install fail2ban` — защита от брутфорса SSH |
| IP whitelist (обязательно) | В Nginx: раскомментировать `allow/deny` блок, указать IP WIPON |
| Rate limiting | В Nginx: `limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;` |
| Мониторинг | Prometheus + Grafana или простой healthcheck через cron |
| Бэкапы SQLite | `data/conversations.db` — snapshot-ы + `user_profiles`. Бэкапить периодически |
| Ротация ключей | Менять API_KEY периодически, координируя с WIPON |

---

## 15. Устранение неполадок

| Проблема | Решение |
|---|---|
| `Connection refused :11434` | `sudo systemctl start ollama` — Ollama не запущен |
| `model not found` | `ollama pull ministral-3:14b-instruct-2512-q8_0` — модель не скачана |
| `nvidia-smi` не работает | `sudo apt install nvidia-driver-550 && sudo reboot` |
| Ответ > 2 мин | Проверить `nvidia-smi`: модель может быть на CPU вместо GPU |
| `CUDA out of memory` | Проверить `nvidia-smi` — нет ли лишних процессов |
| 502 Bad Gateway (Nginx) | `sudo systemctl status crm-sales-bot` — бот не запущен |
| 504 Gateway Timeout | Увеличить `proxy_read_timeout` в Nginx (бот думает долго) |
| Первый запрос ~30 сек | Нормально: Ollama загружает модель в VRAM при первом запросе |
| `ModuleNotFoundError` | `source .venv/bin/activate && pip install -e .` |
| TLS не работает | `sudo certbot renew --dry-run` — проверить сертификат |
| `ERR_CONNECTION_REFUSED` :443 | `sudo systemctl status nginx` + проверить UFW |

---

## 16. Потребление ресурсов (GEX44)

| Ресурс | Доступно | Потребление в покое | При запросе |
|---|---|---|---|
| GPU VRAM | 20 GB | ~9-10 GB (модель + runtime-кэши) | ~10-12 GB |
| RAM | 64 GB | ~3 GB | ~4 GB |
| CPU | 14 ядер | < 5% | 20-40% |
| Время ответа | — | — | 5-20 сек |

> Время ответа на GEX44 (RTX 4000 SFF Ada) будет чуть больше, чем на RTX 5090, но в пределах нормы.

---

## 17. Порты (итого)

| Сервис | Порт | Слушает | Доступ извне |
|---|---|---|---|
| SSH | 22 | 0.0.0.0 | Да (только по ключам) |
| Nginx HTTP | 80 | 0.0.0.0 | Да (редирект на 443) |
| Nginx HTTPS | 443 | 0.0.0.0 | Да |
| CRM Bot API | 8000 | 127.0.0.1 | Нет (только через Nginx) |
| Ollama LLM | 11434 | 127.0.0.1 | Нет |

---

## 18. Стоимость

| Статья | Сумма |
|---|---|
| Сервер GEX44 (ежемесячно) | ~€184-205/мес |
| Setup fee (разовый) | ~€264 |
| Домен (опционально) | ~€10-15/год |
| TLS (Let's Encrypt) | Бесплатно |
| **Итого (первый месяц)** | **~€450-470** |
| **Итого (последующие)** | **~€184-205/мес** |

---

## Чеклист развёртывания

```
СЕРВЕР
[ ] GEX44 заказан и активирован
[ ] SSH-ключ загружен, root-доступ есть
[ ] Пользователь deploy создан
[ ] SSH защищён (root отключён, пароли отключены)
[ ] UFW настроен (22, 80, 443)
[ ] Система обновлена (apt upgrade)

NVIDIA + OLLAMA
[ ] NVIDIA-драйвер установлен (nvidia-smi работает)
[ ] Ollama установлен и запущен как systemd-сервис
[ ] Модель ministral-3:14b-instruct-2512-q8_0 скачана (ollama list)

БОТ
[ ] Репозиторий склонирован в /home/deploy/crm_sales_bot
[ ] Python venv создан, зависимости установлены (pip install -e .)
[ ] FastAPI + Uvicorn установлены
[ ] src/api.py актуален (autonomous-only + user_profiles + structured errors + SQLite WAL/timeouts)
[ ] /etc/crm-sales-bot.env создан с правами 600
[ ] API_KEY сгенерирован и задан в /etc/crm-sales-bot.env
[ ] DB_PATH задан в /etc/crm-sales-bot.env
[ ] Интерактивный тест пройден (python3 -m src.bot --flow autonomous)
[ ] Systemd-юнит crm-sales-bot.service создан и запущен
[ ] curl http://127.0.0.1:8000/health отвечает OK

СЕТЬ + БЕЗОПАСНОСТЬ
[ ] DNS настроен (домен → IP сервера)
[ ] Nginx настроен как reverse proxy
[ ] Nginx: Authorization header проксируется
[ ] Nginx: IP allowlist (IP WIPON-серверов) — раскомментировать
[ ] TLS-сертификат получен (certbot)
[ ] curl https://bot.example.com/health отвечает OK снаружи

ИНТЕГРАЦИЯ (MVP)
[ ] Тестовый запрос с Bearer-токеном прошёл (см. раздел 10.3)
[ ] Тест продолжения диалога — бот помнит контекст (раздел 10.4)
[ ] Тест ошибки авторизации — 401 при неверном ключе (раздел 10.5)
[ ] Профиль пользователя сохраняется и читается через /api/v1/users/{user_id}/profile (раздел 10.6)
[ ] Модель Ollama прогрета (первый запрос прошёл без ошибок)
[ ] API_KEY передан команде WIPON для настройки n8n
[ ] WIPON n8n workflow подключен и шлёт тестовые запросы
[ ] Fallback на Vertex/OpenAI проверен (при ошибке «машины»)
```
