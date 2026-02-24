import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UgdLicenseRepository } from '../data/ugd-license.repository';
import { getManager } from 'typeorm';
import { StoreDao } from '../../../common/dao/store.dao';

@Injectable()
export class UgdLicenseService {
  constructor(@InjectRepository(UgdLicenseRepository) private readonly ugdLicenseRepo: UgdLicenseRepository) {}

  async testService() {
    const manager = getManager();
    return (await manager.query(
      'SELECT ugd_licenses.id as license_id, stores.id as store_id from ugd_licenses ' +
        'inner join stores on ugd_licenses.bin = stores.buisness_bin ' +
        'where status = $1 and stores.ugd_license_id is null and ' +
        'stores.buisness_ugd_id = ugd_licenses.ugds_id and ' +
        'stores.buisness_dgd_id = ugd_licenses.dgds_id and ' +
        'stores.license_number = ugd_licenses.license_number',
      ['Действительный'],
    )) as Array<{ license_id: number; store_id: number }>;
  }
}
