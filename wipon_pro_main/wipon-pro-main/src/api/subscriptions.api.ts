import request from "@/api/request";

export const getSubsRequest = () => request.get("/subscription/all");

export const buySubsRequest = (data: any) => request.post("/subscription/buy", data);

export const makeRefund = (data: any) => request.post("/subscription/refund", data);
