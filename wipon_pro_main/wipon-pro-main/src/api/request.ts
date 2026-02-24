import axios from "axios";
import config from "@/config/index";
import router from "@/router";
import { store } from "@/store";
import { notify } from "@kyvg/vue3-notification";

const instance = axios.create({
  baseURL: `${config.apiUrl}/${config.apiVersion}`,
  headers: {
    Accept: "application/json",
  },
});

instance.interceptors.request.use(
  (config: any) => {
    const authToken = store.getters.authTokenGet;
    if (authToken) {
      config.headers.Authorization = "Bearer " + authToken;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

instance.interceptors.response.use(
  (response) => response,
  async function (error) {
    const {
      status,
      data: { message },
    } = error.response;
    const UNAUTHORIZED_STATUS_CODE = 401;
    const INTERNAL_SERVER_ERROR = 500;
    if (status === INTERNAL_SERVER_ERROR) {
      notify({
        text: "Упс..., что-то пошло не так, обратитесь в тех. поддержку",
        type: "error",
        ignoreDuplicates: true,
      });
    } else if ((message && typeof message === "string") || Array.isArray(message)) {
      notify({
        text: Array.isArray(message) ? message[0] : message,
        type: "error",
      });
    } else if (message && message.error) {
      notify({
        text: message.error,
        type: "error",
        ignoreDuplicates: true,
      });
    }
    if (status === UNAUTHORIZED_STATUS_CODE) {
      store.commit("setSelectedRateTypeId", null);
      store.commit("setCompany", {});
      store.commit("setHasSubscriptions", false);
      await store.dispatch("logout");
      await router.push({ name: "auth.login" });
    }
    return Promise.reject(error);
  }
);

export default instance;
