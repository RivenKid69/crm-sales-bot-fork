import { StoreDao } from '../../../common/dao/store.dao';
import { EntityRepository, Repository } from 'typeorm';

@EntityRepository(StoreDao)
export class StoresRepository extends Repository<StoreDao> {}
