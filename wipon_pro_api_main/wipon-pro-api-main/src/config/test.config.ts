export default {
  user: {
    name: 'Apple tester',
    email: 'no_reply@email.apple.com',
    phone_number: '+76967713569',
    work_phone_number: '+76967713569',
    app_language: 'en',
  },
  _user: {
    name: 'API tester',
    email: 'testwipon@yandex.ru',
    phone_number: '+77000000000',
    work_phone_number: '+77000000000',
    app_language: 'en',
  },
  store: {
    buisness_store_name: 'Apple Union Square',
    buisness_store_address: 'Астана Infinite Loop 1',
    buisness_bin: '000000000000',
    license_number: '00000000',
  },
  auth_code: '310117',
  // список телефонов пользователей, запросы с которых не изменяют БД (для тестирования в production)
  productionwhitelist: ['+77474326149'],
};
