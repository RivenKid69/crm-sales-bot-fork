import { EntityRepository, Repository } from 'typeorm';
import { LicenseDao } from '../../../common/dao/license.dao';

@EntityRepository(LicenseDao)
export class LicensesRepository extends Repository<LicenseDao> {}
