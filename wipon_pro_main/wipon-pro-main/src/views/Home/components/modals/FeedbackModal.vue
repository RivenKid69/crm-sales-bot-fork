<template>
  <div class="overlay" @click="hideModal">
    <div class="modal-card">
      <div class="feedback">
        <div class="feedback-block">
          <div class="feedback-block__title">Техподдержка</div>
          <div class="feedback-block__item">
            <a href="tel:+77719365061" class="feedback-block__link"> + 7 771 936 50 61 </a>
          </div>
          <div class="feedback-block__item">
            <a href="tel:+77719365062" class="feedback-block__link"> + 7 771 936 50 62 </a>
          </div>
          <div class="feedback-block__item">
            <a href="mailto:operator@wiponapp.com" class="feedback-block__link"> operator@wiponapp.com </a>
          </div>
        </div>
        <div class="feedback-block">
          <div class="feedback-block__title">Бухгалтерия</div>
          <div class="feedback-block__item">
            <a href="mailto:info@wiponapp.com" class="feedback-block__link"> info@wiponapp.com </a>
          </div>
          <div class="feedback-block__item">ПН-ПТ 09:00-18:00</div>
          <div class="feedback-block__item">Обед 13:00-14:00</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { defineComponent } from "vue";

export default defineComponent({
  name: "FeedbackModal",
  setup(props, { emit }) {
    const hideModal = (e) => {
      const target = e.target;
      if (target && target.className.includes("overlay")) {
        return emit("cancel");
      }
    };

    return {
      hideModal,
    };
  },
});
</script>

<style lang="scss">
.feedback {
  padding: 24px 24px 0 24px;
  &-block {
    margin-bottom: 24px;

    &__title {
      color: $dark;
      font-weight: 500;
      font-size: 18px;
      margin-bottom: 12px;
    }

    &__item {
      margin-bottom: 5px;
    }

    &__link {
      color: $primary;
    }
  }
}
</style>
