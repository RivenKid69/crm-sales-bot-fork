<template>
  <BaseModal
    :classname="'payment-modal'"
    title="Пополнить баланс"
    subtitle="Выберите тариф и подходящий способ оплаты. Также, вы можете просто совершить банковский платёж на любую сумму на ваш лицевой счёт."
    show-footer
    @cancel="hideModal"
    :loading="isLoading"
  >
    <template v-slot:body>
      <div class="payment-checkboxes">
        <div v-for="rate in rateList" :key="rate.type" @click="setActiveRateInfo(rate.type)" class="payment-checkbox">
          <div class="checkbox" :class="{ checkbox_active: rate.isActive }"></div>
          <div class="payment-checkbox__info">
            <span class="payment-checkbox__title"> {{ rate.title }} </span>
            <span class="payment-checkbox__price"> {{ priceFilter(rate.price) }} ₸</span>
          </div>
        </div>
      </div>
    </template>
    <template v-slot:footer>
      <div class="payment-modal__footer">
        <div class="payment__options">
          <div
            v-for="paymentOption in paymentOptionsList"
            :key="paymentOption.id"
            @click="setSelectedPaymentOption(paymentOption.id)"
            class="payment__option"
            :class="{ payment__option_active: paymentOption.isActive }"
          >
            <img class="payment__option-icon" :src="paymentOption.icon" alt="" />
            <span class="payment__option-title"> {{ paymentOption.title }} </span>
          </div>
        </div>
        <div v-show="selectedPaymentOption.id === bankOptionId" class="payment__description">
          <div class="payment__description-info">
            Мы сформировали счёт на оплату на тариф <span style="font-weight: 500"> {{ selectedRate.title }} </span>,
            скачайте его, и сделайте банковский перевод. Деньги поступят на ваш баланс в течении рабочего дня.
          </div>
          <base-button @click="downloadInvoicePdf" class="payment__download-check" small>
            <img src="@/assets/images/icons/download.svg" alt="" class="payment__download-check-icon" />
            Скачать счёт на оплату
          </base-button>
        </div>
        <div v-show="selectedPaymentOption.id === kaspiOptionId" class="payment__description">
          <div class="payment__description-info">
            1. В мобильном приложении войдите в раздел <span style="font-weight: 500">«Платежи»</span> <br />
            2. Перейдите в <span style="font-weight: 500">«Финансовые платежи»</span>, выберите
            <span style="font-weight: 500">«Wipon»</span> <br />
            3. Введите ваш лицевой счёт: <span style="font-weight: 500"> {{ account.number }} </span> <br />
            4. Оплатите <span style="font-weight: 500"> {{ priceFilter(selectedRate.price) }} тг </span>
          </div>
        </div>
        <div v-show="selectedPaymentOption.id === qiwiiOptionId" class="payment__description">
          <div class="payment__description-info">
            1. В терминале, выберите <span style="font-weight: 500">«Оплата услуг»</span> <br />
            2. Нажмите на <span style="font-weight: 500">«Другие услуги»</span> и выберите
            <span style="font-weight: 500">«Wipon»</span> <br />
            3. Введите ваш лицевой счёт: <span style="font-weight: 500"> {{ account.number }} </span> <br />
            4. Внесите <span style="font-weight: 500"> {{ priceFilter(selectedRate.price) }} тг </span>, и не забудьте
            учесть комиссию терминала
          </div>
        </div>
      </div>
    </template>
  </BaseModal>
</template>

<script>
import { computed, defineComponent, reactive, ref, nextTick } from "vue";
import BaseModal from "@/components/base/BaseModal";
import BaseButton from "@/components/base/BaseButton";
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from "@/config/rates";
import { useStore } from "@/store";
import { notify } from "@kyvg/vue3-notification";
import axios from "axios";
import { downloadBlob } from "@/utils/helpers";

