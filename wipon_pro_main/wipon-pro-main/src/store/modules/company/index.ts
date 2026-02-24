import { GetterTree, MutationTree, ActionContext, CommitOptions } from "vuex";

import { initialState } from "../../initialState";
import { getCompanyRequest, setCompanyRequest, updateCompanyRequest } from "@/api/company.api";
import { getUgdsRequest } from "@/api/ugds.api";
import { getDgdsRequest } from "@/api/dgds.api";
import { getStoreTypesRequest } from "@/api/storeTypes.api";
import router from "@/router";

export type MutationPayload = {
  setCompany: any;
  setUgds: [];
  setDgds: [];
  setStoreTypes: [];
  setHasStore: boolean;
};

export const mutations: MutationTree<State> & Mutations = {
  setCompany({ company }, payload) {
    company.company = payload;
  },
  setUgds({ company }, payload) {
    company.ugds = payload;
  },
  setDgds({ company }, payload) {
    company.dgds = payload;
  },
  setStoreTypes({ company }, payload) {
    company.storeTypes = payload;
  },
  setHasStore({ company }, payload) {
    localStorage.setItem("hasStore", String(payload));
    company.hasStore = payload;
  },
};

export type Getters = {
  company(state: State): any;
  ugds(state: State): any[];
  dgds(state: State): any[];
  storeTypes(state: State): any[];
  hasStore(state: State): boolean | string;
};

export const getters: GetterTree<State, State> & Getters = {
  company: ({ company }) => company.company,
  ugds: ({ company }) => company.ugds,
  dgds: ({ company }) => company.dgds,
  storeTypes: ({ company }) => company.storeTypes,
  hasStore: ({ company }) => company.hasStore,
};

export type ActionsPayload = {
  getCompany: [payload: null, returnVal: Promise<any>];
  getUgds: [payload: string, returnVal: Promise<any>];
  getDgds: [payload: string, returnVal: Promise<any>];
  getStoreTypes: [payload: string, returnVal: Promise<any>];
  setCompany: [payload: any, returnVal: Promise<any>];
  updateCompany: [payload: string, returnVal: Promise<any>];
};

export const actions: Actions = {
  getCompany({ commit }) {
    return getCompanyRequest().then(async (response: any) => {
      const {
        data: { data },
      } = response;
      const company = {
        companyName: data?.payer_name, // Название организации
        licenserName: data?.buisness_full_legal_name, // Название лицензиата
        payerEmail: data?.payer_email, // Электронная почта организации
        payerAddress: data?.payer_address, // Юридический адрес
        bin: data?.payer_bin, // БИН/ИИН
        phoneNumber: data?.user?.phone_number, // Номер телефона
        licenseNumber: data?.license_number, // Номер лицензии
        licenserBin: data?.buisness_bin, // БИН/ИИН лицензиата
        businessDgd: data?.dgd,
        businessStoreAddress: data?.buisness_store_address, // Адрес объекта деятельности
        businessStoreName: data?.buisness_store_name, // Название объекта деятельности
        businessStoreType: data?.buisness_store_type,
        postalAddress: data?.payer_postal_address, // Почтовый адрес для получения документов
        businessUgd: data?.ugd,
      };

      if (!company.licenserBin) {
        commit("setHasStore", false);
        commit("setCompany", {});
        await router.push({ name: "auth.store" });
      } else {
        commit("setCompany", company);
        commit("setHasStore", true);
      }

      return company;
    });
  },
  getUgds({ commit }) {
    return getUgdsRequest().then((response: any) => {
      const {
        data: { data },
      } = response;
      const ugds = data.map((item: any) => ({
        id: item.id,
        dgdId: item.dgd_id,
        ...item,
      }));
      commit("setUgds", ugds);
    });
  },
  getDgds({ commit }) {
    return getDgdsRequest().then((response: any) => {
      const {
        data: { data },
      } = response;
      const dgds = data.map((item: any) => ({
        id: item.id,
        ...item,
      }));

      commit("setDgds", dgds);
    });
  },
  getStoreTypes({ commit }) {
    return getStoreTypesRequest().then((response: any) => {
      const {
        data: { data },
      } = response;
      const storeTypes = data.map((item: any) => ({
        id: item.id,
        ...item,
      }));

      commit("setStoreTypes", storeTypes);
    });
  },
  setCompany({ commit }, payload) {
    return setCompanyRequest(payload).then((res) => commit("setHasStore", true));
  },
  updateCompany(ctx, payload) {
    return updateCompanyRequest(payload);
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
