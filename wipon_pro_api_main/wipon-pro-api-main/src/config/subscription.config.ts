require('dotenv').config();

export default {
  lifetime: 365, // Количество дней, на которые активируется подписка
  quarter_lifetime: 90,
  monthly_lifetime: 30,
  nurkassa_type: 'Nurkassa', // подписка активирована через Нуркассу
  cost: 12000, // Цена подписки на %lifetime% дней
  quarter_cost: 3000, // цена подписки на один квартал
  monthly_cost: 1000,
  type: 'Sapphire', // Тип подписки
  quarter_type: 'Topaz',
  monthly_type: 'Zirkon',
};

export const MOBILE_TYPE = 1;
export const DESKTOP_TYPE = 2;
export const TSD_TYPE = 3;

export const MOBILE_PRICE = 12000;
export const DESKTOP_PRICE = 15000;
export const TSD_PRICE = 30000;

export const subscriptionsTypePrice = {
  [MOBILE_TYPE]: MOBILE_PRICE,
  [DESKTOP_TYPE]: DESKTOP_PRICE,
  [TSD_TYPE]: TSD_PRICE,
};

export const TSD_TYPE_NAME = 'mobile_scan';
export const DESKTOP_TYPE_NAME = 'desktop';

export const subscriptionsTypeName = {
  [DESKTOP_TYPE]: DESKTOP_TYPE_NAME,
  [TSD_TYPE]: TSD_TYPE_NAME,
};

export const expiringSubPushNotificationText =
  'Уважаемый налогоплательщик! В ближайшее время истекает срок действия активного прибора! Реализация алкогольной продукции без прибора идентификации УКМ влечет государственный штраф до 600 МРП';
