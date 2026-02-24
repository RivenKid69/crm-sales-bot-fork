<template>
  <section class="store-page">
    <div class="store-page__wrapper">
      <div class="col-4 store-page__info">
        <base-back-link @click="handleBackButtonClick" />
        <h2 class="store-page__title">Общие понятия и требования к заполнению полей</h2>
        <p class="store-page__text">
          Внимательно заполните все поля. После прохождения регистрации редактирование данных будет невозможно.
        </p>
        <p class="store-page__text">
          Пользователь самостояльно несет ответственность за корректность введенных данных. ТОО «Вайпоинг» не несет
          ответственности за регистрацию пользователя в мобильном приложении.
        </p>
        <p class="store-page__text">
          Указание ложных данных влечет за собой ответственность по Статье 274 Уголовного Кодекса РК
        </p>
        <base-checkbox v-model="checkbox">Ознакомлен и согласен</base-checkbox>
      </div>
      <form class="col-7 store-page__forms" @submit.prevent="handleFormSubmit">
        <div class="store-page__forms-header">
          <h2 class="store-page__forms-title">Регистрация</h2>
        </div>
        <div class="store-page__forms-body">
          <h2 class="store-page__forms-subtitle">Данные о лицензии</h2>
          <div class="store-page__forms-inputs d-flex">
            <div class="store-page__forms-left">
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.businessFullLegalName"
                  name="buisness_full_legal_name"
                  label="название лицензиата*"
                  :errors="errors"
                  @input="clearError('buisness_full_legal_name')"
                  light
                  autofocus
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.licenseNumber"
                  :errors="errors"
                  name="license_number"
                  @input="clearError('license_number')"
                  input-type="text"
                  v-mask="'#*'"
                  label="номер лицензии*"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.businessBin"
                  :errors="errors"
                  @input="clearError('buisness_bin')"
                  label="бин/иин лицензиата*"
                  v-mask="'### ### ### ###'"
                  name="buisness_bin"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.storeName"
                  :errors="errors"
                  name="buisness_store_name"
                  @input="clearError('buisness_store_name')"
                  label="название объекта деятельности*"
                  light
                />
              </div>
            </div>
            <div class="store-page__forms-right">
              <div class="store-page__forms-input">
                <base-select
                  v-model="storeForm.storeTypeId"
                  :errors="errors"
                  label="Вид реализации*"
                  :options="storeTypeOptions"
                  name="buisness_store_type_id"
                  @change="clearError('buisness_store_type_id')"
                  optionName="name_ru"
                  :default="'Выберите вид реализации'"
                  class="select"
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.storeAddress"
                  :errors="errors"
                  @input="clearError('buisness_store_address')"
                  name="buisness_store_address"
                  label="адрес объекта деятельности*"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-select
                  v-model="storeForm.dgdId"
                  :errors="errors"
                  label="дгд (лицензиар)*"
                  :options="dgdOptions"
                  @change="clearError('buisness_dgd_id')"
                  name="buisness_dgd_id"
                  optionName="name_ru"
                  :default="'Выберите ДГД (Лицензиар)'"
                  class="select"
                />
              </div>
              <div>
                <base-select
                  v-model="storeForm.ugdId"
                  :errors="errors"
                  label="угд*"
                  :options="ugdsToSelectedDgd"
                  :disabled="!chosenDgdId"
                  @change="clearError('buisness_ugd_id')"
                  optionName="name_ru"
                  name="buisness_ugd_id"
                  :default="'Выберите УГД'"
                  class="select"
                />
              </div>
            </div>
          </div>
          <h2 class="store-page__forms-subtitle store-page__forms-subtitle--second">
            Реквизиты для счет фактур и актов
          </h2>
          <div class="store-page__forms-inputs d-flex">
            <div class="store-page__forms-left">
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.payerName"
                  :errors="errors"
                  label="название организации*"
                  name="payer_name"
                  @input="clearError('payer_name')"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.businessAddress"
                  :errors="errors"
                  label="юридический адрес*"
                  @input="clearError('payer_address')"
                  name="payer_address"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.businessPostalAddress"
                  :errors="errors"
                  label="почтовый адрес для документов*"
                  @input="clearError('payer_postal_address')"
                  name="payer_postal_address"
                  light
                />
              </div>
            </div>
            <div class="store-page__forms-right">
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.payerBin"
                  :errors="errors"
                  name="payer_bin"
                  v-mask="'### ### ### ###'"
                  @input="clearError('payer_bin')"
                  label="бин/иин*"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.payerBinRepeat"
                  :errors="errors"
                  label="введите бин/иин еще раз*"
                  @input="clearError('payer_bin_repeat')"
                  v-mask="'### ### ### ###'"
                  name="payer_bin_repeat"
                  light
                />
              </div>
              <div class="store-page__forms-input">
                <base-input
                  v-model="storeForm.payerEmail"
                  :errors="errors"
                  label="электронная почта организации"
                  @input="clearError('payer_email')"
                  name="payer_email"
                  light
                />
              </div>
            </div>
          </div>
        </div>
        <div class="store-page__footer">
          <div class="store-page__button-wrapper col-sm-12 col-md-8 col-5">
            <base-button filled type="primary" html-type="submit" :disabled="!checkbox" class="store-page__button">
              Завершить регистрацию
            </base-button>
          </div>
        </div>
      </form>
      <base-loader v-if="loading" type="primary" size="large" />
    </div>
  </section>
