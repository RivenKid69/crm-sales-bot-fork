export type licenseResponseType = {
  license: {
    id: number;
    region?: {
      id: number;
      name_ru: string;
      name_en: string;
      name_kk: string;
    };
    city?: string;
    legal_name?: string;
    address?: string;
    bin?: string;
  };
};
