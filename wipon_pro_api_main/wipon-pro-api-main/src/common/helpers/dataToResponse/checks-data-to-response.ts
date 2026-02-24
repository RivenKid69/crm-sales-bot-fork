import { CheckDao } from '../../dao/check.dao';
import { formatItemDataToResponse, newAppendProductCodeToItem } from './item-data-to-response';
import { getItemsStatusAttribute } from '../format-attributes';

interface UsersChecks {
  created_at: string;
  sticker_photo: any;
  item: {
    id: number;
    product: {
      name: string;
      type: string;
      organization: string;
    };
    status: string;
    serial_number: string;
    product_code: string | null;
    bottled_at: string;
  };
}

export const formatCheckDataToResponse = (check: CheckDao | undefined) => {
  if (!check) return null;
  const response: any = {
    created_at: check.created_at,
    sticker_photo: check.sticker_photo,
    item: formatItemDataToResponse(check.item),
  };
  return response;
};

export const formatNewCheckDataToResponse = (payload: any): UsersChecks => {
  return {
    created_at: payload.created_at,
    sticker_photo: payload.sticker_photo,
    item: {
      id: payload.item_id,
      product: {
        name: payload.product_name,
        type: payload.product_type,
        organization: payload.product_organization,
      },
      status: String(getItemsStatusAttribute(payload.item_status)),
      serial_number: payload.item_serial_number,
      product_code: newAppendProductCodeToItem(payload.item_excise_code, payload.item_serial_number),
      bottled_at: payload.item_bottled_at,
    },
  };
};
