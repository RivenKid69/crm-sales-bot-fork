<template>
  <div class="overlay profile-overlay" @click="hideModal">
    <div class="modal-card profile-modal">
      <div class="store-page__forms">
        <div class="store-page__forms-header">
          <h2 class="store-page__forms-title">Профиль</h2>
        </div>
        <div class="store-page__forms-body">
          <h2 class="store-page__forms-subtitle">Данные о лицензии</h2>
          <div class="profile-info">
            <div class="profile-info__left">
              <div class="profile-info__item">
                <div class="profile-info__item-label">Телефон</div>
                <div class="profile-info__item-value">{{ profileInfo.phoneNumber }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">БИН/ИИН Лицензиата</div>
                <div class="profile-info__item-value">{{ profileInfo.licenserBin }}</div>
              </div>
            </div>
            <div class="profile-info__right">
              <div class="profile-info__item">
                <div class="profile-info__item-label">Номер лицензии</div>
                <div class="profile-info__item-value">{{ profileInfo.licenseNumber }}</div>
              </div>
              <div v-if="profileInfo.payerEmail" class="profile-info__item">
                <div class="profile-info__item-label">Почта</div>
                <div class="profile-info__item-value">{{ profileInfo.payerEmail }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="store-page__forms-body">
          <h2 class="store-page__forms-subtitle">Реквизиты для счет фактур и актов</h2>
          <div class="profile-info">
            <div class="profile-info__left">
              <div class="profile-info__item">
                <div class="profile-info__item-label">Название организации</div>
                <div class="profile-info__item-value">{{ profileInfo.companyName }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">Адрес объекта деятельности</div>
                <div class="profile-info__item-value">{{ profileInfo.businessStoreAddress }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">Название объекта деятельности</div>
                <div class="profile-info__item-value">{{ profileInfo.businessStoreName }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">Название лицензиата</div>
                <div class="profile-info__item-value">{{ profileInfo.licenserName }}</div>
              </div>
            </div>
            <div class="profile-info__right">
              <div class="profile-info__item">
                <div class="profile-info__item-label">БИН/ИИН</div>
                <div class="profile-info__item-value">{{ profileInfo.bin }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">Юридический адрес</div>
                <div class="profile-info__item-value">{{ profileInfo.payerAddress }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">Почтовый адрес</div>
                <div class="profile-info__item-value">{{ profileInfo.postalAddress }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="store-page__forms-body">
          <h2 class="store-page__forms-subtitle">Прочие данные</h2>
          <div class="profile-info">
            <div class="profile-info__left">
              <div class="profile-info__item">
                <div class="profile-info__item-label">Вид реализации</div>
                <div class="profile-info__item-value">{{ profileInfo.businessStoreType.name_ru }}</div>
              </div>
              <div class="profile-info__item">
                <div class="profile-info__item-label">Лицензиар (ДГД)</div>
                <div class="profile-info__item-value">{{ profileInfo.businessDgd.name_ru }}</div>
              </div>
            </div>
            <div class="profile-info__right">
              <div class="profile-info__item">
                <div class="profile-info__item-label">УГД</div>
                <div class="profile-info__item-value">{{ profileInfo.businessUgd.name_ru }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { computed, defineComponent, ref } from "vue";
import { useStore } from "@/store";

export default defineComponent({
  name: "ProfileModal",
  setup(props, { emit }) {
    const store = useStore();
    const hideModal = (e) => {
      const target = e.target;
      if (target && target.className.includes("overlay")) {
        return emit("cancel");
      }
    };

    const profileInfo = computed(() => store.getters.company);

    return {
      profileInfo,
      hideModal,
    };
  },
});
</script>

<style lang="scss">
.profile {
  &-info {
    display: flex;
    justify-content: space-between;
    gap: 20px;

    &__item {
      margin-bottom: 16px;

      &-label {
        color: $secondary-light-1;
        margin-bottom: 8px;
      }

      &-value {
        color: $dark;
      }
    }
  }

  &-modal {
    top: 40% !important;
    position: absolute !important;
  }

  &-overlay {
    min-height: 1200px !important;
  }
}

@media (max-width: 500px) {
  .profile {
    &-modal {
      top: 45% !important;
    }
  }
}
</style>
