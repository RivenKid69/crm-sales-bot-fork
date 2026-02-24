<template>
  <a class="base-back-link">Назад</a>
</template>

<script>
import { defineComponent } from "vue";

export default defineComponent({
  name: "BaseBackLink",
});
</script>

<style lang="scss">
.base-back-link {
  color: $primary;
  font-weight: 500;
  display: flex;
  align-items: center;
  cursor: pointer;
  &::before {
    content: "";
    width: 16px;
    height: 16px;
    display: block;
    background-image: url("../../assets/images/icons/arrow-back.svg");
    margin-right: 12px;
  }
}
</style>
