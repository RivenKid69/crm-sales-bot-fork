import { GetterTree, MutationTree, ActionContext, CommitOptions } from "vuex";

import { initialState } from "../../initialState";
import { buySubsRequest, getSubsRequest } from "@/api/subscriptions.api";
import { DESKTOP_PRICE, DESKTOP_TYPE, MOBILE_PRICE, MOBILE_TYPE, TSD_PRICE, TSD_TYPE } from "@/config/rates";

export type MutationPayload = {
  setSubscriptions: any;
  setHasSubscriptions: boolean;
  setSelectedRateTypeId: any;
  setInvoiceData: any;
};

export const mutations: MutationTree<State> & Mutations = {
  setSubscriptions({ subscriptions }, payload) {
    subscriptions.rates = payload;
  },
  setHasSubscriptions({ subscriptions }, payload) {
    subscriptions.hasSubscriptions = payload;
  },
  setSelectedRateTypeId({ subscriptions }, payload) {
    subscriptions.selectedRateTypeId = payload;
  },
  setInvoiceData({ subscriptions }, payload) {
    subscriptions.invoiceData = payload;
  },
};

export type Getters = {
  subscriptions(state: State): any[];
  hasSubscriptions(state: State): boolean;
  rateInfoData(state: State): any[];
  getSelectedRateTypeId(state: State): any;
  getSelectedRate(state: State): any;
  getInvoiceData(state: State): any;
};

export const getters: GetterTree<State, State> & Getters = {
  subscriptions: ({ subscriptions }) => subscriptions.rates,
  hasSubscriptions: ({ subscriptions }) => subscriptions.hasSubscriptions,
  rateInfoData: ({ subscriptions }) => subscriptions.rateInfoData,
  getSelectedRateTypeId: ({ subscriptions }) => subscriptions.selectedRateTypeId,
  getSelectedRate: ({ subscriptions }) =>
    subscriptions.rateInfoData.find((i) => i.type == subscriptions.selectedRateTypeId),
  getInvoiceData: ({ subscriptions }) => subscriptions.invoiceData,
};

export type ActionsPayload = {
  getSubscription: [payload: string, returnVal: void];
  buySubscription: [payload: any, returnVal: Promise<any>];
  setInvoiceData: [payload: any, returnVal: void];
};

export const actions: Actions = {
  setInvoiceData({ commit }, payload) {
    commit("setInvoiceData", payload);
  },

  async getSubscription({ commit }) {
    const {
      data: { data },
    } = await getSubsRequest();
    const date = new Date();
    const yearAgo = new Date(date.setFullYear(date.getFullYear() - 1));
    const fillData = []
      .concat(
        data.mobile.map((i: any) => ({
          ...i,
          type: MOBILE_TYPE,
          activated_at: new Date(i.created_at),
          name: "Смартфон, 1 год",
          custom_id: `${MOBILE_TYPE}_${i.id}`,
          price: MOBILE_PRICE,
        })),
        data.desktop.map((i: any) => ({
          ...i,
          is_active: new Date(i.updated_at).getTime() > yearAgo.getTime(),
          expires_at: new Date(new Date(i.updated_at).setFullYear(new Date(i.updated_at).getFullYear() + 1)),
          activated_at: new Date(i.updated_at),
          type: DESKTOP_TYPE,
          name: "Компьютер, 1 год",
          custom_id: `${DESKTOP_TYPE}_${i.id}`,
          price: DESKTOP_PRICE,
        })),
        data.tsd.map((i: any) => ({
          ...i,
          is_active: new Date(i.updated_at).getTime() > yearAgo.getTime(),
          expires_at: new Date(new Date(i.updated_at).setFullYear(new Date(i.updated_at).getFullYear() + 1)),
          activated_at: new Date(i.updated_at),
          type: TSD_TYPE,
          name: "ТСД, 1 год",
          custom_id: `${TSD_TYPE}_${i.id}`,
          price: TSD_PRICE,
        }))
      )
      .sort((a: any, b: any) => {
        if (a.is_active) return -1;
        return new Date(b.expires_at).getTime() - new Date(a.expires_at).getTime();
      });
    const activeRate: any = fillData.find((item: any) => item.is_active);
    if (activeRate) {
      commit("setHasSubscriptions", true);
      commit("setSelectedRateTypeId", activeRate.type);
    } else {
      commit("setHasSubscriptions", false);
      commit("setSelectedRateTypeId", null);
    }
    commit("setSubscriptions", fillData);
  },
  async buySubscription({ commit, state, dispatch }, payload) {
    const formData: { type: number; change_subscription_type?: boolean } = {
      type: payload,
    };
    if (state.subscriptions.hasSubscriptions) {
      formData.change_subscription_type = true;
    }

    await buySubsRequest(formData);
    await dispatch("getAccount");
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
