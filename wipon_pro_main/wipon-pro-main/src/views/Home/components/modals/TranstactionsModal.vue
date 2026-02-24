<template>
  <BaseModal title="История транзакций" subtitle="" class="trans-modal">
    <template v-slot:body>
      <tabs @tabChanged="changeTab">
        <tab v-for="(i, idx) in tabs" :key="idx" :title="i.title">
          <div v-if="trans.length" class="transactions__list">
            <div class="transactions__item" v-for="(item, ind) in trans" :key="ind">
              <div class="transaction__date">{{ dateFilter(item.created_at) }}</div>
              <div class="transactions__info">
                <div class="transactions__name">
                  {{ item.sum > 0 ? "Пополнение баланса" : item.provider }}
                </div>
                <div class="transactions__value" :class="{ 'transactions__value--positive': item.sum > 0 }">
                  {{ item.sum }} ₸
                </div>
              </div>
            </div>
          </div>
          <div v-else class="transactions__list">
            <div class="transactions__item">Отсутствуют операции</div>
          </div>
        </tab>
      </tabs>
    </template>
  </BaseModal>
</template>

<script lang="ts">
import { computed, defineComponent, onBeforeMount, ref, SetupContext } from "vue";
import BaseModal from "@/components/base/BaseModal.vue";
import { useStore } from "@/store";
import BaseTabs from "@/components/base/BaseTabs.vue";
import BaseTab from "@/components/base/BaseTab.vue";

export default defineComponent({
  name: "TransactionsModal",
  setup(props, { emit }: SetupContext) {
    const store = useStore();
    const tabs = ref([
      {
        title: "Все",
        type: 0,
      },
      {
        title: "Пополнения",
        type: 1,
      },
      {
        title: "Снятия",
        type: 2,
      },
    ]);
    const tabType = ref(0);
    const trans = computed(() => {
      return tabType.value
        ? store.getters.transGet.filter((item: any) => item.isType === tabType.value)
        : store.getters.transGet.map((el) => el);
    });

    const changeTab = (e: any) => {
      tabType.value = e;
    };

    const dateFilter = (date: string) => {
      return new Intl.DateTimeFormat("ru-RU", {
        year: "numeric",
        month: "long",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(date));
    };

    return {
      tabs,
      changeTab,
      trans,
      dateFilter,
    };
  },
  components: {
    BaseModal,
    tabs: BaseTabs,
    tab: BaseTab,
  },
});
</script>
<style lang="scss">
.trans-modal {
  .transactions__list {
    max-height: 300px;
    overflow: auto;
  }
  .transactions__item {
    padding: 1.5rem;
  }

  .transactions__info {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .transaction__date {
    font-weight: 400;
    color: #46586b;
    font-size: 14px;
  }
  .transactions__name {
    font-weight: 400;
    font-size: 16px;
    line-height: 22px;
    margin-top: 3px;
  }
  .transactions__value {
    color: $danger;
  }
  .transactions__value--positive {
    color: $success;
  }
}

@media (max-width: 585px) {
  .trans-modal {
    .transactions__item {
      padding: 1rem;
    }

    .transactions__info {
      gap: 10px;
    }
  }
}
</style>
