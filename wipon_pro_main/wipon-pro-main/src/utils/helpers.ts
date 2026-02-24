import { AxiosResponse } from "axios";

export const sleep = (miliseconds: number) => {
  return new Promise((resolve) => {
    setTimeout(() => resolve(true), miliseconds);
  });
};

export const downloadBlob = (response: AxiosResponse, fileName: string) => {
  if (response.data && response.data instanceof Blob) {
    const blob = response.data;
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore
    if (window.navigator.msSaveOrOpenBlob) {
      navigator.msSaveBlob(blob, fileName);
      return;
    }
    const link = document.createElement("a");
    link.href = window.URL.createObjectURL(blob);
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
};
