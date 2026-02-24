import request from "@/api/request";

export const sendVerificationCodeRequest = (phone: string) =>
  request.post("/auth", {
    phone_number: phone,
  });

export const getApiTokenRequest = (phone: any, verificationCode: any) =>
  request.post("/auth", {
    phone_number: phone,
    auth_code: verificationCode,
  });

export const getUserData = () => request.get("/user");
