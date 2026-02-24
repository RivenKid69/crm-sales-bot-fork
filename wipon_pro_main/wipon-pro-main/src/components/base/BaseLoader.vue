<template>
  <div class="base-loader__wrapper" :class="{ 'base-loader__wrapper_modal': modalLoader }">
    <div
      :class="{
        'base-loader_primary': type === 'primary',
        'base-loader_light': type === 'light',
        'base-loader_danger': type === 'danger',
        'base-loader_large': size === 'large',
      }"
      class="base-loader"
    />
  </div>
</template>

<script>
import { defineComponent } from "vue";

export default defineComponent({
  name: "BaseLoader",
  props: {
    type: {
      type: String,
      default: "default",
    },
    size: {
      type: String,
      default: "small",
    },
    modalLoader: {
      type: Boolean,
      default: false,
    },
  },
});
</script>

<style lang="scss">
.base-loader__wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  position: absolute;
  background-color: #fff;
  opacity: 0.7;

  &_modal {
    position: absolute;
    top: 0;
    left: 0;
    border-radius: 20px;
  }
}

.base-loader {
  display: inline-block;
}

.base-loader:after {
  content: " ";
  display: block;
  width: 16px;
  height: 16px;
  margin: 2px;
  border-radius: 50%;
  border: 4px solid $dark;
  border-color: $dark transparent $dark transparent;
  animation: base-loader 1.2s linear infinite;
}

.base-loader_primary:after {
  border: 4px solid $primary;
  border-color: $primary transparent $primary transparent;
}

.base-loader_light:after {
  border: 4px solid #fff;
  border-color: #fff transparent #fff transparent;
}

.base-loader_danger:after {
  border: 4px solid $danger;
  border-color: $danger transparent $danger transparent;
}

.base-loader_large:after {
  width: 40px;
  height: 40px;
  margin: 6px;
  border-width: 6px;
}

@keyframes base-loader {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
