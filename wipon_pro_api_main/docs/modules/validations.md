# validations

Этот модуль отвечает за валидацию данных в приложении, проверяя, что введённые значения соответствуют существующим записям в базе данных и соблюдают формат. Он используется для предотвращения ошибок, связанных с некорректными ID, числами или ссылками на несуществующие объекты. Модуль взаимодействует с DAO-модулями для проверки данных в базе и предоставляет валидационные правила другим частям приложения.

## Responsibilities

- Проверка существования сущностей (например, товаров, пользователей) в базе данных перед их использованием
- Валидация числовых полей, чтобы избежать ошибок при обработке данных
- Предотвращение сохранения объектов с некорректными ссылками на несуществующие записи

## Domains

This module covers the following business domains:

- валидация данных, бэкенд-логика
- валидация данных в API
- валидация, база данных
- валидация данных, API
- валидация
- валидация данных
- база данных
- валидация данных, база данных

## Dependencies

This module depends on:

- База данных — для проверки существования записей
- Библиотеки валидации (например, class-validator) — для реализации правил валидации

## Main Exports

- `IsItemExistsConstraint — для проверки существования товара`
- `IsNumericConstraint — для валидации числовых полей`
- `IsDgdExistsConstraint — для проверки существования DGD-записи`
- `IsUgdExistsConstraint — для проверки существования UGD-записи`
- `IsRegionExistsConstraint — для проверки существования региона`
- `IsStoreTypeExistsConstraint — для проверки существования типа магазина`

## Components

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsItemExistsConstraint

Этот код создаёт валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Обеспечивает целостность данных, предотвращая использование несуществующих идентификаторов в приложении

**Key Behaviors:**
- Проверка существования магазина по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования товара по ID

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:method:IsNumericConstraint:defaultMessage

Этот код создает кастомный валидатор, который проверяет, является ли значение числом. Он использует библиотеку class-validator для добавления этой проверки к полям в классах сущностей.

**Purpose:** Обеспечивает корректную валидацию числовых полей в сущностях, чтобы избежать ошибок при обработке данных

**Key Behaviors:**
- Проверяет, является ли значение числом
- Возвращает пользовательское сообщение об ошибке при несоответствии
- Интегрируется с class-validator для использования в сущностях
- Работает с любыми строковыми значениями
- Поддерживает настройку сообщений об ошибках

**Uses:** class-validator

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsDgdExists

Этот код проверяет, существует ли запись DGD с указанным ID в базе данных. Он использует декоратор для валидации значений в классах, например, при создании или обновлении объектов.

**Purpose:** Убедиться, что ссылка на DGD в данных корректна и соответствует существующей записи в базе данных.

**Key Behaviors:**
- Проверка существования записи DGD по ID
- Использование декоратора для валидации в классах
- Асинхронная проверка через DAO
- Интеграция с другими модулями через DAO
- Поддержка настройки валидации через параметры

**Uses:** class-validator, DgdDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/user.dao

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных перед сохранением. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Обеспечивает целостность данных, предотвращая сохранение ссылок на несуществующие объекты

**Key Behaviors:**
- Проверка существования записи в базе данных
- Использование асинхронной валидации
- Интеграция с DAO-слоем для доступа к данным
- Регистрация валидаторов на уровне классов
- Поддержка настраиваемых параметров валидации

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/item.dao

Этот код создает кастомные валидаторы, которые проверяют, существует ли запись в базе данных по определённому ID. Например, проверяет, есть ли магазин, товар, регион или пользователь с указанным ID.

**Purpose:** Используется для проверки корректности данных перед сохранением или обновлением в базе данных.

**Key Behaviors:**
- Проверка существования записи по ID
- Использование кастомных валидаторов
- Интеграция с DAO-слоем для доступа к данным
- Асинхронная проверка данных
- Регистрация валидаторов на уровне классов

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/ugd.dao

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных перед обработкой данных. Например, проверяет, есть ли магазин с определенным ID или пользователь с таким номером телефона.

**Purpose:** Убеждается, что приложение работает только с существующими данными и предотвращает ошибки из-за несуществующих записей

**Key Behaviors:**
- Проверка существования записи в базе данных
- Использование асинхронной валидации
- Интеграция с DAO-слоем для доступа к данным
- Регистрация валидаторов на уровне классов
- Поддержка настраиваемых параметров валидации

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsUgdExistsConstraint

Этот код проверяет, существует ли определённый объект в базе данных, например, магазин или пользователь. Он использует DAO (Data Access Object) для поиска объекта по его идентификатору и возвращает результат проверки.

**Purpose:** Убедиться, что данные, которые вводит пользователь, действительно существуют в базе данных, чтобы избежать ошибок.

