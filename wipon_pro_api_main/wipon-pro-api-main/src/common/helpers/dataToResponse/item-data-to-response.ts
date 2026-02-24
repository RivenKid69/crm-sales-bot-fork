import { ItemDao } from '../../dao/item.dao';
import { getItemsStatusAttribute } from '../format-attributes';
import { formatProductDataToResponse } from './product-data-to-response';
import * as substr from 'locutus/php/strings/substr';

export const formatItemDataToResponse = (item: ItemDao | undefined) => {
  if (!item) return null;
  const response: any = {
    id: item.id,
    product: formatProductDataToResponse(item.product),
    status: getItemsStatusAttribute(item.status),
    serial_number: item.serial_number,
    product_code: appendProductCodeToItem(item),
    bottled_at: item.bottled_at,
  };
  return response;
};

const appendProductCodeToItem = (item: ItemDao) => {
  if (item.excise_code) {
    const exciseCode = item.excise_code;
    const length = exciseCode.length;
    if (length > 4) return `***${substr(exciseCode, length - 4)}`;
    return exciseCode;
  } else if (item.serial_number) {
    return item.serial_number;
  }
  return null;
};

export const newAppendProductCodeToItem = (excise_code: string, serial_number: string) => {
  if (excise_code) {
    const length = excise_code.length;
    if (length > 4) return `***${substr(excise_code, length - 4)}`;
    return excise_code;
  } else if (serial_number) {
    return serial_number;
  }
  return null;
};
