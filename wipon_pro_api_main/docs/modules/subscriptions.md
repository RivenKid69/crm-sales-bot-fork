# subscriptions

Модуль подписок отвечает за управление подписками пользователей, включая их активацию, отслеживание и взаимодействие с другими частями приложения. Он использует базу данных через TypeORM, обрабатывает уведомления через Push-сервисы, интегрируется с платежами через Billing-модуль и использует очереди задач Bull для асинхронных операций. Модуль взаимодействует с модулями пользователей, устройств и аккаунтов для получения данных и отправки уведомлений.

## Responsibilities

- Управление жизненным циклом подписок (активация, отмена, обновление)
- Обработка уведомлений и оповещений через Push-сервисы
- Интеграция с платежными системами для подсчёта и управления подписками

## Domains

This module covers the following business domains:

- подписки, уведомления, платежи
- подписки, уведомления, балансировка нагрузки
- модули и зависимости
- база данных, уведомления, интеграции
- утилиты, api, база данных
- база данных, уведомления, оплата, авторизация
- управление подписками, уведомления, интеграции
- база данных, утилиты, api
- база данных, уведомления, сервисы, api
- подписки, уведомления, платежи, очереди задач
- управление подписками, уведомления, логирование, интеграция модулей
- подписки, уведомления, логика бизнес-процессов
- подписки, платежи, уведомления
- управление подписками, оповещения, интеграция

## Dependencies

This module depends on:

- @nestjs/common
- @nestjs/bull
- @nestjs/axios
- @nestjs/typeorm
- typeorm (для работы с базой данных)
- push.service (для отправки уведомлений)

## Main Exports

- `SubscriptionsModule (основной модуль, предоставляющий функционал управления подписками)`
- `subscription.repository (для работы с базой данных)`
- `subscriptions.controller (для обработки HTTP-запросов)`
- `use-cases (для выполнения бизнес-логики подписок)`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./domain/subscriptions.service

Этот код импортирует модуль NestJS, который отвечает за управление подписками. Он использует репозитории, сервисы, контроллеры и другие модули для обработки данных и логики подписок.

**Purpose:** Создает модуль для управления подписками пользователей, включая взаимодействие с базой данных, уведомлениями и другими сервисами.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с другими модулями (пользователи, устройства, аккаунты)
- Обрабатывает бизнес-логику подписок
- Использует Bull для асинхронных задач
- Взаимодействует с внешними сервисами (Push, Billing)

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../../common/services/billing/billing.service

Этот модуль NestJS отвечает за работу с подписками пользователей. Он использует базу данных, сервисы для уведомлений и платежей, а также интегрируется с другими модулями, такими как пользователи и устройства.

**Purpose:** Обеспечивает функционал управления подписками, включая активацию, подсчет и получение информации о подписках пользователей

**Key Behaviors:**
- Интеграция с базой данных через TypeORM
- Использование внешних сервисов для уведомлений и платежей
- Работа с другими модулями, такими как пользователи и устройства
- Обработка подписок через очереди (BullModule)
- Экспорт ключевых use-case для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./domain/use-cases/count-users-active-subscription.use-case

Этот код импортирует и настраивает модуль подписок, который использует репозитории, сервисы, use-кейсы и внешние модули для работы с подписками пользователей. Он подключает базу данных, очереди и другие сервисы.

**Purpose:** Создание и управление подписками пользователей в приложении

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрирует сервисы для уведомлений и оплаты
- Подключает внешние модули (пользователи, устройства, аккаунты)
- Реализует бизнес-логику через use-кейсы
- Использует очереди для асинхронных операций

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../stores/stores.module

Этот код создает модуль для работы с подписками в приложении. Он использует репозитории, сервисы, контроллеры и другие модули, чтобы управлять подписками пользователей и взаимодействовать с внешними системами, такими как уведомления и оплаты.

**Purpose:** Модуль нужен для организации логики подписок, включая их активацию, отслеживание и взаимодействие с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, аккаунтов и устройств
- Обрабатывает подписки и активирует их
- Использует Bull для асинхронных задач, например, отправки уведомлений
- Экспортирует сервисы для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:@nestjs/common

Этот код импортирует модуль NestJS, который управляет подписками пользователей. Он использует репозитории, сервисы, кейсы и подключается к другим модулям, таким как пользователи, устройства и аккаунты, а также использует очередь для уведомлений.

