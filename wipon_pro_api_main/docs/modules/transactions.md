# transactions

Модуль transactions отвечает за обработку финансовых транзакций, подписок и уведомлений в приложении. Он интегрируется с платежными системами, отправляет уведомления через FCM и управляет асинхронными задачами с помощью Bull. Модуль взаимодействует с другими частями системы, такими как модули пользователей, подписок и учета.

## Responsibilities

- Обработка платежей и финансовых транзакций
- Управление подписками и их автоматическим списанием
- Отправка уведомлений пользователям через FCM и другие каналы

## Domains

This module covers the following business domains:

- платежи, финансовые транзакции
- платежи, подписки, уведомления
- платежи
- платежи, финансовые транзакции, уведомления
- платежи, баланс, подписки
- база данных, утилиты, api
- уведомления
- платежи, транзакции, подписки

## Dependencies

This module depends on:

- @nestjs/common
- @nestjs/bull
- payment gateways (внешние библиотеки для обработки платежей)
- FCM (Firebase Cloud Messaging для отправки уведомлений)

## Main Exports

- `TransactionsModule`
- `TransactionsController`
- `TransactionsService`
- `SubscriptionChargeConsumer`
- `SubscriptionChargeProducerService`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:@nestjs/common

Этот код создает модуль для управления транзакциями, который использует сервисы для работы с платежами, уведомлениями и подписками, а также интегрируется с другими частями приложения через модули.

**Purpose:** Обеспечивает обработку финансовых операций, уведомлений и асинхронных задач по подпискам

**Key Behaviors:**
- Обработка транзакций через контроллер
- Интеграция с сервисами оплаты и уведомлений
- Асинхронная обработка подписок через Bull
- Связь с модулями пользователей и счетов
- Работа с FCM для push-уведомлений

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:class:TransactionsModule

Этот модуль отвечает за обработку транзакций, связанных с платежами и подписками. Он использует сервисы для управления транзакциями, интегрируется с другими модулями, такими как пользователи и аккаунты, и настраивает очередь задач для обработки подписок.

**Purpose:** Обеспечивает обработку транзакций, подписок и уведомлений в приложении

**Key Behaviors:**
- Обработка транзакций через TransactionsService
- Интеграция с модулями пользователей и аккаунтов
- Использование очереди задач Bull для обработки подписок
- Отправка уведомлений через FCM
- Работа с сервисами оплаты и уведомлений

**Uses:** @nestjs/common, @nestjs/bull, UsersModule, AccountsModule, SubscriptionsModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:@nestjs/bull

Этот код создает модуль для управления транзакциями, подключая сервисы для работы с пользователями, счетами, подписками и уведомлениями. Использует Bull для обработки задач в фоне.

**Purpose:** Обеспечивает логику обработки транзакций с интеграцией платежей, уведомлений и подписок

**Key Behaviors:**
- Обработка транзакций через TransactionsService
- Интеграция с платежной системой через BillingService
- Отправка уведомлений через PushService
- Обработка подписок в фоновом режиме через Bull
- Связь с модулями пользователей и счетов

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:./domain/transactions.service

Этот код создает модуль для управления транзакциями, который использует сервисы для работы с платежами, уведомлениями и фоновыми задачами. Он подключает модули пользователей, счетов и подписок.

**Purpose:** Обеспечивает обработку финансовых операций, интеграцию с платежными системами и уведомлениями

**Key Behaviors:**
- Обработка транзакций через API
- Интеграция с системой оплаты
- Отправка уведомлений через FCM
- Обработка фоновых задач по оплате
- Работа с подписками пользователей

**Uses:** @nestjs/common, @nestjs/bull, UsersModule, AccountsModule, SubscriptionsModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../accounts/accounts.module

Этот код создает модуль для управления транзакциями, который использует контроллер для обработки запросов, сервисы для логики бизнес-правил и подключает другие модули (пользователи, счета, подписки) для взаимодействия с данными. Также используется очередь задач для обработки оплат и уведомлений.

**Purpose:** Обеспечивает обработку финансовых транзакций, оповещений и подписок в приложении

**Key Behaviors:**
- Обработка HTTP-запросов через контроллер
- Использование сервисов для бизнес-логики
- Интеграция с модулями пользователей и счетов
- Обработка подписок через очередь задач
- Отправка уведомлений через FCM

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../../common/services/push/push.service

Этот код импортирует сервис для отправки уведомлений (PushService), который используется для взаимодействия с системой уведомлений в приложении.

**Purpose:** Позволяет отправлять уведомления пользователям через FCM или другие каналы

**Key Behaviors:**
- Отправка уведомлений пользователям
- Интеграция с FCM модулем
- Использование в модуле транзакций
- Работа с сервисами подписок и оплат
- Поддержка асинхронных операций через Bull

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../../common/services/consumer/subscriptionCharge.consumer

