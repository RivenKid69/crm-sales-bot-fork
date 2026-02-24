import { createStore, Store as VuexStore, CommitOptions, DispatchOptions, createLogger } from "vuex";

import { initialState } from "./initialState";

import * as moduleAuth from "./modules/auth";
import * as moduleCompany from "./modules/company";
import * as moduleAccount from "./modules/account";
import * as moduleSubs from "./modules/subscriptions";

export type State = typeof initialState;

const plugins = [];
if (process.env.NODE_ENV === "development") {
  plugins.push(createLogger());
}

export const store = createStore({
  state: initialState,
  mutations: {
    ...moduleAuth.mutations,
    ...moduleCompany.mutations,
    ...moduleAccount.mutations,
    ...moduleSubs.mutations,
  },
  getters: {
    ...moduleAuth.getters,
    ...moduleCompany.getters,
    ...moduleAccount.getters,
    ...moduleSubs.getters,
  },
  actions: {
    ...moduleAuth.actions,
    ...moduleCompany.actions,
    ...moduleAccount.actions,
    ...moduleSubs.actions,
  },
  plugins,
});

type MutationPayload = moduleAuth.MutationPayload &
  moduleCompany.MutationPayload &
  moduleAccount.MutationPayload &
  moduleSubs.MutationPayload;

type ActionsPayload = moduleAuth.ActionsPayload &
  moduleCompany.ActionsPayload &
  moduleAccount.ActionsPayload &
  moduleSubs.ActionsPayload;

type Getters = moduleAuth.Getters & moduleCompany.Getters & moduleAccount.Getters & moduleSubs.Getters;

export type Store = Omit<VuexStore<State>, "getters" | "commit" | "dispatch"> & {
  commit<K extends keyof MutationPayload>(key: K, payload: MutationPayload[K], options?: CommitOptions): void;
} & {
  dispatch<K extends keyof ActionsPayload>(
    key: K,
    payload?: ActionsPayload[K][0],
    options?: DispatchOptions
  ): ActionsPayload[K][1];
} & {
  getters: {
    [K in keyof Getters]: ReturnType<Getters[K]>;
  };
};

export function useStore(): Store {
  return store as Store;
}
