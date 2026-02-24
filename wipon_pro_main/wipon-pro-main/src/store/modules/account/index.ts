import { GetterTree, MutationTree, ActionContext, CommitOptions } from "vuex";

import { initialState } from "../../initialState";
import { getAccountRequest, getTransactionsRequest } from "@/api/account.api";

export type MutationPayload = {
  setAccount: { balance: number; number: string };
  setTransactions: any;
};

export const mutations: MutationTree<State> & Mutations = {
  setAccount({ account }, payload) {
    account.balance = payload.balance;
    account.number = payload.number;
  },
  setTransactions({ account }, payload) {
    account.transactions = payload;
  },
};

export type Getters = {
  accountGet(state: State): { balance: number; number: string };
  transGet(state: State): any[];
};

export const getters: GetterTree<State, State> & Getters = {
  accountGet: ({ account }) => account,
  transGet: ({ account }) => account.transactions,
};

export type ActionsPayload = {
  getAccount: [payload: string, returnVal: void];
  getTransactions: [payload: any, returnVal: void];
};

export const actions: Actions = {
  async getAccount({ commit }) {
    const {
      data: { data },
    } = await getAccountRequest();
    const account = data.reduce(
      (acc: { balance: number }, { balance, number }: any) => ({
        number,
        balance: acc.balance + +balance,
      }),
      { balance: 0 }
    );
    commit("setAccount", account);
  },

  async getTransactions({ commit }) {
    const {
      data: { data },
    } = await getTransactionsRequest();
    const trans = data.map((item: any) => ({
      ...item,
      isType: item.sum > 0 ? 1 : 2,
    }));
    commit("setTransactions", trans);
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