export default defineComponent({
  name: "PaymentModal",
  components: {
    BaseModal,
    BaseButton,
  },

  setup(props, { emit }) {
    const store = useStore();
    const isLoading = ref(false);
    const rateList = reactive([
      {
        type: MOBILE_TYPE,
        title: "Смартфон, 1 год",
        price: 12000,
        isActive: true,
      },
      {
        type: DESKTOP_TYPE,
        title: "Компьютер, 1 год",
        price: 15000,
        isActive: false,
      },
      {
        type: TSD_TYPE,
        title: "ТСД, 1 год",
        price: 30000,
        isActive: false,
      },
    ]);
    const selectedRate = computed(() => rateList.find((rate) => rate.isActive));
    const bankOptionId = ref(1);
    const kaspiOptionId = ref(2);
    const qiwiiOptionId = ref(3);

    const account = computed(() => store.getters.accountGet);

    const paymentOptionsList = reactive([
      {
        id: bankOptionId,
        title: "Банковский перевод",
        icon: require("@/assets/images/icons/builder.svg"),
        isActive: true,
      },
      {
        id: kaspiOptionId,
        title: "Kaspi.kz",
        icon: require("@/assets/images/icons/kaspi.svg"),
        isActive: false,
      },
      {
        id: qiwiiOptionId,
        title: "QIWI",
        icon: require("@/assets/images/icons/qiwi.svg"),
        isActive: false,
      },
    ]);

    const priceFilter = (value) => {
      return Intl.NumberFormat("ru-RU", { style: "decimal" }).format(value);
    };

    const selectedPaymentOption = computed(() => paymentOptionsList.find((el) => el.isActive));
    const setSelectedPaymentOption = (id) => {
      paymentOptionsList.forEach((el) => (el.id === id ? (el.isActive = true) : (el.isActive = false)));
    };

    const setActiveRateInfo = (type) => {
      rateList.forEach((rate) => (rate.type === type ? (rate.isActive = true) : (rate.isActive = false)));
    };
    const hideModal = () => {
      emit("hideModal");
    };

    const generateInvoiceData = () => {
      const date = new Date();
      const formattedDigitDate = new Intl.DateTimeFormat("ru-RU", {
        year: "2-digit",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(date);

      const formattedReadableDate = new Intl.DateTimeFormat("ru-RU", {
        year: "numeric",
        month: "long",
        day: "2-digit",
      }).format(date);

      const company = store.getters.company;
      const account = store.getters.accountGet;
      const user = store.getters.getUser;
      const ratePrice = priceFilter(selectedRate.value.price);
      const rateName =
        selectedRate.value.type === MOBILE_TYPE
          ? "Мобильное приложение"
          : selectedRate.value.type === DESKTOP_TYPE
          ? "Компьютер"
          : "ТСД";

      let invoiceNumber = formattedDigitDate.replace(/[., :]/g, "");
      if (user.id) invoiceNumber += user.id;
      invoiceNumber += selectedRate.value.type;

      return {
        number: invoiceNumber,
        numberDate: formattedReadableDate,
        customerBin: company.licenserBin,
        customerOrganization: company.licenserName,
        accountNumber: account.number,
        ratePrice,
        rateName,
        rateLetterPrice: sum_letters(selectedRate.value.price),
      };
    };

    const razUp = (e) => {
      return e[1].toUpperCase() + e.substring(2);
    };

    const numLetters = (k, d) => {
      let i = "",
        e = [
          [
            "",
            "тысяч",
            "миллион",
            "миллиард",
            "триллион",
            "квадриллион",
            "квинтиллион",
            "секстиллион",
            "септиллион",
            "октиллион",
            "нониллион",
            "дециллион",
          ],
          ["а", "и", ""],
          ["", "а", "ов"],
        ];
      if (k == "" || k == "0") return " ноль"; // 0
      k = k.split(/(?=(?:\d{3})+$)/); // разбить число в массив с трёхзначными числами
      if (k[0].length == 1) k[0] = "00" + k[0];
      if (k[0].length == 2) k[0] = "0" + k[0];
      for (let j = k.length - 1; j >= 0; j--) {
        if (k[j] != "000") {
          i =
            (((d && j == k.length - 1) || j == k.length - 2) && (k[j][2] == "1" || k[j][2] == "2")
              ? t(k[j], 1)
              : t(k[j])) +
            declOfNum(k[j], e[0][k.length - 1 - j], j == k.length - 2 ? e[1] : e[2]) +
            i;
        }
      }
      function t(k, d) {
        // преобразовать трёхзначные числа
        let e = [
          ["", " один", " два", " три", " четыре", " пять", " шесть", " семь", " восемь", " девять"],
          [
            " десять",
            " одиннадцать",
            " двенадцать",
            " тринадцать",
            " четырнадцать",
            " пятнадцать",
            " шестнадцать",
            " семнадцать",
            " восемнадцать",
            " девятнадцать",
          ],
          [
            "",
            "",
            " двадцать",
            " тридцать",
            " сорок",
            " пятьдесят",
            " шестьдесят",
            " семьдесят",
            " восемьдесят",
            " девяносто",
          ],
          [
            "",
            " сто",
            " двести",
            " триста",
            " четыреста",
            " пятьсот",
            " шестьсот",
            " семьсот",
            " восемьсот",
            " девятьсот",
          ],
          ["", " одна", " две"],
        ];
        return e[3][k[0]] + (k[1] == 1 ? e[1][k[2]] : e[2][k[1]] + (d ? e[4][k[2]] : e[0][k[2]]));
      }
      return i;
    };

    const sum_letters = (num) => {
      num = num.toString();
      return razUp(numLetters(num, 1));
    };

    const declOfNum = (n, t, o) => {
      const k = [2, 0, 1, 1, 1, 2, 2, 2, 2, 2];
      return t == "" ? "" : " " + t + (n[n.length - 2] == "1" ? o[2] : o[k[n[n.length - 1]]]);
    };

    const downloadInvoicePdf = async () => {
      try {
        isLoading.value = true;
        const invoiceData = generateInvoiceData();
        const response = await axios.post("https://api.cabinet.wipon.pro/v1/pdf/generate-invoice", invoiceData, {
          responseType: "blob",
        });
        const fileName = `Wipon_invoice_${invoiceData.number}.pdf`;
        await downloadBlob(response, fileName);
      } catch (e) {
        notify({
          text: "Произошла ошибка при генерации счета на оплату. Обратитесь в тех поддержку",
          type: "error",
          ignoreDuplicates: true,
        });
      } finally {
        isLoading.value = false;
      }
    };

    return {
      isLoading,
      kaspiOptionId,
      bankOptionId,
      qiwiiOptionId,
      rateList,
      setActiveRateInfo,
      setSelectedPaymentOption,
      selectedRate,
      selectedPaymentOption,
      paymentOptionsList,
      account,
      priceFilter,
      hideModal,
      downloadInvoicePdf,
    };
  },
});
</script>

<style lang="scss">
.payment-modal {
  //position: absolute;
  width: 580px;
  max-height: 600px;
  overflow-y: auto;

  &__footer {
    display: flex;
    padding: 12px 0 24px 0;
  }
}

.payment {
  &__options {
    display: flex;
    flex-direction: column;
    border-right: 1px solid $secondary-light-2;
    min-width: 35%;
  }

  &__option {
    display: flex;
    align-items: center;
    padding: 10px 24px;
    cursor: pointer;

    &-icon {
      margin-right: 10px;
    }

    &_active {
      color: $primary;
      background: $primary-light-2;
    }
  }

  &__description {
    padding: 16px 20px;

    &-info {
      line-height: 1.5;
    }
  }

  &__download-check {
    margin-top: 20px;

    &-icon {
      margin-right: 8px;
    }
  }
}

.payment-checkboxes {
  display: flex;
  justify-content: space-between;
  gap: 15px;
}

.payment-checkbox {
  display: flex;
  align-items: center;
  cursor: pointer;

  &__info {
    display: flex;
    flex-direction: column;
    margin-left: 10px;
  }

  &__price {
    font-weight: 500;
  }
}

@media (max-width: 600.98px) {
  .payment-modal {
    width: 90%;
    max-height: 530px;

    &__footer {
      flex-direction: column;
    }
  }

  .payment-checkboxes {
    flex-direction: column;
  }

  .payment-checkbox {
    &__info {
      margin-left: 25px;
    }
  }

  .payment__options {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .payment__option {
    padding: 10px;
  }
}
</style>
