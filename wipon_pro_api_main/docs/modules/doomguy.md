# doomguy

Модуль Doomguy служит для отправки уведомлений в Slack, логирования ошибок и интеграции с SMS-системой. Он обеспечивает централизованную отправку важной информации команде, например, о действиях пользователей, статусе SMS или критических ошибках. Можно представить его как дежурного сотрудника, который мгновенно информирует команду о важных событиях в приложении.

## Responsibilities

- Отправка уведомлений в Slack о действиях пользователей, ошибках и статусе SMS
- Логирование критических ошибок при взаимодействии с внешними системами
- Интеграция с SMS-модулем для передачи обратной связи и статусов сообщений

## Domains

This module covers the following business domains:

- утилиты, логирование, интеграции
- мessaging/notifications
- утилиты, логирование, уведомления
- утилиты/уведомления
- messaging/notifications
- messaging
- утилиты, логирование, api
- уведомления, логирование

## Dependencies

This module depends on:

- @nestjs/common
- @nestjs/axios
- Slack API (через HTTP-запросы)

## Main Exports

- `DoomguyService (основной класс, предоставляющий методы для отправки уведомлений и логирования)`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:import:../../helpers/datetime

Этот код создает сервис для отправки сообщений в Slack через HTTP-запросы. Он логирует ошибки, использует настройки приложения и формирует сообщения с данными пользователей и SMS-отчетами.

**Purpose:** Сервис нужен для отправки уведомлений и отчетов в Slack, а также для логирования ошибок при взаимодействии с внешними системами.

