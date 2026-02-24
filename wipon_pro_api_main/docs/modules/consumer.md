# consumer

Этот модуль отвечает за обработку фоновых задач, связанных с уведомлениями и оплатой подписок. Он использует брокер сообщений Bull для управления очередями задач, отправляет push-уведомления через Firebase и автоматизирует процесс оплаты подписок. Модуль работает в фоновом режиме, чтобы не блокировать основной поток приложения.

## Responsibilities

- Обработка фоновых задач по отправке push-уведомлений через Firebase
- Автоматизация процесса оплаты подписок и их активации
- Логирование выполнения задач и обработка ошибок в фоновых процессах

## Domains

This module covers the following business domains:

- платежи
- платежи, подписки, авторизация
- уведомления, очереди задач, firebase
- платежи, подписки
- messaging
- уведомления
- биллинг
- уведомления, api, брокер сообщений
- уведомления, api, фоновые задачи
- уведомления, мессенджер

## Dependencies

This module depends on:

- @nestjs/bull для работы с очередями задач
- firebase-admin/lib/messaging/messaging-api для отправки уведомлений через Firebase
- typeorm для работы с базой данных
- bull для управления очередями задач
- @nestjs/common для общих функций и аннотаций

## Main Exports

- `PushConsumer для обработки задач по отправке уведомлений`
- `SubscriptionChargeConsumer для обработки задач по оплате и активации подписок`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:@nestjs/bull

Этот код использует библиотеку Bull для обработки задач в фоновом режиме. Он получает данные о уведомлении, создает запись в базе данных и отправляет уведомление через FCM (Firebase Cloud Messaging).

**Purpose:** Обработка уведомлений в фоновом режиме и их отправка пользователям через FCM.

**Key Behaviors:**
- Обработка задач из очереди 'push_pro-job'
- Создание уведомлений в базе данных
- Отправка уведомлений через FCM
- Логирование ошибок и успешных операций
- Использование кастомного логгера

**Uses:** @nestjs/bull, bull, firebase-admin, notifications-service, fcm-service

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../../../config/subscription.config

Этот код создает обработчик задач для оплаты подписок пользователей. Он проверяет наличие пользователя, активирует подписку и обрабатывает платежи через сервисы и use-cases.

**Purpose:** Автоматизировать процесс оплаты подписок и управления активацией для пользователей

**Key Behaviors:**
- Обработка задач из очереди Bull
- Поиск пользователя по ID
- Проверка активной подписки
- Обработка платежей через BillingService
- Логирование операций

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common, custom logger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../../types/subsCharge-job.type

Этот код обрабатывает задания по оплате подписок пользователей. Он проверяет наличие пользователя, оплачивает подписку и активирует её, если оплата успешна.

**Purpose:** Обработка асинхронных задач по пополнению подписок в системе

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Проверка существования пользователя
- Оплата подписки через billingService
- Активация подписки после оплаты
- Логирование процесса выполнения

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:method:SubscriptionChargeConsumer:constructor

Этот код обрабатывает задания по оплате подписок пользователей. Он ищет пользователя, проверяет активную подписку, списывает деньги и активирует подписку, если она не активна. Использует логирование и транзакции для безопасности.

**Purpose:** Обработка асинхронных задач по пополнению подписок в системе оплаты

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Проверка наличия активной подписки у пользователя
- Списание средств через billingService
- Активация подписки в транзакции
- Логирование процесса выполнения

**Uses:** @nestjs/bull, typeorm, bull, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:../../logger/request-logger

Этот код создает обработчик задач для отправки уведомлений через FCM (Firebase Cloud Messaging). Он использует библиотеку Bull для обработки задач в фоновом режиме и логирует действия с помощью кастомного логгера.

**Purpose:** Обработка задач по отправке уведомлений в фоновом режиме и логирование их выполнения.

