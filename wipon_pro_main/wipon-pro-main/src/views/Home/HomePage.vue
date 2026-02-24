<template>
  <section class="section main">
    <div v-if="usersCompany.companyName" class="main__title">
      {{ usersCompany.companyName ? usersCompany.companyName : "Название компании" }}
    </div>
    <div class="main-cards">
      <div class="main-cards__first">
        <AccountCard @click-trans="onClickTrans" @showPaymentModal="showPaymentModal = true" />
      </div>
      <div class="main-cards__second">
        <RatesCard @onClickChooseRate="onChooseRate" @showRateDetails="showRateDetails" />
      </div>
    </div>
  </section>
  <BuyRateModal v-if="buyRatesModal" @click-rate="onClickRate" @cancel="buyRatesModal = false" />
  <ActivateRateModal v-if="activeRatesModal" @click-activate="onActivateClick" @cancel="activeRatesModal = false" />
  <ActivatedRateModal v-if="activedRatesModal" @cancel="activedRatesModal = false" />
  <TransactionsModal v-if="transactionsModal" @cancel="transactionsModal = false" />
  <RateDetailsModal
    v-if="showRateDetailsModal"
    :rateCustomId="selectedRateCustomId"
    @cancel="showRateDetailsModal = false"
  />
  <PaymentModal v-if="showPaymentModal" @hideModal="showPaymentModal = false" />
</template>

<script>
import AccountCard from "@/views/Home/components/AccountCard.vue";
import RatesCard from "@/views/Home/components/RatesCard.vue";
import BuyRateModal from "@/views/Home/components/modals/BuyRateModal.vue";
import { computed, defineComponent, nextTick, onBeforeMount, onMounted, ref } from "vue";
import ActivateRateModal from "@/views/Home/components/modals/ActivateRateModal.vue";
import { useStore } from "@/store";
import ActivatedRateModal from "./components/modals/ActivatedRateModal.vue";
import TransactionsModal from "@/views/Home/components/modals/TranstactionsModal.vue";
import RateDetailsModal from "@/views/Home/components/modals/RateDetailsModal.vue";
import PaymentModal from "@/views/Home/components/modals/PaymentModal";
import { useRoute, useRouter } from "vue-router";

export default defineComponent({
  name: "HomePage",
  components: {
    TransactionsModal,
    AccountCard,
    RatesCard,
    BuyRateModal,
    ActivateRateModal,
    ActivatedRateModal,
    RateDetailsModal,
    PaymentModal,
  },
  setup() {
    const store = useStore();
    const route = useRoute();
    const router = useRouter();
    const activeRatesModal = ref(false);
    const activedRatesModal = ref(false);
    const transactionsModal = ref(false);
    const showRateDetailsModal = ref(false);
    const showPaymentModal = ref(false);
    const selectedRateCustomId = ref("");
    const buyRatesModal = ref(false);
    const selectedDevice = computed(() => store.getters.getSelectedRate);
    const usersCompany = computed(() => store.getters.company);
    const user = computed(() => store.getters.getUser);

    const onChooseRate = () => {
      buyRatesModal.value = true;
    };

    const onClickRate = () => {
      buyRatesModal.value = false;
      activeRatesModal.value = true;
    };

    const onClickTrans = () => {
      transactionsModal.value = true;
    };

    const showRateDetails = (id) => {
      showRateDetailsModal.value = true;
      selectedRateCustomId.value = id;
    };

    const onActivateClick = async () => {
      activeRatesModal.value = false;
      await nextTick(() => {
        activedRatesModal.value = true;
      });
    };

    onBeforeMount(async () => {
      if (!usersCompany.value.licenserBin) {
        await store.dispatch("getCompany");
      }
      if (!user.value.id) {
        await store.dispatch("getUser");
      }
    });

    onMounted(() => {
      if (route.query.activateMobile) {
        router.replace({ name: "main.home" });
        buyRatesModal.value = true;
      }
    });

    return {
      buyRatesModal,
      activeRatesModal,
      selectedDevice,
      activedRatesModal,
      showRateDetailsModal,
      showPaymentModal,
      selectedRateCustomId,
      onChooseRate,
      onClickRate,
      onActivateClick,
      onClickTrans,
      showRateDetails,
      transactionsModal,
      usersCompany,
    };
  },
});
</script>

<style lang="scss">
.main {
  &__title {
    font-weight: 500;
    font-size: 32px;
    margin-bottom: 24px;
  }

  &-cards {
    display: flex;

    &__first {
      width: 320px;
      margin-right: 20px;
    }

    &__second {
      flex: 1 1 auto;
    }
  }
}

@media (max-width: 778.98px) {
  .main {
    &__title {
      font-size: 24px;
    }

    &-cards {
      flex-direction: column;

      &__first {
        width: 100%;
        margin-right: 0;
        margin-bottom: 24px;
      }
    }
  }
}
</style>
