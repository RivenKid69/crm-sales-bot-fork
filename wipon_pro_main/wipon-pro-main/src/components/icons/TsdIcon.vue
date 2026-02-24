<template>
  <svg
    :width="large ? 40 : 22"
    :height="large ? 40 : 18"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path d="M21 16V21H3V16H5V19H19V16H21ZM3 11H21V13H3V11ZM21 8H19V5H5V8H3V3H21V8Z" fill="currentColor" />
  </svg>
</template>

<script lang="ts">
import { defineComponent } from "vue";

export default defineComponent({
  name: "TsdIcon",
  props: {
    large: {
      type: Boolean,
      default: false,
    },
  },
});
</script>
