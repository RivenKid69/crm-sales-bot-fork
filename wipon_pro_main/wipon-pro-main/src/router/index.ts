import { createRouter, createWebHistory } from "vue-router";
import routes from "./routes";
import { store } from "@/store";

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  linkActiveClass: "active",
  linkExactActiveClass: "exact-active",
  scrollBehavior() {
    return { top: 0 };
  },
  routes,
});

router.beforeEach(async (to, from, next) => {
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-ignore
  document.title = to.meta.title || "Wipon Pro - Личный кабинет";
  if (to.query.abt) {
    store.commit("setAuthToken", to.query.abt);
    await store.dispatch("getCompany");
    if (to.query.activateMobile) {
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      return next({ name: "main.home", query: { activateMobile: true } });
    }
    return next({ name: "main.home" });
  }
  const authToken = store.getters.authTokenGet;
  if (to.matched.some((route) => route.meta.requiresAuth)) {
    if (!authToken) {
      return next({ name: "auth.login" });
    }
    const hasStore = store.getters.hasStore;
    await store.dispatch("getUser");
    if (to.meta.requiresStore && !hasStore) return next({ name: "auth.store" });

    if (to.name === "auth.store" && hasStore) return next({ name: "main.home" });
    return next();
  }
  if (to.matched.some((route) => route.meta.onlyLoggedOut)) {
    if (authToken) return next({ name: "main.home" });
    if (!authToken) return next();
  }
  next();
});

export default router;
