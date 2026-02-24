<template>
  <header class="header">
    <nav class="nav">
      <div class="header__logo">
        <router-link class="header__logo-link" :to="{ name: 'main.home' }">
          <img src="@/assets/images/icons/logo-white.svg" alt="Logo" class="header__logo-img" />
          <span class="header__logo-title"> Wipon Pro </span>
        </router-link>
      </div>
      <ul class="nav__list">
        <li class="nav__list-item">
          <router-link @click="showFeedbackModal = true" to="/" class="nav__link">
            <img src="@/assets/images/icons/chat.svg" alt="" class="nav__link-icon" />
            Обратная связь
          </router-link>
        </li>
        <li class="nav__list-item">
          <router-link @click="showProfileModal = true" to="/" class="nav__link">
            <img src="@/assets/images/icons/user.svg" alt="" class="nav__link-icon" />
            Профиль
          </router-link>
        </li>
        <li class="nav__list-item nav__list-logout">
          <span @click="logout" class="nav__link">
            <img src="@/assets/images/icons/logout.svg" alt="" />
          </span>
        </li>
      </ul>
      <div @click.stop="showMobileMenu = !showMobileMenu" class="nav__menu">
        <img src="@/assets/images/icons/hamburger.svg" alt="Menu" />
        <ul class="nav__mobile" v-show="showMobileMenu">
          <li class="nav__list-item">
            <router-link @click="showFeedbackModal = true" to="/" class="nav__link">
              <img src="@/assets/images/icons/chat.svg" alt="" class="nav__link-icon" />
              Обратная связь
            </router-link>
          </li>
          <li class="nav__list-item">
            <router-link @click="showProfileModal = true" to="/" class="nav__link">
              <img src="@/assets/images/icons/user.svg" alt="" class="nav__link-icon" />
              Профиль
            </router-link>
          </li>
          <li class="nav__list-item nav__list-logout">
            <span @click="logout" class="nav__link">
              <img src="@/assets/images/icons/logout.svg" class="nav__link-icon" alt="" />
              Выйти
            </span>
          </li>
        </ul>
      </div>
    </nav>
  </header>
  <FeedbackModal v-if="showFeedbackModal" @cancel="showFeedbackModal = false" />
  <ProfileModal v-if="showProfileModal" @cancel="showProfileModal = false" />
</template>

<script lang="ts">
import { useStore } from "@/store";
import { defineComponent, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import FeedbackModal from "@/views/Home/components/modals/FeedbackModal.vue";
import ProfileModal from "@/views/Home/components/modals/ProfileModal.vue";

export default defineComponent({
  name: "TheHeader",
  components: { FeedbackModal, ProfileModal },
  setup() {
    const store = useStore();
    const router = useRouter();
    const showFeedbackModal = ref(false);
    const showProfileModal = ref(false);
    const showMobileMenu = ref(false);
    const logout = async () => {
      store.commit("setSelectedRateTypeId", null);
      store.commit("setCompany", {});
      store.commit("setHasSubscriptions", false);
      store.dispatch("logout");
      await router.push({ name: "auth.login" });
    };

    const handleOutsideClickOfMobileMenu = () => {
      showMobileMenu.value = false;
    };

    onBeforeUnmount(() => {
      if (showMobileMenu.value) document.removeEventListener("click", handleOutsideClickOfMobileMenu);
    });

    watch(showMobileMenu, (value) => {
      value
        ? document.addEventListener("click", handleOutsideClickOfMobileMenu)
        : document.removeEventListener("click", handleOutsideClickOfMobileMenu);
    });

    return {
      showFeedbackModal,
      showProfileModal,
      showMobileMenu,
      logout,
    };
  },
});
</script>

<style lang="scss" scoped>
.header {
  padding: 12px 28px 12px 40px;
  background: $header-bg;
  color: $white;

  &__logo {
    &-link {
      display: flex;
      align-items: center;
    }

    &-title {
      font-size: 24px;
      font-weight: bold;
      margin-left: 8px;
    }
  }
}

.nav {
  display: flex;
  align-items: center;
  justify-content: space-between;

  &__list {
    display: flex;
    align-items: center;

    &-item {
      padding: 0 16px;
    }

    &-logout {
      padding: 0 8px;
    }
  }

  &__link {
    display: flex;
    align-items: center;
    cursor: pointer;

    &-icon {
      margin-right: 8px;
    }
  }

  &__menu {
    display: none;
  }

  &__mobile {
    display: none;
  }
}

@media (max-width: 991.98px) {
  .header {
    padding: 12px 20px 12px 20px;
  }
}

@media (max-width: 599.98px) {
  .header {
    &__logo {
      &-title {
        font-size: 18px;
      }
    }
  }

  .nav {
    &__menu {
      position: relative;
      display: block;
    }

    &__list {
      display: none;

      &-item {
        padding: 0;
        margin-bottom: 16px;

        &:nth-last-child(1) {
          margin-bottom: 0;
        }
      }
    }

    &__mobile {
      position: absolute;
      right: 0;
      bottom: -125px;
      background: $primary-dark-2;
      display: flex;
      flex-direction: column;
      padding: 12px 16px;
      border-radius: 10px;
      min-width: 210px;
    }
  }
}
</style>
