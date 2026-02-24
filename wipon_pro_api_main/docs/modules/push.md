# push

Этот модуль отвечает за отправку push-уведомлений пользователям мобильных приложений. В нем есть два основных сервиса: PushService, который отправляет уведомления напрямую, и PushProducerService, который обрабатывает их асинхронно через очередь задач. Модуль использует данные о пользователях, настройки и библиотеку Bull для фоновой обработки.

## Responsibilities

- Отправка push-уведомлений с учетом устройства и количества непрочитанных сообщений
- Асинхронная обработка уведомлений через очередь задач с задержкой
- Интеграция с системой пользователей и настройками уведомлений

## Domains

This module covers the following business domains:

- уведомления, асинхронные задачи
- уведомления, мобильные приложения
- мessaging/notifications
- push-уведомления, асинхронные задачи
- messaging
- асинхронные задачи, уведомления, очереди сообщений
- уведомления
- мessaging/push notifications

## Dependencies

This module depends on:

- @nestjs/common
- @nestjs/bull
- Bull

## Main Exports

- `PushService`
- `PushProducerService`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:class:PushService

PushService отправляет push-уведомления пользователям, проверяя наличие устройства, определяя платформу (Android/iOS), используя токен для уведомлений и учитывая количество непрочитанных сообщений.

**Purpose:** Используется для отправки push-уведомлений в мобильных приложениях

**Key Behaviors:**
- Отправка уведомлений на Android и iOS
- Проверка наличия устройства у пользователя
- Определение платформы устройства
- Подсчёт непрочитанных уведомлений
- Использование внешнего сервиса для отправки сообщений

**Uses:** @nestjs/common, NotificationDao, UserDao, PushProducerService, appConfig

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:class:PushProducerService

Этот класс отправляет push-уведомления через очередь. Он использует библиотеку Bull для асинхронной обработки задач, сохраняя сообщения в очередь 'push_pro-job'.

**Purpose:** Обеспечивает отправку push-уведомлений пользователям с задержкой и обработкой в фоновом режиме

**Key Behaviors:**
- Отправка сообщений в очередь для обработки
- Поддержка разных платформ (iOS/Android)
- Работа с токенами устройств
- Обработка нечитаемых сообщений
- Интеграция с системой уведомлений

**Uses:** @nestjs/common, @nestjs/bull, bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:import:../../../config/app.config

Этот код создает сервис для отправки push-уведомлений. Он проверяет, есть ли у пользователя устройство, определяет его платформу (Android или iOS), считает количество непрочитанных уведомлений и отправляет сообщение через специальный сервис.

**Purpose:** Отправка push-уведомлений пользователям с учетом их устройства и количества непрочитанных сообщений

**Key Behaviors:**
- Определение платформы устройства пользователя
- Подсчет непрочитанных уведомлений
- Отправка сообщений через push-производителя
- Использование конфигурации окружения
- Проверка наличия токена устройства

**Uses:** @nestjs/common, NotificationDao, UserDao, PushProducerService, appConfig

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:import:../../dao/user.dao

Этот код создает сервис для отправки уведомлений на устройства пользователей. Он проверяет, есть ли у пользователя устройство и токен для уведомлений, определяет платформу (Android или iOS), считает количество непрочитанных уведомлений и отправляет сообщение через другой сервис.

**Purpose:** Этот сервис нужен для отправки уведомлений пользователям в мобильном приложении.

**Key Behaviors:**
- Проверяет наличие устройства у пользователя
- Определяет платформу устройства
- Считает количество непрочитанных уведомлений
- Отправляет уведомление через сервис-производителя
- Возвращает результат успешной отправки

**Uses:** @nestjs/common, NotificationDao, UserDao, PushProducerService, appConfig

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:method:PushProducerService:sendMessage

Этот метод отправляет уведомления пользователям через асинхронную очередь. Он добавляет задачу в очередь, как будто ставит напоминание для другого сотрудника, который позже обработает это уведомление.

**Purpose:** Позволяет отправлять уведомления без прямого взаимодействия с пользователем в момент вызова метода

**Key Behaviors:**
- Отправляет уведомления через очередь
- Принимает параметры: пользователь, токен, сообщение, платформа и количество непрочитанных сообщений
- Использует Bull для работы с очередями
- Работает асинхронно, не блокируя основной поток
- Инжектит очередь через декоратор @InjectQueue

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:import:../../dao/notification.dao

Этот сервис отправляет push-уведомления пользователям. Он проверяет, есть ли у пользователя устройство, определяет его платформу (Android или iOS), считает количество непрочитанных уведомлений и использует другой сервис для отправки сообщения.

**Purpose:** Отправка push-уведомлений пользователям с учетом их устройства и количества непрочитанных сообщений

**Key Behaviors:**
- Отправка уведомлений на Android/iOS
- Проверка наличия устройства у пользователя
- Подсчет непрочитанных уведомлений
- Использование конфигурации окружения
- Интеграция с внешним сервисом отправки

**Uses:** @nestjs/common, NotificationDao, appConfig, UserDao, PushProducerService

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:import:@nestjs/bull

Этот код создает сервис, который отправляет push-уведомления через очередь. Он использует Bull для асинхронной обработки задач и NestJS для управления зависимостями.

**Purpose:** Позволяет отправлять уведомления в фоновом режиме, не блокируя основной поток приложения.

