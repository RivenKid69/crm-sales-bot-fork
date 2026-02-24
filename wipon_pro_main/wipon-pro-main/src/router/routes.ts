import { RouteRecordRaw } from "vue-router";
import MainLayout from "@/layouts/MainLayout.vue";
import EmptyLayout from "@/layouts/EmptyLayout.vue";
import { store } from "@/store";

const routes: Array<RouteRecordRaw> = [
  {
    path: "/auth",
    component: EmptyLayout,
    children: [
      {
        path: "verification",
        name: "auth.verification",
        meta: {
          onlyLoggedOut: true,
          title: "Wipon Pro - Верификация",
        },
        component: () => import(/* webpackChunkName: "authGroup" */ "@/views/Login/VerificationCode.vue"),
      },
      {
        path: "store",
        name: "auth.store",
        meta: {
          requiresAuth: true,
          title: "Wipon Pro - Заполнение данных о торговой точке",
        },
        component: () => import(/* webpackChunkName: "authGroup" */ "@/views/Login/StorePage.vue"),
      },
      {
        path: "login",
        name: "auth.login",
        meta: {
          onlyLoggedOut: true,
          title: "Wipon Pro - Авторизация",
        },
        component: () => import(/* webpackChunkName: "authGroup" */ "@/views/Login/LoginPage.vue"),
      },
    ],
  },
  {
    path: "/",
    component: MainLayout,
    meta: {
      requiresAuth: true,
      requiresStore: true,
      title: "Wipon Pro - Личный кабинет",
    },
    children: [
      {
        path: "",
        name: "main.home",
        component: () => import(/* webpackChunkName: "main" */ "@/views/Home/HomePage.vue"),
      },
    ],
  },
];

export default routes;
