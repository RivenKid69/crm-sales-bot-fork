import { ItemDao } from '../dao/item.dao';

export const getItemsStatusAttribute = (value) => {
  if (value === ItemDao.ITEM_STATUS_VALID) return 'valid';
  if (value === ItemDao.ITEM_STATUS_FAKE) return 'fake';
  if (value === ItemDao.ITEM_STATUS_ATLAS) return 'atlas';
};
