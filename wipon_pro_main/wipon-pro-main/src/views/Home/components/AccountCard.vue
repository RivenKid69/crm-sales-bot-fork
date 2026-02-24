<template>
  <Card title="Аккаунт">
    <div class="account-page">
      <div class="account-page__top">
        <div class="account-page__balance">
          <p class="account-page__title">Баланс</p>
          <span class="account-page__value">{{ account.balance ? formatMoney(account.balance) : 0 }} тг</span>
        </div>
        <a class="account-page__transactions-link" @click="onclickTrans">Транзакции</a>
      </div>
      <div class="account-page__license-number">
        <p class="account-page__title">лицевой счёт</p>
        <span class="account-page__value">{{ account.number ? account.number : "..." }}</span>
      </div>
      <base-button @click="showPaymentModal" block small>Пополнить баланс</base-button>
      <!--      <div class="account-page__bottom">-->
      <!--        <img class="account-page__icon" src="@/assets/images/icons/builder.svg" alt="" />-->
      <!--        Чтобы пополнить баланс, совершите перевод на лицевой счёт-->
      <!--      </div>-->
    </div>
  </Card>
</template>

<script lang="ts">
import Card from "@/components/Card.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import { computed, defineComponent, onBeforeMount, ref } from "vue";
import { useStore } from "@/store";

export default defineComponent({
  name: "AccountCard",
  components: {
    Card,
    BaseButton,
  },
  setup(props, { emit }) {
    const store = useStore();
    const formatMoney = (price: number) => {
      return Intl.NumberFormat("ru-RU", { style: "decimal" }).format(price);
    };
    const account = computed(() => store.getters.accountGet);

    const getTrans = () => store.dispatch("getTransactions");
    const getAccount = () => {
      store.dispatch("getAccount");
    };

    const showPaymentModal = () => {
      emit("showPaymentModal");
    };

    const onclickTrans = () => {
      emit("click-trans");
    };

    onBeforeMount(() => {
      getAccount();
      getTrans();
    });

    return {
      account,
      onclickTrans,
      formatMoney,
      showPaymentModal,
    };
  },
});
</script>

<style lang="scss">
.account-page {
  &__top {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }
  &__balance {
    display: flex;
    flex-direction: column;
  }
  &__title {
    margin-bottom: 0.5rem;
    font-size: 0.75rem;
    text-transform: uppercase;
  }
  &__value {
    font-size: 1rem;
  }
  &__transactions-link {
    color: $primary;
    cursor: pointer;
  }
  &__license-number {
    margin-bottom: 1.5rem;
  }

  &__bottom {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 14px;
    font-weight: 400;
    color: $secondary-color;
  }

  &__icon {
    margin-right: 10px;
  }
}
</style>
