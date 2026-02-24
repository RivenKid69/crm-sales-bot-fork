<template>
  <label class="base-checkbox flex items-center">
    {{ label }}
    <input class="base-checkbox__input" type="checkbox" v-model="inputValue" />
    <span class="base-checkbox__checkmark"></span>
    <slot></slot>
  </label>
</template>

<script lang="ts">
import { computed, defineComponent, ref, SetupContext } from "vue";
import { useStore } from "@/store";

export default defineComponent({
  name: "BaseCheckbox",
  props: {
    modelValue: { type: [String, Boolean] },
    label: { type: String, required: false },
    trueValue: { default: true },
    falseValue: { default: false },
  },
  setup(props, { emit }: SetupContext) {
    const loading = ref(false);
    const inputValue = computed({
      get: () => props.modelValue,
      set: (value) => emit("update:modelValue", value),
    });
    return {
      inputValue,
    };
  },
});
</script>

<style lang="scss" scoped>
.base-checkbox {
  display: flex;
  align-items: center;
  position: relative;
  cursor: pointer;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
  user-select: none;
  font-size: 12px;
  font-weight: 600;
  color: #081d34;
}
.base-checkbox__input {
  position: absolute;
  opacity: 0;
  cursor: pointer;
  height: 0;
  width: 0;
}
.base-checkbox__checkmark {
  top: 0;
  left: 0;
  height: 18px;
  width: 18px;
  border-radius: 2px;
  background-color: #eee;
  border: 1px solid #ccc;
  margin-right: 11px;
}
.base-checkbox:hover input ~ .base-checkbox__checkmark {
  background-color: #ccc;
}
.base-checkbox input:checked ~ .base-checkbox__checkmark {
  background-color: $secondary-color;
}
.base-checkbox__checkmark:after {
  content: "";
  position: absolute;
  display: none;
}
.base-checkbox input:checked ~ .base-checkbox__checkmark:after {
  display: block;
}
.base-checkbox .base-checkbox__checkmark:after {
  left: 5px;
  top: 1px;
  width: 7px;
  height: 11px;
  border: solid white;
  border-width: 0 2px 2px 0;
  -webkit-transform: rotate(45deg);
  -ms-transform: rotate(45deg);
  transform: rotate(45deg);
}
</style>