**Purpose:** Обеспечивает функциональность подписок, активации, уведомлений и взаимодействия с другими частями приложения

**Key Behaviors:**
- Управляет подписками пользователей
- Использует репозитории для работы с базой данных
- Интегрируется с другими модулями (пользователи, устройства, аккаунты)
- Использует очередь для отправки уведомлений
- Обрабатывает активацию подписок и подсчет активных подписок

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./data/subscription.repository

Этот модуль управляет подписками пользователей. Он использует базу данных для хранения информации о подписках, а также включает сервисы для работы с пользователями, уведомлениями и оплатой.

**Purpose:** Модуль нужен для организации и управления подписками пользователей в приложении.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, аккаунтов и устройств
- Работает с уведомлениями через Bull и Push сервисы
- Обрабатывает активацию и отслеживание подписок
- Экспортирует ключевые use-cases для других модулей

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./presenter/subscriptions.controller

Этот модуль управляется подписками пользователей, используя TypeORM для работы с базой данных, интегрируется с сервисами уведомлений, оплаты и другими модулями, а также содержит бизнес-логику для управления подписками.

**Purpose:** Обеспечивает функциональность для управления подписками, взаимодействия с пользователями и другими сервисами через модули и очереди задач.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, аккаунтов и устройств
- Обрабатывает бизнес-логику подписок и активации
- Использует Bull для работы с очередями задач
- Использует HttpModule для внешних API-запросов

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:@nestjs/bull

Этот модуль объединяет репозитории, сервисы и контроллеры для работы с подписками пользователей. Он использует базу данных, очереди задач и интеграции с другими модулями, такими как пользователи, устройства и брокер сообщений.

**Purpose:** Обеспечивает обработку подписок, уведомлений и взаимодействие с другими сервисами в приложении.

**Key Behaviors:**
- Интеграция с базой данных через TypeORM
- Использование очередей задач через Bull
- Обработка подписок и активации через сервисы
- Взаимодействие с другими модулями (пользователи, устройства, аккаунты)
- Отправка уведомлений через Push-сервис

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../users/users.module

Этот модуль отвечает за управление подписками пользователей. Он использует базу данных, сервисы уведомлений и интегрируется с другими модулями, такими как пользователи, устройства и брокер сообщений.

**Purpose:** Обеспечивает функционал управления подписками, уведомлениями и взаимодействием с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, устройств и аккаунтов
- Обрабатывает активацию и поиск подписок
- Использует брокер сообщений Bull для асинхронных задач
- Работает с сервисами уведомлений и оплаты

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:class:SubscriptionsModule

Этот модуль отвечает за управление подписками пользователей. Он использует базу данных через TypeORM, подключается к другим модулям, таким как пользователи и устройства, и включает сервисы для работы с уведомлениями и оплатой.

**Purpose:** Обеспечивает функционал для управления подписками, оповещений и интеграции с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей и устройств
- Обрабатывает активацию и поиск подписок
- Использует сервисы для оповещений и оплаты
- Поддерживает асинхронные задачи через Bull

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./domain/use-cases/find-users-all-subscriptions.use-case

Этот код импортирует и настраивает модуль NestJS для работы с подписками. Он использует TypeORM для взаимодействия с базой данных, интегрируется с другими модулями (пользователи, устройства, аккаунты) и настраивает очередь задач для отправки уведомлений.

**Purpose:** Обеспечить функциональность для управления подписками, отслеживания активных подписок и взаимодействия с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулем пользователей
- Настройка очереди задач Bull для уведомлений
- Обработка активации подписок
- Экспортирует use-cases для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../../common/services/push/push.producer.service

Этот модуль объединяет репозитории, сервисы и контроллеры для работы с подписками пользователей. Он использует TypeORM для взаимодействия с базой данных, Bull для фоновых задач и интегрируется с другими модулями, такими как пользователи, устройства и аккаунты.

**Purpose:** Обеспечивает функциональность для управления подписками, уведомлениями и взаимодействием с внешними сервисами.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, устройств и аккаунтов
- Обрабатывает активацию и поиск подписок
- Использует Bull для фоновых задач
- Использует внешние сервисы, такие как push и billing

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./domain/use-cases/find-users-active-subscription.use-case

Этот код настраивает модуль подписок в NestJS, подключая репозитории, сервисы, контроллеры и другие модули. Он использует TypeORM для работы с базой данных и Bull для обработки задач.

**Purpose:** Управление подписками пользователей, включая активацию, поиск и подсчет активных подписок

