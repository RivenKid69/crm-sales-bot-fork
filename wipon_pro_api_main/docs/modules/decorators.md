# decorators

Этот модуль содержит набор декораторов, которые упрощают работу с контроллерами в NestJS. Декоратор @Provider помогает идентифицировать и управлять провайдерами, @FullUrl извлекает полный URL-адрес запроса, а @User получает информацию о текущем пользователе. Это делает код более читаемым и упрощает реализацию задач, таких как логирование, авторизация и инъекция зависимостей.

## Responsibilities

- Упрощает идентификацию и управление провайдерами через декоратор @Provider
- Позволяет извлекать полный URL-адрес запроса с помощью декоратора @FullUrl
- Облегчает доступ к информации о текущем пользователе через декоратор @User

## Domains

This module covers the following business domains:

- веб-приложения, логирование, API
- настройки, инъекция зависимостей
- api
- авторизация
- веб-приложения (HTTP-запросы)
- web-приложения (HTTP-запросы)
- NestJS, декораторы, метаданные

## Dependencies

This module depends on:

- @nestjs/common
- express

## Main Exports

- `Provider`
- `FullUrl`
- `User`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/provider.decorator.ts:file

Этот файл создаёт декоратор `Provider`, который позволяет добавлять метаданные к классам или методам в NestJS. Он использует `SetMetadata` для хранения информации о провайдере, которую можно позже использовать в других частях приложения.

**Purpose:** Декоратор используется для указания имени провайдера, что помогает в управлении зависимостями и модулями в NestJS.

**Key Behaviors:**
- Добавляет метаданные к классам или методам
- Использует `SetMetadata` для хранения информации о провайдере
- Упрощает управление зависимостями в NestJS
- Позволяет идентифицировать провайдер в других частях приложения
- Используется в декораторах для модулей и сервисов

**Uses:** @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/full-url.decorator.ts:file

Этот код создает декоратор для NestJS, который собирает полный URL-адрес из текущего HTTP-запроса. Он использует протокол, хост и путь из запроса, чтобы сформировать полную ссылку.

**Purpose:** Позволяет легко получать полный URL в контроллерах NestJS для логирования, генерации ссылок или аналитики

**Key Behaviors:**
- Сбор полного URL из запроса
- Использование NestJS декораторов
- Работа с объектом Request из Express
- Комбинация частей URL в одну строку
- Переносимый декоратор для контроллеров

**Uses:** @nestjs/common, express

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/full-url.decorator.ts:import:url

Этот код создает декоратор FullUrl, который собирает полный URL-адрес из частей запроса (протокол, хост и путь). Он использует объекты NestJS и Express для получения информации из HTTP-запроса.

**Purpose:** Позволяет получать полный URL-адрес в контроллерах NestJS для логирования, аналитики или перенаправления.

**Key Behaviors:**
- Создает декоратор для извлечения URL из запроса
- Использует NestJS и Express для работы с HTTP-запросами
- Формирует полный URL из протокола, хоста и пути
- Прост в использовании в контроллерах NestJS
- Полезен для логирования и аналитики запросов

**Uses:** @nestjs/common, express, url

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/user.decorator.ts:import:@nestjs/common

Этот код создаёт декоратор User, который извлекает объект пользователя из HTTP-запроса. Он использует ExecutionContext для доступа к запросу и возвращает данные пользователя из request.user.

**Purpose:** Упрощает доступ к информации о текущем пользователе в контроллерах NestJS

**Key Behaviors:**
- Извлекает данные пользователя из HTTP-запроса
- Использует ExecutionContext для получения контекста запроса
- Возвращает объект user из запроса

**Uses:** @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/provider.decorator.ts:function:Provider

Эта функция помечает определённый класс как поставщика, используя метаданные. Она принимает строку с названием поставщика и сохраняет её для дальнейшего использования в приложении.

**Purpose:** Используется для идентификации и организации поставщиков в приложении, например, для инъекции зависимостей или выбора конкретного поставщика в зависимости от контекста.

**Key Behaviors:**
- Помечает класс как поставщика
- Принимает строку с названием поставщика
- Сохраняет метаданные для использования в других частях приложения
- Используется в связке с NestJS
- Упрощает управление поставщиками в приложении

**Uses:** @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/full-url.decorator.ts:import:express

Этот код создает декоратор для NestJS, который извлекает полный URL текущего запроса. Он использует объект запроса из Express и формирует URL с помощью модуля 'url'.

**Purpose:** Позволяет получать полный URL запроса в контроллерах NestJS для логирования, аналитики или других целей.

**Key Behaviors:**
- Извлекает полный URL из HTTP-запроса
- Использует модуль 'url' для формирования URL
- Создает кастомный декоратор для NestJS
- Работает с объектом запроса Express
- Используется в контроллерах для получения информации о запросе

**Uses:** @nestjs/common, express, url

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/provider.decorator.ts:import:@nestjs/common

Этот код определяет кастомный декоратор Provider, который добавляет метаданные к классам или методам. Он использует SetMetadata из NestJS для хранения информации о провайдере.

**Purpose:** Позволяет добавлять метаданные для идентификации провайдеров в NestJS-приложении

**Key Behaviors:**
- Создает кастомный декоратор
- Добавляет метаданные 'provider' к классам/методам
- Использует SetMetadata из @nestjs/common
- Позволяет читать метаданные в других частях приложения
- Прост в использовании для аннотирования провайдеров

**Uses:** @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/user.decorator.ts:file

Этот код создает декоратор User, который извлекает объект пользователя из HTTP-запроса. Он использует NestJS-функцию createParamDecorator для получения данных из контекста выполнения.

**Purpose:** Позволяет легко получать информацию о текущем пользователе в контроллерах NestJS-приложения

**Key Behaviors:**
- Извлекает объект пользователя из HTTP-запроса
- Работает с контекстом выполнения NestJS
- Позволяет использовать user в контроллерах как декоратор
- Не требует внутренних зависимостей
- Упрощает доступ к аутентифицированному пользователю

**Uses:** @nestjs/common

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/full-url.decorator.ts:function:fullUrl

Эта функция создает полный URL-адрес текущего запроса, объединяя протокол (http/https), хост и путь. Декоратор позволяет использовать этот URL в контроллерах NestJS.

**Purpose:** Позволяет получить полный URL-адрес запроса для логирования, аналитики или передачи в другие сервисы

**Key Behaviors:**
- Генерация полного URL из частей запроса
- Использование как декоратора в контроллерах NestJS
- Работа с объектом запроса Express

**Uses:** @nestjs/common, url (Node.js)

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/decorators/full-url.decorator.ts:import:@nestjs/common

Этот код создает декоратор, который извлекает полный URL-адрес из HTTP-запроса. Он использует объект запроса Express и модуль url для построения строки URL.

**Purpose:** Позволяет легко получать полный URL-адрес запроса в контроллерах NestJS для логирования или аналитики

**Key Behaviors:**
- Извлекает протокол, хост и путь из запроса
- Создает полный URL с помощью модуля url
- Работает как декоратор в NestJS для использования в контроллерах
- Использует ExecutionContext для получения объекта запроса
- Поддерживает работу с Express

**Uses:** @nestjs/common, express, url

---


## Metrics

- **Entities:** 10
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*