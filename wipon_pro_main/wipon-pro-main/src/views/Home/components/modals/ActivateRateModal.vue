<template>
  <BaseModal
    title="Активация тарифа"
    :subtitle="subtitle"
    :showFooter="true"
    classname="modal-card--rate-activate"
    :loading="loading"
    @cancel="handleCancel"
  >
    <template v-slot:body>
      <div class="rate-activate">
        <div class="rate-activate__body">
          <div class="rate-activate__left">
            <div class="rate-activate__title">Тариф</div>
            <div class="rate-activate__info">
              <img :src="activatedInfo.icon" class="rate-activate__icon" alt="" />
              <div class="rate-activate__name">{{ activatedInfo.name }}, {{ activatedInfo.duration }} год</div>
            </div>
          </div>
          <div class="rate-activate__right">
            <div class="rate-activate__title">Дата активации</div>
            <div class="rate-activate__start-date">
              {{ formatted }}
            </div>
          </div>
        </div>
      </div>
    </template>
    <template v-slot:footer>
      <div class="rate-activate__bottom">
        <base-button type="primary" class="rate__button" :block="true" @click="handleCancel"> Отменить </base-button>
        <base-button type="primary" filled class="rate__button" :block="true" @click="handleSubmit">
          Активировать
        </base-button>
      </div>
    </template>
  </BaseModal>
</template>

<script lang="ts">
import { computed, defineComponent, nextTick, onMounted, ref } from "vue";
import BaseModal from "@/components/base/BaseModal.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import { useStore } from "@/store";

export default defineComponent({
  name: "ActivateRateModal",
  setup(props, { emit }) {
    const store = useStore();
    const activatedInfo = computed(() => store.getters.getSelectedRate);
    const loading = ref(false);
    const subtitle = computed(() => `С вашего баланса спишется ${activatedInfo.value.price} ₸`);
    const date = ref(new Date());
    const options = {
      year: "numeric",
      month: "long",
      day: "numeric",
    };
    const formatted = date.value.toLocaleDateString("ru-RU", options);
    const hasActiveSubscription = computed(() => store.getters.hasSubscriptions);
    const activeSubscription = computed(() => {
      return store.getters.subscriptions.find((sub) => sub.is_active);
    });

    const handleSubmit = () => {
      loading.value = true;
      store
        .dispatch("buySubscription", activatedInfo.value.type)
        .then(async () => {
          await store.dispatch("getSubscription");
          await store.dispatch("getTransactions");
          await store.dispatch("getAccount");
          await nextTick(() => {
            emit("click-activate");
          });
        })
        .finally(() => {
          loading.value = false;
        });
    };

    const handleCancel = () => {
      if (!hasActiveSubscription.value) {
        store.commit("setSelectedRateTypeId", null);
      }
      if (hasActiveSubscription.value && activeSubscription.value) {
        store.commit("setSelectedRateTypeId", activeSubscription.value.type);
      }
      emit("cancel");
    };

    return {
      subtitle,
      formatted,
      activatedInfo,
      handleSubmit,
      handleCancel,
      loading,
    };
  },
  components: {
    BaseButton,
    BaseModal,
  },
});
</script>