**Key Behaviors:**
- Отправляет сообщения в очередь 'push_pro-job'
- Использует инъекцию зависимостей для получения очереди
- Принимает данные пользователя и сообщения
- Работает с асинхронной обработкой задач
- Использует Bull для управления очередями

**Uses:** @nestjs/bull, @nestjs/common, bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:file

Этот сервис отправляет уведомления через очередь, используя библиотеку Bull. Он добавляет задачи в очередь для асинхронной обработки сообщений.

**Purpose:** Обеспечивает асинхронную отправку push-уведомлений пользователям

**Key Behaviors:**
- Добавляет задачи в очередь 'push_pro-job'
- Обрабатывает отправку сообщений асинхронно
- Использует Bull для управления очередями
- Принимает данные пользователя и сообщения
- Инжектится в другие компоненты через @Injectable

**Uses:** @nestjs/common, @nestjs/bull, bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:method:PushService:send

Этот метод отправляет push-уведомления пользователю, проверяя наличие устройства, токена и платформы. Он считает количество непрочитанных уведомлений и использует сервис для отправки сообщения.

**Purpose:** Отправка push-уведомлений с проверкой данных и подсчетом непрочитанных сообщений

**Key Behaviors:**
- Проверка наличия устройства и токена
- Определение платформы (Android/iOS)
- Подсчет непрочитанных уведомлений
- Отправка сообщения через сервис-производитель
- Возврат результата (true/false)

**Uses:** NotificationDao, UserDao, PushProducerService, appConfig

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:method:PushService:constructor

Этот метод отправляет push-уведомления пользователю, проверяя наличие устройства, определяя платформу (Android или iOS), увеличивая счётчик непрочитанных уведомлений и используя отдельный сервис для отправки сообщения.

**Purpose:** Отправка push-уведомлений с учётом устройства и количества непрочитанных сообщений

**Key Behaviors:**
- Проверка наличия устройства у пользователя
- Определение платформы (Android/iOS)
- Увеличение счётчика непрочитанных уведомлений
- Отправка сообщения через push-сервис
- Возврат результата (true/false) в зависимости от успешности

**Uses:** NotificationDao, UserDao, PushProducerService, appConfig

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:import:./push.producer.service

Этот код создает сервис для отправки уведомлений на устройства пользователей. Он проверяет наличие устройства, определяет платформу (Android/iOS), считает непрочитанные уведомления и отправляет сообщение через отдельный сервис.

**Purpose:** Отправка push-уведомлений пользователям с учетом их настроек и состояния

**Key Behaviors:**
- Отправка уведомлений на устройства
- Определение платформы устройства
- Подсчет непрочитанных сообщений
- Использование конфигурации окружения
- Работа с базой данных через DAO

**Uses:** @nestjs/common, NotificationDao, UserDao, appConfig, PushProducerService

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:import:bull

Этот код создает сервис, который отправляет уведомления через очередь. Он использует Bull для асинхронной обработки задач, сохраняя сообщения в Redis-хранилище.

**Purpose:** Обеспечивает отложенную отправку уведомлений без блокировки основного потока приложения

**Key Behaviors:**
- Добавляет задачи в очередь 'push_pro-job'
- Использует Redis для хранения сообщений
- Поддерживает асинхронную обработку
- Работает с токенами устройств
- Обрабатывает разные платформы

**Uses:** @nestjs/bull, bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.service.ts:import:@nestjs/common

Этот код создает сервис для отправки push-уведомлений. Он проверяет, есть ли у пользователя устройство, определяет его платформу (Android или iOS), считает количество непрочитанных уведомлений и отправляет сообщение через отдельный сервис-производитель.

**Purpose:** Обеспечивает отправку push-уведомлений пользователям с учетом их устройства и количества непрочитанных сообщений

**Key Behaviors:**
- Отправка push-уведомлений на Android и iOS
- Проверка наличия устройства у пользователя
- Определение платформы устройства
- Обновление счетчика непрочитанных уведомлений
- Использование конфигурации окружения

**Uses:** @nestjs/common, NotificationDao, UserDao, PushProducerService, appConfig

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:import:@nestjs/common

Этот код создает сервис для отправки уведомлений через очередь. Он использует Bull для асинхронной обработки задач и NestJS для инъекции зависимости очереди.

**Purpose:** Обеспечивает отправку push-уведомлений в фоновом режиме через очередь задач

**Key Behaviors:**
- Использует Bull для управления очередями
- Отправляет сообщения в очередь 'push_pro-job'
- Поддерживает асинхронную обработку данных
- Интегрируется с NestJS через декораторы
- Работает с пользовательскими данными и токенами

**Uses:** @nestjs/common, @nestjs/bull, bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/push/push.producer.service.ts:method:PushProducerService:constructor

Этот класс - сервис, который отправляет push-уведомления через очередь. Он использует Bull для асинхронной обработки задач и добавляет сообщения в очередь 'push_pro-job' с данными о пользователе и сообщении.

**Purpose:** Позволяет отправлять push-уведомления асинхронно, не блокируя основной поток приложения

**Key Behaviors:**
- Использует Bull для асинхронной обработки
- Добавляет задачи в очередь 'push_pro-job'
- Принимает данные о пользователе и сообщении
- Поддерживает несколько платформ
- Работает с нечитаемыми сообщениями

**Uses:** @nestjs/bull, @nestjs/common, bull

---


## Metrics

- **Entities:** 15
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*