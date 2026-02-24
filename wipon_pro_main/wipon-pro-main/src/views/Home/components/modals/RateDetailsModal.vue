<template>
  <BaseModal
    :title="rateDetails.name"
    :subtitle="`${rateDetails.price} ₸`"
    :showFooter="rateDetails.is_active"
    :show-rate-details="true"
    :rateType="rateDetails.type"
    :is-rate-active="rateDetails.is_active"
    classname="modal-card--rate-activate"
    :loading="isLoading"
    @cancel="handleCancel"
  >
    <template v-slot:body>
      <div class="rate-activate">
        <div class="rate-activate__body">
          <div class="rate-activate__left">
            <div class="rate-activate__title">Активирован</div>
            <div class="rate-activate__info">
              <div class="rate-activate__name">{{ formatDate(rateDetails.activated_at) }}</div>
            </div>
          </div>
          <div class="rate-activate__right">
            <div class="rate-activate__title">{{ rateDetails.is_active ? "Истекает" : "Истёк" }}</div>
            <div class="rate-activate__start-date">{{ formatDate(rateDetails.expires_at) }}</div>
          </div>
        </div>
      </div>
    </template>
    <template v-slot:footer>
      <div v-if="rateDetails.is_active" class="rate-details__footer">
        <template v-if="rateInfo.type === mobileType">
          <ul class="rate-activated__list">
            <li v-for="(item, key) in rateInfo.list" :key="key">
              {{ item }}
            </li>
          </ul>
          <div class="rate-activated__bottom">
            <base-button @click="redirect(rateInfo.appStore_link)" class="rate__button" :block="true">
              <a :href="rateInfo.appStore_link" class="rate__button--link">
                <span class="rate-button__icon rate-button__icon--app-store">
                  <img src="@/assets/images/icons/appStore.svg" alt="" />
                </span>
                App Store
              </a>
            </base-button>
            <base-button @click="redirect(rateInfo.playMarket_link)" class="rate__button" :block="true">
              <a :href="rateInfo.playMarket_link" class="rate__button--link">
                <span class="rate-button__icon rate-button__icon--play-market">
                  <img src="@/assets/images/icons/playMarket.svg" alt="" />
                </span>
                Google Play
              </a>
            </base-button>
          </div>
        </template>
        <template v-else-if="rateInfo.type === desktopType">
          <ul class="rate-activated__list">
            <li v-for="(item, key) in rateInfo.list" :key="key">
              {{ item }}
            </li>
          </ul>
          <div class="rate-activated__bottom">
            <base-button @click="redirect(rateInfo.download_link)" class="rate__button" :block="true">
              <a :href="rateInfo.download_link" class="rate__button--link">
                <span class="rate-button__icon">
                  <img src="@/assets/images/icons/download.svg" alt="" />
                </span>
                Скачать приложение
              </a>
            </base-button>
            <base-button @click="downloadQr" class="rate__button" :block="true">
              <span class="rate-button__icon">
                <img src="@/assets/images/icons/qr-code.svg" alt="" />
              </span>
              Скачать QR-код
            </base-button>
          </div>
        </template>
        <template v-else>
          <ul class="rate-activated__list">
            <li v-for="(item, key) in rateInfo.list" :key="key">
              {{ item }}
            </li>
          </ul>
          <div class="rate-activated__bottom flex-column">
            <div class="rate-activated__tsd-button">
              <base-button-drop-down class="rate__button" :block="true" :links="rateInfo.download_drop_down">
                <span class="rate-button__icon">
                  <img src="@/assets/images/icons/download.svg" alt="" />
                </span>
                Скачать APK
              </base-button-drop-down>
              <base-button
                @click="redirect(rateInfo.playMarket_link)"
                class="rate__button rate-activated__tsd-button_right"
                :block="true"
              >
                <span class="rate-button__icon rate-button__icon--play-market">
                  <img src="@/assets/images/icons/playMarket.svg" alt="" />
                </span>
                Google Play
              </base-button>
            </div>
            <base-button @click="downloadQr" class="rate__button" :block="true">
              <span class="rate-button__icon">
                <img src="@/assets/images/icons/qr-code.svg" alt="" />
              </span>
              Скачать QR-код
            </base-button>
          </div>
        </template>
        <div v-if="!isTwoWeeksPassedFromPurchase" class="rate-details__refund-wrapper">
          <div class="divider"></div>
          <div class="rate-details__refund">
            <span class="rate-details__refund-text">
              У вас есть <span style="font-weight: bold">14 дней</span>, чтобы произвести возврат. По окончанию срока,
              такой возможности не будет
            </span>
            <base-button @click="makeRefundRequest" class="rate-details__refund-button" small>Возврат</base-button>
          </div>
        </div>
      </div>
    </template>
  </BaseModal>
