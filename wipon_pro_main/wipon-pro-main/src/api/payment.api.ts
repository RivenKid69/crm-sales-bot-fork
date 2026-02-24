import request from "@/api/request";

export const generateInvoice = (data: any) =>
  request.post("/pdf/invoice", data, {
    responseType: "blob",
  });
