import { DESKTOP_PRICE, DESKTOP_TYPE, MOBILE_PRICE, MOBILE_TYPE, TSD_PRICE, TSD_TYPE } from "@/config/rates";

export const initialState = {
  auth: {
    phone: localStorage.getItem("phone") || "",
    deviceId: localStorage.getItem("deviceId") || "",
    authToken: localStorage.getItem("authToken") || "",
    user: {},
  },
  company: {
    company: {},
    ugds: [],
    dgds: [],
    storeTypes: [],
    hasStore: localStorage.getItem("hasStore") === "true",
  },
  account: {
    balance: 0,
    number: "",
    transactions: [],
  },
  subscriptions: {
    rates: [],
    hasSubscriptions: false,
    invoiceData: {},
    selectedRate: {},
    selectedRateTypeId: null,
    rateInfoData: [
      {
        id: 1,
        name: "Смартфон",
        actived_info: "Тариф на смартфон успешно активирован!",
        duration: 1,
        price: MOBILE_PRICE,
        list: ["Скачайте приложение Wipon Pro в AppStore или Google Play", "Авторизуйтесь с помощью телефона"],
        type: MOBILE_TYPE,
        icon_green: require("@/assets/images/icons/phone-green.svg"),
        icon: require("@/assets/images/icons/phone.svg"),
        appStore_link: "https://apps.apple.com/ru/app/wipon-pro/id1179029540",
        playMarket_link: "https://play.google.com/store/apps/details?id=com.wipon.pro",
      },
      {
        id: 2,
        name: "Десктоп",
        actived_info: "Тариф на компьютер успешно активирован!",
        duration: 1,
        price: DESKTOP_PRICE,
        list: ["Скачайте приложение Wipon Pro", "Авторизуйтесь", "Скачайте QR-код и отсканируйте его"],
        type: DESKTOP_TYPE,
        icon_green: require("@/assets/images/icons/desktop-green.svg"),
        icon: require("@/assets/images/icons/desktop.svg"),
        download_link: "https://wipon.pro/downloads/wipon-desktop.exe",
      },
      {
        id: 3,
        name: "ТСД",
        actived_info: "Тариф на ТСД успешно активирован!",
        duration: 1,
        price: TSD_PRICE,
        list: [
          "Скачайте APK приложения или скачайте через Google Play",
          "Авторизуйтесь",
          "Скачайте QR-код и отсканируйте его",
        ],
        type: TSD_TYPE,
        icon_green: require("@/assets/images/icons/tsd-green.svg"),
        icon: require("@/assets/images/icons/tsd.svg"),
        playMarket_link: "https://play.google.com/store/apps/details?id=com.wipon.pro",
        download_drop_down: [
          {
            name: "Zebra MC 36, Honeywell, EDA50 K",
            link: "https://wipon.pro/downloads/wipon-pro-tsd.apk",
          },
          {
            name: "Zebra EMDK",
            link: "https://wipon.pro/downloads/wipon-pro-tsd-emdk.apk",
          },
        ],
      },
    ],
  },
};
