import { EntityRepository, Repository } from 'typeorm';
import { StoreTypeDao } from '../../../common/dao/store-type.dao';

@EntityRepository(StoreTypeDao)
export class StoreTypesRepository extends Repository<StoreTypeDao> {}
