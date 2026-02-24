# notifications

Модуль уведомлений отвечает за отправку, хранение и управление уведомлениями в приложении. Он использует FCM для отправки push-уведомлений, взаимодействует с модулем пользователей для определения получателей, а также сохраняет данные уведомлений в базе данных. Модуль предоставляет API для других частей приложения, чтобы они могли отправлять или получать уведомления.

## Responsibilities

- Отправка push-уведомлений через FCM и другие сервисы
- Хранение и управление данными уведомлений в базе данных
- Обработка запросов от других модулей на отправку или получение уведомлений

## Domains

This module covers the following business domains:

- уведомления, мессенджеры, база данных
- уведомления, push-уведомления, база данных
- уведомления, push-сообщения, база данных
- уведомления
- уведомления, база данных, push-сообщения
- база данных, уведомления, api
- уведомления, мессенджер

## Dependencies

This module depends on:

- @nestjs/common — для базовой инфраструктуры и функциональности
- @nestjs/typeorm — для работы с базой данных
- FCM (Firebase Cloud Messaging) — для отправки push-уведомлений

## Main Exports

- `NotificationsModule — основной класс, который настраивает и управляет всеми функциями модуля уведомлений`
- `notifications.controller — для обработки HTTP-запросов, связанных с уведомлениями`
- `notifications.service — для реализации бизнес-логики уведомлений`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:../users/users.module

Этот код создаёт модуль для работы с уведомлениями в NestJS. Он подключает базу данных через TypeORM, использует сервисы для отправки уведомлений и интегрируется с модулем пользователей и FCM (Firebase Cloud Messaging).

**Purpose:** Обеспечивает логику отправки уведомлений, хранения данных и взаимодействия с внешними сервисами

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулем пользователей
- Подключает FCM для отправки уведомлений
- Экспортирует сервис уведомлений для использования в других модулях
- Использует контроллер для обработки HTTP-запросов

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:class:NotificationsModule

Этот класс - модуль NestJS, который собирает все компоненты для работы с уведомлениями. Он подключает базу данных, сервисы и контроллеры, необходимые для отправки уведомлений через FCM.

**Purpose:** Организует логику уведомлений в приложении, обеспечивая связь между базой данных, сервисами и внешними системами вроде FCM.

**Key Behaviors:**
- Интеграция с базой данных через TypeORM
- Обработка уведомлений через FCM
- Экспорт сервиса для использования в других модулях
- Разделение логики на контроллеры, сервисы и репозитории
- Использование модулей пользователей и FCM

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:../fcm/fcm.module

Этот модуль отвечает за работу с уведомлениями в приложении. Он использует TypeORM для взаимодействия с базой данных, подключается к модулю пользователей и модулю FCM для отправки уведомлений через Firebase.

**Purpose:** Обеспечивает отправку, хранение и управление уведомлениями в приложении

**Key Behaviors:**
- Использует TypeORM для работы с репозиторием уведомлений
- Интегрируется с модулем пользователей
- Подключается к FCM для отправки уведомлений
- Предоставляет сервис для логики уведомлений
- Экспортирует сервис уведомлений для других модулей

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:@nestjs/common

Этот модуль NestJS отвечает за работу с уведомлениями. Он использует TypeORM для взаимодействия с базой данных, подключается к модулю пользователей и FCM для отправки уведомлений. Также содержит контроллер, сервис и репозиторий для обработки данных.

**Purpose:** Обеспечивает хранение, отправку и управление уведомлениями в приложении

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулем пользователей
- Использует FCM для отправки push-уведомлений
- Содержит контроллер для обработки HTTP-запросов
- Экспортирует сервис для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:../../common/services/push/push.service

Этот код создает модуль для работы с уведомлениями в NestJS. Он подключает базу данных через TypeORM, использует сервисы для отправки уведомлений и интегрируется с модулем пользователей и FCM (Firebase Cloud Messaging).

**Purpose:** Обеспечивает логику работы с уведомлениями, включая хранение данных, отправку уведомлений и взаимодействие с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с FCM для отправки уведомлений
- Использует сервисы из общих модулей
- Экспортирует сервис уведомлений для других модулей
- Разделяет логику на слои: данные, бизнес-логика, представление

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule, PushService

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:./data/notifications.repository

Этот код создает модуль для работы с уведомлениями в приложении. Он использует базу данных через TypeORM, контроллер для обработки запросов, сервис для логики и подключает другие модули, такие как UsersModule и FcmModule.

**Purpose:** Модуль нужен для организации работы с уведомлениями, включая отправку, хранение и взаимодействие с другими частями приложения.

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулем пользователей (UsersModule)
- Использует FCM для отправки уведомлений
- Предоставляет сервис для логики уведомлений
- Экспортирует сервис для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:./presenter/notifications.controller

Этот код создает модуль для работы с уведомлениями. Он подключает базу данных через TypeORM, использует сервисы для отправки уведомлений и контроллер для обработки запросов.

**Purpose:** Обеспечивает работу с уведомлениями, включая их хранение, отправку и управление

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулем пользователей
- Использует FCM для отправки уведомлений
- Предоставляет API через контроллер
- Экспортирует сервис для использования в других модулях

**Uses:** @nestjs/common, @nestjs/typeorm

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:@nestjs/typeorm

Этот код создает модуль для работы с уведомлениями в приложении. Он использует TypeORM для работы с базой данных, подключает модули пользователей и FCM, и содержит сервисы для отправки уведомлений.

**Purpose:** Обеспечивает логику и инфраструктуру для отправки и хранения уведомлений в приложении

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Обрабатывает HTTP-запросы через контроллер
- Интегрируется с FCM для push-уведомлений
- Экспортирует сервис для использования в других модулях
- Подключает модуль пользователей для работы с данными

**Uses:** @nestjs/common, @nestjs/typeorm, typeorm, UsersModule, FcmModule

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/notifications/notifications.module.ts:import:./domain/notifications.service

Этот код создает модуль NestJS для работы с уведомлениями. Он подключает базу данных через TypeORM, использует сервисы для отправки уведомлений и интегрируется с другими модулями приложения.

**Purpose:** Создает модуль для управления уведомлениями, включая их хранение и отправку

**Key Behaviors:**
- Использует TypeORM для работы с базой данных
- Интегрируется с модулем пользователей (UsersModule)
- Использует FCM для отправки push-уведомлений
- Экспортирует сервис уведомлений для использования в других модулях
- Содержит контроллер для обработки HTTP-запросов

**Uses:** @nestjs/common, @nestjs/typeorm, UsersModule, FcmModule

---


## Metrics

- **Entities:** 9
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*