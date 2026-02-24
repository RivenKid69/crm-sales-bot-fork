<template>
  <BaseModal :show-header="false" @cancel="handleCancel">
    <template v-slot:body>
      <div class="rate-activated">
        <div class="rate-activated__body">
          <span class="rate-activated__img">
            <img :src="activatedInfo.icon_green" alt="" />
          </span>
          <h2 class="rate-activated__title">
            {{ activatedInfo.actived_info }}
          </h2>
          <ul class="rate-activated__list">
            <li v-for="(item, key) in activatedInfo.list" :key="key">
              {{ item }}
            </li>
          </ul>
        </div>
        <div class="rate-activated__bottom" :class="{ 'flex-column': activatedInfo.type === tsd_type }">
          <template v-if="activatedInfo.type === mobile_type">
            <base-button @click="redirect(activatedInfo.appStore_link)" class="rate__button" :block="true">
              <a :href="activatedInfo.appStore_link" class="rate__button--link">
                <span class="rate-button__icon rate-button__icon--app-store">
                  <img src="@/assets/images/icons/appStore.svg" alt="" />
                </span>
                App Store
              </a>
            </base-button>
            <base-button @click="redirect(activatedInfo.playMarket_link)" class="rate__button" :block="true">
              <a :href="activatedInfo.playMarket_link" class="rate__button--link">
                <span class="rate-button__icon rate-button__icon--play-market">
                  <img src="@/assets/images/icons/playMarket.svg" alt="" />
                </span>
                Google Play
              </a>
            </base-button>
          </template>
          <template v-else-if="activatedInfo.type === desktop_type">
            <base-button @click="redirect(activatedInfo.download_link)" class="rate__button" :block="true">
              <a :href="activatedInfo.download_link" class="rate__button--link">
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
          </template>
          <template v-else>
            <div class="rate-activated__tsd-button">
              <base-button-drop-down class="rate__button" :block="true" :links="activatedInfo.download_drop_down">
                <span class="rate-button__icon">
                  <img src="@/assets/images/icons/download.svg" alt="" />
                </span>
                Скачать APK
              </base-button-drop-down>
              <base-button
                @click="redirect(activatedInfo.playMarket_link)"
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
          </template>
        </div>
      </div>
    </template>
  </BaseModal>
</template>

<script>
import { computed, defineComponent, ref } from "vue";
import BaseModal from "@/components/base/BaseModal.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseButtonDropDown from "@/components/base/BaseButtonDropDown.vue";
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from "@/config/rates";
import { useStore } from "@/store";
import formatDataToSvgAndDownload from "@/utils/download-qr";

export default defineComponent({
  name: "ActivatedRateModal",
  setup(props, { emit }) {
    const store = useStore();
    const mobile_type = ref(MOBILE_TYPE);
    const desktop_type = ref(DESKTOP_TYPE);
    const tsd_type = ref(TSD_TYPE);
    const activatedInfo = computed(() => store.getters.getSelectedRate);
    const qrUrl = ref("");

    const downloadQr = async () => {
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
      location.href = url;
    };

    return {
      activatedInfo,
      mobile_type,
      desktop_type,
      tsd_type,
      downloadQr,
      qrUrl,
      handleCancel,
      redirect,
    };
  },
  components: {
    BaseButton,
    BaseModal,
    BaseButtonDropDown,
  },
});
</script>
