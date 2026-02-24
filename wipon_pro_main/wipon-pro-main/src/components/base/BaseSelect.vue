<template>
  <div class="base-select" :tabindex="tabindex" @blur="open = false">
    <div v-if="label" class="base-select__label">{{ label }}</div>
    <div
      class="base-select__selected"
      :class="{
        open,
        'base-select__selected--error': getErrors.length,
        'base-select_disabled': !getErrors.length && disabled,
      }"
      @click="toggleSelect"
    >
      {{ selected }}
    </div>
    <div class="base-select__items" :class="{ selectHide: !open }">
      <div class="base-select__item" v-for="(option, i) of options" :key="i" @click="selectItem(option)">
        {{ option[optionName] }}
      </div>
    </div>
    <div v-for="error in getErrors" :key="error.type">
      <p class="base-input__error-item">{{ error.text }}</p>
    </div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, ref, SetupContext } from "vue";

export default defineComponent({
  name: "BaseSelect",
  props: {
    modelValue: {
      type: [String, Number],
      default: "",
    },
    options: {
      type: Array,
      required: true,
    },
    name: {
      type: String,
      default: "name",
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    optionName: {
      type: String,
      default: "name",
    },
    default: {
      type: String,
      required: false,
      default: null,
    },
    tabindex: {
      type: Number,
      required: false,
      default: 0,
    },
    label: {
      type: String,
      default: "",
    },
    errors: {
      type: Array,
      default: () => [],
    },
  },
  setup(props, { emit }: SetupContext) {
    const open = ref(false);
    const selected = ref(props.default ? props.default : props.options.length > 0 ? props.options[0] : null);

    const getErrors = computed(() => props.errors.filter((i: any) => i.type === props.name));

    const selectItem = (option: any) => {
      open.value = false;
      selected.value = option[props.optionName];
      emit("update:modelValue", option.id);
      emit("change");
    };

    const toggleSelect = () => {
      if (props.disabled) return;
      open.value = !open.value;
    };

    return {
      selected,
      open,
      selectItem,
      toggleSelect,
      getErrors,
    };
  },
  // mounted() {
  //   this.$emit("input", this.selected);
  // },
});
</script>

<style lang="scss">
.base-select {
  position: relative;
  width: 100%;
  text-align: left;
  outline: none;
  padding-bottom: 2rem;

  &_disabled {
    background: $secondary-light-2;
    color: $secondary-light-1;
  }
}

.base-select__label {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 500;
  text-transform: uppercase;
  color: $secondary-color;
}

.base-select__selected {
  border-radius: 6px;
  border: 1px solid #d4def5;
  cursor: pointer;
  user-select: none;
  position: relative;
  padding: 14px 20px;
}
.base-select__selected--error {
  border: 1px solid #f45555;
  border-radius: 6px;
}

.base-select__selected.open {
  border: 1px solid $primary;
}

.base-select__selected:after {
  position: absolute;
  content: "";
  top: 22px;
  right: 10px;
  width: 12px;
  height: 7px;
  background-image: url("../../assets/images/icons/arrow-down.svg");
  background-size: cover;
}

.base-select__selected.open:after {
  transform: rotate(180deg);
}

.base-select__items {
  z-index: 9;
  padding: 7px 0;
  color: $dark;
  border-radius: 10px;
  //overflow: hidden;
  position: absolute;
  border: 1px solid #d4def5;
  background-color: #fff;
  left: 0;
  right: 0;
  margin-top: 10px;
  max-height: 300px;
  overflow: auto;
}

.base-select__item {
  padding: 7px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 14px;
}
.base-input__error-item {
  color: $danger;
  margin: 2px;
  font-size: 11px;
}
.base-select__item:hover {
  opacity: 0.8;
}

.selectHide {
  display: none;
}
</style>
