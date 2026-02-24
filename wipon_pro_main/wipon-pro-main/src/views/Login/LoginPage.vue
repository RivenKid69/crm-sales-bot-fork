<template>
  <div class="empty-layout">
    <form class="login-page" @submit.prevent="handleFormSubmit">
      <div class="login-page__content">
        <h2 class="login-page__title">Авторизация в Wipon Pro</h2>
        <p class="login-page__text">Введите номер телефона для входа</p>
        <base-input v-model="phone" label="Телефон" prefix="+7" v-mask="'(###) ###-##-##'" light autofocus />
        <base-button
          filled
          type="primary"
          html-type="submit"
          class="login-page__submit-button"
          :block="true"
          :disabled="!isPhoneValid"
        >
          Продолжить
        </base-button>
      </div>
      <base-loader v-if="loading" type="primary" size="large" />
    </form>
  </div>
</template>
<script lang="ts">
import { defineComponent, ref, computed } from "vue";
import { useStore } from "@/store";
import { useRouter } from "vue-router";
import BaseInput from "@/components/base/BaseInput.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseLoader from "@/components/base/BaseLoader.vue";
import { AxiosError } from "axios";
import { notify } from "@kyvg/vue3-notification";

export default defineComponent({
  name: "LoginPage",
  components: {
    "base-input": BaseInput,
    "base-button": BaseButton,
    "base-loader": BaseLoader,
  },
  setup() {
    const store = useStore();
    const router = useRouter();
    const loading = ref(false);
    const phone = ref("");

    const isPhoneValid = computed(() => phone.value.length === 15);

    const startLoading = () => {
      loading.value = true;
    };

    const navigateToVerificationCodePage = () => {
      router.push({ name: "auth.verification" });
    };

    const finishLoading = () => {
      loading.value = false;
    };

    const handleErrorInLogin = (e: AxiosError) => {
      const error = e.response?.data?.message;
      if (error && error.status === "pending") {
        notify({
          text: `Повторная отправка смс-кода возможна только через ${error.resend_cooldown} секунд`,
          type: "error",
          ignoreDuplicates: true,
          duration: 5000,
        });
      }
    };

    const clearMaskedPhoneNumber = () => {
      return phone.value.replaceAll(/[() -]/g, "");
    };

    const handleFormSubmit = () => {
      const clearedPhone = clearMaskedPhoneNumber();
      const phoneWithPrefix = `+7${clearedPhone}`;
      if (!isPhoneValid.value) return;
      startLoading();
      store
        .dispatch("sendVerificationCode", phoneWithPrefix)
        .then(navigateToVerificationCodePage)
        .catch(handleErrorInLogin)
        .finally(finishLoading);
    };

    return {
      handleFormSubmit,
      phone,
      loading,
      isPhoneValid,
    };
  },
});
</script>

<style lang="scss">
.login-page {
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100vh;

  &__content {
    width: $auth-form-wd;
    background-color: #fff;
    border-radius: $border-radius;
    padding: $auth-form-inner-padding;
  }

  &__title {
    font-size: 1.125rem;
    font-weight: 500;
    margin-bottom: 8px;
  }

  &__text {
    color: $secondary-color;
    margin-bottom: 30px;
  }
}

@media (max-width: 575.98px) {
  .login-page {
    &__content {
      width: 90%;
      padding: 1rem;
    }
  }
}
</style>
