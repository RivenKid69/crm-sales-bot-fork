<template>
  <BaseModal
    :title="hasSubscriptions ? 'Смена тарифа' : 'Тариф'"
    :subtitle="
      hasSubscriptions
        ? 'При смене тарифа, текущий перестанет работать. Если вы хотите его сохранить, рекомендуем приобрести тариф на новом акккаунте.'
        : 'После оплаты у вас активируется Wipon Pro на выбранном устройстве, и мы предоставим всю нужную информацию по использоваю.'
    "
  >
    <template v-slot:body>
      <div v-for="rate in ratesData" :key="rate.type" class="rate rate__list">
        <div class="rate__left">
          <span class="rate__icon">
            <img :src="rate.icon" alt="" />
          </span>
          <div class="rate__info">
            <div class="rate__name">{{ rate.name }}, {{ rate.duration }} год</div>
            <div class="rate__price">{{ Intl.NumberFormat("ru-RU", { style: "decimal" }).format(rate.price) }} тг</div>
          </div>
        </div>
        <base-button
          type="primary"
          filled
          class="rate__button"
          small
          :disabled="account.balance < rate.price"
          @click="onClickBuy(rate)"
        >
          Купить
        </base-button>
      </div>
    </template>
  </BaseModal>
</template>

<script lang="ts">
import { computed, defineComponent, ref, SetupContext, watch } from "vue";
import BaseModal from "@/components/base/BaseModal.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import { DESKTOP_PRICE, DESKTOP_TYPE, MOBILE_PRICE, MOBILE_TYPE, TSD_PRICE, TSD_TYPE } from "@/config/rates";
import { useStore } from "@/store";

export default defineComponent({
  name: "BuyRateModal",
  setup(props, { emit }: SetupContext) {
    const store = useStore();
    const account = computed(() => store.getters.accountGet);
    const selectedRateTypeId = computed(() => store.getters.getSelectedRateTypeId);
    const hasSubscriptions = computed(() => store.getters.hasSubscriptions);
    const ratesData = computed(() => store.getters.rateInfoData.filter((i) => i.type !== selectedRateTypeId.value));

    const onClickBuy = (rate: any) => {
      emit("click-rate");
      store.commit("setSelectedRateTypeId", rate.type);
    };

    return {
      onClickBuy,
      account,
      ratesData,
      hasSubscriptions,
    };
  },
  components: {
    BaseButton,
    BaseModal,
  },
});
</script>
