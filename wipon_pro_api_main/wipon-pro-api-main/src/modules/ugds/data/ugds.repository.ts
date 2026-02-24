import { EntityRepository, Repository } from 'typeorm';
import { UgdDao } from '../../../common/dao/ugd.dao';

@EntityRepository(UgdDao)
export class UgdsRepository extends Repository<UgdDao> {}
