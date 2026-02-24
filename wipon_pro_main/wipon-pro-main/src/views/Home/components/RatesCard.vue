<template>
  <Card title="Тарифы" class="rate-main-page" :small-padding="hasSubscription">
    <template v-slot:header v-if="rates.length">
      <base-button @btn-click="doSomething" class="rate-page__button" :small="hasSubscription">
        {{ hasSubscription ? "Сменить тариф" : "Выбрать тариф" }}
      </base-button>
    </template>
    <div v-if="!rates.length" class="rate-page__select">
      <h2 class="rate-page__title">У вас нет активных тарифов</h2>
      <div class="rate-page__text">
        Выберите подходящее устройство и <br />
        активируйте его
      </div>
      <div>
        <base-button filled type="primary" class="rate-page__button" @btn-click="doSomething">
          Выбрать тариф
        </base-button>
      </div>
    </div>
    <div v-else>
      <div class="rate-page__list">
        <!--        <div class="rate__current-text">текущий тариф</div>-->
        <div
          v-for="(rate, index) in rates"
          :key="index"
          class="rate-page__item"
          :class="{
            // 'rate-page__item--phone': rate.type === 1,
            // 'rate-page__item--pc': rate.type === 2,
            // 'rate-page__item--tsd': rate.type === 3,
            'rate-page__item--expired': !rate.is_active,
          }"
        >
          <div class="rate__item-head">
            <div class="rate-page__info" :class="{ 'rate-page--expired': !rate.is_active }">
              <div class="rate-page__icon" :class="{ 'rate-page__icon--expired': !rate.is_active }">
                <svg
                  v-if="rate.type === 1"
                  width="22"
                  height="18"
                  viewBox="0 0 14 20"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M2 2V18H12V2H2ZM1 0H13C13.2652 0 13.5196 0.105357 13.7071 0.292893C13.8946 0.48043 14 0.734784 14 1V19C14 19.2652 13.8946 19.5196 13.7071 19.7071C13.5196 19.8946 13.2652 20 13 20H1C0.734784 20 0.48043 19.8946 0.292893 19.7071C0.105357 19.5196 0 19.2652 0 19V1C0 0.734784 0.105357 0.48043 0.292893 0.292893C0.48043 0.105357 0.734784 0 1 0ZM7 15C7.26522 15 7.51957 15.1054 7.70711 15.2929C7.89464 15.4804 8 15.7348 8 16C8 16.2652 7.89464 16.5196 7.70711 16.7071C7.51957 16.8946 7.26522 17 7 17C6.73478 17 6.48043 16.8946 6.29289 16.7071C6.10536 16.5196 6 16.2652 6 16C6 15.7348 6.10536 15.4804 6.29289 15.2929C6.48043 15.1054 6.73478 15 7 15Z"
                    fill="currentColor"
                  />
                </svg>
                <svg
                  v-if="rate.type === 2"
                  width="22"
                  height="18"
                  viewBox="0 0 22 18"
                  fill="currentColor"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M3 2V13H19V2H3ZM1 1.007C1 0.451 1.455 0 1.992 0H20.008C20.556 0 21 0.449 21 1.007V15H1V1.007ZM0 16H22V18H0V16Z"
                    fill="currentColor"
                  />
                </svg>
                <svg
                  v-if="rate.type === 3"
                  width="22"
                  height="18"
                  viewBox="0 0 18 18"
                  fill="currentColor"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M12 0H18V5H16V2H12V0ZM6 0V2H2V5H0V0H6ZM12 18V16H16V13H18V18H12ZM6 18H0V13H2V16H6V18ZM0 8H18V10H0V8Z"
                    fill="currentColor"
                  />
                </svg>
              </div>
              <div class="rate-page__info-block">
                <div class="rate-page__title">
                  <span @click="showRateDetails(rate.custom_id)" class="rate-page__title_cursor">{{ rate.name }}</span>
                </div>
                <div class="rate-page--expired">{{ rate.expired_day }}</div>
              </div>
              <base-button-drop-down
                v-if="rate.is_active"
                class="rate__dropdown-button"
                small
                :links="getActiveRateLinks(rate.type)"
              >
                <span class="rate-button__icon">
                  <img src="@/assets/images/icons/download.svg" alt="" />
                </span>
                Скачать
              </base-button-drop-down>
            </div>
          </div>
          <div v-if="rate.is_active" class="rate-page__bottom">
            <div class="rate-page__progress-bar">
              <div class="rate-page__progress-value" :style="{ width: rate.calcWidth + '%' }"></div>
            </div>
            <div class="rate-page__dates">
              <span class="rate-page__activated">{{ formatDate(rate.activated_at) }}</span>
              <span class="rate-page__activated">{{ formatDate(rate.expires_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>

<script>
import Card from "@/components/Card";
import BaseButton from "@/components/base/BaseButton";
import BaseButtonDropDown from "@/components/base/BaseButtonDropDown";

import { computed, defineComponent, onBeforeMount } from "vue";
import { useStore } from "@/store";
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from "@/config/rates";

export default defineComponent({
  name: "RatesCard",
  components: {
    Card,
    BaseButton,
    BaseButtonDropDown,
  },
  setup(props, { emit }) {
    const store = useStore();
    const formatDate = (date = Date.now()) => {
      return new Intl.DateTimeFormat("ru-RU", {
        year: "numeric",
        month: "long",
        day: "2-digit",
      }).format(new Date(date));
    };

    const rates = computed(() =>
      store.getters.subscriptions.map((item) => ({
        ...item,
        expired_day:
          getDifferenceDays(item.expires_at) / (1000 * 3600 * 24) > 1
            ? Math.round(getDifferenceDays(item.expires_at) / (1000 * 3600 * 24)) + " дней до истечения"
            : // : `Истёк ${new Date(item.expires_at).toLocaleDateString("ru-Ru")}`,
              `Истёк ${formatDate(item.expires_at)}`,
        calcWidth: getLeftPercent(item.expires_at),
      }))
    );

    const mobileLinks = [
      {
        name: "App Store",
        link: "https://apps.apple.com/ru/app/wipon-pro/id1179029540",
      },
      {
        name: "Google Play",
        link: "https://play.google.com/store/apps/details?id=com.wipon.pro",
      },
    ];

    const desktopLinks = [
      {
        name: "Приложение",
        link: "https://wipon.pro/downloads/wipon-desktop.exe",
      },
      {
        name: "QR-код",
        isQr: true,
        link: "",
      },
    ];

    const tsdLinks = [
      {
        name: "(APK) Zebra MC 36, Honeywell, EDA50 K",
        link: "https://wipon.pro/downloads/wipon-pro-tsd.apk",
      },
      {
        name: "(APK) Zebra EMDK",
        link: "https://wipon.pro/downloads/wipon-pro-tsd-emdk.apk",
      },
      {
        name: "Google Play",
        link: "https://play.google.com/store/apps/details?id=com.wipon.pro",
      },
      {
        name: "QR-код",
        isQr: true,
        link: "",
      },
    ];

    const getActiveRateLinks = (type) => {
      if (type === MOBILE_TYPE) return mobileLinks;
      if (type === DESKTOP_TYPE) return desktopLinks;
      if (type === TSD_TYPE) return tsdLinks;
    };

    const getLeftPercent = (expiresAt) => {
      const leftDays = Math.round(getDifferenceDays(expiresAt) / (1000 * 3600 * 24));
      if (leftDays >= 365) return 100;
      return Math.floor((leftDays * 100) / 365);
    };

    const getRates = () => {
      store.dispatch("getSubscription");
    };

    const hasSubscription = computed(() => store.getters.hasSubscriptions);

    const getDifferenceDays = (expires_at) => {
      return new Date(expires_at).getTime() - new Date().getTime();
    };

    const showRateDetails = (id) => {
      emit("showRateDetails", id);
    };

    const doSomething = () => {
      emit("onClickChooseRate");
    };

    onBeforeMount(() => {
      getRates();
    });

    return {
      rates,
      hasSubscription,
      getActiveRateLinks,
      formatDate,
      getRates,
      doSomething,
      showRateDetails,
    };
  },
});
</script>
<style lang="scss">
.rate-main-page .card__body {
  padding: 0;
}
.rate-page__select {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  padding: 4rem 0;
}
.rate-page__title {
  margin-bottom: 0.5rem;
  font-size: 1rem;
  color: $dark;

  &_cursor {
    cursor: pointer;
  }
}
.rate-page__text {
  text-align: center;
  margin-bottom: 1rem;
  color: $secondary-color;
}
.rate-page__info {
  display: flex;
  align-items: center;
  padding-bottom: 1rem;
}

.rate-page__dates {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rate-page--expired {
  padding-bottom: 0;
}

.rate-page__item {
  color: $secondary-color;
  padding: 1.5rem;
  border-bottom: 1px solid $secondary-light-2;
}

.rate-page__item:last-child {
  border-bottom: none;
}

.rate-page__item-head {
  display: flex;
  justify-content: space-between;
}

//.rate-page__item--expired .rate-page__progress-value {
//  background-color: $danger;
//  width: 100% !important;
//}

.rate-page__icon {
  color: $primary;
  margin-right: 21px;

  &--expired {
    color: $secondary-color;
  }
}

//.rate-page__item--phone .rate-page__info::before {
//  content: "";
//  display: block;
//  width: 14px;
//  height: 20px;
//  background-image: url("../../../assets/images/icons/phone.svg");
//  margin-right: 21px;
//}
//
//.rate-page__item--pc .rate-page__info::before {
//  content: "";
//  display: block;
//  width: 22px;
//  height: 18px;
//  background-image: url("../../../assets/images/icons/pc.svg");
//  margin-right: 21px;
//}
//
//.rate-page__item--tsd .rate-page__info::before {
//  content: "";
//  display: block;
//  width: 18px;
//  height: 18px;
//  background-image: url("../../../assets/images/icons/tsd-mini.svg");
//  margin-right: 21px;
//}

.rate-page__current-text {
  padding-bottom: 1rem;
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 500;
}

.rate-page__progress-bar {
  background-color: #ebf0ff;
  border-radius: $border-radius;
  height: 1rem;
  margin-bottom: 0.5rem;
}

.rate-page__progress-value {
  background-color: $primary;
  border-radius: $border-radius;
  height: 1rem;
}
</style>