**Key Behaviors:**
- Проверка существования объекта по ID
- Использование DAO для доступа к данным
- Асинхронная проверка
- Интеграция с фреймворком class-validator
- Реализация кастомных валидаторов

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsUgdExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убедиться, что данные, которые принимает система, соответствуют реальным записям в базе данных

**Key Behaviors:**
- Проверка существования магазина по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Асинхронная валидация через базу данных

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsDgdExistsConstraint

Этот код проверяет, существует ли запись в базе данных для определённого ID. Например, он проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убедиться, что данные, которые вводит пользователь, соответствуют реальным записям в базе данных

**Key Behaviors:**
- Проверка существования записи по ID
- Асинхронная валидация через базу данных
- Использование декораторов для валидации полей
- Поддержка различных типов данных (числа, строки)
- Интеграция с DAO-слоем для доступа к данным

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:function:IsNumeric

Этот код создает валидатор, который проверяет, является ли значение числом. Он использует декоратор для применения проверки к свойству класса и выводит ошибку, если значение не число

**Purpose:** Используется для проверки корректности числовых данных в формах или API

**Key Behaviors:**
- Проверяет, что значение можно преобразовать в число
- Выводит пользовательское сообщение об ошибке
- Работает как декоратор для классов
- Использует внешнюю библиотеку class-validator
- Поддерживает настройку сообщений об ошибках

**Uses:** class-validator

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:method:IsNumericConstraint:validate

Этот код создает валидатор, который проверяет, является ли значение числом. Если значение не число, он выводит сообщение об ошибке. Он используется для проверки данных в формах

**Purpose:** Позволяет проверять числовые поля в приложении и отображать ошибки, если данные введены неправильно

**Key Behaviors:**
- Проверяет, что значение можно преобразовать в число
- Генерирует сообщение об ошибке при неудачной проверке
- Работает как декоратор для классов в TypeScript
- Использует библиотеку class-validator для валидации
- Поддерживает настройку сообщений об ошибках

**Uses:** class-validator

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsUgdExists

Этот код проверяет, существует ли запись UGD в базе данных по заданному ID. Он использует декоратор для валидации данных перед сохранением или обновлением.

**Purpose:** Убедиться, что ссылка на UGD-запись действительна и не указывает на несуществующий объект

**Key Behaviors:**
- Проверка существования UGD по ID
- Асинхронная валидация через базу данных
- Использование декораторов для валидации полей в DTO
- Интеграция с DAO для доступа к данным
- Поддержка настройки валидации через параметры

**Uses:** class-validator, UgdDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsLedgerExists

Этот код создает валидаторы, которые проверяют, существует ли связанный объект в базе данных перед сохранением. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Обеспечивает целостность данных, предотвращая сохранение объектов с некорректными ссылками на несуществующие сущности

**Key Behaviors:**
- Проверка существования магазина по ID
- Проверка существования пользователя по номеру телефона
- Асинхронная валидация через базу данных
- Использование декораторов для привязки валидации к полям классов
- Поддержка различных типов сущностей (магазины, пользователи, товары и т.д.)

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsRegionExistsConstraint

Этот код проверяет, существует ли регион с определенным ID в базе данных. Он использует DAO для запроса данных и возвращает true, если регион найден.

**Purpose:** Убедиться, что вводимые данные содержат действительный ID региона перед его использованием в приложении

**Key Behaviors:**
- Проверка существования записи в базе данных
- Использование DAO для взаимодействия с БД
- Асинхронная валидация данных
- Интеграция с фреймворком class-validator
- Применение к свойствам классов

**Uses:** class-validator, RegionDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsDgdExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Каждый валидатор использует DAO (Data Access Object) для проверки наличия записи и применяется как декоратор к свойствам классов.

**Purpose:** Обеспечивает проверку корректности данных перед их сохранением или обновлением в базе данных

**Key Behaviors:**
- Проверка существования записи по ID
- Асинхронная валидация через базу данных
- Использование декораторов для применения правил
- Поддержка разных типов сущностей (store, region, user и др.)

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsStoreTypeExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Каждый валидатор использует DAO (Data Access Object) для проверки наличия записи в таблице.

**Purpose:** Убедиться, что данные, которые вводятся в систему, ссылаются на реально существующие объекты в базе данных

**Key Behaviors:**
- Проверка существования storeType по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования товара по ID

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsRegionExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Каждый валидатор использует DAO (Data Access Object) для поиска записи и возвращает результат проверки.

**Purpose:** Убедиться, что данные, которые вводятся в систему, ссылаются на реально существующие объекты в базе данных

**Key Behaviors:**
- Проверка существования storeType по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования пользователя по номеру телефона

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, UserDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsItemExists

Этот код создает валидатор, который проверяет существует ли товар с заданным ID. Он использует DAO для поиска товара в базе данных и возвращает true, если товар найден.

**Purpose:** Убедиться, что вводимый ID товара соответствует существующему элементу в базе данных

