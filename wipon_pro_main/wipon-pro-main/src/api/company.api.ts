import request from "@/api/request";

export const getCompanyRequest = () => request.get("/store");

export const setCompanyRequest = (payload: any) => request.post("/store", payload);

export const updateCompanyRequest = (payload: any) => request.post("/store/update", payload);
