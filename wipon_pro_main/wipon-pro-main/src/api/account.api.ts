import request from "@/api/request";

export const getAccountRequest = () => request.get("/accounts");

export const getTransactionsRequest = () => request.get("/transactions");