**Key Behaviors:**
- Обработка задач из очереди 'push_pro-job'
- Отправка уведомлений через FCM
- Логирование успешных и неудачных попыток отправки
- Использование кастомного логгера для отслеживания действий
- Интеграция с сервисами уведомлений и FCM

**Uses:** @nestjs/bull, bull, firebase-admin, request-logger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:../../../modules/fcm/fcm.service.

Этот код обрабатывает задания на отправку уведомлений через FCM (Firebase Cloud Messaging). Он получает данные о пользователе и сообщении, создает уведомление в системе и отправляет его на устройство через Firebase.

**Purpose:** Обработка заданий на отправку уведомлений в фоновом режиме для уведомления пользователей

**Key Behaviors:**
- Обрабатывает задания из очереди 'push_pro-job'
- Создает уведомления в системе через NotificationsService
- Отправляет уведомления через FCM с использованием FcmService
- Логирует ошибки и успешные отправки уведомлений
- Использует кастомный логгер для отслеживания процесса

**Uses:** @nestjs/bull, bull, firebase-admin, notifications.service, fcm.service

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../../logger/request-logger

Этот код обрабатывает задания по оплате подписок пользователей. Он проверяет активную подписку, списывает деньги с баланса и активирует подписку, если оплата прошла успешно. Использует логирование и транзакции для надежности.

**Purpose:** Обработка асинхронных задач по пополнению подписок в системе биллинга

**Key Behaviors:**
- Обработка заданий из очереди 'billing_pro-job'
- Проверка наличия активной подписки у пользователя
- Списание средств с баланса пользователя
- Активация подписки после успешной оплаты
- Логирование процесса выполнения задания

**Uses:** @nestjs/bull, bull, @nestjs/common, typeorm, request-logger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:class:SubscriptionChargeConsumer

Этот класс обрабатывает задания по оплате подписок. Он ищет пользователя, проверяет активную подписку, списывает деньги с баланса и активирует подписку, если всё прошло успешно.

**Purpose:** Обработка асинхронных задач по пополнению подписок пользователей

**Key Behaviors:**
- Обработка задач из очереди Bull
- Поиск пользователя по ID
- Проверка активной подписки
- Списание средств с баланса
- Активация подписки после успешной оплаты

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:@nestjs/common

Этот код обрабатывает задания по оплате подписок пользователей. Он проверяет наличие пользователя, оплачивает подписку, если она не активна, и включает её, используя транзакции для безопасности данных.

**Purpose:** Обработка асинхронных задач по пополнению подписок пользователей в системе

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Поиск пользователя по ID
- Проверка активной подписки
- Оплата подписки через BillingService
- Использование транзакций для безопасного обновления данных

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:firebase-admin/lib/messaging/messaging-api

Этот код обрабатывает задания на отправку уведомлений через FCM (Firebase Cloud Messaging). Он берет данные из очереди, создает уведомление в системе и отправляет его пользователю через Firebase, логируя результаты.

**Purpose:** Обработка фоновых задач по отправке уведомлений пользователям в реальном времени

**Key Behaviors:**
- Обработка задач из очереди Bull
- Отправка FCM уведомлений через Firebase
- Логирование успешных и ошибочных попыток
- Использование сервисов для работы с уведомлениями и FCM
- Работа с кастомным логгером

**Uses:** @nestjs/bull, bull, firebase-admin, notifications-service, fcm-service

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:../../../modules/notifications/domain/notifications.service

Этот код создает обработчик задач для отправки уведомлений. Он берет данные из очереди, создает уведомление в системе и отправляет его через Firebase на мобильное устройство.

**Purpose:** Обработка асинхронных задач по отправке push-уведомлений пользователям

**Key Behaviors:**
- Обработка задач из очереди 'push_pro-job'
- Создание записей об уведомлениях в базе данных
- Отправка уведомлений через Firebase
- Логирование успешных и ошибочных попыток
- Работа с токенами устройств и пользовательскими данными

**Uses:** @nestjs/bull, bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../billing/billing.service

