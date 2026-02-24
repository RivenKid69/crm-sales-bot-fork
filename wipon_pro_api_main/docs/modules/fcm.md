# fcm

Этот модуль отвечает за отправку push-уведомлений через Firebase Cloud Messaging (FCM) в мобильных приложениях. Он использует асинхронную обработку задач через Bull, конфигурацию из @nestjs/config и интеграцию с Firebase Admin SDK. Модуль взаимодействует с другими частями системы для отправки уведомлений пользователям, например, при создании заказа или сообщения.

## Responsibilities

- Отправка push-уведомлений конкретным пользователям через Firebase
- Обработка асинхронных задач по отправке уведомлений с использованием очередей Bull
- Использование конфигурации из @nestjs/config для настройки Firebase

## Domains

This module covers the following business domains:

- мобильные уведомления, push-уведомления
- уведомления, мобильные приложения
- messaging/notifications
- push-уведомления
- уведомления
- уведомления, api, база данных
- мобильные уведомления

## Dependencies

This module depends on:

- @nestjs/common
- @nestjs/config
- @nestjs/bull
- firebase-admin

## Main Exports

- `FcmModule`
- `FcmService`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:@nestjs/common

Этот код импортирует необходимые зависимости для создания модуля FCM в NestJS. Он использует Firebase Admin SDK для работы с FCM, Bull для асинхронной обработки задач, а также интегрируется с модулем уведомлений и сервисами для отправки сообщений.

**Purpose:** Обеспечивает интеграцию с Firebase Cloud Messaging и поддержку асинхронной обработки уведомлений в приложении

**Key Behaviors:**
- Инициализация Firebase с использованием конфигурации из .env
- Использование Bull для асинхронной обработки задач
- Интеграция с модулем уведомлений
- Поддержка отправки уведомлений через FCM
- Использование конфигурационного сервиса для получения данных

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:@nestjs/config

Этот код импортирует необходимые зависимости для модуля Firebase Cloud Messaging (FCM). Он использует NestJS, Bull для очередей, Firebase Admin SDK и сервисы для работы с уведомлениями и конфигурацией.

**Purpose:** Подготовка модуля для отправки push-уведомлений через Firebase с использованием конфигурации и асинхронной обработки задач.

**Key Behaviors:**
- Импорт модулей и сервисов из других частей приложения
- Использование Bull для управления очередями задач
- Инициализация Firebase с помощью конфигурации из .env
- Интеграция с модулем уведомлений
- Экспорт сервисов для использования в других модулях

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:@nestjs/bull

Этот модуль настраивает систему уведомлений через Firebase Cloud Messaging (FCM), используя Bull для обработки задач в очереди. Он подключает сервисы для отправки и получения уведомлений, а также инициализирует Firebase с настройками из конфигурации.

**Purpose:** Обработка асинхронных задач по отправке уведомлений через FCM с использованием очередей Bull

**Key Behaviors:**
- Инициализация Firebase с настройками из конфигурации
- Использование Bull для управления очередями задач
- Интеграция с модулем уведомлений
- Поддержка асинхронной отправки уведомлений
- Использование конфигурационного сервиса для получения данных

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.service..ts:class:FcmService

Этот класс отправляет уведомления через Firebase Cloud Messaging. Он использует токен устройства и данные сообщения для отправки уведомления

**Purpose:** Позволяет отправлять push-уведомления пользователям в мобильных приложениях

**Key Behaviors:**
- Отправка уведомлений через FCM
- Использование токена устройства для доставки
- Асинхронная работа с Firebase
- Интеграция с NestJS через @Injectable
- Работа с объектом MessagingPayload

**Uses:** @nestjs/common, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.service..ts:import:@nestjs/common

Этот код создает сервис для отправки уведомлений через Firebase Cloud Messaging. Он использует Firebase Admin SDK и работает с токенами устройств и заголовками сообщений.

**Purpose:** Позволяет отправлять push-уведомления пользователям через Firebase в NestJS-приложении

**Key Behaviors:**
- Отправка уведомлений по токену устройства
- Использование Firebase Admin SDK
- Работа с объектами MessagingPayload
- Инъекция сервиса в другие компоненты
- Асинхронная отправка сообщений

**Uses:** @nestjs/common, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:../../common/services/consumer/push.consumer

Этот код создает модуль для работы с Firebase Cloud Messaging (FCM), который отправляет уведомления. Использует очередь задач Bull для обработки сообщений и подключается к модулю уведомлений.

**Purpose:** Позволяет отправлять уведомления через FCM с поддержкой асинхронной обработки сообщений

**Key Behaviors:**
- Инициализация Firebase с конфигом из .env
- Настройка очереди задач Bull для обработки уведомлений
- Интеграция с модулем уведомлений
- Обработка уведомлений через producer/consumer паттерн
- Использование конфигурации для Firebase

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:./fcm.service.

Этот модуль настраивает Firebase Cloud Messaging (FCM) для отправки уведомлений. Он использует конфигурацию из .env файла, асинхронные очереди через Bull и подключается к модулю уведомлений

**Purpose:** Обеспечивает отправку push-уведомлений через Firebase с поддержкой асинхронной обработки

**Key Behaviors:**
- Инициализация Firebase с конфигом из окружения
- Использование Bull для асинхронных задач
- Экспорт сервисов для других модулей
- Подключение к модулю уведомлений
- Работа с push-уведомлениями через FCM

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:class:FcmModule

Этот модуль настраивает Firebase Cloud Messaging для отправки уведомлений. Он использует очередь задач Bull для обработки уведомлений и подключается к модулю уведомлений. Инициализирует Firebase с настройками из конфига.

