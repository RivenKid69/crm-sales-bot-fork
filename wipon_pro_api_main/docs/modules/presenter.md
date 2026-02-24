# presenter

Этот модуль отвечает за предоставление данных о типах магазинов через REST-интерфейс. Он принимает HTTP-запросы, использует сервис для получения данных, применяет трансформации и возвращает результат. Также добавляет документацию через Swagger для удобства разработчиков.

## Responsibilities

- Обработка HTTP-запросов для получения списка типов магазинов
- Интеграция с сервисным слоем для получения данных из домена
- Применение трансформаций данных перед отправкой ответа

## Domains

This module covers the following business domains:

- api
- API

## Dependencies

This module depends on:

- @nestjs/common (для базовой функциональности контроллеров)
- @nestjs/swagger (для генерации документации API)

## Main Exports

- `StoreTypesController (основной класс, обрабатывающий HTTP-запросы)`
- `getStoreTypes (метод для получения данных)`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:import:@nestjs/common

Этот код создает контроллер для обработки HTTP-запросов к эндпоинту /store-types. Он использует сервис для получения данных и интерсептор для преобразования ответа, а также добавляет документацию через Swagger.

**Purpose:** Позволяет получать список типов магазинов через REST-интерфейс с поддержкой документации и преобразования данных

**Key Behaviors:**
- Обработка GET-запросов к /store-types
- Использование StoreTypesService для получения данных
- Применение TransformInterceptor к ответу
- Добавление документации через Swagger
- Асинхронное выполнение запроса к базе данных

**Uses:** @nestjs/common, @nestjs/swagger, StoreTypesService, TransformInterceptor

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:import:@nestjs/swagger

Этот код создает контроллер для получения списка типов магазинов. Он использует сервис для получения данных и Swagger для документирования API.

**Purpose:** Позволяет получить список типов магазинов через HTTP-запрос и документировать этот эндпоинт для пользователей и разработчиков.

**Key Behaviors:**
- Получает список типов магазинов
- Использует сервис для логики получения данных
- Документирует API с помощью Swagger
- Применяет интерцептор для преобразования данных
- Обрабатывает GET-запросы на эндпоинт /store-types

**Uses:** @nestjs/common, @nestjs/swagger, StoreTypesService, TransformInterceptor

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:method:StoreTypesController:constructor

Этот код создает контроллер, который обрабатывает GET-запросы для получения списка типов магазинов. Он использует сервис для получения данных и добавляет документацию через Swagger.

**Purpose:** Позволяет получить список доступных типов магазинов через API-эндпоинт

**Key Behaviors:**
- Обрабатывает GET-запросы по адресу /store-types
- Использует Swagger для документирования API
- Применяет интерцептор для преобразования ответа
- Делегирует логику сервису StoreTypesService
- Возвращает список всех типов магазинов

**Uses:** StoreTypesService, TransformInterceptor, @nestjs/common, @nestjs/swagger

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:method:StoreTypesController:getStoreTypes

Этот метод получает список типов магазинов через сервис и возвращает его с помощью интерцептора, который может изменять формат ответа. Декораторы Swagger описывают документацию API для этого эндпоинта.

**Purpose:** Позволяет получить список доступных типов магазинов через HTTP-запрос

**Key Behaviors:**
- Получает данные через StoreTypesService
- Использует TransformInterceptor для обработки ответа
- Добавляет документацию через Swagger
- Обрабатывает GET-запросы по адресу /store-types

**Uses:** @nestjs/common, @nestjs/swagger, StoreTypesService, TransformInterceptor

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:class:StoreTypesController

Этот класс — контроллер, который получает список типов магазинов. Он использует сервис для получения данных и интерцептор для преобразования ответа. Декораторы добавляют документацию через Swagger.

**Purpose:** Позволяет получать список типов магазинов через HTTP-запрос и документировать этот эндпоинт для других разработчиков.

**Key Behaviors:**
- Получает список типов магазинов
- Использует сервис для логики
- Преобразует ответ с помощью интерцептора
- Добавляет документацию через Swagger
- Обрабатывает GET-запросы на эндпоинт /store-types

**Uses:** StoreTypesService, TransformInterceptor, ApiOperation, ApiOkResponse, ApiTags

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:import:../domain/store-types.service

Этот код создает контроллер для обработки HTTP-запросов к эндпоинту /store-types. Он использует сервис для получения данных и интерцептор для преобразования ответа, а также добавляет документацию через Swagger.

**Purpose:** Позволяет получить список типов магазинов через REST-интерфейс с поддержкой документации и трансформации данных

**Key Behaviors:**
- Обработка GET-запросов на эндпоинт /store-types
- Использование сервиса для получения данных
- Применение интерцептора для трансформации ответа
- Добавление документации через Swagger
- Интеграция с NestJS

**Uses:** @nestjs/common, @nestjs/swagger, StoreTypesService, TransformInterceptor

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/modules/store-types/presenter/store-types.controller.ts:import:../../../common/interceptor/transform.interceptor

Этот код создает контроллер для получения списка типов магазинов. Он использует сервис для получения данных и интерцептор для преобразования ответа, а также документирует API с помощью Swagger.

**Purpose:** Обеспечивает возможность получать список типов магазинов через HTTP-запрос и документирует этот эндпоинт для удобства разработчиков.

**Key Behaviors:**
- Получает данные из сервиса StoreTypesService
- Использует TransformInterceptor для обработки ответа
- Документирует API с помощью Swagger
- Обрабатывает GET-запросы на эндпоинт /store-types
- Возвращает список типов магазинов

**Uses:** @nestjs/common, @nestjs/swagger, StoreTypesService, TransformInterceptor

---


## Metrics

- **Entities:** 7
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*