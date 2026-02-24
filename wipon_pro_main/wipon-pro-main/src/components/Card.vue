<template>
  <div class="card">
    <div class="card__title" :class="{ card__title_sm: smallPadding }">
      {{ title }}
      <slot name="header"></slot>
    </div>
    <div class="divider"></div>
    <div class="card__body">
      <slot></slot>
    </div>
  </div>
</template>

<script>
export default {
  name: "Card",
  props: {
    title: {
      type: String,
      required: true,
      default: "Заголовок",
    },

    smallPadding: {
      type: Boolean,
      default: false,
    },
  },
};
</script>
