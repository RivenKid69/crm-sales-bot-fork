<template>
  <div class="empty-layout">
    <form class="verification-page" @submit.prevent="handleFormSubmit">
      <div class="verification-page__content">
        <div class="verification-page__back">
          <base-back-link @click="handleBackButtonClick" />
        </div>
        <h2 class="verification-page__title">СМС подтверждение</h2>
        <p class="verification-page__text">Вам был отправлен 6-значный СМС-код, введите его ниже</p>
        <base-input-code
          :fields="6"
          label="смс-код"
          @change="verificationCode = $event"
          @complete="completed = true"
        ></base-input-code>
        <base-button
          filled
          type="primary"
          html-type="submit"
          class="verification-page__submit-button"
          :disabled="!completed"
          :block="true"
        >
          Продолжить
        </base-button>
        <base-button
          html-type="button"
          class="verification-page__submit-button"
          :block="true"
          @click="resendVerificationCode"
          :disabled="!canResendVerificationCode"
        >
          Не пришло СМС?
          <span v-show="!canResendVerificationCode"> ({{ leftTimerSecs }}) </span>
        </base-button>
      </div>
      <base-loader v-if="loading" type="primary" size="large" />
    </form>
  </div>
</template>
<script>
import BaseButton from "@/components/base/BaseButton.vue";
import BaseInputCode from "@/components/base/BaseInputCode.vue";
import { computed, defineComponent, onBeforeMount, onMounted, ref } from "vue";
import { useStore } from "@/store";
import { useRouter } from "vue-router";
import BaseLoader from "@/components/base/BaseLoader";
import BaseBackLink from "@/components/base/BaseBackLink";
// import { notify } from "@kyvg/vue3-notification";

export default defineComponent({
  name: "VerificationCode",
  components: {
    BaseInputCode,
    BaseButton,
    BaseLoader,
    BaseBackLink,
  },
  setup() {
    const store = useStore();
    const router = useRouter();
    const completed = ref(false);
    const verificationCode = ref("");
    const leftTimerSecs = ref(60);
    const loading = ref(false);
    const phone = computed(() => store.getters.phoneGet);
    const hasStore = computed(() => store.getters.hasStore);
    const canResendVerificationCode = computed(() => leftTimerSecs.value === 0);

    const handleBackButtonClick = () => {
      router.push({ name: "auth.login" });
    };

    const navigateToPhoneNumberPage = () => {
      router.push({ name: "auth.login" });
    };

    const handleGetAuthTokenRequestError = () => {
      return null;
    };

    const navigateToCabinetPage = () => {
      router.push({ name: "main.home" });
    };

    const startTimerToResendVerificationCode = () => {
      const intervalId = setInterval(() => {
        if (leftTimerSecs.value === 1) clearInterval(intervalId);
        leftTimerSecs.value--;
      }, 1000);
    };

    const resendVerificationCode = () => {
      loading.value = true;
      store
        .dispatch("sendVerificationCode", phone.value)
        .then(() => {
          leftTimerSecs.value = 60;
          startTimerToResendVerificationCode();
        })
        .finally(() => {
          loading.value = false;
        });
    };

    const handleFormSubmit = () => {
      if (verificationCode.value.length !== 6) return;
      loading.value = true;
      store
        .dispatch("getAuthToken", verificationCode.value)
        .then(async () => {
          await store.dispatch("getCompany");
          if (hasStore.value) {
            navigateToCabinetPage();
          }
          // else {
          //   navigateToCabinetPage();
          // }
        })
        .catch(handleGetAuthTokenRequestError)
        .finally(() => (loading.value = false));
    };

    onBeforeMount(() => {
      if (!phone.value) {
        navigateToPhoneNumberPage();
      }
      if (store.getters.authTokenGet) {
        navigateToCabinetPage();
      }
    });

    onMounted(() => {
      startTimerToResendVerificationCode();
    });

    return {
      completed,
      verificationCode,
      handleFormSubmit,
      navigateToCabinetPage,
      loading,
      handleBackButtonClick,
      leftTimerSecs,
      canResendVerificationCode,
      resendVerificationCode,
    };
  },
});
</script>

<style lang="scss">
.verification-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100vh;

  &__back {
    position: absolute;
    top: -40px;
    left: 0;
  }
}
.verification-page__content {
  position: relative;
  width: $auth-form-wd;
  background-color: #fff;
  border-radius: $border-radius;
  padding: $auth-form-inner-padding;
}
.verification-page__title {
  font-size: 1.125rem;
  font-weight: 500;
  padding-bottom: 1rem;
}

.verification-page__text {
  color: $secondary-color;
  padding-bottom: 2rem;
}

.verification-page__link {
  color: $primary-light-1;
  text-decoration: none;
}
.verification-page__submit-button {
  margin-bottom: 12px;
}

@media (max-width: 575.98px) {
  .verification-page {
    &__content {
      width: 90%;
      padding: 1rem;
    }
  }
}
</style>
