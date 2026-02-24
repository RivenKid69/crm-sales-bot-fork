import { EntityRepository, Repository } from 'typeorm';
import { ExciseHashesDao } from '../../../common/dao/excise-hashes.dao';

@EntityRepository(ExciseHashesDao)
export class ExciseHashesRepository extends Repository<ExciseHashesDao> {}