**Key Behaviors:**
- Проверка существования товара по ID
- Асинхронная валидация через базу данных
- Интеграция с DAO для доступа к данным
- Реиспользуемый валидатор для разных сценариев
- Работает с объектами класса-validator

**Uses:** class-validator, ItemDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsStoreTypeExists

Этот код проверяет, существует ли определённый объект (например, тип магазина, DGD, UGD и т.д.) в базе данных по его ID. Если объект не найден, валидация не пройдёт.

**Purpose:** Убеждается, что переданные данные соответствуют существующим записям в базе данных, предотвращая ошибки при работе с неправильными ID.

**Key Behaviors:**
- Проверяет существование объекта по ID
- Использует DAO для взаимодействия с базой данных
- Асинхронная проверка через Promise
- Интегрируется с фреймворком class-validator
- Можно применять к разным типам объектов (магазины, пользователи и т.д.)

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/region.dao

Этот код создает кастомные валидаторы для проверки существования записей в базе данных. Каждый валидатор использует соответствующий DAO-класс, чтобы убедиться, что объект с определенным ID существует перед сохранением данных.

**Purpose:** Обеспечивает корректность данных, проверяя, что связанные сущности уже существуют в базе данных.

**Key Behaviors:**
- Проверка существования storeTypeId в базе данных
- Проверка существования dgdId в базе данных
- Проверка существования ugdId в базе данных
- Проверка существования regionId в базе данных
- Проверка существования itemId в базе данных

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsPhoneExistsInUsers

Этот код создает валидаторы для проверки существования записей в базе данных. Каждая функция проверяет, существует ли объект (например, магазин или пользователь) по его идентификатору, используя соответствующий DAO (Data Access Object).

**Purpose:** Обеспечивает валидацию данных перед сохранением, предотвращая ссылки на несуществующие объекты

**Key Behaviors:**
- Проверка существования записей в БД
- Асинхронная валидация через DAO
- Персонализированные декораторы для разных сущностей
- Интеграция с класс-валидатором
- Поддержка настраиваемых параметров валидации

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:class:IsNumericConstraint

Этот код создает валидатор, который проверяет, является ли строка числом. Если значение не число, выводится ошибка. Используется с декоратором для проверки полей в классах.

**Purpose:** Позволяет проверять корректность числовых данных в формах, API или базах данных

**Key Behaviors:**
- Проверяет, можно ли преобразовать строку в число
- Выводит пользовательское сообщение об ошибке
- Работает как декоратор для классов
- Использует библиотеку class-validator
- Подходит для проверки входных данных

**Uses:** class-validator

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/store-type.dao

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по определённому ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убедиться, что данные, которые вводят пользователи, соответствуют реальным записям в базе данных

**Key Behaviors:**
- Проверка существования записи в базе данных по ID
- Использование DAO для взаимодействия с базой данных
- Интеграция с библиотекой class-validator для валидации
- Асинхронная проверка данных
- Реиспользуемость валидаторов в разных частях приложения

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/ledger.dao

Этот код создает валидаторы для проверки существования записей в базе данных. Каждый валидатор проверяет, существует ли объект (например, магазин или пользователь) по его ID перед сохранением данных.

**Purpose:** Убедиться, что приложения не используют несуществующие идентификаторы объектов в операциях создания/обновления

**Key Behaviors:**
- Проверка существования записей в БД
- Асинхронная валидация через DAO
- Интеграция с ORM через class-validator
- Проверка уникальности телефонных номеров
- Поддержка разных типов сущностей

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:component:IsNumeric

Этот код проверяет, является ли значение числом. Если пользователь вводит, например, буквы вместо цифр, будет выдано предупреждение. Это как контрольный замок, который не позволяет залить в бак бензина вместо воды

**Purpose:** Проверка корректности числовых данных в формах или API

**Key Behaviors:**
- Проверяет, можно ли преобразовать строку в число
- Генерирует ошибку если значение не число
- Работает как декоратор для классов
- Поддерживает настраиваемые сообщения об ошибках
- Интегрируется с фреймворками вроде NestJS

**Uses:** class-validator

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:class-validator

Этот код создает кастомные валидаторы для проверки существования записей в базе данных. Каждый валидатор использует DAO (Data Access Object) для проверки, существует ли объект с определенным ID.

**Purpose:** Обеспечивает валидацию данных, предотвращая использование несуществующих идентификаторов в запросах

**Key Behaviors:**
- Проверка существования storeType по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования пользователя по номеру телефона

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, UserDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsLedgerExistsConstraint

Этот код создает валидаторы для проверки существования записей в базе данных. Каждый валидатор проверяет, существует ли объект с определенным ID через соответствующий DAO (Data Access Object).

**Purpose:** Обеспечивает корректность данных, предотвращая использование несуществующих идентификаторов в бизнес-логике

