# Развёртывание CRM Sales Bot — Hetzner GPU Server

> Инструкция для системного администратора / DevOps-инженера.
> Цель: развернуть бота на выделенном GPU-сервере Hetzner как постоянно работающий сервис.

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

**GEX44 — оптимальный выбор.** Модели qwen3:14b (~9 GB VRAM) + embeddings (~1 GB) умещаются в 20 GB VRAM с запасом.

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

```
                        Интернет
                           │
                    ┌──────┴──────┐
                    │   Hetzner   │
                    │  Firewall   │
                    └──────┬──────┘
                           │ :443 (HTTPS)
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
│  │ qwen3:14b│     │     Bot      │     │embeddings│ │
│  │ :11434   │     │   (Python)   │     │(in-proc)│ │
│  └──────────┘     └──────────────┘     └─────────┘ │
│       GPU                                           │
│  RTX 4000 SFF                                       │
│    20 GB VRAM                                       │
└─────────────────────────────────────────────────────┘
                           ▲
                           │ HTTPS POST /api/v1/process
                           │
              ┌────────────┴───────────┐
              │   Внешняя система      │
              │ (мессенджер-платформа,  │
              │  MongoDB, Wazzup и тд) │
              └────────────────────────┘
```

**Ключевой принцип:** бот — **stateless**. Состояние диалога (snapshot) хранится во внешней системе. Бот принимает snapshot на вход, обрабатывает сообщение, возвращает обновлённый snapshot.

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
sudo systemctl restart sshd
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
curl -fsSL https://ollama.ai/install.sh | sh

# Проверка
ollama --version

# Ollama автоматически создаёт systemd-сервис
sudo systemctl enable ollama
sudo systemctl start ollama

# Скачивание модели (~9 GB)
ollama pull qwen3:14b

# Проверка
ollama list
# Должна появиться строка: qwen3:14b ... 9.3 GB

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

> **Первый запуск** скачает embedding-модели (~1-2 GB):
> - `ai-forever/FRIDA` — для семантического поиска по базе знаний
> - `BAAI/bge-reranker-v2-m3` — для ре-ранкинга результатов
>
> Модели кешируются в `~/.cache/huggingface/`.

### 6.3 Проверка в интерактивном режиме

```bash
source /home/deploy/crm_sales_bot/.venv/bin/activate
python3 -m src.bot

# В консоли бота набрать:
# > Привет, расскажи о вашей CRM
# Бот должен ответить осмысленно
# > /quit  — выход
```

---

## 7. API-обёртка (FastAPI)

Бот поставляется без HTTP-сервера. Для работы по сети нужна API-обёртка.

### 7.1 Создать файл API-сервера

Создать файл `src/api.py`:

```python
"""
REST API обёртка для CRM Sales Bot.
Запуск: uvicorn src.api:app --host 127.0.0.1 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.bot import SalesBot
from src.llm import OllamaLLM

logger = logging.getLogger(__name__)

# Глобальный LLM-клиент (переиспользуется между запросами)
_llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация LLM при старте, очистка при остановке."""
    global _llm
    _llm = OllamaLLM()
    logger.info("LLM client initialized")
    yield
    _llm = None


app = FastAPI(
    title="CRM Sales Bot API",
    version="1.0.0",
    lifespan=lifespan,
)


class ProcessRequest(BaseModel):
    message: str = Field(..., description="Сообщение пользователя")
    snapshot: dict | None = Field(None, description="Snapshot предыдущего состояния")
    flow_name: str = Field("spin_selling", description="Методология продаж")
    config_name: str = Field("default", description="Имя конфигурации")


class HealthResponse(BaseModel):
    status: str
    model: str


@app.get("/health", response_model=HealthResponse)
async def health():
    """Проверка доступности сервиса."""
    return HealthResponse(status="ok", model="qwen3:14b")


@app.post("/api/v1/process")
async def process_message(req: ProcessRequest):
    """
    Обработка одного хода диалога.

    - Если передан snapshot — восстанавливает бота из него.
    - Если нет — создаёт нового бота с указанным flow.
    - Возвращает ответ бота + обновлённый snapshot.
    """
    try:
        if req.snapshot:
            bot = SalesBot.from_snapshot(req.snapshot, llm=_llm)
        else:
            bot = SalesBot(_llm, flow_name=req.flow_name, config_name=req.config_name)

        result = bot.process(req.message)
        snapshot = bot.to_snapshot()

        return {
            **result,
            "snapshot": snapshot,
        }
    except Exception as e:
        logger.exception("Error processing message")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 8. Systemd-сервисы

### 8.1 Ollama (уже создан при установке)

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

### 8.2 CRM Sales Bot

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
> **--workers 1** — обязательно. Бот загружает embedding-модели в GPU-память.
> Несколько воркеров будут дублировать загрузку и исчерпают VRAM.

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

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
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
# {"status":"ok","model":"qwen3:14b"}

# Ollama
curl http://127.0.0.1:11434/api/tags
```

