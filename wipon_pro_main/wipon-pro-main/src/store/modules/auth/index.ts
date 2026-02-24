import { GetterTree, MutationTree, ActionContext, CommitOptions } from "vuex";

import { initialState } from "../../initialState";
import { getApiTokenRequest, getUserData, sendVerificationCodeRequest } from "@/api/auth.api";
import { store } from "@/store";

export type MutationPayload = {
  setPhone: string;
  setDeviceId: string;
  setAuthToken: string;
  setHasStore: boolean;
  setUser: any;
};

export const mutations: MutationTree<State> & Mutations = {
  setPhone({ auth }, phone) {
    auth.phone = phone;
    localStorage.setItem("phone", phone);
  },
  setDeviceId({ auth }, deviceId) {
    auth.deviceId = deviceId;
    localStorage.setItem("deviceId", deviceId);
  },
  setAuthToken({ auth }, authToken) {
    auth.authToken = authToken;
    localStorage.setItem("authToken", authToken);
  },
  setHasStore({ company }, payload) {
    company.hasStore = payload;
  },
  setUser({ auth }, payload) {
    auth.user = payload;
  },
};

export type Getters = {
  phoneGet(state: State): string;
  deviceIdGet(state: State): string;
  authTokenGet(state: State): string;
  getUser(state: State): any;
};

export const getters: GetterTree<State, State> & Getters = {
  phoneGet: ({ auth }) => auth.phone,
  deviceIdGet: ({ auth }) => auth.deviceId,
  authTokenGet: ({ auth }) => auth.authToken,
  getUser: ({ auth }) => auth.user,
};

export type ActionsPayload = {
  sendVerificationCode: [payload: string, returnVal: Promise<any>];
  getAuthToken: [payload: string, returnVal: Promise<any>];
  logout: [payload: void, returnVal: void];
  getUser: [payload: void, returnVal: void];
};

export const actions: Actions = {
  sendVerificationCode({ commit }, payload): Promise<any> {
    commit("setPhone", payload);
    return sendVerificationCodeRequest(payload);
  },
  async getAuthToken({ commit, getters }, verificationCode) {
    const phone = getters.phoneGet;

    if (!phone) {
      throw new Error("Phone number is not set");
    }

    const {
      data: { data },
    } = await getApiTokenRequest(phone, verificationCode);

    const authToken = data.api_token || "";
    commit("setAuthToken", authToken);

    const deviceId = data.device_code || "";
    commit("setDeviceId", deviceId);
  },

  logout({ commit }) {
    commit("setPhone", "");
    commit("setDeviceId", "");
    commit("setAuthToken", "");
    commit("setHasStore", false);
    commit("setUser", {});
  },

  async getUser({ commit }) {
    const {
      data: { data },
    } = await getUserData();
    delete data.store;
    commit("setUser", data);
  },
};

type Actions = {
  [Property in keyof ActionsPayload]: (
    augContext: AugmentedActionContext,
    payload: ActionsPayload[Property][0]
  ) => ActionsPayload[Property][1];
};

type AugmentedActionContext = {
  commit<K extends keyof MutationPayload>(key: K, payload: MutationPayload[K], options?: CommitOptions): void;
} & Omit<ActionContext<State, State>, "commit">;

type Mutations = {
  [Property in keyof MutationPayload]: (state: State, payload: MutationPayload[Property]) => void;
};

type State = typeof initialState;
