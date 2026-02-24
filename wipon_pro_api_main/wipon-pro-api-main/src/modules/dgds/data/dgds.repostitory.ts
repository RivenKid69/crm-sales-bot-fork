import { EntityRepository, Repository } from 'typeorm';
import { DgdDao } from '../../../common/dao/dgd.dao';

@EntityRepository(DgdDao)
export class DgdsRepostitory extends Repository<DgdDao> {}