Этот код обрабатывает задания по оплате подписок пользователей. Он проверяет наличие пользователя, проверяет активную подписку, списывает деньги и активирует подписку, если всё прошло успешно.

**Purpose:** Автоматическая обработка платежей за подписки в фоновом режиме

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Проверка существования пользователя
- Проверка активной подписки
- Транзакционное списание средств
- Логирование процесса

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:bull

Этот код создает обработчик задач для отправки уведомлений через FCM. Он берет данные из очереди, создает уведомление в системе и отправляет его пользователю по токену

**Purpose:** Обработка асинхронных задач по отправке push-уведомлений пользователям

**Key Behaviors:**
- Обработка задач из очереди 'push_pro-job'
- Создание записей уведомлений в базе
- Отправка FCM-сообщений по токенам
- Логирование успешных и неудачных попыток отправки
- Использование кастомного логгера для отслеживания процесса

**Uses:** @nestjs/bull, bull, firebase-admin, notifications-service, fcm-service

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:method:PushConsumer:constructor

Этот код обрабатывает задания на отправку уведомлений. Он берет данные из очереди, создает уведомление в базе и отправляет его через FCM (Firebase Cloud Messaging) на устройство пользователя.

**Purpose:** Обработка уведомлений в фоновом режиме для отправки пользователю

**Key Behaviors:**
- Обрабатывает задания из очереди 'push_pro-job'
- Создает уведомление в базе данных через NotificationsService
- Отправляет уведомление через FCM на устройство пользователя
- Логирует ошибки и успешные отправки уведомлений
- Использует кастомный логгер для отслеживания процесса

**Uses:** @nestjs/bull, bull, firebase-admin, notificationsService, fcmService

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:@nestjs/bull

Этот код создает обработчик задач для платформы NestJS, который обрабатывает задания по оплате подписок пользователей. Он проверяет наличие пользователя, активную подписку, списывает деньги и активирует подписку, если всё прошло успешно.

**Purpose:** Обработка асинхронных задач по оплате подписок пользователей в системе

**Key Behaviors:**
- Обработка задач из очереди 'billing_pro-job'
- Проверка существования пользователя
- Списание средств с пользователя
- Активация подписки после оплаты
- Логирование процесса выполнения

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../../../modules/subscriptions/domain/use-cases/activate-users-subscription.use-case

Этот код - потребитель задач, который обрабатывает оплату подписки пользователя. Он проверяет активную подписку, списывает деньги и активирует подписку, если оплата прошла успешно.

**Purpose:** Автоматизация процесса оплаты и активации подписок пользователей

**Key Behaviors:**
- Обработка задач из очереди Bull
- Проверка наличия активной подписки
- Списание средств через BillingService
- Транзакционное обновление данных в базе
- Логирование процесса выполнения

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../../../modules/subscriptions/domain/use-cases/count-users-active-subscription.use-case

Этот код обрабатывает задания по оплате подписок пользователей. Он ищет пользователя, проверяет активную подписку, списывает деньги и активирует подписку, если всё прошло успешно.

**Purpose:** Обработка оплаты подписок в фоновом режиме с использованием очередей задач

**Key Behaviors:**
- Обработка заданий из очереди 'billing_pro-job'
- Проверка наличия пользователя по ID
- Списание средств с пользователя
- Активация подписки после оплаты
- Логирование процесса выполнения

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:bull

Этот код обрабатывает задания по оплате подписок пользователей. Он проверяет наличие активной подписки, списывает деньги с баланса и активирует подписку, если оплата прошла успешно.

**Purpose:** Обработка асинхронных задач по пополнению подписок пользователей в системе

**Key Behaviors:**
- Обработка заданий из очереди 'billing_pro-job'
- Проверка наличия пользователя по ID
- Списание средств с баланса пользователя
- Активация подписки после успешной оплаты
- Использование транзакций для обеспечения целостности данных

**Uses:** @nestjs/bull, bull, typeorm, @nestjs/common, custom logger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:import:../../types/push-job.type