### 10.2 Снаружи (с любой машины)

```bash
# Health-check через Nginx + TLS
curl https://bot.example.com/health
# {"status":"ok","model":"qwen3:14b"}
```

### 10.3 Тестовый запрос (новый диалог)

```bash
curl -X POST https://bot.example.com/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет, расскажи о вашей CRM",
    "flow_name": "spin_selling"
  }'
```

Ожидаемый ответ — JSON с полями `response`, `intent`, `state`, `snapshot` и др.

### 10.4 Тестовый запрос (продолжение диалога)

Взять `snapshot` из предыдущего ответа и отправить следующее сообщение:

```bash
curl -X POST https://bot.example.com/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Сколько стоит?",
    "snapshot": { ... скопировать snapshot из предыдущего ответа ... }
  }'
```

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
| `flow` | Активная методология продаж (по умолчанию `spin_selling`) |
| `feature_flags` | Включение/отключение 62 фич |

### 11.2 База знаний

`src/knowledge/data/` — 17 YAML-файлов с 1969 секциями: цены, продукты, оборудование, интеграции, FAQ и т.д.

### 11.3 Методологии продаж (flows)

`src/yaml_config/flows/` — 21 flow:
`spin_selling`, `aida`, `bant`, `meddic`, `neat`, `challenger`, `consultative`, `autonomous` и др.

Переключение flow — через параметр `flow_name` в API-запросе.

### 11.4 Переменные окружения

Проект **не использует** `.env` файлов. Вся конфигурация — в YAML.

Единственное исключение — переопределение feature flags через окружение:

```bash
export FF_tone_analysis=true
export FF_reranker=false
```

Для systemd — добавить в `[Service]` секцию юнита:

```ini
Environment=FF_tone_analysis=true
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
ollama pull qwen3:14b
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

### Рекомендации на будущее

| Мера | Как |
|---|---|
| Fail2ban | `sudo apt install fail2ban` — защита от брутфорса SSH |
| API-ключ | Добавить header `X-API-Key` в FastAPI для авторизации клиентов |
| Rate limiting | В Nginx: `limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;` |
| IP whitelist | В Nginx: `allow <IP_мессенджер_платформы>; deny all;` |
| Мониторинг | Prometheus + Grafana или простой healthcheck через cron |
| Бэкапы | Код в Git, конфиги в YAML — бэкапить нечего (бот stateless) |

---

## 15. Устранение неполадок

| Проблема | Решение |
|---|---|
| `Connection refused :11434` | `sudo systemctl start ollama` — Ollama не запущен |
| `model not found` | `ollama pull qwen3:14b` — модель не скачана |
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
| GPU VRAM | 20 GB | ~10 GB (модель + embeddings) | ~11-12 GB |
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
[ ] Модель qwen3:14b скачана (ollama list)

БОТ
[ ] Репозиторий склонирован в /home/deploy/crm_sales_bot
[ ] Python venv создан, зависимости установлены (pip install -e .)
[ ] FastAPI + Uvicorn установлены
[ ] src/api.py создан
[ ] Интерактивный тест пройден (python3 -m src.bot)
[ ] Systemd-юнит crm-sales-bot.service создан и запущен
[ ] curl http://127.0.0.1:8000/health отвечает OK

СЕТЬ
[ ] DNS настроен (домен → IP сервера)
[ ] Nginx настроен как reverse proxy
[ ] TLS-сертификат получен (certbot)
[ ] curl https://bot.example.com/health отвечает OK снаружи
[ ] Тестовый диалог прошёл успешно
[ ] Embedding-модели скачались (первый запрос прошёл)
```
