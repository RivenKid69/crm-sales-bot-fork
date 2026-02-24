import { ProductDao } from '../../dao/product.dao';

export const formatProductDataToResponse = (product: ProductDao | undefined) => {
  if (!product) return null;
  const response: any = {
    name: product.name,
    type: product.type,
    organization: product.organization,
  };
  return response;
};