Этот код создает обработчик задач для отправки уведомлений через FCM. Он использует сервисы для создания уведомлений и отправки их на устройства, логирует процесс и ошибки.

**Purpose:** Обработка задач по отправке push-уведомлений в фоновом режиме

**Key Behaviors:**
- Обработка задач из очереди 'push_pro-job'
- Создание уведомлений через NotificationsService
- Отправка уведомлений через FCM
- Логирование успешных и ошибочных попыток
- Использование кастомного логгера для отслеживания процесса

**Uses:** @nestjs/bull, bull, firebase-admin, notifications-service, fcm-service

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:typeorm

Этот код обрабатывает задания по оплате подписок пользователей. Он использует библиотеку Bull для асинхронной обработки задач, проверяет активные подписки, взаимодействует с базой данных через TypeORM и управляет оплатой через сервис billingService.

**Purpose:** Обработка оплаты подписок пользователей в фоновом режиме для избежания блокировки основного потока приложения

**Key Behaviors:**
- Обработка заданий из очереди 'billing_pro-job'
- Проверка существования пользователя в базе данных
- Проверка активной подписки у пользователя
- Выполнение транзакции для оплаты и активации подписки
- Логирование процесса выполнения задания

**Uses:** @nestjs/bull, bull, @nestjs/common, typeorm, rxjs

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:import:../../../modules/users/domain/use-cases/find-user-by-id.use-case

Этот код обрабатывает задания по оплате подписок пользователей. Он проверяет наличие пользователя, проверяет активную подписку, списывает деньги и активирует подписку, если всё прошло успешно.

**Purpose:** Обработка асинхронных задач по оплате подписок с гарантией целостности данных

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Проверка существования пользователя
- Списание средств с карты
- Активация подписки в транзакции
- Логирование процесса

**Uses:** @nestjs/bull, bull, @nestjs/common, typeorm, typeorm-transaction, logger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:class:PushConsumer

Этот класс обрабатывает задания на отправку уведомлений через FCM. Он получает данные о токене, платформе и сообщении, создает уведомление в базе и отправляет его пользователю через Firebase.

**Purpose:** Обработка асинхронных задач по отправке push-уведомлений в фоновом режиме

**Key Behaviors:**
- Обработка задач из очереди Bull
- Создание записей об уведомлениях в базе
- Отправка сообщений через Firebase Cloud Messaging
- Логирование ошибок и успешных отправок
- Работа с токенами устройств разных платформ

**Uses:** @nestjs/bull, bull, firebase-admin, messaging-api

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/push.consumer.ts:method:PushConsumer:readOperationJob

Этот метод обрабатывает задания из очереди 'push_pro' для отправки уведомлений. Он извлекает данные из задания, создает уведомление и отправляет его через FCM (Firebase Cloud Messaging) на указанный токен устройства.

**Purpose:** Обработка асинхронных задач по отправке push-уведомлений пользователям

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Отправка FCM-уведомлений через Firebase
- Логирование успешных и ошибочных операций
- Использование сервисов для создания уведомлений
- Асинхронная обработка задач

**Uses:** @nestjs/bull, bull, firebase-admin, notificationsService, fcmService

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/services/consumer/subscriptionCharge.consumer.ts:method:SubscriptionChargeConsumer:readOperationJob

Этот метод обрабатывает задания по оплате подписки пользователей. Он ищет пользователя, проверяет активную подписку, списывает деньги и активирует подписку, если всё прошло успешно.

**Purpose:** Обработка оплаты подписок в фоновом режиме для избежания блокировки основного потока приложения

**Key Behaviors:**
- Обработка заданий из очереди Bull
- Проверка существования пользователя
- Списание средств с пользователя
- Активация подписки после оплаты
- Логирование процесса и ошибок

**Uses:** @nestjs/bull, typeorm, @nestjs/common, bull

---


## Metrics

- **Entities:** 24
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*