**Key Behaviors:**
- Отправка сообщений в Slack через HTTP-запросы
- Логирование ошибок с деталями запроса и ответа
- Использование настроек приложения для выбора канала в Slack
- Формирование сообщений с информацией о пользователях и SMS-отчетах
- Поддержка разных режимов (production, staging)

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, config/app.config, helpers/datetime

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:method:DoomguyService:ck(messageFi

Этот сервис отправляет сообщения в Slack через HTTP-запросы. Он формирует разные типы сообщений (обратная связь, SMS-отчеты, ошибки) и отправляет их в соответствующие каналы, используя настройки окружения.

**Purpose:** Уведомляет команду о важных событиях, ошибках и обратной связи через Slack-каналы

**Key Behaviors:**
- Отправка сообщений в Slack с разным содержанием
- Обработка ошибок и логирование проблем
- Использование настроек окружения для выбора каналов
- Формирование сообщений из переданных данных
- Использование кастомного логгера для ошибок

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, helpers/datetime

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:method:DoomguyService:авке SMS:
     

Этот код отправляет сообщения в Slack через HTTP-запросы для уведомлений. Он формирует текст сообщений, отправляет их по webhook-URL и логирует ошибки, если что-то пошло не так.

**Purpose:** Используется для отправки уведомлений о событиях в приложении (например, обратная связь пользователей, статус SMS, ошибки) в Slack-каналы.

**Key Behaviors:**
- Отправка сообщений в Slack через webhook
- Формирование текста сообщений на основе данных из приложения
- Логирование ошибок при неудачных попытках отправки
- Разделение каналов в зависимости от окружения (production/staging)
- Поддержка нескольких типов уведомлений (обратная связь, статус SMS, ошибки)

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, helpers/datetime, modules/sms/dto/post-callback.dto

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:import:@nestjs/common

Этот код создает сервис для отправки уведомлений в Slack через HTTP-запросы. Он логирует ошибки, использует настройки приложения и формирует сообщения с данными пользователей и SMS-отчетами.

**Purpose:** Нужен для автоматической отправки уведомлений о действиях пользователей, ошибках и SMS-статусах в Slack-каналы

**Key Behaviors:**
- Отправка сообщений в Slack через webhook
- Логирование ошибок с детализацией ответов
- Использование разных каналов в зависимости от окружения
- Формирование сообщений с данными пользователей и SMS-отчетами
- Использование текущего времени для логирования

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, config/app.config, helpers/datetime, modules/sms/dto/post-callback.dto

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:method:DoomguyService:constructor

Этот класс отправляет сообщения в Slack через HTTP-запросы. Он формирует сообщения с данными пользователей, SMS-отчетами и ошибками, отправляя их в разные каналы в зависимости от окружения.

**Purpose:** Используется для отправки уведомлений и отчетов в Slack, чтобы команда могла отслеживать действия пользователей, ошибки и статус SMS.

**Key Behaviors:**
- Отправка сообщений в Slack через HTTP-запросы
- Формирование сообщений с данными пользователей
- Отправка SMS-отчетов в зависимости от окружения
- Логирование ошибок при отправке сообщений
- Использование разных каналов в Slack для разных окружений

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, helpers/datetime, modules/sms/dto/post-callback.dto

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:import:../../logger/error-logger

Этот код создает сервис, который отправляет сообщения в Slack через HTTP-запросы. Он логирует ошибки, использует настройки приложения и формирует сообщения с данными пользователей и ошибок.

**Purpose:** Нужен для отправки уведомлений в Slack о действиях пользователей, SMS-статусах и ошибках в приложении

**Key Behaviors:**
- Отправка сообщений в Slack через webhook
- Логирование ошибок с детализацией
- Использование разных каналов в зависимости от окружения
- Форматирование сообщений с данными пользователей и ошибок
- Использование кастомного логгера для ошибок

**Uses:** @nestjs/common, @nestjs/axios, error-logger, app.config, getNowAlmatyTime, PostCallbackDto

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:class:DoomguyService

Этот класс отправляет сообщения в Slack через вебхуки для уведомлений о фидбеке, SMS-статусах и ошибках. Использует разные каналы в зависимости от окружения (production/staging).

**Purpose:** Обеспечивает централизованную отправку уведомлений в Slack для мониторинга и анализа данных из приложения

**Key Behaviors:**
- Отправка сообщений в Slack через вебхуки
- Использование разных каналов для production/staging
- Логирование ошибок при отправке
- Форматирование сообщений с деталями (текст, дата, имя пользователя и т.д.)
- Использование кастомного логгера для ошибок

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, helpers/datetime, modules/sms/dto/post-callback.dto

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:property:DoomguyService:_hookUrl

Это приватное свойство хранит URL вебхука Slack для отправки уведомлений. Используется для отправки сообщений в каналы Slack при разных событиях (например, ошибки, обратная связь, SMS-отчеты).

**Purpose:** Позволяет отправлять уведомления в Slack для мониторинга и оперативного реагирования на события в приложении

**Key Behaviors:**
- Хранит URL для отправки сообщений в Slack
- Используется в методах для отправки уведомлений в зависимости от события
- Работает с разными каналами в зависимости от окружения (production/staging)
- Используется в связке с HTTP-запросами для отправки данных в Slack
- Используется в критических сценариях, таких как ошибки и обратная связь

**Uses:** @nestjs/axios, appConfig, createCustomErrorLogger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:import:../../../modules/sms/dto/post-callback.dto

Этот код создает сервис в NestJS, который отправляет сообщения в Slack через HTTP-запросы. Он использует настройки приложения, логгер ошибок и функции для работы со временем и данными из DTO.

**Purpose:** Отправка уведомлений и отчетов в Slack для мониторинга и обработки сообщений, ошибок и SMS-уведомлений в приложении.

**Key Behaviors:**
- Отправка сообщений в Slack через HTTP-запросы
- Использование настроек приложения для выбора канала в Slack
- Логирование ошибок с деталями запроса и ответа
- Форматирование сообщений с информацией о пользователях и SMS-отчетах
- Поддержка разных каналов в зависимости от среды (production/staging)

**Uses:** @nestjs/common, @nestjs/axios, logger/error-logger, config/app.config, helpers/datetime, modules/sms/dto/post-callback.dto

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:method:DoomguyService:executeCurl

Этот метод отправляет HTTP POST-запросы в Slack через вебхук и возвращает статус успеха. При ошибке логирует сообщение и детали ответа.

**Purpose:** Используется для отправки уведомлений в Slack каналы при различных событиях в приложении.

**Key Behaviors:**
- Отправляет сообщения в Slack через вебхук
- Логирует ошибки при сбое соединения
- Использует конфигурационные настройки окружения
- Поддерживает разные каналы для разных окружений (production/staging)
- Возвращает статус выполнения (успех/провал)

**Uses:** @nestjs/axios, logger/error-logger, config/app.config, helpers/datetime

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:import:@nestjs/axios

Этот код создает сервис для отправки сообщений в Slack через HTTP-запросы. Он использует HttpService из @nestjs/axios для отправки данных по webhook-URL и логирует ошибки с помощью кастомного логгера. Сервис может отправлять сообщения о фидбеке, отчеты по SMS и уведомления о критических ошибках.

**Purpose:** Сервис нужен для отправки важной информации в Slack, например, о фидбеке пользователей, статусе SMS или критических ошибках в приложении.

**Key Behaviors:**
- Отправка сообщений в Slack через webhook
- Логирование ошибок при отправке
- Использование конфигурации из app.config
- Отправка сообщений о фидбеке, SMS и критических ошибках
- Использование времени Алматы для логирования

**Uses:** @nestjs/common, @nestjs/axios, axios

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/doomguy/doomguy.service.ts:import:../../../config/app.config

Этот код создает сервис для отправки сообщений в Slack через HTTP-запросы. Он использует конфигурацию, логгер и вспомогательные функции для отправки уведомлений о фидбеке, SMS-колбеках и ошибках.

**Purpose:** Обеспечивает интеграцию с Slack для уведомлений о событиях в приложении

**Key Behaviors:**
- Отправка сообщений в Slack через webhook
- Разделение каналов для разных окружений (production/staging)
- Логирование ошибок при отправке
- Использование DTO для структурированных данных
- Форматирование сообщений с деталями событий

**Uses:** @nestjs/axios, @nestjs/common, custom error logger, app.config, datetime helper

---


## Metrics

- **Entities:** 12
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*