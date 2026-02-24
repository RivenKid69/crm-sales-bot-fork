<template>
  <button
    :type="htmlType"
    :class="{
      'base-button_primary': type === 'primary',
      'base-button_danger': type === 'danger',
      'base-button_filled': filled,
      'base-button_disabled': disabled,
      block,
      'base-button-small': small,
    }"
    class="base-button"
    @click="handleClick"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<script>
import { defineComponent, ref } from "vue";

export default defineComponent({
  name: "BaseButton",
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
  },
  setup(props, { emit }) {
    const disabled = ref(props.disabled);
    const handleClick = () => {
      if (disabled.value) return;
      emit("btn-click");
    };

    return {
      handleClick,
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
.base-button {
  padding: 0 $btn-padding-y-lg;
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
  white-space: nowrap;
  overflow: hidden;
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

  &-small {
    padding: 6px 10px !important;
  }
}

.base-button:hover {
  background-color: $primary-light-2;
  cursor: pointer;
}

.base-button_disabled {
  color: #959baa;
  border: 1.5px solid #dee2e8;
  cursor: default;
}

.base-button_disabled:hover {
  opacity: 1;
}

.base-button.base-button_filled {
  background-color: white;
  font-weight: 500;
}

.base-button_primary {
  color: $primary;
  border: 1.5px solid $primary;
}

.base-button_primary:hover {
  border: 1.5px solid #2c6dfe;
}

.base-button_primary.base-button_filled {
  color: white;
  background-color: $primary;
}

.base-button_primary.base-button_filled:hover {
  color: white;
  background-color: $primary-light-1;
}

.base-button_primary.base-button_filled.base-button_disabled {
  color: #959baa;
  background-color: #ced3e0;
  border-color: #ced3e0;
}

.base-button_danger {
  color: $dark;
  border: 1.5px solid $danger;
  background-color: transparent;
}

.base-button_danger.base-button_filled {
  color: white;
  background-color: $danger;
}
</style>
