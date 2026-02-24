import { EntityRepository, Repository } from 'typeorm';
import { ItemDao } from '../../../common/dao/item.dao';

@EntityRepository(ItemDao)
export class ItemsRepository extends Repository<ItemDao> {}
