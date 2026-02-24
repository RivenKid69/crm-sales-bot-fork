<template>
  <div class="overlay" @click="hideModal">
    <div class="modal-card" v-bind:class="classname">
      <template v-if="showHeader">
        <div v-if="showRateDetails" class="modal-card__head modal-card__head_flex">
          <div class="modal-card__head-icon">
            <PhoneIcon v-if="rateType === mobileType" large />
            <PcIcon v-if="rateType === desktopType" large />
            <TsdIcon v-if="rateType === tsdType" large />
          </div>
          <div class="modal-card__titles">
            <div class="modal-card__title">
              {{ title }}
            </div>
            <div class="modal-card__subtitle">{{ subtitle }}</div>
          </div>
          <div class="modal-card__head-status-wrapper">
            <span class="modal-card__head-status" :class="{ 'modal-card__head-status_expired': !isRateActive }">
              {{ isRateActive ? "Активен" : "Истёк" }}
            </span>
          </div>
        </div>
        <div v-else class="modal-card__head">
          <div class="modal-card__title">
            {{ title }}
          </div>
          <div class="modal-card__subtitle">{{ subtitle }}</div>
        </div>
        <div class="divider"></div>
      </template>

      <div class="modal-card__body">
        <slot name="body"></slot>
      </div>
      <template v-if="showFooter">
        <div class="divider"></div>
        <div class="modal-card__footer">
          <slot name="footer"></slot>
        </div>
      </template>
      <base-loader v-if="loading" type="primary" size="large" :modal-loader="true" />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from "vue";
import BaseLoader from "@/components/base/BaseLoader.vue";
import PhoneIcon from "@/components/icons/PhoneIcon.vue";
import PcIcon from "@/components/icons/PcIcon.vue";
import TsdIcon from "@/components/icons/TsdIcon.vue";
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from "@/config/rates";

export default defineComponent({
  name: "BaseModal",
  components: { BaseLoader, PhoneIcon, PcIcon, TsdIcon },
  props: {
    title: {
      type: String,
      default: "Заголовок",
    },
    classname: {
      type: String,
      default: "",
    },
    subtitle: {
      type: String,
      default: "Подзаголовок",
    },
    showFooter: {
      type: Boolean,
      required: false,
      default: false,
    },
    showHeader: {
      type: Boolean,
      required: false,
      default: true,
    },
    showRateDetails: {
      type: Boolean,
      required: false,
      default: false,
    },
    rateType: {
      type: Number,
      required: false,
      default: 0,
    },
    isRateActive: {
      type: Boolean,
      required: false,
      default: false,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  setup(props, { emit }) {
    const mobileType = ref(MOBILE_TYPE);
    const desktopType = ref(DESKTOP_TYPE);
    const tsdType = ref(TSD_TYPE);

    const hideModal = (e: any) => {
      const target: HTMLElement = e.target;
      if (target && target.className.includes("overlay")) {
        return emit("cancel");
      }
    };

    return {
      mobileType,
      desktopType,
      tsdType,
      hideModal,
    };
  },
});
</script>