</template>

<script>
import { computed, defineComponent, nextTick, ref } from "vue";
import BaseModal from "@/components/base/BaseModal.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseButtonDropDown from "@/components/base/BaseButtonDropDown.vue";
import { useStore } from "@/store";
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from "@/config/rates";
import formatDataToSvgAndDownload from "@/utils/download-qr";
import { makeRefund } from "@/api/subscriptions.api";
import { notify } from "@kyvg/vue3-notification";
import { sleep } from "@/utils/helpers";

export default defineComponent({
  name: "RateDetailsModal",
  props: {
    rateCustomId: {
      type: String,
      required: true,
    },
  },
  setup(props, { emit }) {
    const store = useStore();
    const mobileType = ref(MOBILE_TYPE);
    const desktopType = ref(DESKTOP_TYPE);
    const tsdType = ref(TSD_TYPE);
    const isLoading = ref(false);
    const formatDate = (date = Date.now()) => {
      return new Intl.DateTimeFormat("ru-RU", {
        year: "numeric",
        month: "long",
        day: "2-digit",
      }).format(new Date(date));
    };

    const rateInfo = computed(() => store.getters.rateInfoData.find((rate) => rate.type === rateDetails.value.type));
    const rateDetails = computed(() => store.getters.subscriptions.find((sub) => sub.custom_id === props.rateCustomId));
    const isTwoWeeksPassedFromPurchase = computed(() => {
      if (rateDetails.value && rateDetails.value.is_active) {
        const ONE_DAY_IN_MS = 86400000;
        const twoWeeksAgo = new Date(Date.now() - ONE_DAY_IN_MS * 14);
        const createdAt =
          rateDetails.value.type === MOBILE_TYPE
            ? new Date(rateDetails.value.created_at)
            : new Date(rateDetails.value.updated_at);
        return createdAt.valueOf() < twoWeeksAgo.valueOf();
      }
      return false;
    });

    const makeRefundRequest = async () => {
      try {
        isLoading.value = true;
        await makeRefund({
          type: rateDetails.value.type,
          id: rateDetails.value.id,
        });
        await sleep(1000);
        notify({
          text: "Возврат был успешно оформлен на ваш тариф",
          type: "success",
        });
        await store.dispatch("getTransactions");
        await store.dispatch("getAccount");
        handleCancel();
        await store.dispatch("getSubscription");
      } finally {
        isLoading.value = false;
      }
    };

    const downloadQr = () => {
      if (store.getters.hasSubscriptions) {
        const activeRate = store.getters.subscriptions.find((sub) => sub.is_active);
        if (activeRate && activeRate.type !== MOBILE_TYPE) {
          formatDataToSvgAndDownload(activeRate.device_code);
        }
      }
    };

    const handleCancel = () => {
      emit("cancel");
    };

    const redirect = (url) => {
      const link = document.querySelector(".invisible-link");
      link.setAttribute("href", url);
      link.click();
    };

    return {
      isLoading,
      mobileType,
      desktopType,
      tsdType,
      rateDetails,
      formatDate,
      rateInfo,
      handleCancel,
      downloadQr,
      redirect,
      makeRefundRequest,
      isTwoWeeksPassedFromPurchase,
    };
  },
  components: {
    BaseButton,
    BaseModal,
    BaseButtonDropDown,
  },
});
</script>
