import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { store } from "./store";
import "@/assets/style/bootstrap-grid/bootstrap-grid.min.css";
import "@/assets/style/base/app.scss";
import VueAxios from "vue-axios";
import axios from "axios";
import { maska } from "maska";
import Notifications from "@kyvg/vue3-notification";

const app = createApp(App).use(store).use(router);
app.use(VueAxios, axios);
app.provide("axios", app.config.globalProperties.axios);
app.directive("mask", maska);
app.use(Notifications);
app.mount("#app");