Этот код создает модуль для обработки транзакций, который использует контроллеры, сервисы и другие модули для управления платежами, уведомлениями и подписками. Он подключается к модулям пользователей, счетов и подписок.

**Purpose:** Обеспечивает централизованную обработку финансовых операций с интеграцией в другие части приложения

**Key Behaviors:**
- Обработка транзакций через контроллер
- Интеграция с системой биллинга
- Отправка уведомлений через FCM
- Обработка подписок и их оплат
- Использование очередей для асинхронной обработки

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../../common/services/billing/billing.service

Этот код создает модуль для обработки транзакций, который использует сервисы для работы с оплатами, уведомлениями и подписками, а также подключает другие модули проекта.

**Purpose:** Обеспечивает централизованное управление финансовыми операциями и интеграцию с системами пользователей, счетов и уведомлений

**Key Behaviors:**
- Обработка транзакций через контроллер
- Использование сервиса для расчета оплат
- Интеграция с модулями пользователей и счетов
- Обработка подписок через очередь задач
- Отправка уведомлений через FCM

**Uses:** @nestjs/common, @nestjs/bull, UsersModule, AccountsModule, SubscriptionsModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:./presenter/transactions.controller

Этот код создает модуль для обработки транзакций, используя контроллер для HTTP-запросов, сервисы для логики и интегрируясь с другими модулями (пользователи, счета, подписки и уведомления). Также использует очередь задач для обработки оплат.

**Purpose:** Модуль нужен для управления транзакциями, взаимодействия с другими частями приложения и обработки асинхронных операций, таких как оплаты и уведомления.

**Key Behaviors:**
- Обработка HTTP-запросов через контроллер
- Использование сервисов для бизнес-логики
- Интеграция с модулями пользователей, счетов и подписок
- Асинхронная обработка задач через BullModule
- Отправка уведомлений через FCM

**Uses:** @nestjs/common, @nestjs/bull, UsersModule, AccountsModule, SubscriptionsModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../subscriptions/subscriptions.module

Этот код создает модуль для управления транзакциями, который использует контроллер для обработки запросов, сервисы для логики и подключается к другим модулям (пользователи, счета, подписки). Также настроен брокер сообщений для обработки задач и уведомлений.

**Purpose:** Обеспечивает обработку финансовых операций, интеграцию с подписками и уведомлениями через FCM

**Key Behaviors:**
- Обработка транзакций через контроллер
- Использование сервисов для расчетов и оповещений
- Интеграция с модулями пользователей и счетов
- Обработка задач через BullMQ
- Отправка уведомлений через FCM

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../../common/services/subscription/subscriptionCharge.producer.service

Этот модуль объединяет контроллер транзакций, сервисы и другие модули для обработки финансовых операций. Он использует очередь для обработки подписок и отправляет уведомления.

**Purpose:** Обеспечивает обработку транзакций, подписок и уведомлений в приложении

**Key Behaviors:**
- Интеграция с модулями пользователей и подписок
- Обработка транзакций через сервисы
- Использование очереди для фоновой обработки
- Отправка уведомлений через FCM
- Работа с сервисами баланса и подписок

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../fcm/fcm.module

Этот код импортирует модуль FCM, который используется для отправки уведомлений через Firebase Cloud Messaging. Он подключает сервисы и другие модули, необходимые для работы с транзакциями и подписками.

**Purpose:** Обеспечивает отправку уведомлений пользователям через Firebase Cloud Messaging

**Key Behaviors:**
- Отправка уведомлений через Firebase Cloud Messaging
- Интеграция с сервисами транзакций и подписок
- Использование асинхронной обработки через Bull
- Подключение к модулям пользователей и счетов
- Использование сервисов для бизнес-логики

**Uses:** @nestjs/common, @nestjs/bull

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/transactions/transactions.module.ts:import:../users/users.module

Этот код создает модуль для управления транзакциями в приложении. Он подключает контроллер для обработки запросов, сервисы для логики бизнес-правил и другие модули (пользователи, счета, подписки). Использует очередь задач для обработки оплат и уведомлений.

**Purpose:** Обеспечивает функционал работы с финансовыми транзакциями, оплатами и уведомлениями пользователей

**Key Behaviors:**
- Обработка транзакций через REST API
- Интеграция с модулями пользователей и счетов
- Обработка подписок и оплат
- Работа с очередями задач (Bull)
- Отправка уведомлений через FCM

**Uses:** @nestjs/common, @nestjs/bull, UsersModule, AccountsModule, SubscriptionsModule

---


## Metrics

- **Entities:** 13
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*