</template>
<script>
import BaseInput from "@/components/base/BaseInput.vue";
import BaseSelect from "@/components/base/BaseSelect.vue";
import { computed, defineComponent, onBeforeMount, ref } from "vue";
import { useStore } from "@/store";
import BaseBackLink from "@/components/base/BaseBackLink.vue";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseCheckbox from "@/components/base/BaseCheckbox.vue";
import { useRouter } from "vue-router";
import BaseLoader from "@/components/base/BaseLoader.vue";
import { notify } from "@kyvg/vue3-notification";

export default defineComponent({
  name: "StorePage",
  components: {
    BaseBackLink,
    BaseInput,
    BaseSelect,
    BaseButton,
    BaseCheckbox,
    BaseLoader,
  },
  setup() {
    const store = useStore();
    const router = useRouter();
    const loading = ref(false);
    const checkbox = ref(false);
    const errors = ref([]);
    const storeTypeOptions = computed(() => store.getters.storeTypes);
    const dgdOptions = computed(() => store.getters.dgds);
    const ugdOptions = computed(() => store.getters.ugds);
    const chosenDgdId = computed(() => storeForm.value.dgdId);
    const ugdsToSelectedDgd = computed(() => {
      if (!chosenDgdId.value) return [];
      return ugdOptions.value.filter((ugd) => ugd.dgd_id === chosenDgdId.value);
    });
    const storeForm = ref({
      payerName: "",
      payerBin: "",
      payerBinRepeat: "",
      payerEmail: "",
      licenseNumber: "",
      storeTypeId: null,
      storeName: "",
      storeAddress: "",
      dgdId: null,
      ugdId: null,
      businessFullLegalName: "",
      businessBin: "",
      businessAddress: "",
      businessPostalAddress: "",
    });

    const toggleCheckbox = () => {
      checkbox.value = !checkbox.value;
    };

    const handleBackButtonClick = () => {
      store.dispatch("logout");
      router.push({ name: "auth.login" });
    };

    const prepareSetCompanyRequestPayload = () => {
      return {
        payer_name: storeForm.value.payerName,
        payer_bin: storeForm.value.payerBin.replaceAll(" ", ""),
        payer_bin_repeat: storeForm.value.payerBinRepeat.replaceAll(" ", ""),
        license_number: storeForm.value.licenseNumber,
        buisness_store_type_id: storeForm.value.storeTypeId,
        buisness_store_name: storeForm.value.storeName,
        buisness_store_address: storeForm.value.storeAddress,
        buisness_dgd_id: storeForm.value.dgdId,
        buisness_ugd_id: storeForm.value.ugdId,
        buisness_full_legal_name: storeForm.value.businessFullLegalName,
        buisness_bin: storeForm.value.businessBin.replaceAll(" ", ""),
        payer_address: storeForm.value.businessAddress,
        payer_postal_address: storeForm.value.businessPostalAddress,
        payer_email: storeForm.value.payerEmail,
      };
    };

    const handleSetCompanyRequestError = (e) => {
      const errorStatus = e?.response?.status;
      if (errorStatus === 422) {
        notify({
          text: "Введены некорректные данные",
          type: "error",
        });
        const { data } = e.response;
        const validationErrors = data?.message?.errors;
        if (validationErrors && typeof validationErrors === "object") {
          for (let errorKey in validationErrors) {
            errors.value.push({
              type: errorKey,
              text: validationErrors[errorKey],
            });
          }
        }
      }
    };

    const handleFormSubmit = () => {
      errors.value = [];

      const payload = prepareSetCompanyRequestPayload();
      for (let prop in payload) {
        if (prop === "payer_bin" || prop === "buisness_bin" || prop === "payer_bin_repeat") {
          if (!payload[prop] || payload[prop].length !== 12) {
            errors.value.push({ type: prop, text: "Введите корректный ИИН" });
          } else if (prop === "payer_bin_repeat" && payload[prop] !== payload["payer_bin"]) {
            errors.value.push({
              type: prop,
              text: "Введенные ИИНы не совпадают",
            });
          }
        } else if (prop === "payer_email") {
          const email = payload[prop];
          if (!email) continue;
          const regExp = /^([A-Za-z0-9_\-.])+@([A-Za-z0-9_\-.])+\.([A-Za-z]{2,4})$/;
          if (!regExp.test(email))
            errors.value.push({
              type: prop,
              text: "введите корректную почту",
            });
        } else if (!payload[prop]) {
          errors.value.push({ type: prop, text: "обязательное поле" });
        }
      }
      if (errors.value.length) return;

      delete payload["payer_bin_repeat"];
      if (!payload["payer_email"]) delete payload["payer_email"];

      loading.value = true;
      store
        .dispatch("setCompany", payload)
        .then(() => router.push({ name: "main.home" }))
        .catch(handleSetCompanyRequestError)
        .finally((loading.value = false));
    };

    const clearError = (e) => {
      errors.value = errors.value.filter((i) => i.type !== e);
    };

    onBeforeMount(() => {
      store.dispatch("getUgds");
      store.dispatch("getDgds");
      store.dispatch("getStoreTypes");
    });

    return {
      storeForm,
      storeTypeOptions,
      dgdOptions,
      ugdOptions,
      chosenDgdId,
      ugdsToSelectedDgd,
      loading,
      handleFormSubmit,
      checkbox,
      toggleCheckbox,
      errors,
      clearError,
      handleBackButtonClick,
    };
  },
});
</script>
