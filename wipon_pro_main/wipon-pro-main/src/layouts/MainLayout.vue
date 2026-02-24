<template>
  <div class="page-wrapper">
    <Header />
    <router-view></router-view>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";
import Header from "@/components/TheHeader.vue";

export default defineComponent({
  name: "MainLayout",
  components: {
    Header,
  },
});
</script>
<style lang="scss" scoped>
.page-wrapper {
  background-color: $primary-light-2;
}
</style>
