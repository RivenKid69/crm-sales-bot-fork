<template>
  <button
    :type="htmlType"
    :class="{
      'base-button_primary': type === 'primary',
      'base-button_danger': type === 'danger',
      'base-button_filled': filled,
      'base-button_disabled': disabled,
      block,
      'base-button-drop-down-small': small,
    }"
    :disabled="disabled"
    class="base-button-drop-down"
    @click.stop="open = !open"
    @blur="closeDropdown"
  >
    <slot />
    <div class="base-button-drop-down__items" :class="{ dropdDownHide: !open }">
      <ul>
        <li v-for="(item, idx) in links" @click="redirect(item)" :key="idx" class="base-button-drop-down__item">
          <a>{{ item.name }}</a>
        </li>
      </ul>
    </div>
  </button>
</template>

<script>
import { defineComponent, ref } from "vue";
import { MOBILE_TYPE } from "@/config/rates";
import { useStore } from "@/store";
import formatDataToSvgAndDownload from "@/utils/download-qr";

export default defineComponent({
  name: "BaseButtonDropDown",
  props: {
    type: {
      type: String,
      default: "default",
    },
    filled: {
      type: Boolean,
      default: false,
    },
    htmlType: {
      type: String,
      default: "",
    },
    loading: {
      type: Boolean,
      default: false,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    block: {
      type: Boolean,
      default: false,
    },
    small: {
      type: Boolean,
      default: false,
    },
    links: {
      type: Array,
      default: () => [],
    },
  },
  setup(props, { emit }) {
    const store = useStore();
    const open = ref(false);
    const closeDropdown = (e) => {
      if (!e.relatedTarget || e.relatedTarget.tagName !== "A") open.value = false;
    };

    const redirect = (item) => {
      const link = document.querySelector(".invisible-link");
      if (item.isQr && store.getters.hasSubscriptions) {
        const activeRate = store.getters.subscriptions.find((sub) => sub.is_active);
        if (activeRate && activeRate.type !== MOBILE_TYPE) {
          return formatDataToSvgAndDownload(activeRate.device_code);
        }
      }
      link.setAttribute("href", item.link);
      link.click();
    };

    return {
      open,
      redirect,
      closeDropdown,
    };
  },
  methods: {
    // handleClick() {
    //   if (this.disabled) return;
    //
    //   this.$emit("click");
    // },
  },
});
</script>

<style lang="scss">
.base-button-drop-down {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 10px 0;
  font-size: 14px;
  font-weight: 400;
  color: $dark;
  transition: 200ms;
  border: 1px solid $secondary-light-2;
  border-radius: 10px;
  box-sizing: border-box;
  outline: none;
  cursor: pointer;
  -webkit-touch-callout: none; /* iOS Safari */
  -webkit-user-select: none; /* Safari */
  -khtml-user-select: none; /* Konqueror HTML */
  -moz-user-select: none; /* Old versions of Firefox */
  -ms-user-select: none; /* Internet Explorer/Edge */
  user-select: none;
  font-family: "IBM Plex Sans", sans-serif;
  background-color: $white;
  letter-spacing: 0.5px;
  position: relative;

  &-small {
    padding: 6px 10px !important;
  }
}

.base-button-drop-down__items {
  padding: 7px 0;
  color: $dark;
  border-radius: 10px;
  position: absolute;
  border: 1px solid #d4def5;
  background-color: #fff;
  right: 0;
  max-width: 140px;
  width: max-content;
  //margin-top: 10px;
  max-height: 300px;
  overflow: auto;
  top: 40px;
  z-index: 5;
}

.base-button-drop-down__item {
  padding: 7px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 14px;
}

.dropdDownHide {
  display: none;
}
</style>
