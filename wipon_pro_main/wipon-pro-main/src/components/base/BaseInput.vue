<template>
  <div class="base-input" :class="{ 'base-input_light': light }">
    <label v-if="label" class="base-input__label">{{ label }}</label>
    <div
      :class="{
        'base-input__wrapper_focused': focused,
        'base-input__wrapper--error': getErrors.length,
      }"
      class="base-input__wrapper"
    >
      <div v-if="prefix" class="base-input__prefix">{{ prefix }}</div>
      <input
        v-model="inputValue"
        :placeholder="placeholder"
        :autofocus="autofocus"
        :disabled="disabled"
        :required="required"
        :type="inputType"
        :class="{
          'base-input__input_no-left-padding': prefix,
          'base-input__input--error': getErrors.length,
        }"
        class="base-input__input"
        @focus="focused = true"
        @blur="focused = false"
      />
    </div>
    <div v-for="error in getErrors" :key="error.type">
      <p class="base-input__error-item">{{ error.text }}</p>
    </div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, ref, SetupContext } from "vue";
export default defineComponent({
  name: "BaseInput",
  props: {
    modelValue: {
      type: [String, Number],
      default: "",
    },
    inputType: {
      type: [String, Number],
      default: "text",
    },
    name: {
      type: String,
      default: "",
    },
    label: {
      type: String,
      default: "",
    },
    placeholder: {
      type: String,
      default: "",
    },
    light: {
      type: Boolean,
      default: false,
    },
    autofocus: {
      type: Boolean,
      default: false,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    mask: {
      type: String,
      default: null,
    },
    required: {
      type: Boolean,
      default: false,
    },
    prefix: {
      type: String,
      default: null,
    },
    errors: {
      type: Array,
      default: () => [],
    },
  },
  setup(props, { emit }: SetupContext) {
    const focused = ref(false);
    const getErrors = computed(() => props.errors.filter((i: any) => i.type === props.name));
    const inputValue = computed({
      get: () => props.modelValue,
      set: (value) => emit("update:modelValue", value),
    });
    return {
      inputValue,
      focused,
      getErrors,
    };
  },
});
</script>

<style lang="scss">
.base-input {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding-bottom: 2rem;
}

.base-input__label {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 500;
  text-transform: uppercase;
  color: $secondary-color;
}

.base-input__wrapper {
  width: 100%;
  display: flex;
  align-items: center;
  color: $dark;
  background-color: $secondary-color;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #d4def5;
  transition: 200ms;

  &--error {
    border: none;
  }
}

.base-input__wrapper_focused {
  border: 1px solid $primary;
}

.base-input__prefix {
  padding: 0 8px;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 18px;
  font-weight: 500;
  color: $secondary-color;
  margin-bottom: 3px;
}

.base-input__input {
  width: 100%;
  padding: 14px 20px;
  font-size: 18px;
  font-weight: 500;
  background-color: transparent;
  border: none;
  outline: none;
  &--error {
    border: 1px solid $danger;
    border-radius: inherit;
  }
}

.base-input__input_no-left-padding {
  padding-left: 0;
}

.base-input_light .base-input__label {
  color: $secondary-color;
}

.base-input_light .base-input__wrapper {
  background-color: white;
}

.base-input__error-item {
  color: $danger;
  margin: 2px;
  font-size: 11px;
}
</style>