**Key Behaviors:**
- Проверка существования storeTypeId в StoreTypeDao
- Проверка существования dgdId в DgdDao
- Асинхронная валидация через DAO
- Использование декораторов class-validator
- Проверка уникальности телефонных номеров в UserDao

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:import:../dao/dgd.dao

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по определенному ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убедиться, что данные, которые обрабатывает приложение, соответствуют существующим записям в базе данных

**Key Behaviors:**
- Проверка существования записи в базе данных
- Асинхронная валидация через DAO
- Интеграция с разными типами сущностей (магазины, пользователи, товары)
- Использование декораторов для привязки к свойствам классов
- Поддержка разных типов данных (числа, строки)

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:function:IsRegionExists

Этот код проверяет, существует ли регион с заданным ID в базе данных. Он использует DAO-класс RegionDao для поиска регионов и возвращает true, если регион найден.

**Purpose:** Убедиться, что вводимые данные содержат действительный ID региона

**Key Behaviors:**
- Проверка существования региона по ID
- Использование DAO для взаимодействия с базой данных
- Асинхронная проверка
- Интеграция с фреймворком валидации
- Работа с объектами в формате DTO

**Uses:** class-validator, RegionDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsLedgerExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убеждается, что данные, которые вводят пользователи, соответствуют реальным записям в базе данных

**Key Behaviors:**
- Проверка существования магазина по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования товара по ID

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsIPhoneNumberExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Каждый валидатор использует DAO (Data Access Object) для проверки наличия записи в таблице.

**Purpose:** Обеспечивает корректность данных при создании/обновлении объектов, проверяя существование связанных сущностей в базе

**Key Behaviors:**
- Проверка существования storeType по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования пользователя по номеру телефона

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, UserDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsStoreTypeExistsConstraint

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по определённому ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убедиться, что данные, которые вводит пользователь, соответствуют реальным записям в базе данных.

**Key Behaviors:**
- Проверка существования записи по ID
- Асинхронная валидация через базу данных
- Использование декораторов для привязки к свойствам классов
- Интеграция с DAO для доступа к данным
- Поддержка разных типов сущностей (магазины, пользователи, товары и т.д.)

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:method:IsItemExistsConstraint:validate

Этот код создает валидаторы, которые проверяют, существует ли запись в базе данных по заданному ID. Например, проверяет, есть ли магазин с таким ID или пользователь с таким номером телефона.

**Purpose:** Убеждается, что данные, которые вводят пользователи, соответствуют реальным записям в базе данных

**Key Behaviors:**
- Проверка существования магазина по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования товара по ID

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, ItemDao, UserDao, LedgerDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:import:class-validator

Этот код создаёт кастомную проверку для числовых значений. Он проверяет, что строка может быть преобразована в число, и выводит ошибку, если это не так. Использует декораторы для привязки проверки к свойствам классов.

**Purpose:** Позволяет валидировать числовые поля в формах или данных, чтобы избежать ошибок при обработке

**Key Behaviors:**
- Проверка, что значение является числом
- Генерация понятного сообщения об ошибке
- Использование декораторов для привязки к свойствам
- Работа с библиотекой class-validator
- Персонализация сообщений об ошибках

**Uses:** class-validator

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-entity-exists.ts:class:IsIPhoneNumberExistsConstraint

Этот код создаёт валидаторы, которые проверяют, существует ли определённый объект в базе данных, например, магазин, DGD, UGD, регион или пользователь. Они используются для проверки данных перед их сохранением.

**Purpose:** Убедиться, что данные, которые вводятся в систему, соответствуют реальным записям в базе данных и не содержат ошибок.

**Key Behaviors:**
- Проверка существования магазина по ID
- Проверка существования DGD по ID
- Проверка существования UGD по ID
- Проверка существования региона по ID
- Проверка существования пользователя по номеру телефона

**Uses:** class-validator, StoreTypeDao, DgdDao, UgdDao, RegionDao, UserDao

---

### /home/corta/crm_sales_bot/wipon_pro_api_main/wipon-pro-api-main/src/common/validations/is-numeric.ts:file

Этот код создает кастомный валидатор, который проверяет, является ли значение числом. Он использует библиотеку class-validator для декораторов и проверки данных в TypeScript-классах.

**Purpose:** Позволяет проверять числовые поля в формах или DTO-объектах, чтобы избежать ошибок с некорректными данными

**Key Behaviors:**
- Проверяет, можно ли преобразовать строку в число
- Возвращает ошибку, если значение не число
- Использует декораторы для привязки к свойствам классов
- Поддерживает настраиваемые сообщения об ошибках
- Работает с библиотекой class-validator

**Uses:** class-validator

---


## Metrics

- **Entities:** 36
- **Total Lines:** 0

---

*Generated by Codebase-Analyzer*