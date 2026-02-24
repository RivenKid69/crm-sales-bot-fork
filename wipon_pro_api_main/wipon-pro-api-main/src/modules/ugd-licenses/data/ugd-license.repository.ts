import { EntityRepository, Repository } from 'typeorm';
import { UgdLicenseDao } from '../../../common/dao/ugd-license.dao';

@EntityRepository(UgdLicenseDao)
export class UgdLicenseRepository extends Repository<UgdLicenseDao> {}
