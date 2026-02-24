<template>
  <svg
    :width="large ? 40 : 22"
    :height="large ? 40 : 18"
    viewBox="0 0 22 18"
    fill="currentColor"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M3 2V13H19V2H3ZM1 1.007C1 0.451 1.455 0 1.992 0H20.008C20.556 0 21 0.449 21 1.007V15H1V1.007ZM0 16H22V18H0V16Z"
      fill="currentColor"
    />
  </svg>
</template>

<script lang="ts">
import { defineComponent } from "vue";

export default defineComponent({
  name: "PcIcon",
  props: {
    large: {
      type: Boolean,
      default: false,
    },
  },
});
</script>