**Key Behaviors:**
- Поиск активных подписок пользователя
- Активация подписки
- Подсчет пользователей с активными подписками
- Интеграция с сервисами уведомлений
- Работа с базой данных через TypeORM

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../../common/services/push/push.service

Этот модуль объединяет репозитории, сервисы и контроллеры для работы с подписками. Он использует TypeORM для работы с базой данных, Bull для очередей сообщений и интегрируется с другими модулями, такими как пользователи, устройства и аккаунты.

**Purpose:** Обеспечивает управление подписками, включая активацию, подсчёт и уведомления

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, устройств и аккаунтов
- Работает с очередями сообщений через Bull
- Обрабатывает активацию и подсчёт подписок
- Использует внешние сервисы, такие как Push и Billing

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:@nestjs/axios

Этот код создает модуль NestJS для управления подписками. Он использует TypeORM для работы с базой данных, Bull для задач в фоне и интегрируется с модулями пользователей, устройств и учетных записей.

**Purpose:** Модуль обеспечивает логику для работы с подписками, включая их активацию, поиск и обработку через внешние сервисы.

**Key Behaviors:**
- Интеграция с базой данных через TypeORM
- Использование Bull для фоновых задач
- Работа с внешними сервисами (Push, Billing)
- Интеграция с модулями пользователей и устройств
- Обработка подписок через use-cases и сервисы

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:./domain/use-cases/activate-users-subscription.use-case

Этот код импортирует и настраивает модуль подписок, который управляет подписками пользователей, используя базу данных, сервисы уведомлений и интеграции с другими частями приложения. Он объединяет репозитории, бизнес-логику и контроллеры для обработки подписок.

**Purpose:** Обеспечивает функционал управления подписками, уведомлениями и взаимодействием с пользователями и устройствами

**Key Behaviors:**
- Работает с данными подписок через TypeORM
- Использует сервисы для отправки уведомлений
- Интегрируется с модулями пользователей и устройств
- Обрабатывает активацию подписок
- Использует очередь задач Bull для асинхронных операций

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../devices/domain/use-cases/find-users-all-devices-by-at.use-case

Этот код импортирует и настраивает модуль подписок в NestJS, используя репозитории, сервисы, контроллеры и другие модули для работы с подписками, пользователями и устройствами.

**Purpose:** Создает и настраивает модуль подписок, который позволяет управлять подписками пользователей, отправлять уведомления и взаимодействовать с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, аккаунтов и устройств
- Работает с очередями сообщений через BullModule
- Использует HTTP-запросы через HttpModule
- Экспортирует сервисы для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../devices/devices.module

Этот код импортирует модуль 'devices.module' и использует его в 'subscriptions.module', чтобы получить доступ к функциональности, связанной с устройствами. Это позволяет использовать use-case, например, для поиска устройств пользователя.

**Purpose:** Импорт нужен, чтобы использовать функциональность из другого модуля в текущем модуле.

**Key Behaviors:**
- Использует функциональность из другого модуля
- Позволяет использовать use-case из 'devices.module'
- Обеспечивает связь между модулями
- Упрощает доступ к общим функциям
- Позволяет использовать сервисы и контроллеры из другого модуля

**Uses:** devices.module

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:../accounts/accounts.module

Этот модуль отвечает за работу с подписками пользователей. Он использует базу данных, сервисы уведомлений и интегрируется с другими модулями, такими как пользователи, устройства и аккаунты.

**Purpose:** Обеспечивает функционал управления подписками, включая активацию, поиск и подсчет активных подписок.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, устройств и аккаунтов
- Работает с сервисами уведомлений и оплаты
- Использует Bull для асинхронных задач
- Экспортирует use-cases для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, UsersModule, StoresModule, AccountsModule, DevicesModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/subscriptions/subscriptions.module.ts:import:@nestjs/typeorm

Этот код импортирует модули и сервисы, необходимые для работы с подписками. Он использует TypeORM для работы с базой данных, Bull для обработки задач и другие сервисы, такие как push и billing.

**Purpose:** Создает модуль для управления подписками, включая работу с базой данных, обработку событий и взаимодействие с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулями пользователей, аккаунтов и устройств
- Обрабатывает задачи через Bull
- Использует сервисы push и billing для уведомлений и оплаты
- Экспортирует use-cases для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, @nestjs/bull, @nestjs/axios, typeorm

---


## Metrics

- **Entities:** 20
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*