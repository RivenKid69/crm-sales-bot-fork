import { RegionDao } from '../../../common/dao/region.dao';
import { EntityRepository, Repository } from 'typeorm';

@EntityRepository(RegionDao)
export class RegionsRepository extends Repository<RegionDao> {}