**Purpose:** Позволяет отправлять push-уведомления через Firebase с поддержкой асинхронной обработки

**Key Behaviors:**
- Инициализация Firebase с конфигурацией из .env
- Использование Bull для очередей задач
- Экспорт сервисов для отправки уведомлений
- Интеграция с модулем уведомлений
- Поддержка асинхронной обработки сообщений

**Uses:** @nestjs/bull, @nestjs/config, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:../../common/services/push/push.producer.service

Этот модуль настраивает Firebase Cloud Messaging (FCM) в приложении, используя конфигурацию из .env файла и интегрируется с модулем уведомлений и системой очередей Bull для обработки сообщений.

**Purpose:** Позволяет отправлять уведомления через FCM и обрабатывать их с помощью очередей и модуля уведомлений.

**Key Behaviors:**
- Инициализация Firebase с использованием конфигурации из .env
- Интеграция с модулем уведомлений через forwardRef
- Использование Bull для обработки очередей сообщений
- Экспорт сервисов FCM и PushProducer для использования в других модулях
- Поддержка отправки уведомлений через FCM

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.service..ts:method:FcmService:sendNotification

Этот метод отправляет уведомления на мобильные устройства через Firebase Cloud Messaging. Он использует уникальный токен устройства и данные сообщения, которые передаются как параметры.

**Purpose:** Позволяет отправлять push-уведомления конкретным пользователям в мобильных приложениях

**Key Behaviors:**
- Отправка сообщений через Firebase
- Использование токена устройства для доставки
- Поддержка кастомных данных в сообщении
- Асинхронная отправка уведомлений
- Интеграция с Firebase Admin SDK

**Uses:** firebase-admin, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.service..ts:import:firebase-admin/lib/messaging/messaging-api

Этот код создает сервис для отправки уведомлений через Firebase Cloud Messaging (FCM). Он использует библиотеку Firebase Admin и принимает токен устройства и данные сообщения для отправки уведомления.

**Purpose:** Позволяет отправлять push-уведомления пользователям мобильных приложений через FCM в NestJS-приложении

**Key Behaviors:**
- Отправка сообщений на устройства по токену
- Использование Firebase Admin для работы с FCM
- Интеграция с NestJS через @Injectable

**Uses:** firebase-admin, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:firebase-admin

Этот модуль настраивает Firebase Cloud Messaging для отправки уведомлений. Он использует конфигурацию из .env файла, создает очередь задач с помощью Bull и подключается к модулю уведомлений.

**Purpose:** Позволяет отправлять push-уведомления через Firebase в приложении

**Key Behaviors:**
- Инициализация Firebase с секретными ключами
- Создание очереди задач для обработки уведомлений
- Предоставление сервисов для работы с FCM
- Интеграция с модулем уведомлений
- Обработка конфигурационных переменных

**Uses:** @nestjs/bull, firebase-admin, @nestjs/config

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:method:FcmModule:constructor

Этот модуль настраивает работу с Firebase Cloud Messaging (FCM), используя конфигурационные данные и интегрируется с системой уведомлений. Он также использует Bull для обработки сообщений в очередях.

**Purpose:** Обеспечивает отправку push-уведомлений через FCM в приложении

**Key Behaviors:**
- Инициализация Firebase Admin SDK с данными из конфигурации
- Использование Bull для управления очередями сообщений
- Интеграция с модулем уведомлений через forwardRef
- Обработка push-сообщений через producer и consumer
- Безопасное хранение и использование Firebase-ключей через ConfigService

**Uses:** @nestjs/common, @nestjs/config, @nestjs/bull, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.module.ts:import:../notifications/notifications.module

Этот модуль настраивает отправку уведомлений через Firebase Cloud Messaging (FCM). Он использует очередь задач для обработки уведомлений и подключается к модулю уведомлений. Инициализирует Firebase с настройками из конфигурации.

**Purpose:** Обеспечивает отправку push-уведомлений через FCM с поддержкой асинхронной обработки через очередь

**Key Behaviors:**
- Инициализация Firebase с конфигурацией из .env
- Использование Bull для асинхронной обработки уведомлений
- Подключение к модулю уведомлений через forwardRef
- Предоставление сервисов для отправки и получения уведомлений
- Конфигурация очереди 'push_pro' для обработки задач

**Uses:** @nestjs/bull, @nestjs/common, firebase-admin

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.service..ts:file

Этот сервис отправляет уведомления через Firebase Cloud Messaging. Он использует Firebase Admin SDK для отправки сообщений на устройства по их токенам.

**Purpose:** Позволяет отправлять уведомления пользователям мобильного приложения

**Key Behaviors:**
- Отправка уведомлений по конкретным токенам устройств
- Использование Firebase Admin SDK для работы с FCM
- Поддержка кастомных payload данных
- Интеграция с NestJS через @Injectable
- Асинхронная отправка сообщений

**Uses:** firebase-admin, @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/fcm/fcm.service..ts:import:firebase-admin

Этот код создает сервис для отправки уведомлений через Firebase Cloud Messaging. Он использует Firebase Admin SDK и работает с токенами устройств и сообщениями в определенном формате

**Purpose:** Позволяет отправлять push-уведомления пользователям мобильного приложения через Firebase

**Key Behaviors:**
- Отправка уведомлений по токену устройства
- Использование Firebase Admin SDK
- Работа с сообщениями в формате MessagingPayload
- Интеграция с NestJS через Injectable
- Асинхронная отправка сообщений

**Uses:** firebase-admin, @nestjs/common

---


## Metrics

- **Entities:** 16
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*